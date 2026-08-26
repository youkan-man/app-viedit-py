from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeET

from .component_files import augment_non_xml_files
from .component_model import DatasetComponentModel, parse_tuple, parse_xml, serialize_xml
from .errors import AppError
from .filesystem import (
    JobPaths,
    file_inventory,
    resolve_inside,
    safe_relative_path,
    sha256_file,
    utc_now_iso,
    validate_rsrc_xml,
)

MAX_COMPONENT_UPDATES = 200
MAX_COMPONENT_VALUE_BYTES = 64 * 1024


def _element_at(root, locator: list[int]):
    element = root
    for index in locator:
        children = list(element)
        if index < 0 or index >= len(children):
            raise AppError(
                "XML構造が解析時から変更されています。コンポーネント一覧を再読込してください。",
                code="component_model_stale",
                status_code=409,
            )
        element = children[index]
    return element


def _validate_property_value(prop: dict[str, Any], value: str) -> str:
    if "\x00" in value:
        raise AppError(
            "プロパティ値にNUL文字は使用できません。",
            code="invalid_component_value",
            status_code=422,
            details={"property_id": prop["id"]},
        )
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_COMPONENT_VALUE_BYTES:
        raise AppError(
            "プロパティ値が上限を超えています。",
            code="component_value_too_large",
            status_code=413,
            details={
                "property_id": prop["id"],
                "max_bytes": MAX_COMPONENT_VALUE_BYTES,
            },
        )
    value_type = prop["value_type"]
    text = value.strip()
    try:
        if value_type == "bool" and text.lower() not in {"true", "false"}:
            raise ValueError
        if value_type == "int":
            int(text, 0)
        if value_type == "float":
            float(text)
        if value_type in {"rect", "point", "tuple"}:
            parsed = parse_tuple(value)
            expected = {"rect": 4, "point": 2}.get(value_type)
            if parsed is None or (expected is not None and len(parsed) != expected):
                raise ValueError
    except ValueError as exc:
        raise AppError(
            f"{prop['name']} の値が {value_type} として不正です。",
            code="invalid_component_value",
            status_code=422,
            details={
                "property_id": prop["id"],
                "value_type": value_type,
            },
        ) from exc
    return value


