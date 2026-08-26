from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as DefusedET

from .errors import AppError
from .filesystem import (
    MANIFEST_NAME,
    JobPaths,
    file_inventory,
    make_zip,
    read_json,
    resolve_inside,
    safe_extract_zip,
    safe_filename,
    safe_relative_path,
    sha256_file,
    utc_now_iso,
    validate_rsrc_xml,
)


class ExtractServiceMixin:
    def extract_vi(
        self,
        paths: JobPaths,
        source_path: Path,
        *,
        text_encoding: str,
        verbosity: int,
        raw_connectors: bool,
        verify_roundtrip: bool,
    ) -> dict[str, Any]:
        encoding = self.validate_encoding(text_encoding)
        verbosity_args = self._verbosity_arguments(verbosity)
        metadata = self.store.load(paths)
        source_hash = sha256_file(source_path)
        stem = safe_filename(source_path.stem, "labview")
        main_xml = paths.dataset / f"{stem}.xml"

        arguments = [
            "--extract",
            "--rsrc",
            str(source_path.resolve()),
            "--xml",
            str(main_xml.resolve()),
            "--textcp",
            encoding,
            *verbosity_args,
        ]
        if raw_connectors:
            arguments.append("--raw-connectors")

        metadata.update({"status": "extracting", "text_encoding": encoding})
        self.store.save(paths, metadata)
        extract_result = self._run_stage("VI→XML変換", arguments, paths.dataset)
        if not main_xml.is_file():
            raise AppError(
                "pylabview は正常終了しましたが、メインXMLが生成されませんでした。",
                code="missing_main_xml",
                status_code=500,
            )

        attributes = validate_rsrc_xml(main_xml)
        verification: dict[str, Any] = {"requested": verify_roundtrip, "status": "not_requested"}
        roundtrip_path: Path | None = None
        verification_log: dict[str, Any] | None = None

        if verify_roundtrip:
            source_suffix = source_path.suffix.lower() or f".{self.infer_extension(attributes)}"
            roundtrip_path = paths.output / f"{stem}-roundtrip{source_suffix}"
            create_arguments = [
                "--create",
                "--xml",
                main_xml.name,
                "--rsrc",
                str(roundtrip_path.resolve()),
                "--textcp",
                encoding,
                *verbosity_args,
            ]
            try:
                verify_result = self._run_stage("ラウンドトリップ検証", create_arguments, main_xml.parent)
                verification_log = verify_result.as_dict()
                if not roundtrip_path.is_file():
                    raise AppError(
                        "検証用RSRCファイルが生成されませんでした。",
                        code="missing_roundtrip_file",
                        status_code=500,
                    )
                recreated_hash = sha256_file(roundtrip_path)
                verification = {
                    "requested": True,
                    "status": "completed",
                    "binary_identical": recreated_hash == source_hash,
                    "source_sha256": source_hash,
                    "recreated_sha256": recreated_hash,
                    "source_size": source_path.stat().st_size,
                    "recreated_size": roundtrip_path.stat().st_size,
                }
            except AppError as exc:
                verification = {
                    "requested": True,
                    "status": "failed",
                    "message": exc.message,
                    "details": exc.details,
                }

        self._write_workspace_manifest(
            paths,
            metadata,
            main_xml,
            source_name=source_path.name,
            source_sha256=source_hash,
            raw_connectors=raw_connectors,
            verification=verification,
        )

        dataset_zip = paths.output / f"{stem}-xml-dataset.zip"
        make_zip(paths.dataset, dataset_zip)
        files, files_truncated = file_inventory(paths.dataset)
        main_xml_size = main_xml.stat().st_size

        artifacts: dict[str, str] = {
            "dataset": self._relative(paths, dataset_zip),
            "main_xml": self._relative(paths, main_xml),
        }
        if roundtrip_path and roundtrip_path.is_file():
            artifacts["roundtrip"] = self._relative(paths, roundtrip_path)

        metadata.update(
            {
                "status": "completed",
                "source": {
                    "name": source_path.name,
                    "size": source_path.stat().st_size,
                    "sha256": source_hash,
                },
                "main_xml": main_xml.relative_to(paths.dataset).as_posix(),
                "main_xml_attributes": attributes,
                "main_xml_size": main_xml_size,
                "xml_editable": main_xml_size <= self.settings.inline_xml_max_bytes,
                "files": files,
                "files_truncated": files_truncated,
                "verification": verification,
                "artifacts": artifacts,
                "logs": {
                    "extract": extract_result.as_dict(),
                    **({"verification": verification_log} if verification_log else {}),
                },
            }
        )
        self.store.save(paths, metadata)
        return self.public_metadata(paths, metadata)

    def _manifest_main_xml(self, dataset: Path) -> Path | None:
        for manifest_path in sorted(dataset.rglob(MANIFEST_NAME)):
            try:
                manifest = read_json(manifest_path)
            except AppError:
                continue
            value = manifest.get("main_xml")
            if not isinstance(value, str):
                continue
            try:
                relative = safe_relative_path(value)
                candidate = resolve_inside(manifest_path.parent, relative)
            except AppError:
                continue
            if candidate.is_file():
                try:
                    validate_rsrc_xml(candidate)
                except AppError:
                    continue
                return candidate
        return None

    def find_main_xml(self, dataset: Path, hint: str | None = None) -> Path:
        if hint and hint.strip():
            relative = safe_relative_path(hint)
            candidate = resolve_inside(dataset, relative)
            if not candidate.is_file():
                raise AppError(
                    f"指定されたメインXMLがZIP内にありません: {relative.as_posix()}",
                    code="main_xml_not_found",
                    status_code=422,
                )
            validate_rsrc_xml(candidate)
            return candidate

        from_manifest = self._manifest_main_xml(dataset)
        if from_manifest is not None:
            return from_manifest

        candidates: list[Path] = []
        for candidate in sorted(dataset.rglob("*.xml")):
            try:
                root = DefusedET.parse(candidate).getroot()
            except Exception:
                continue
            if root.tag == "RSRC":
                candidates.append(candidate)

        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise AppError(
                "RSRCルートを持つメインXMLが見つかりません。",
                code="main_xml_not_found",
                status_code=422,
            )
        relative_candidates = [item.relative_to(dataset).as_posix() for item in candidates[:50]]
        raise AppError(
            "メインXML候補が複数あります。画面の『メインXMLパス』に1つ指定してください。",
            code="ambiguous_main_xml",
            status_code=422,
            details={"candidates": relative_candidates, "truncated": len(candidates) > 50},
        )

    def import_dataset(
        self,
        paths: JobPaths,
        upload_path: Path,
        *,
        original_name: str,
        main_xml_hint: str | None,
        text_encoding: str,
    ) -> dict[str, Any]:
        encoding = self.validate_encoding(text_encoding)
        metadata = self.store.load(paths)
        metadata.update({"status": "importing", "text_encoding": encoding})
        self.store.save(paths, metadata)

        if zipfile.is_zipfile(upload_path):
            safe_extract_zip(upload_path, paths.dataset, self.settings)
            upload_kind = "zip"
        elif upload_path.suffix.lower() == ".xml":
            destination = paths.dataset / safe_filename(original_name, "main.xml")
            if destination.suffix.lower() != ".xml":
                destination = destination.with_suffix(".xml")
            shutil.copy2(upload_path, destination)
            upload_kind = "xml"
        else:
            raise AppError(
                "XMLデータセットはZIP、または単独のXMLとしてアップロードしてください。",
                code="unsupported_dataset",
                status_code=422,
            )

        main_xml = self.find_main_xml(paths.dataset, main_xml_hint)
        attributes = validate_rsrc_xml(main_xml)
        upload_hash = sha256_file(upload_path)
        metadata.update(
            {
                "status": "imported",
                "dataset_upload": {
                    "name": original_name,
                    "kind": upload_kind,
                    "size": upload_path.stat().st_size,
                    "sha256": upload_hash,
                },
                "main_xml": main_xml.relative_to(paths.dataset).as_posix(),
                "main_xml_attributes": attributes,
                "main_xml_size": main_xml.stat().st_size,
                "xml_editable": main_xml.stat().st_size <= self.settings.inline_xml_max_bytes,
                "artifacts": {
                    **metadata.get("artifacts", {}),
                    "main_xml": self._relative(paths, main_xml),
                },
            }
        )
        self._write_workspace_manifest(
            paths,
            metadata,
            main_xml,
            imported_source_name=original_name,
            imported_source_sha256=upload_hash,
        )
        archive_stem = safe_filename(Path(original_name).stem, "dataset")
        self._refresh_dataset_archive(paths, metadata, fallback_stem=archive_stem)
        files, files_truncated = file_inventory(paths.dataset)
        metadata.update({"files": files, "files_truncated": files_truncated})
        self.store.save(paths, metadata)
        return metadata
