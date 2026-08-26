from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import AppError
from .filesystem import (
    JobPaths,
    file_inventory,
    resolve_inside,
    safe_filename,
    sha256_file,
    utc_now_iso,
    validate_rsrc_xml,
)


class RebuildServiceMixin:
    def rebuild(
        self,
        paths: JobPaths,
        *,
        output_name: str | None,
        text_encoding: str | None,
        verbosity: int = 1,
    ) -> dict[str, Any]:
        metadata = self.store.load(paths)
        artifacts = metadata.get("artifacts", {})
        main_xml_rel = artifacts.get("main_xml")
        if not isinstance(main_xml_rel, str):
            raise AppError("このジョブにはメインXMLがありません。", code="missing_main_xml", status_code=409)
        main_xml = resolve_inside(paths.root, Path(main_xml_rel))
        if not main_xml.is_file():
            raise AppError("メインXMLが見つかりません。", code="missing_main_xml", status_code=410)
        attributes = validate_rsrc_xml(main_xml)
        encoding = self.validate_encoding(text_encoding or str(metadata.get("text_encoding", "mac_roman")))
        verbosity_args = self._verbosity_arguments(verbosity)
        extension = self.infer_extension(attributes)

        source_meta = metadata.get("source")
        source_name = source_meta.get("name") if isinstance(source_meta, dict) else None
        default_stem = Path(str(source_name or main_xml.stem)).stem
        proposed = output_name.strip() if output_name else f"{default_stem}-reconstructed.{extension}"
        filename = safe_filename(proposed, f"reconstructed.{extension}")
        if not Path(filename).suffix:
            filename = f"{filename}.{extension}"
        output_path = paths.output / filename
        if output_path.exists():
            output_path.unlink()

        metadata["status"] = "rebuilding"
        self.store.save(paths, metadata)
        arguments = [
            "--create",
            "--xml",
            main_xml.name,
            "--rsrc",
            str(output_path.resolve()),
            "--textcp",
            encoding,
            *verbosity_args,
        ]
        result = self._run_stage("XML→RSRC再構成", arguments, main_xml.parent)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise AppError(
                "pylabview は正常終了しましたが、再構成ファイルが生成されませんでした。",
                code="missing_reconstructed_file",
                status_code=500,
            )

        reconstructed = {
            "name": output_path.name,
            "size": output_path.stat().st_size,
            "sha256": sha256_file(output_path),
            "text_encoding": encoding,
            "created_at": utc_now_iso(),
            "stale": False,
        }
        metadata.update(
            {
                "status": "completed",
                "text_encoding": encoding,
                "reconstructed": reconstructed,
                "artifacts": {
                    **artifacts,
                    "reconstructed": self._relative(paths, output_path),
                },
                "logs": {**metadata.get("logs", {}), "rebuild": result.as_dict()},
            }
        )
        self.store.save(paths, metadata)
        return self.public_metadata(paths, metadata)

    def read_main_xml(self, paths: JobPaths) -> bytes:
        metadata = self.store.load(paths)
        main_xml_rel = metadata.get("artifacts", {}).get("main_xml")
        if not isinstance(main_xml_rel, str):
            raise AppError("メインXMLがありません。", code="missing_main_xml", status_code=404)
        main_xml = resolve_inside(paths.root, Path(main_xml_rel))
        if not main_xml.is_file():
            raise AppError("メインXMLが見つかりません。", code="missing_main_xml", status_code=410)
        size = main_xml.stat().st_size
        if size > self.settings.inline_xml_max_bytes:
            raise AppError(
                "XMLが画面編集サイズの上限を超えています。ダウンロードして編集してください。",
                code="xml_too_large_for_editor",
                status_code=413,
                details={"size": size, "max_bytes": self.settings.inline_xml_max_bytes},
            )
        return main_xml.read_bytes()

    def update_main_xml(self, paths: JobPaths, content: bytes) -> dict[str, Any]:
        if len(content) > self.settings.max_upload_bytes:
            raise AppError(
                "XMLサイズが上限を超えています。",
                code="upload_too_large",
                status_code=413,
                details={"max_bytes": self.settings.max_upload_bytes},
            )
        metadata = self.store.load(paths)
        main_xml_rel = metadata.get("artifacts", {}).get("main_xml")
        if not isinstance(main_xml_rel, str):
            raise AppError("メインXMLがありません。", code="missing_main_xml", status_code=404)
        main_xml = resolve_inside(paths.root, Path(main_xml_rel))

        fd, temporary_name = tempfile.mkstemp(prefix=f".{main_xml.name}.", suffix=".xml", dir=main_xml.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            temporary_path = Path(temporary_name)
            attributes = validate_rsrc_xml(temporary_path)
            os.replace(temporary_path, main_xml)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

        xml_modified_at = utc_now_iso()
        xml_hash = sha256_file(main_xml)
        metadata.update(
            {
                "status": "xml_modified",
                "main_xml_attributes": attributes,
                "main_xml_size": main_xml.stat().st_size,
                "xml_editable": main_xml.stat().st_size <= self.settings.inline_xml_max_bytes,
                "xml_modified_at": xml_modified_at,
                "xml_sha256": xml_hash,
            }
        )
        if isinstance(metadata.get("reconstructed"), dict):
            metadata["reconstructed"]["stale"] = True
        if isinstance(metadata.get("verification"), dict):
            metadata["verification"]["stale"] = True
        self._write_workspace_manifest(
            paths,
            metadata,
            main_xml,
            xml_modified_at=xml_modified_at,
            xml_sha256=xml_hash,
            verification_stale=True,
        )
        self._refresh_dataset_archive(paths, metadata, fallback_stem=main_xml.stem)
        files, files_truncated = file_inventory(paths.dataset)
        metadata.update({"files": files, "files_truncated": files_truncated})
        self.store.save(paths, metadata)
        return self.public_metadata(paths, metadata)

    def artifact_path(self, paths: JobPaths, artifact_name: str) -> Path:
        metadata = self.store.load(paths)
        allowed = {"dataset", "main_xml", "reconstructed", "roundtrip"}
        if artifact_name not in allowed:
            raise AppError("成果物の指定が不正です。", code="invalid_artifact", status_code=404)
        relative = metadata.get("artifacts", {}).get(artifact_name)
        if not isinstance(relative, str):
            raise AppError("指定された成果物はまだありません。", code="artifact_not_found", status_code=404)
        path = resolve_inside(paths.root, Path(relative))
        if not path.is_file():
            raise AppError("成果物が見つかりません。", code="artifact_not_found", status_code=410)
        return path

    def public_metadata(self, paths: JobPaths, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        source = metadata or self.store.load(paths)
        # JSON round-trip creates a detached, JSON-safe copy before adding derived fields.
        payload = json.loads(json.dumps(source, ensure_ascii=False))
        artifacts = payload.get("artifacts", {})
        payload["urls"] = {
            key: f"/api/jobs/{paths.job_id}/download/{key}"
            for key in artifacts
            if key in {"dataset", "main_xml", "reconstructed", "roundtrip"}
        }
        payload["xml_url"] = f"/api/jobs/{paths.job_id}/xml"
        payload["rebuild_url"] = f"/api/jobs/{paths.job_id}/rebuild"
        payload["delete_url"] = f"/api/jobs/{paths.job_id}"
        return payload