class ComponentServiceMixin:
    def _component_cache_state(
        self,
    ) -> tuple[
        dict[str, tuple[tuple[tuple[str, int, int], ...], DatasetComponentModel]],
        threading.RLock,
    ]:
        if not hasattr(self, "_component_model_cache"):
            self._component_model_cache = {}
        if not hasattr(self, "_component_model_lock"):
            self._component_model_lock = threading.RLock()
        return self._component_model_cache, self._component_model_lock

    @staticmethod
    def _component_fingerprint(paths: JobPaths) -> tuple[tuple[str, int, int], ...]:
        return tuple(
            (
                path.relative_to(paths.dataset).as_posix(),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in sorted(item for item in paths.dataset.rglob("*") if item.is_file())
        )

    def invalidate_component_model(self, paths: JobPaths) -> None:
        cache, lock = self._component_cache_state()
        with lock:
            cache.pop(paths.job_id, None)

    def _load_component_model(
        self, paths: JobPaths, *, force: bool = False
    ) -> DatasetComponentModel:
        fingerprint = self._component_fingerprint(paths)
        if not fingerprint:
            raise AppError(
                "XMLデータセットがありません。",
                code="dataset_xml_not_found",
                status_code=409,
            )
        cache, lock = self._component_cache_state()
        with lock:
            cached = cache.get(paths.job_id)
            if not force and cached and cached[0] == fingerprint:
                return cached[1]

        try:
            model = DatasetComponentModel.analyze(
                paths.dataset,
                max_bytes=self.settings.max_archive_bytes,
            )
            augment_non_xml_files(model, paths.dataset)
        except ValueError as exc:
            raise AppError(
                "XMLデータセットが解析上限を超えています。",
                code="component_model_too_large",
                status_code=413,
                details={"max_bytes": self.settings.max_archive_bytes},
            ) from exc
        xml_files = [file for file in model.files if not getattr(file, "format", "")]
        if not any(file.error is None for file in xml_files):
            raise AppError(
                "解析できるXMLがありません。",
                code="component_model_unavailable",
                status_code=422,
                details={"warnings": model.warnings[:50]},
            )
        with lock:
            cache[paths.job_id] = (fingerprint, model)
        return model

    def component_model_summary(self, paths: JobPaths) -> dict[str, Any]:
        model = self._load_component_model(paths)
        payload = model.summary()
        files = payload.get("files", [])
        xml_files = [file for file in files if not file.get("opaque")]
        opaque_files = [file for file in files if file.get("opaque")]
        payload["summary"].update(
            {
                "dataset_files": len(files),
                "xml_files": len(xml_files),
                "parsed_files": sum(
                    1 for file in xml_files if file.get("error") is None
                ),
                "failed_files": sum(
                    1 for file in xml_files if file.get("error") is not None
                ),
                "opaque_files": len(opaque_files),
                "opaque_bytes": sum(int(file.get("size", 0)) for file in opaque_files),
            }
        )
        payload.update(
            {
                "job_id": paths.job_id,
                "generated_at": utc_now_iso(),
                "components_url": f"/api/jobs/{paths.job_id}/components",
            }
        )
        return payload

    def list_components(
        self,
        paths: JobPaths,
        *,
        query: str = "",
        file: str = "",
        kind: str = "",
        parent_id: str | None = None,
        roots_only: bool = False,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        model = self._load_component_model(paths)
        if roots_only:
            roots = [
                model.component_summary(component)
                for component in model.components.values()
                if component["parent_id"] is None
                and (not file or component["file"] == file)
                and (not kind or component["kind"] == kind)
                and (
                    not query.strip()
                    or query.lower()
                    in " ".join(
                        str(component.get(key, ""))
                        for key in (
                            "name",
                            "class_name",
                            "uid",
                            "tag",
                            "path",
                            "file",
                            "kind",
                        )
                    ).lower()
                )
            ]
            roots.sort(key=lambda component: (component["file"], component["path"]))
            payload = {
                "total": len(roots),
                "offset": offset,
                "limit": limit,
                "items": roots[offset : offset + limit],
            }
        else:
            payload = model.list_components(
                query=query,
                file=file,
                kind=kind,
                parent_id=parent_id,
                offset=offset,
                limit=limit,
            )
        payload["job_id"] = paths.job_id
        return payload

    def component_detail(self, paths: JobPaths, component_id: str) -> dict[str, Any]:
        model = self._load_component_model(paths)
        try:
            return model.detail(component_id)
        except KeyError as exc:
            raise AppError(
                "コンポーネントが見つかりません。解析結果を再読込してください。",
                code="component_not_found",
                status_code=404,
            ) from exc

    def update_component(
        self,
        paths: JobPaths,
        component_id: str,
        *,
        expected_file_sha256: str,
        updates: list[dict[str, str]],
    ) -> dict[str, Any]:
        if not updates or len(updates) > MAX_COMPONENT_UPDATES:
            raise AppError(
                f"プロパティ更新は1〜{MAX_COMPONENT_UPDATES}件で指定してください。",
                code="invalid_component_updates",
                status_code=422,
            )
        model = self._load_component_model(paths)
        component = model.components.get(component_id)
        if component is None:
            raise AppError(
                "コンポーネントが見つかりません。解析結果を再読込してください。",
                code="component_not_found",
                status_code=404,
            )
        if component.get("kind") in {"binary", "metadata"}:
            raise AppError(
                "不透明ファイルとメタデータファイルは読み取り専用です。",
                code="component_read_only",
                status_code=422,
            )
        relative = safe_relative_path(component["file"])
        target = resolve_inside(paths.dataset, relative)
        current_sha = sha256_file(target)
        if current_sha != expected_file_sha256 or current_sha != component["file_sha256"]:
            self.invalidate_component_model(paths)
            raise AppError(
                "XMLが解析後に変更されています。コンポーネント一覧を再読込してください。",
                code="component_model_stale",
                status_code=409,
                details={"path": component["file"]},
            )

        seen: set[str] = set()
        selected: list[tuple[dict[str, Any], str]] = []
        for update in updates:
            property_id = str(update.get("property_id", ""))
            if not property_id or property_id in seen:
                raise AppError(
                    "プロパティ更新に重複または空のIDがあります。",
                    code="invalid_component_updates",
                    status_code=422,
                )
            seen.add(property_id)
            prop = model.properties.get(property_id)
            if prop is None or prop["component_id"] != component_id:
                raise AppError(
                    "指定されたプロパティはこのコンポーネントに属していません。",
                    code="component_property_not_found",
                    status_code=404,
                    details={"property_id": property_id},
                )
            if not prop["editable"]:
                raise AppError(
                    "構造識別子、参照、バイナリ値はこの画面から変更できません。",
                    code="component_property_read_only",
                    status_code=422,
                    details={"property_id": property_id, "name": prop["name"]},
                )
            selected.append(
                (prop, _validate_property_value(prop, str(update.get("value", ""))))
            )

        raw = target.read_bytes()
        root = parse_xml(raw)
        changed_ids: list[str] = []
        for prop, value in selected:
            element = _element_at(root, prop["locator"])
            if prop["attribute"] is not None:
                if prop["attribute"] not in element.attrib:
                    raise AppError(
                        "属性がXMLから削除されています。コンポーネント一覧を再読込してください。",
                        code="component_model_stale",
                        status_code=409,
                        details={"property_id": prop["id"]},
                    )
                previous = element.attrib[prop["attribute"]]
                if previous != value:
                    element.attrib[prop["attribute"]] = value
                    changed_ids.append(prop["id"])
            else:
                previous = element.text or ""
                if previous != value:
                    element.text = value
                    changed_ids.append(prop["id"])

        if not changed_ids:
            return {
                "job": self.public_metadata(paths),
                "component": model.detail(component_id),
                "updated_properties": [],
            }

        updated_bytes = serialize_xml(root, raw)
        try:
            SafeET.fromstring(updated_bytes)
        except Exception as exc:
            raise AppError(
                "更新後のXMLが不正です。",
                code="invalid_component_update",
                status_code=422,
                details={"reason": str(exc)},
            ) from exc

        metadata = self.store.load(paths)
        main_relative_value = metadata.get("main_xml")
        is_main = (
            isinstance(main_relative_value, str)
            and main_relative_value == relative.as_posix()
        )
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".xml", dir=target.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(updated_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            attributes: dict[str, str] | None = None
            if is_main:
                attributes = validate_rsrc_xml(temporary_path)
            os.replace(temporary_path, target)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        modified_at = utc_now_iso()
        metadata.update(
            {
                "status": "xml_modified",
                "component_modified_at": modified_at,
                "component_modified_file": relative.as_posix(),
                "component_modified_id": component_id,
                "component_modified_properties": changed_ids,
            }
        )
        if is_main and attributes is not None:
            metadata.update(
                {
                    "main_xml_attributes": attributes,
                    "main_xml_size": target.stat().st_size,
                    "xml_editable": target.stat().st_size
                    <= self.settings.inline_xml_max_bytes,
                    "xml_modified_at": modified_at,
                    "xml_sha256": sha256_file(target),
                }
            )
        if isinstance(metadata.get("reconstructed"), dict):
            metadata["reconstructed"]["stale"] = True
        if isinstance(metadata.get("verification"), dict):
            metadata["verification"]["stale"] = True

        artifacts = metadata.get("artifacts", {})
        main_artifact = artifacts.get("main_xml") if isinstance(artifacts, dict) else None
        if isinstance(main_artifact, str):
            main_xml = resolve_inside(paths.root, Path(main_artifact))
            if main_xml.is_file():
                self._write_workspace_manifest(
                    paths,
                    metadata,
                    main_xml,
                    component_modified_at=modified_at,
                    component_modified_file=relative.as_posix(),
                    component_modified_id=component_id,
                    verification_stale=True,
                )
                self._refresh_dataset_archive(
                    paths, metadata, fallback_stem=main_xml.stem
                )

        files, files_truncated = file_inventory(paths.dataset)
        metadata.update({"files": files, "files_truncated": files_truncated})
        self.store.save(paths, metadata)
        self.invalidate_component_model(paths)
        refreshed = self._load_component_model(paths, force=True)
        refreshed_component = refreshed.components.get(component_id)
        if refreshed_component is None:
            raise AppError(
                "更新後にコンポーネントを再特定できませんでした。XMLは保存されています。",
                code="component_reindex_required",
                status_code=409,
            )
        return {
            "job": self.public_metadata(paths, metadata),
            "component": refreshed.detail(component_id),
            "updated_properties": changed_ids,
        }
