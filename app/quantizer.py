from __future__ import annotations

import contextlib
import io
import math
import re
import xml.etree.ElementTree as StdET
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Literal

from defusedxml import ElementTree as SafeET

from .errors import AppError

RoundingMode = Literal["nearest", "floor", "ceil"]
CoordinateKind = Literal["object", "connector", "wire"]

# HeapNodeRect fields emitted by pylabview/LVheap.py plus additional bounds/rect
# names found in LabVIEW front-panel and block-diagram heaps. A value is only
# touched when its complete text is a 4-integer coordinate tuple.
RECT_TAGS = {
    "bounds",
    "contrect",
    "dbounds",
    "pbounds",
    "hoodbounds",
    "iconbounds",
    "growareabounds",
    "docbounds",
    "dynbounds",
    "savedsize",
    "termbounds",
    "view",
    "scalerect",
    "totalbounds",
    "sizerect",
    "srcrect",
    "crectabove",
    "crectbelow",
    "subviglyphbounds",
    "callerglyphbounds",
}

# HeapNodePoint fields emitted by pylabview/LVheap.py. Point values are stored
# as (y, x), but snapping each coordinate independently is order agnostic.
POINT_TAGS = {
    "origin",
    "minpanesize",
    "minpanelsize",
    "termhotpoint",
    "minbutsize",
    "nrc",
    "orc",
    "termofst",
    "pos",
    "hotpoint",
}

CONNECTOR_TOKENS = (
    "connector",
    "conpane",
    "terminal",
    "term",
    "glyph",
    "tunnel",
    "port",
)
WIRE_TOKENS = (
    "wire",
    "line",
    "segment",
    "route",
    "path",
    "bend",
    "fboxline",
)
BINARY_WIRE_TOKENS = ("compressedwiretable",)

