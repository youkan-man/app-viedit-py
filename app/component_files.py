from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .component_model import DatasetComponentModel, short_hash

TEXT_EXTENSIONS = {".txt", ".map", ".ini", ".cfg", ".log", ".csv"}
HEADER_BYTES = 4096
STRUCTURED_TEXT_LIMIT = 1024 * 1024
CHUNK_BYTES = 1024 * 1024


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


def _hash_and_head(path: Path) -> tuple[str, int, bytes]:
    digest = hashlib.sha256()
    size = 0
    head = bytearray()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
            if len(head) < HEADER_BYTES:
                head.extend(chunk[: HEADER_BYTES - len(head)])
    return digest.hexdigest(), size, bytes(head)


def _read_small(path: Path, size: int) -> bytes | None:
    if size > STRUCTURED_TEXT_LIMIT:
        return None
    return path.read_bytes()


def _detect_format(
    path: Path,
    *,
    size: int,
    head: bytes,
) -> tuple[str, str, list[tuple[str, str, str, Any]]]:
    suffix = path.suffix.lower()
    raw = _read_small(path, size)
    if suffix == ".json":
        if raw is None:
            return (
                "json",
                "JSON_FILE",
                [
                    (
                        "parse_status",
                        f"not expanded: file exceeds {STRUCTURED_TEXT_LIMIT} bytes",
                        "string",
                        {"expanded": False, "limit": STRUCTURED_TEXT_LIMIT},
                    )
                ],
            )
        try:
            parsed = json.loads(raw.decode("utf-8"))
            keys = list(parsed) if isinstance(parsed, dict) else []
            return (
                "json",
                "JSON_FILE",
                [
                    ("json_type", type(parsed).__name__, "string", type(parsed).__name__),
                    (
                        "top_level_keys",
                        ", ".join(str(key) for key in keys[:100]),
                        "string",
                        keys[:100],
                    ),
                ],
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return "binary", "BINARY_FILE", []
    if suffix in TEXT_EXTENSIONS:
        candidate = raw if raw is not None else head
        try:
            text = candidate.decode("utf-8")
            extra: list[tuple[str, str, str, Any]] = [
                ("text_preview", text[:4096], "string", text[:4096])
            ]
            if raw is None:
                extra.append(
                    (
                        "preview_status",
                        f"first {len(head)} bytes only",
                        "string",
                        {"partial": True, "preview_bytes": len(head)},
                    )
                )
            return "text", "TEXT_FILE", extra
        except UnicodeDecodeError:
            pass
    return "binary", "BINARY_FILE", []


def augment_non_xml_files(model: DatasetComponentModel, dataset_root: Path) -> None:
    known = {file.path for file in model.files}
    for path in sorted(item for item in dataset_root.rglob("*") if item.is_file()):
        relative = path.relative_to(dataset_root).as_posix()
        if relative in known:
            continue
        digest, size, head = _hash_and_head(path)
        format_name, root_tag, extra = _detect_format(
            path,
            size=size,
            head=head,
        )
        component_id = short_hash("opaque-component", relative)
        properties: list[dict[str, Any]] = [
            _property(
                component_id=component_id,
                file=relative,
                file_sha=digest,
                name="size",
                value=str(size),
                value_type="int",
                parsed=size,
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
                value=head[:128].hex(" "),
                value_type="binary",
                parsed={"size": size, "preview_bytes": min(size, 128)},
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
                size=size,
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
