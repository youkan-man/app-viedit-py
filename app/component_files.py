from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .component_model import DatasetComponentModel, short_hash

TEXT_EXTENSIONS = {".txt", ".map", ".ini", ".cfg", ".log", ".csv"}


@dataclass(slots=True)
class OpaqueFileModel:
    path: str
    sha256: str
    size: int
    root_tag: str
    elements: int
    attributes: int
    scalar_values: int
    components: list[str]
    root_component_id: str
    format: str
    error: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
            "root_tag": self.root_tag,
            "elements": self.elements,
            "attributes": self.attributes,
            "scalar_values": self.scalar_values,
            "component_count": len(self.components),
            "root_component_id": self.root_component_id,
            "format": self.format,
            "opaque": True,
            "error": self.error,
        }


def _property(
    *,
    component_id: str,
    file: str,
    file_sha: str,
    name: str,
    value: str,
    value_type: str,
    parsed: Any,
) -> dict[str, Any]:
    property_id = short_hash("opaque-property", file, name)
    return {
        "id": property_id,
        "component_id": component_id,
        "file": file,
        "file_sha256": file_sha,
        "locator": [],
        "attribute": None,
        "path": f"/{file}/{name}",
        "name": name,
        "tag": "FILE",
        "normalized_name": name.lower(),
        "field_name": name.lower(),
        "value": value if len(value) <= 8192 else None,
        "preview": value[:509] + "..." if len(value) > 512 else value,
        "value_size": len(value),
        "value_type": value_type,
        "parsed": parsed,
        "editable": False,
        "structural": True,
        "reference_like": False,
        "binary": value_type == "binary",
    }


def _detect_format(path: Path, raw: bytes) -> tuple[str, str, list[tuple[str, str, str, Any]]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            parsed = json.loads(raw.decode("utf-8"))
            keys = list(parsed) if isinstance(parsed, dict) else []
            return (
                "json",
                "JSON_FILE",
                [
                    ("json_type", type(parsed).__name__, "string", type(parsed).__name__),
                    ("top_level_keys", ", ".join(str(key) for key in keys[:100]), "string", keys[:100]),
                ],
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "binary", "BINARY_FILE", []
    if suffix in TEXT_EXTENSIONS:
        try:
            text = raw.decode("utf-8")
            return (
                "text",
                "TEXT_FILE",
                [("text_preview", text[:4096], "string", text[:4096])],
            )
        except UnicodeDecodeError:
            pass
    return "binary", "BINARY_FILE", []


def augment_non_xml_files(model: DatasetComponentModel, dataset_root: Path) -> None:
    known = {file.path for file in model.files}
    for path in sorted(item for item in dataset_root.rglob("*") if item.is_file()):
        relative = path.relative_to(dataset_root).as_posix()
        if relative in known:
            continue
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        format_name, root_tag, extra = _detect_format(path, raw)
        component_id = short_hash("opaque-component", relative)
        properties: list[dict[str, Any]] = [
            _property(
                component_id=component_id,
                file=relative,
                file_sha=digest,
                name="size",
                value=str(len(raw)),
                value_type="int",
                parsed=len(raw),
            ),
            _property(
                component_id=component_id,
                file=relative,
                file_sha=digest,
                name="sha256",
                value=digest,
                value_type="string",
                parsed=digest,
            ),
            _property(
                component_id=component_id,
                file=relative,
                file_sha=digest,
                name="extension",
                value=path.suffix.lower(),
                value_type="string",
                parsed=path.suffix.lower(),
            ),
            _property(
                component_id=component_id,
                file=relative,
                file_sha=digest,
                name="header_hex",
                value=raw[:128].hex(" "),
                value_type="binary",
                parsed={"size": len(raw), "preview_bytes": min(len(raw), 128)},
            ),
        ]
        for name, value, value_type, parsed in extra:
            properties.append(
                _property(
                    component_id=component_id,
                    file=relative,
                    file_sha=digest,
                    name=name,
                    value=value,
                    value_type=value_type,
                    parsed=parsed,
                )
            )
        for prop in properties:
            model.properties[prop["id"]] = prop
        property_ids = [prop["id"] for prop in properties]
        tree = {
            "kind": "file",
            "tag": root_tag,
            "path": f"/{relative}",
            "locator": [],
            "attribute_property_ids": [],
            "text_property_id": None,
            "children": [
                {
                    "kind": prop["value_type"],
                    "tag": prop["name"],
                    "path": prop["path"],
                    "locator": [],
                    "attribute_property_ids": [],
                    "text_property_id": prop["id"],
                    "children": [],
                }
                for prop in properties
            ],
        }
        model.components[component_id] = {
            "id": component_id,
            "file": relative,
            "file_sha256": digest,
            "locator": [],
            "path": f"/{relative}",
            "tag": root_tag,
            "role": "file",
            "kind": "binary" if format_name == "binary" else "metadata",
            "class_name": format_name,
            "uid": "",
            "name": relative,
            "parent_id": None,
            "children": [],
            "property_ids": property_ids,
            "editable_property_count": 0,
            "reference_ids": [],
            "bounds": None,
            "points": [],
            "property_tree": tree,
            "depth": 0,
        }
        model.files.append(
            OpaqueFileModel(
                path=relative,
                sha256=digest,
                size=len(raw),
                root_tag=root_tag,
                elements=0,
                attributes=0,
                scalar_values=len(properties),
                components=[component_id],
                root_component_id=component_id,
                format=format_name,
            )
        )
    # File relationships were initially resolved against XML files only. Run the
    # resolver again after opaque files are represented as file components.
    model._resolve_references()
