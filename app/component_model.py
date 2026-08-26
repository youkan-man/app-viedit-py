from __future__ import annotations

import contextlib
import hashlib
import io
import re
import xml.etree.ElementTree as StdET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeET

SYSTEM_COMPONENT_TAGS = {"slrootobject", "slobject"}
SYSTEM_ARRAY_TAGS = {"slarray", "slarrayelement"}
SYSTEM_REFERENCE_TAGS = {"slreference"}
CLASS_NAMES = {"slclass", "class", "ofclassname", "classname"}
UID_NAMES = {"sluid", "uid", "ofid", "id", "ofwireid", "wireid", "ofconid", "conid"}
LABEL_NAMES = (
    "ofdisplayname", "displayname", "ofnodename", "nodename", "ofname", "name",
    "offname", "fname", "oflabel", "label", "ofscriptname", "scriptname",
    "ofdescription", "description", "ofvblname", "vblname",
)
STRUCTURAL_NAMES = {
    "slclass", "sluid", "slstockobj", "slelements", "slindex", "slstocksource",
    "formatversion", "type", "typehex", "encoding", "file", "format", "index",
}
EDIT_TEXT_TOKENS = (
    "name", "label", "description", "caption", "text", "tip", "help",
    "scriptname", "vblname",
)
EDIT_APPEARANCE_TOKENS = (
    "color", "font", "visible", "hidden", "disabled", "bold", "italic",
    "justify", "alignment", "opacity", "pattern",
)
EDIT_DATA_TOKENS = (
    "value", "default", "minimum", "maximum", "min", "max", "step",
    "increment", "precision", "digits",
)
UNSAFE_STRUCTURE_TOKENS = (
    "class", "uid", "reference", "ref", "owner", "parent", "type", "index",
    "count", "number", "ninputs", "noutputs", "flags", "version", "offset",
    "length", "elements", "file", "format", "stock", "source",
)
RECT_NAMES = {
    "bounds", "contrect", "dbounds", "pbounds", "hoodbounds", "iconbounds",
    "growareabounds", "docbounds", "dynbounds", "savedsize", "termbounds", "view",
    "scalerect", "totalbounds", "sizerect", "srcrect", "crectabove", "crectbelow",
    "subviglyphbounds", "callerglyphbounds",
}
POINT_NAMES = {
    "origin", "minpanesize", "minpanelsize", "termhotpoint", "minbutsize", "nrc",
    "orc", "termofst", "pos", "hotpoint",
}
REFERENCE_TOKENS = (
    "reference", "ref", "owner", "parent", "root", "mate", "otherside", "dco",
    "wireid", "conid", "nodelist", "termlist", "reflist", "tunnellist", "signal",
)
FILE_TOKENS = ("file", "path")
BINARY_TOKENS = (
    "binary", "compressed", "pixmap", "image", "streamdata", "buffer", "buf", "code",
    "table", "bitmap", "bmp",
)
COMPONENT_TOKENS = (
    "control", "indicator", "constant", "function", "primitive", "structure", "loop",
    "case", "sequence", "subvi", "invoke", "propertynode", "wire", "terminal", "connector",
    "tunnel", "pane", "panel", "diagram", "cluster", "array", "decoration", "node",
)
INTEGER_RE = re.compile(r"^[+-]?(?:0[xX][0-9A-Fa-f]+|[0-9]+)$")
FLOAT_RE = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
TUPLE_RE = re.compile(
    r"^\s*\(\s*([+-]?(?:0[xX][0-9A-Fa-f]+|\d+))\s*,\s*"
    r"([+-]?(?:0[xX][0-9A-Fa-f]+|\d+))\s*"
    r"(?:,\s*([+-]?(?:0[xX][0-9A-Fa-f]+|\d+))\s*,\s*"
    r"([+-]?(?:0[xX][0-9A-Fa-f]+|\d+))\s*)?\)\s*$"
)
XML_DECL_RE = re.compile(r"^\s*(<\?xml\s+[^?]*\?>)", re.IGNORECASE)
MAX_INLINE_VALUE = 8192