_INTEGER = r"[+-]?(?:0[xX][0-9A-Fa-f]+|[0-9]+)"
TUPLE_RE = re.compile(
    rf"^(?P<leading>\s*)\(\s*(?P<v1>{_INTEGER})\s*,\s*(?P<v2>{_INTEGER})"
    rf"(?:\s*,\s*(?P<v3>{_INTEGER})\s*,\s*(?P<v4>{_INTEGER}))?\s*\)(?P<trailing>\s*)$"
)
XML_DECLARATION_RE = re.compile(r"^\s*(<\?xml\s+[^?]*\?>)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class QuantizeOptions:
    grid_size: int = 8
    rounding: RoundingMode = "nearest"
    include_objects: bool = True
    include_connectors: bool = True
    include_wires: bool = True
    resize_rectangles: bool = False

    def validate(self) -> None:
        if not 1 <= self.grid_size <= 256:
            raise AppError(
                "グリッド粒度は1〜256で指定してください。",
                code="invalid_grid_size",
                status_code=422,
            )
        if self.rounding not in {"nearest", "floor", "ceil"}:
            raise AppError(
                "丸め方式が不正です。",
                code="invalid_rounding",
                status_code=422,
            )
        if not (self.include_objects or self.include_connectors or self.include_wires):
            raise AppError(
                "少なくとも1つの対象を選択してください。",
                code="empty_quantize_scope",
                status_code=422,
            )


@dataclass(frozen=True, slots=True)
class ParsedTuple:
    values: tuple[int, ...]
    tokens: tuple[str, ...]
    leading: str
    trailing: str


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    name = tag.rsplit("}", 1)[-1]
    return name.rsplit(":", 1)[-1]


def _normalized_name(tag: object) -> str:
    return re.sub(r"[^a-z0-9]", "", _local_name(tag).lower())


def _contains_token(names: Iterable[str], tokens: tuple[str, ...]) -> bool:
    return any(token in name for name in names for token in tokens)


def _parse_tuple(text: str | None) -> ParsedTuple | None:
    if text is None:
        return None
    match = TUPLE_RE.fullmatch(text)
    if not match:
        return None
    tokens = [match.group("v1"), match.group("v2")]
    if match.group("v3") is not None:
        tokens.extend([match.group("v3"), match.group("v4")])
    try:
        values = tuple(int(token, 0) for token in tokens)
    except ValueError:
        return None
    return ParsedTuple(
        values=values,
        tokens=tuple(tokens),
        leading=match.group("leading"),
        trailing=match.group("trailing"),
    )


def _format_like(token: str, value: int) -> str:
    stripped = token.strip()
    unsigned = stripped.lstrip("+-")
    is_negative = value < 0
    absolute = abs(value)
    if unsigned.lower().startswith("0x"):
        uppercase = "X" in unsigned or any(char in "ABCDEF" for char in unsigned[2:])
        digits = format(absolute, "X" if uppercase else "x")
        prefix = "0X" if unsigned.startswith("0X") else "0x"
        sign = "-" if is_negative else "+" if stripped.startswith("+") else ""
        return f"{sign}{prefix}{digits}"
    if value >= 0 and stripped.startswith("+"):
        return f"+{value}"
    return str(value)


def _format_tuple(parsed: ParsedTuple, values: tuple[int, ...]) -> str:
    formatted = [
        _format_like(token, value)
        for token, value in zip(parsed.tokens, values, strict=True)
    ]
    return f"{parsed.leading}({', '.join(formatted)}){parsed.trailing}"


def _quantize_scalar(value: int, grid: int, mode: RoundingMode) -> int:
    if mode == "floor":
        return math.floor(value / grid) * grid
    if mode == "ceil":
        return math.ceil(value / grid) * grid
    # Deliberately use half-away-from-zero rather than Python's banker's round;
    # this makes dragging and positive/negative diagram coordinates symmetric.
    absolute = abs(value)
    rounded = ((absolute * 2 + grid) // (grid * 2)) * grid
    return -rounded if value < 0 else rounded


def _quantize_dimension(value: int, grid: int, mode: RoundingMode) -> int:
    if value == 0:
        return 0
    sign = -1 if value < 0 else 1
    quantized = abs(_quantize_scalar(abs(value), grid, mode))
    if quantized == 0:
        quantized = grid
    return sign * quantized


def _quantize_values(
    values: tuple[int, ...], options: QuantizeOptions, *, kind: CoordinateKind
) -> tuple[int, ...]:
    grid = options.grid_size
    mode = options.rounding
    if len(values) == 2:
        return tuple(_quantize_scalar(value, grid, mode) for value in values)
    if len(values) != 4:
        return values

    left, top, right, bottom = values
    new_left = _quantize_scalar(left, grid, mode)
    new_top = _quantize_scalar(top, grid, mode)

    # For wire rectangles/segments, all edges are route coordinates. For object
    # and connector bounds the default is translation-only, so controls do not
    # accidentally resize merely because they were one pixel off-grid.
    if kind == "wire":
        return (
            new_left,
            new_top,
            _quantize_scalar(right, grid, mode),
            _quantize_scalar(bottom, grid, mode),
        )

    width = right - left
    height = bottom - top
    if options.resize_rectangles:
        width = _quantize_dimension(width, grid, mode)
        height = _quantize_dimension(height, grid, mode)
    return (new_left, new_top, new_left + width, new_top + height)


def _classify(
    element: StdET.Element,
    ancestors: tuple[StdET.Element, ...],
    tuple_length: int,
) -> CoordinateKind | None:
    local = _normalized_name(element.tag)
    lineage = tuple(_normalized_name(item.tag) for item in (*ancestors, element))

    if _contains_token(lineage, WIRE_TOKENS):
        return "wire"
    if _contains_token(lineage, CONNECTOR_TOKENS):
        return "connector"

    # pylabview may serialize enum names as OF__bounds / OF__origin. The
    # normalized form is therefore "ofbounds" / "oforigin"; strip the field
    # prefix for matching while retaining the full lineage for classification.
    field_name = local[2:] if local.startswith("of") and len(local) > 2 else local
    if tuple_length == 4 and (
        field_name in RECT_TAGS
        or field_name.endswith("bounds")
        or field_name.endswith("rect")
    ):
        return "object"
    if tuple_length == 2 and (
        field_name in POINT_TAGS
        or field_name.endswith("point")
        or field_name.endswith("ofst")
        or field_name.endswith("pos")
    ):
        return "object"
    return None


def _kind_enabled(kind: CoordinateKind, options: QuantizeOptions) -> bool:
    return {
        "object": options.include_objects,
        "connector": options.include_connectors,
        "wire": options.include_wires,
    }[kind]


def _element_path(
    element: StdET.Element,
    parent_map: dict[StdET.Element, StdET.Element],
) -> str:
    parts: list[str] = []
    current = element
    while True:
        name = _local_name(current.tag) or "node"
        parent = parent_map.get(current)
        if parent is None:
            parts.append(name)
            break
        siblings = [child for child in list(parent) if _local_name(child.tag) == name]
        if len(siblings) > 1:
            with contextlib.suppress(ValueError):
                name = f"{name}[{siblings.index(current) + 1}]"
        parts.append(name)
        current = parent
    return "/" + "/".join(reversed(parts))


def _register_namespaces(content: str) -> None:
    try:
        for _, (prefix, uri) in StdET.iterparse(io.StringIO(content), events=("start-ns",)):
            # Reserved prefixes cannot be registered and are already handled by ET.
            if prefix not in {"xml", "xmlns"}:
                StdET.register_namespace(prefix or "", uri)
    except (StdET.ParseError, ValueError):
        # SafeET validation below remains authoritative. Namespace registration is
        # only a serialization fidelity improvement.
        return


def quantize_xml(
    content: str,
    options: QuantizeOptions,
    *,
    require_rsrc_root: bool = True,
) -> dict[str, Any]:
    options.validate()
    if not content.strip():
        raise AppError("XMLが空です。", code="empty_xml", status_code=422)

    try:
        # First perform hardened validation. A second stdlib parse is used only
        # after this succeeds so comments and processing instructions survive.
        SafeET.fromstring(content)
    except Exception as exc:
        raise AppError(
            "XMLを解析できません。",
            code="invalid_xml",
            status_code=422,
            details={"reason": str(exc)},
        ) from exc

    _register_namespaces(content)
    parser = StdET.XMLParser(
        target=StdET.TreeBuilder(insert_comments=True, insert_pis=True)
    )
    try:
        root = StdET.fromstring(content, parser=parser)
    except StdET.ParseError as exc:
        raise AppError(
            "XMLを解析できません。",
            code="invalid_xml",
            status_code=422,
            details={"reason": str(exc)},
        ) from exc

    root_tag = _local_name(root.tag)
    if require_rsrc_root and root_tag != "RSRC":
        raise AppError(
            "メインXMLのルート要素は RSRC である必要があります。",
            code="not_rsrc_xml",
            status_code=422,
            details={"root_tag": root_tag},
        )

    parent_map = {child: parent for parent in root.iter() for child in parent}
    ancestors_cache: dict[StdET.Element, tuple[StdET.Element, ...]] = {}

    def ancestors_for(element: StdET.Element) -> tuple[StdET.Element, ...]:
        cached = ancestors_cache.get(element)
        if cached is not None:
            return cached
        lineage: list[StdET.Element] = []
        current = parent_map.get(element)
        while current is not None:
            lineage.append(current)
            current = parent_map.get(current)
        result = tuple(reversed(lineage))
        ancestors_cache[element] = result
        return result

    matched_by_kind: Counter[str] = Counter()
    changed_by_kind: Counter[str] = Counter()
    changed_by_tag: Counter[str] = Counter()
    changed_values = 0
    samples: list[dict[str, Any]] = []
    binary_wire_blocks = 0

    for element in root.iter():
        local = _normalized_name(element.tag)
        is_opaque_wire_table = (
            local == "wiretable"
            and len(element) == 0
            and bool((element.text or "").strip())
            and _parse_tuple(element.text) is None
        )
        if local in BINARY_WIRE_TOKENS or is_opaque_wire_table:
            binary_wire_blocks += 1

        parsed = _parse_tuple(element.text)
        if parsed is None:
            continue
        kind = _classify(element, ancestors_for(element), len(parsed.values))
        if kind is None or not _kind_enabled(kind, options):
            continue

        matched_by_kind[kind] += 1
        quantized = _quantize_values(parsed.values, options, kind=kind)
        if quantized == parsed.values:
            continue

        before = element.text or ""
        after = _format_tuple(parsed, quantized)
        element.text = after
        changed_by_kind[kind] += 1
        changed_by_tag[_local_name(element.tag) or "node"] += 1
        changed_values += sum(1 for old, new in zip(parsed.values, quantized, strict=True) if old != new)
        if len(samples) < 40:
            samples.append(
                {
                    "path": _element_path(element, parent_map),
                    "tag": _local_name(element.tag),
                    "kind": kind,
                    "before": before.strip(),
                    "after": after.strip(),
                }
            )

    total_changes = sum(changed_by_kind.values())
    if total_changes == 0:
        serialized = content
    else:
        declaration_match = XML_DECLARATION_RE.match(content)
        declaration = declaration_match.group(1) if declaration_match else ""
        serialized = StdET.tostring(root, encoding="unicode", short_empty_elements=True)
        if declaration:
            serialized = f"{declaration}\n{serialized}"
        if content.endswith("\n"):
            serialized += "\n"

    warnings: list[str] = []
    if sum(matched_by_kind.values()) == 0:
        warnings.append(
            "対象となる座標タプルが見つかりませんでした。対象VIでは配置情報が別XMLまたはBINへ外部化されている可能性があります。"
        )
    if options.include_wires and matched_by_kind["wire"] == 0:
        warnings.append(
            "XML上で配線ルート座標を検出できませんでした。compressedWireTableなどのバイナリ配線情報は変更していません。"
        )
    elif binary_wire_blocks:
        warnings.append(
            f"バイナリ/圧縮形式の配線ブロックを{binary_wire_blocks}件検出しました。XMLで展開された座標だけを変更しています。"
        )

    return {
        "content": serialized,
        "report": {
            "root_tag": root_tag,
            "grid_size": options.grid_size,
            "rounding": options.rounding,
            "resize_rectangles": options.resize_rectangles,
            "matched_elements": sum(matched_by_kind.values()),
            "changed_elements": total_changes,
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
            "changed_by_tag": dict(changed_by_tag.most_common(30)),
            "samples": samples,
            "warnings": warnings,
        },
    }
