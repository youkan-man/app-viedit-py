from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from .errors import AppError
from .filesystem import (
    JobPaths,
    file_inventory,
    read_json,
    resolve_inside,
    safe_relative_path,
    sha256_file,
    utc_now_iso,
    validate_rsrc_xml,
    write_json_atomic,
)
from .quantizer import QuantizeOptions, quantize_xml

PREVIEW_DIRECTORY = ".quantize-preview"
PREVIEW_METADATA = "preview.json"
PREVIEW_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


class QuantizeServiceMixin:
    def _quantize_preview_root(self, paths: JobPaths) -> Path:
        return paths.root / PREVIEW_DIRECTORY

    def _load_quantize_preview(
        self, paths: JobPaths, preview_id: str
    ) -> tuple[Path, dict[str, Any]]:
        if not PREVIEW_ID_RE.fullmatch(preview_id):
            raise AppError(
                "クオンタイズプレビューIDが不正です。",
                code="invalid_quantize_preview",
                status_code=404,
            )
        preview_root = self._quantize_preview_root(paths)
        metadata_path = preview_root / PREVIEW_METADATA
        if not metadata_path.is_file():
            raise AppError(
                "クオンタイズプレビューが見つかりません。もう一度差分を解析してください。",
                code="quantize_preview_not_found",
                status_code=404,
            )
        preview = read_json(metadata_path)
        if preview.get("preview_id") != preview_id:
            raise AppError(
                "クオンタイズプレビューが更新されています。もう一度差分を解析してください。",
                code="quantize_preview_stale",
                status_code=409,
            )
        return preview_root, preview

    def preview_dataset_quantization(
        self,
        paths: JobPaths,
        *,
        current_main_xml: str | None,
        options: QuantizeOptions,
    ) -> dict[str, Any]:
        options.validate()
        metadata = self.store.load(paths)
        main_relative_value = metadata.get("main_xml")
        if not isinstance(main_relative_value, str):
            raise AppError(
                "このジョブにはメインXMLがありません。",
                code="missing_main_xml",
                status_code=409,
            )
        main_relative = safe_relative_path(main_relative_value)
        main_xml = resolve_inside(paths.dataset, main_relative)
        if not main_xml.is_file():
            raise AppError(
                "メインXMLが見つかりません。",
                code="missing_main_xml",
                status_code=410,
            )

        current_main_bytes: bytes | None = None
        if current_main_xml is not None:
            current_main_bytes = current_main_xml.encode("utf-8")
            if len(current_main_bytes) > self.settings.inline_xml_max_bytes:
                raise AppError(
                    "メインXMLが画面編集サイズの上限を超えています。",
                    code="xml_too_large_for_editor",
                    status_code=413,
                    details={
                        "size": len(current_main_bytes),
                        "max_bytes": self.settings.inline_xml_max_bytes,
                    },
                )

        preview_root = self._quantize_preview_root(paths)
        shutil.rmtree(preview_root, ignore_errors=True)
        staged_root = preview_root / "files"
        staged_root.mkdir(parents=True, exist_ok=True)
        preview_id = uuid4().hex

        matched_by_kind: Counter[str] = Counter()
        changed_by_kind: Counter[str] = Counter()
        changed_by_tag: Counter[str] = Counter()
        changed_values = 0
        matched_elements = 0
        changed_elements = 0
        binary_warnings: list[str] = []
        samples: list[dict[str, Any]] = []
        file_reports: list[dict[str, Any]] = []
        staged_files: list[dict[str, Any]] = []
        scanned_files = 0
        skipped_files = 0
        total_xml_bytes = 0

        xml_files = sorted(
            path
            for path in paths.dataset.rglob("*")
            if path.is_file() and path.suffix.lower() == ".xml"
        )
        if not xml_files:
            raise AppError(
                "データセット内にXMLファイルがありません。",
                code="dataset_xml_not_found",
                status_code=409,
            )

        for xml_path in xml_files:
            relative = xml_path.relative_to(paths.dataset)
            relative_name = relative.as_posix()
            disk_bytes = xml_path.read_bytes()
            input_bytes = (
                current_main_bytes
                if relative == main_relative and current_main_bytes is not None
                else disk_bytes
            )
            total_xml_bytes += len(input_bytes)
            if total_xml_bytes > self.settings.max_archive_bytes:
                shutil.rmtree(preview_root, ignore_errors=True)
                raise AppError(
                    "クオンタイズ対象XMLの合計サイズが上限を超えています。",
                    code="quantize_dataset_too_large",
                    status_code=413,
                    details={"max_bytes": self.settings.max_archive_bytes},
                )
            if len(input_bytes) > self.settings.max_upload_bytes:
                skipped_files += 1
                binary_warnings.append(
                    f"{relative_name}: XMLサイズが処理上限を超えるためスキップしました。"
                )
                continue
            try:
                input_text = input_bytes.decode("utf-8")
            except UnicodeDecodeError:
                skipped_files += 1
                binary_warnings.append(
                    f"{relative_name}: UTF-8 XMLとして読み込めないためスキップしました。"
                )
                continue

            is_main = relative == main_relative
            try:
                result = quantize_xml(
                    input_text,
                    options,
                    require_rsrc_root=is_main,
                )
            except AppError as exc:
                if is_main:
                    shutil.rmtree(preview_root, ignore_errors=True)
                    raise
                skipped_files += 1
                binary_warnings.append(
                    f"{relative_name}: XMLを解析できないためスキップしました（{exc.message}）。"
                )
                continue

            scanned_files += 1
            report = result["report"]
            output_bytes = result["content"].encode("utf-8")
            matched_elements += int(report.get("matched_elements", 0))
            changed_elements += int(report.get("changed_elements", 0))
            changed_values += int(report.get("changed_values", 0))
            matched_by_kind.update(report.get("matched_by_kind", {}))
            changed_by_kind.update(report.get("changed_by_kind", {}))
            changed_by_tag.update(report.get("changed_by_tag", {}))

            for warning in report.get("warnings", []):
                if "バイナリ/圧縮形式" in warning and len(binary_warnings) < 100:
                    binary_warnings.append(f"{relative_name}: {warning}")
            for sample in report.get("samples", []):
                if len(samples) >= 80:
                    break
                samples.append({"file": relative_name, **sample})

            file_report = {
                "path": relative_name,
                "root_tag": report.get("root_tag", ""),
                "matched_elements": report.get("matched_elements", 0),
                "changed_elements": report.get("changed_elements", 0),
                "changed_values": report.get("changed_values", 0),
            }
            if len(file_reports) < 200:
                file_reports.append(file_report)

            # Stage coordinate changes and any unsaved main-editor content. This
            # makes Apply a coherent dataset operation instead of reloading and
            # accidentally discarding the editor's current XML.
            if output_bytes != disk_bytes:
                staged_path = resolve_inside(staged_root, relative)
                staged_path.parent.mkdir(parents=True, exist_ok=True)
                staged_path.write_bytes(output_bytes)
                staged_files.append(
                    {
                        "path": relative_name,
                        "disk_sha256": _sha256_bytes(disk_bytes),
                        "input_sha256": _sha256_bytes(input_bytes),
                        "output_sha256": _sha256_bytes(output_bytes),
                        "size": len(output_bytes),
                        "is_main_xml": is_main,
                        "editor_modified": is_main and input_bytes != disk_bytes,
                        "changed_elements": report.get("changed_elements", 0),
                    }
                )

        if matched_elements == 0:
            binary_warnings.append(
                "データセット内で対象となる座標タプルを検出できませんでした。配置情報がBINまたは未対応ブロックへ保持されている可能性があります。"
            )
        if options.include_wires and matched_by_kind["wire"] == 0:
            binary_warnings.append(
                "XML上で配線ルート座標を検出できませんでした。compressedWireTableや外部BIN内の配線情報は変更していません。"
            )

        report_payload: dict[str, Any] = {
            "preview_id": preview_id,
            "grid_size": options.grid_size,
            "rounding": options.rounding,
            "resize_rectangles": options.resize_rectangles,
            "scanned_files": scanned_files,
            "skipped_files": skipped_files,
            "staged_files": len(staged_files),
            "matched_elements": matched_elements,
            "changed_elements": changed_elements,
            "changed_values": changed_values,
            "matched_by_kind": {
                "object": matched_by_kind["object"],
                "connector": matched_by_kind["connector"],
                "wire": matched_by_kind["wire"],
            },
            "changed_by_kind": {
                "object": changed_by_kind["object"],
                "connector": changed_by_kind["connector"],
                "wire": changed_by_kind["wire"],
            },
            "changed_by_tag": dict(changed_by_tag.most_common(40)),
            "files": file_reports,
            "files_truncated": scanned_files > len(file_reports),
            "samples": samples,
            "warnings": binary_warnings[:100],
            "warnings_truncated": len(binary_warnings) > 100,
        }
        preview_payload = {
            "format": "pylabview-coordinate-quantize-preview",
            "format_version": 1,
            "preview_id": preview_id,
            "created_at": utc_now_iso(),
            "job_id": paths.job_id,
            "main_xml": main_relative.as_posix(),
            "options": asdict(options),
            "files": staged_files,
            "report": report_payload,
        }
        write_json_atomic(preview_root / PREVIEW_METADATA, preview_payload)
        return report_payload

    def apply_dataset_quantization(
        self,
        paths: JobPaths,
        *,
        preview_id: str,
    ) -> dict[str, Any]:
        preview_root, preview = self._load_quantize_preview(paths, preview_id)
        staged_root = preview_root / "files"
        entries = preview.get("files")
        if not isinstance(entries, list):
            raise AppError(
                "クオンタイズプレビューの形式が不正です。",
                code="invalid_quantize_preview",
                status_code=500,
            )
        if not entries:
            shutil.rmtree(preview_root, ignore_errors=True)
            metadata = self.store.load(paths)
            payload = self.public_metadata(paths, metadata)
            payload["quantization"] = {
                **preview.get("report", {}),
                "applied": False,
                "message": "反映する変更はありません。",
            }
            return payload

        prepared: list[tuple[Path, Path, Path]] = []
        backup_root = preview_root / "backup"
        shutil.rmtree(backup_root, ignore_errors=True)
        backup_root.mkdir(parents=True, exist_ok=True)

        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise AppError(
                    "クオンタイズプレビューのファイル情報が不正です。",
                    code="invalid_quantize_preview",
                    status_code=500,
                )
            relative = safe_relative_path(entry["path"])
            target = resolve_inside(paths.dataset, relative)
            staged = resolve_inside(staged_root, relative)
            backup = resolve_inside(backup_root, relative)
            if not target.is_file() or not staged.is_file():
                raise AppError(
                    "クオンタイズ対象ファイルが見つかりません。もう一度差分を解析してください。",
                    code="quantize_preview_stale",
                    status_code=409,
                    details={"path": entry["path"]},
                )
            expected_sha = entry.get("disk_sha256")
            if not isinstance(expected_sha, str) or sha256_file(target) != expected_sha:
                raise AppError(
                    "解析後にXMLデータセットが変更されています。もう一度差分を解析してください。",
                    code="quantize_preview_stale",
                    status_code=409,
                    details={"path": entry["path"]},
                )
            if entry.get("is_main_xml"):
                validate_rsrc_xml(staged)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            prepared.append((target, staged, backup))

        metadata_before = self.store.load(paths)
        main_relative_value = metadata_before.get("main_xml")
        if not isinstance(main_relative_value, str):
            raise AppError(
                "このジョブにはメインXMLがありません。",
                code="missing_main_xml",
                status_code=409,
            )
        main_xml = resolve_inside(paths.dataset, safe_relative_path(main_relative_value))

        try:
            for target, staged, _ in prepared:
                _write_bytes_atomic(target, staged.read_bytes())

            attributes = validate_rsrc_xml(main_xml)
            applied_at = utc_now_iso()
            metadata = self.store.load(paths)
            metadata.update(
                {
                    "status": "xml_modified",
                    "main_xml_attributes": attributes,
                    "main_xml_size": main_xml.stat().st_size,
                    "xml_editable": main_xml.stat().st_size
                    <= self.settings.inline_xml_max_bytes,
                    "xml_modified_at": applied_at,
                    "xml_sha256": sha256_file(main_xml),
                    "last_quantization": {
                        **preview.get("report", {}),
                        "preview_id": preview_id,
                        "applied": True,
                        "applied_at": applied_at,
                    },
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
                xml_modified_at=applied_at,
                xml_sha256=metadata["xml_sha256"],
                verification_stale=True,
                last_quantization=metadata["last_quantization"],
            )
            self._refresh_dataset_archive(paths, metadata, fallback_stem=main_xml.stem)
            files, files_truncated = file_inventory(paths.dataset)
            metadata.update({"files": files, "files_truncated": files_truncated})
            self.store.save(paths, metadata)
        except Exception:
            for target, _, backup in reversed(prepared):
                if backup.is_file():
                    _write_bytes_atomic(target, backup.read_bytes())
            raise

        shutil.rmtree(preview_root, ignore_errors=True)
        payload = self.public_metadata(paths, metadata)
        payload["quantization"] = metadata["last_quantization"]
        return payload

    def discard_dataset_quantization(
        self,
        paths: JobPaths,
        *,
        preview_id: str | None = None,
    ) -> dict[str, Any]:
        preview_root = self._quantize_preview_root(paths)
        if preview_id is not None:
            self._load_quantize_preview(paths, preview_id)
        existed = preview_root.exists()
        shutil.rmtree(preview_root, ignore_errors=True)
        return {"discarded": existed, "job_id": paths.job_id}