def local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def normalized_name(tag: object) -> str:
    return re.sub(r"[^a-z0-9]", "", local_name(tag).lower())


def field_name(tag: object) -> str:
    name = normalized_name(tag)
    if name.startswith("of") and len(name) > 2:
        return name[2:]
    return name


def parse_tuple(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    match = TUPLE_RE.fullmatch(value)
    if not match:
        return None
    tokens = [match.group(1), match.group(2)]
    if match.group(3) is not None:
        tokens.extend([match.group(3), match.group(4)])
    try:
        return tuple(int(token, 0) for token in tokens)
    except ValueError:
        return None


def short_hash(*parts: object, length: int = 24) -> str:
    digest = hashlib.sha256("\0".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return digest[:length]


def strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def classify_value(name: str, value: str, *, has_children: bool = False) -> tuple[str, Any]:
    text = value.strip()
    tuple_value = parse_tuple(text)
    base = field_name(name)
    normalized = normalized_name(name)
    if tuple_value is not None:
        if len(tuple_value) == 4 and (base in RECT_NAMES or base.endswith("bounds") or base.endswith("rect")):
            left, top, right, bottom = tuple_value
            return "rect", {
                "left": left, "top": top, "right": right, "bottom": bottom,
                "x": left, "y": top, "width": right - left, "height": bottom - top,
            }
        if len(tuple_value) == 2 and (
            base in POINT_NAMES or base.endswith("point") or base.endswith("ofst") or base.endswith("pos")
        ):
            y, x = tuple_value
            return "point", {"x": x, "y": y, "storage_order": "y,x"}
        return "tuple", list(tuple_value)
    if text.lower() in {"true", "false"}:
        return "bool", text.lower() == "true"
    if INTEGER_RE.fullmatch(text):
        return "int", int(text, 0)
    if FLOAT_RE.fullmatch(text):
        try:
            return "float", float(text)
        except ValueError:
            pass
    if any(token in normalized for token in BINARY_TOKENS) or len(text) > MAX_INLINE_VALUE:
        return "binary", {"size": len(value), "preview": value[:160]}
    if any(token in normalized for token in FILE_TOKENS):
        return "path", text
    if any(token in normalized for token in REFERENCE_TOKENS):
        return "reference", text
    if has_children:
        return "mixed", text
    return "string", strip_quotes(text)


def classify_component(tag: str, class_name: str, properties: list[dict[str, Any]], role: str) -> str:
    if role == "file":
        return "file"
    class_key = normalized_name(class_name)
    if class_key in {
        "term",
        "fpterm",
        "terminal",
        "connector",
        "tunnel",
        "port",
        "conpaneconnection",
        "growterminfo",
    }:
        return "connector"
    if class_key in {"wire", "signal", "hsignal", "fboxline"}:
        return "wire"
    haystack = " ".join(
        [normalized_name(tag), normalized_name(class_name)]
        + [normalized_name(prop["name"]) for prop in properties[:200]]
    )
    rules = (
        ("wire", ("wire", "segment", "route")),
        ("connector", ("connector", "conpane", "terminal", "term", "tunnel", "port")),
        ("structure", ("structure", "loop", "case", "sequence", "frame", "event")),
        ("subvi", ("subvi", "invoke", "call", "method")),
        ("constant", ("constant", "cnst", "literal")),
        ("control", ("control", "indicator", "dco", "frontpanel")),
        ("function", ("function", "primitive", "node", "operator")),
        ("container", ("cluster", "array", "pane", "panel", "diagram")),
        ("decoration", ("decoration", "label", "text")),
    )
    for kind, tokens in rules:
        if any(token in haystack for token in tokens):
            return kind
    return "component" if role == "component" else "xml-node"


def component_candidate(element: StdET.Element, parent: StdET.Element | None, root: StdET.Element) -> tuple[bool, str]:
    tag = normalized_name(element.tag)
    attrs = {normalized_name(name) for name in element.attrib}
    if element is root:
        return True, "file"
    if tag in SYSTEM_COMPONENT_TAGS:
        return True, "component"
    if tag in SYSTEM_ARRAY_TAGS or tag in SYSTEM_REFERENCE_TAGS or tag.startswith("of"):
        return False, ""
    if attrs & (CLASS_NAMES | UID_NAMES) and (len(element) or any(token in tag for token in COMPONENT_TOKENS)):
        return True, "component"
    if parent is root and normalized_name(root.tag) == "rsrc" and (len(element) or element.attrib):
        return True, "section"
    if len(element) and any(token in tag for token in COMPONENT_TOKENS):
        return True, "component"
    return False, ""


def display_path(element: StdET.Element, parent_map: dict[StdET.Element, StdET.Element]) -> str:
    parts: list[str] = []
    current = element
    while True:
        name = local_name(current.tag) or "node"
        parent = parent_map.get(current)
        if parent is None:
            parts.append(name)
            break
        siblings = [child for child in list(parent) if local_name(child.tag) == name]
        if len(siblings) > 1:
            name = f"{name}[{siblings.index(current) + 1}]"
        parts.append(name)
        current = parent
    return "/" + "/".join(reversed(parts))


def locator_map(root: StdET.Element) -> dict[StdET.Element, tuple[int, ...]]:
    result: dict[StdET.Element, tuple[int, ...]] = {root: ()}
    stack = [root]
    while stack:
        parent = stack.pop()
        prefix = result[parent]
        children = list(parent)
        for index in range(len(children) - 1, -1, -1):
            child = children[index]
            result[child] = (*prefix, index)
            stack.append(child)
    return result


def parse_xml(raw: bytes) -> StdET.Element:
    SafeET.fromstring(raw)
    parser = StdET.XMLParser(target=StdET.TreeBuilder(insert_comments=True, insert_pis=True))
    return StdET.fromstring(raw, parser=parser)


def register_namespaces(raw: bytes) -> None:
    try:
        text = raw.decode("utf-8-sig")
        for _, item in StdET.iterparse(io.StringIO(text), events=("start-ns",)):
            prefix, uri = item
            if prefix not in {"xml", "xmlns"}:
                StdET.register_namespace(prefix or "", uri)
    except (UnicodeDecodeError, StdET.ParseError, ValueError):
        return


def serialize_xml(root: StdET.Element, original: bytes) -> bytes:
    register_namespaces(original)
    try:
        text = original.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("XML is not UTF-8") from exc
    declaration_match = XML_DECL_RE.match(text)
    declaration = declaration_match.group(1) if declaration_match else ""
    serialized = StdET.tostring(root, encoding="unicode", short_empty_elements=True)
    if declaration:
        serialized = f"{declaration}\n{serialized}"
    if text.endswith("\n"):
        serialized += "\n"
    return serialized.encode("utf-8")


@dataclass(slots=True)
class FileModel:
    path: str
    sha256: str
    size: int
    root_tag: str
    elements: int
    attributes: int
    scalar_values: int
    components: list[str] = field(default_factory=list)
    root_component_id: str = ""
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
            "error": self.error,
        }


class DatasetComponentModel:
    def __init__(self) -> None:
        self.files: list[FileModel] = []
        self.components: dict[str, dict[str, Any]] = {}
        self.properties: dict[str, dict[str, Any]] = {}
        self.relationships: list[dict[str, Any]] = []
        self._uid_index: dict[str, list[str]] = defaultdict(list)
        self.warnings: list[str] = []

    @classmethod
    def analyze(cls, dataset_root: Path, *, max_bytes: int) -> DatasetComponentModel:
        model = cls()
        total = 0
        xml_files = sorted(path for path in dataset_root.rglob("*") if path.is_file() and path.suffix.lower() == ".xml")
        for path in xml_files:
            raw = path.read_bytes()
            total += len(raw)
            if total > max_bytes:
                raise ValueError("dataset XML exceeds analysis limit")
            relative = path.relative_to(dataset_root).as_posix()
            try:
                model._analyze_file(relative, raw)
            except Exception as exc:
                model.files.append(FileModel(
                    path=relative,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    size=len(raw),
                    root_tag="",
                    elements=0,
                    attributes=0,
                    scalar_values=0,
                    error=str(exc),
                ))
                model.warnings.append(f"{relative}: {exc}")
        model._resolve_references()
        return model

    def _analyze_file(self, relative: str, raw: bytes) -> None:
        root = parse_xml(raw)
        parent_map = {child: parent for parent in root.iter() for child in parent}
        locators = locator_map(root)
        file_hash = hashlib.sha256(raw).hexdigest()
        elements = [element for element in root.iter() if isinstance(element.tag, str)]
        file_model = FileModel(
            path=relative,
            sha256=file_hash,
            size=len(raw),
            root_tag=local_name(root.tag),
            elements=len(elements),
            attributes=sum(len(element.attrib) for element in elements),
            scalar_values=sum(1 for element in elements if (element.text or "").strip()),
        )
        self.files.append(file_model)

        boundaries: dict[StdET.Element, tuple[str, str]] = {}
        for element in elements:
            is_candidate, role = component_candidate(element, parent_map.get(element), root)
            if is_candidate:
                component_id = short_hash("component", relative, locators[element])
                boundaries[element] = (component_id, role)

        ordered = sorted(boundaries, key=lambda element: len(locators[element]))
        for element in ordered:
            component_id, role = boundaries[element]
            parent_component_id = None
            parent = parent_map.get(element)
            while parent is not None:
                if parent in boundaries:
                    parent_component_id = boundaries[parent][0]
                    break
                parent = parent_map.get(parent)
            component = {
                "id": component_id,
                "file": relative,
                "file_sha256": file_hash,
                "locator": list(locators[element]),
                "path": display_path(element, parent_map),
                "tag": local_name(element.tag),
                "role": role,
                "kind": "",
                "class_name": "",
                "uid": "",
                "name": "",
                "parent_id": parent_component_id,
                "children": [],
                "property_ids": [],
                "editable_property_count": 0,
                "reference_ids": [],
                "bounds": None,
                "points": [],
                "property_tree": None,
                "depth": len(locators[element]),
            }
            self.components[component_id] = component
            file_model.components.append(component_id)
            if element is root:
                file_model.root_component_id = component_id
            if parent_component_id:
                self.components[parent_component_id]["children"].append(component_id)

        owner_map: dict[StdET.Element, str] = {}
        for element in elements:
            current: StdET.Element | None = element
            while current is not None:
                if current in boundaries:
                    owner_map[element] = boundaries[current][0]
                    break
                current = parent_map.get(current)

        for element in elements:
            component_id = owner_map[element]
            locator = locators[element]
            path = display_path(element, parent_map)
            for attr_name, attr_value in element.attrib.items():
                self._add_property(self._property_record(
                    component_id=component_id,
                    file=relative,
                    locator=locator,
                    xml_path=f"{path}/@{attr_name}",
                    name=f"@{attr_name}",
                    tag=local_name(element.tag),
                    attribute=attr_name,
                    value=attr_value,
                    has_children=False,
                ))
            text = element.text or ""
            if text.strip():
                self._add_property(self._property_record(
                    component_id=component_id,
                    file=relative,
                    locator=locator,
                    xml_path=path,
                    name=local_name(element.tag),
                    tag=local_name(element.tag),
                    attribute=None,
                    value=text,
                    has_children=bool(len(element)),
                ))

        for element in ordered:
            component_id, _ = boundaries[element]
            component = self.components[component_id]
            props = [self.properties[prop_id] for prop_id in component["property_ids"]]
            component["class_name"] = self._identity_value(props, CLASS_NAMES)
            component["uid"] = self._identity_value(props, UID_NAMES)
            component["name"] = self._preferred_label(props) or component["class_name"] or component["tag"]
            component["kind"] = classify_component(component["tag"], component["class_name"], props, component["role"])
            component["bounds"] = self._preferred_bounds(props)
            component["points"] = [
                {"property_id": prop["id"], "name": prop["name"], **prop["parsed"]}
                for prop in props if prop["value_type"] == "point"
            ][:100]
            if component["uid"]:
                self._uid_index[component["uid"]].append(component_id)
                with contextlib.suppress(ValueError):
                    self._uid_index[str(int(component["uid"], 0))].append(component_id)

        for element in ordered:
            component_id, _ = boundaries[element]
            self.components[component_id]["property_tree"] = self._build_tree(
                element, component_id, boundaries, locators, parent_map
            )

    def _property_record(
        self,
        *,
        component_id: str,
        file: str,
        locator: tuple[int, ...],
        xml_path: str,
        name: str,
        tag: str,
        attribute: str | None,
        value: str,
        has_children: bool,
    ) -> dict[str, Any]:
        value_type, parsed = classify_value(name, value, has_children=has_children)
        normalized = normalized_name(name)
        base = field_name(name)
        normalized_key = normalized.lstrip("@").replace("_", "")
        base_key = base.lstrip("@").replace("_", "")
        structural = (
            normalized_key in STRUCTURAL_NAMES
            or base_key in STRUCTURAL_NAMES
            or any(token in base_key for token in UNSAFE_STRUCTURE_TOKENS)
        )
        reference_like = value_type == "reference" or normalized_name(tag) in SYSTEM_REFERENCE_TAGS
        binary = value_type == "binary"
        if structural:
            edit_level = "read_only_structure"
        elif reference_like:
            edit_level = "read_only_reference"
        elif binary or has_children:
            edit_level = "read_only_complex"
        elif value_type in {"rect", "point"} or value_type == "string" and any(
            token in base_key for token in EDIT_TEXT_TOKENS
        ) or value_type in {"int", "float", "bool"} and any(
            token in base_key
            for token in (*EDIT_APPEARANCE_TOKENS, *EDIT_DATA_TOKENS)
        ):
            edit_level = "safe"
        else:
            edit_level = "read_only_unclassified"
        editable = edit_level == "safe"
        property_id = short_hash("property", file, locator, attribute or "#text")
        preview = value if len(value) <= 512 else value[:509] + "..."
        return {
            "id": property_id,
            "component_id": component_id,
            "file": file,
            "locator": list(locator),
            "attribute": attribute,
            "path": xml_path,
            "name": name,
            "tag": tag,
            "normalized_name": normalized,
            "field_name": base,
            "value": value if len(value) <= MAX_INLINE_VALUE else None,
            "preview": preview,
            "value_size": len(value),
            "value_type": value_type,
            "parsed": parsed,
            "editable": editable,
            "edit_level": edit_level,
            "structural": structural,
            "reference_like": reference_like,
            "binary": binary,
        }

    def _add_property(self, prop: dict[str, Any]) -> None:
        self.properties[prop["id"]] = prop
        component = self.components[prop["component_id"]]
        component["property_ids"].append(prop["id"])
        if prop["editable"]:
            component["editable_property_count"] += 1
        if prop["reference_like"]:
            relation_id = short_hash("relationship", prop["id"])
            self.relationships.append({
                "id": relation_id,
                "type": "reference",
                "source_component_id": prop["component_id"],
                "property_id": prop["id"],
                "name": prop["name"],
                "target_key": (prop["value"] or prop["preview"]).strip(),
                "target_component_id": None,
                "resolved": False,
            })
            component["reference_ids"].append(relation_id)
        elif prop["value_type"] == "path":
            value = (prop["value"] or prop["preview"]).strip().strip('"')
            if value.lower().endswith((".xml", ".bin", ".vi", ".ctl", ".llb", ".lvlib", ".lvclass")):
                relation_id = short_hash("relationship", prop["id"])
                self.relationships.append({
                    "id": relation_id,
                    "type": "file",
                    "source_component_id": prop["component_id"],
                    "property_id": prop["id"],
                    "name": prop["name"],
                    "target_key": value,
                    "target_file": value,
                    "target_component_id": None,
                    "resolved": False,
                })
                component["reference_ids"].append(relation_id)

    def _identity_value(self, props: list[dict[str, Any]], names: set[str]) -> str:
        for prop in props:
            normalized = prop["normalized_name"].lstrip("@").replace("_", "")
            field = prop["field_name"].lstrip("@").replace("_", "")
            if normalized in names or field in names:
                value = prop["value"] or prop["preview"]
                if value.strip():
                    return strip_quotes(value)
        return ""

    def _preferred_label(self, props: list[dict[str, Any]]) -> str:
        for wanted in LABEL_NAMES:
            for prop in props:
                normalized = prop["normalized_name"].lstrip("@").replace("_", "")
                field = prop["field_name"].lstrip("@").replace("_", "")
                if normalized == wanted or field == wanted:
                    label = strip_quotes(prop["value"] or prop["preview"])
                    if label and len(label) <= 240:
                        return label
        return ""

    def _preferred_bounds(self, props: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates = [prop for prop in props if prop["value_type"] == "rect"]
        if not candidates:
            return None
        order = {name: index for index, name in enumerate(("bounds", "dbounds", "pbounds", "contrect", "termbounds", "iconbounds", "totalbounds"))}
        candidates.sort(key=lambda prop: order.get(prop["field_name"], 99))
        prop = candidates[0]
        return {"property_id": prop["id"], "name": prop["name"], **prop["parsed"]}

    def _build_tree(
        self,
        element: StdET.Element,
        component_id: str,
        boundaries: dict[StdET.Element, tuple[str, str]],
        locators: dict[StdET.Element, tuple[int, ...]],
        parent_map: dict[StdET.Element, StdET.Element],
    ) -> dict[str, Any]:
        def build(current: StdET.Element) -> dict[str, Any]:
            if not isinstance(current.tag, str):
                return {"kind": "comment", "preview": (current.text or "")[:160]}
            if current is not element and current in boundaries:
                child_id = boundaries[current][0]
                child = self.components[child_id]
                return {
                    "kind": "component", "component_id": child_id, "tag": child["tag"],
                    "name": child["name"] or child["tag"], "path": child["path"],
                }
            locator = locators[current]
            path = display_path(current, parent_map)
            attribute_ids = [
                short_hash("property", self.components[component_id]["file"], locator, attr)
                for attr in current.attrib
            ]
            text_id = None
            if (current.text or "").strip():
                text_id = short_hash("property", self.components[component_id]["file"], locator, "#text")
            children = [build(child) for child in list(current)]
            normalized = normalized_name(current.tag)
            if normalized in SYSTEM_ARRAY_TAGS:
                kind = "array"
            elif normalized in SYSTEM_REFERENCE_TAGS:
                kind = "reference"
            elif children:
                kind = "group"
            elif text_id:
                kind = self.properties[text_id]["value_type"]
            else:
                kind = "empty"
            return {
                "kind": kind,
                "tag": local_name(current.tag),
                "path": path,
                "locator": list(locator),
                "attribute_property_ids": attribute_ids,
                "text_property_id": text_id,
                "children": children,
            }
        return build(element)

    def _resolve_references(self) -> None:
        file_by_path = {file.path: file for file in self.files}
        file_by_name: dict[str, list[FileModel]] = defaultdict(list)
        for file in self.files:
            file_by_name[Path(file.path).name].append(file)
        for relationship in self.relationships:
            if relationship["type"] == "file":
                target = relationship.get("target_file", "").replace("\\", "/")
                matches = [file_by_path[target]] if target in file_by_path else file_by_name.get(Path(target).name, [])
                if len(matches) == 1:
                    relationship["resolved"] = True
                    relationship["target_file"] = matches[0].path
                    relationship["target_component_id"] = matches[0].root_component_id or None
                continue
            key = relationship["target_key"].strip().strip('"')
            candidates = list(dict.fromkeys(self._uid_index.get(key, [])))
            if not candidates:
                try:
                    candidates = list(dict.fromkeys(self._uid_index.get(str(int(key, 0)), [])))
                except ValueError:
                    candidates = []
            if len(candidates) == 1:
                relationship["target_component_id"] = candidates[0]
                relationship["resolved"] = True

    def summary(self) -> dict[str, Any]:
        kind_counts = Counter(component["kind"] for component in self.components.values())
        class_counts = Counter(component["class_name"] or "(unknown)" for component in self.components.values())
        element_count = sum(file.elements for file in self.files)
        return {
            "summary": {
                "xml_files": len(self.files),
                "parsed_files": sum(1 for file in self.files if file.error is None),
                "failed_files": sum(1 for file in self.files if file.error is not None),
                "elements": element_count,
                "modeled_elements": element_count,
                "attributes": sum(file.attributes for file in self.files),
                "scalar_values": sum(file.scalar_values for file in self.files),
                "components": len(self.components),
                "properties": len(self.properties),
                "editable_properties": sum(component["editable_property_count"] for component in self.components.values()),
                "relationships": len(self.relationships),
                "resolved_relationships": sum(1 for relation in self.relationships if relation["resolved"]),
                "unresolved_relationships": sum(1 for relation in self.relationships if not relation["resolved"]),
                "kinds": dict(kind_counts.most_common()),
                "classes": dict(class_counts.most_common(100)),
            },
            "files": [file.public() for file in self.files],
            "warnings": self.warnings,
        }

    def component_summary(self, component: dict[str, Any]) -> dict[str, Any]:
        return {
            key: component[key]
            for key in (
                "id", "file", "file_sha256", "path", "tag", "role", "kind", "class_name",
                "uid", "name", "parent_id", "children", "depth", "editable_property_count", "bounds",
            )
        } | {
            "property_count": len(component["property_ids"]),
            "child_count": len(component["children"]),
            "reference_count": len(component["reference_ids"]),
        }

    def list_components(
        self,
        *,
        query: str = "",
        file: str = "",
        kind: str = "",
        parent_id: str | None = None,
        offset: int = 0,
        limit: int = 200,
    ) -> dict[str, Any]:
        query_lower = query.strip().lower()
        items = list(self.components.values())
        if file:
            items = [component for component in items if component["file"] == file]
        if kind:
            items = [component for component in items if component["kind"] == kind]
        if parent_id is not None:
            items = [component for component in items if component["parent_id"] == parent_id]
        if query_lower:
            items = [
                component for component in items
                if query_lower in " ".join(
                    str(component.get(key, ""))
                    for key in ("name", "class_name", "uid", "tag", "path", "file", "kind")
                ).lower()
            ]
        items.sort(key=lambda component: (component["file"], component["path"], component["id"]))
        total = len(items)
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "items": [self.component_summary(component) for component in items[offset:offset + limit]],
        }

    def detail(self, component_id: str) -> dict[str, Any]:
        component = self.components.get(component_id)
        if component is None:
            raise KeyError(component_id)
        properties = [self.properties[prop_id] for prop_id in component["property_ids"]]
        relation_ids = set(component["reference_ids"])
        outbound = [relation for relation in self.relationships if relation["id"] in relation_ids]
        inbound = [relation for relation in self.relationships if relation.get("target_component_id") == component_id]
        breadcrumb: list[dict[str, str]] = []
        current = component
        while current:
            breadcrumb.append({"id": current["id"], "name": current["name"], "tag": current["tag"]})
            parent_id = current["parent_id"]
            current = self.components.get(parent_id) if parent_id else None
        breadcrumb.reverse()
        return {
            **self.component_summary(component),
            "locator": component["locator"],
            "property_tree": component["property_tree"],
            "properties": properties,
            "children_detail": [self.component_summary(self.components[child_id]) for child_id in component["children"]],
            "relationships": {"outbound": outbound, "inbound": inbound},
            "breadcrumb": breadcrumb,
        }
