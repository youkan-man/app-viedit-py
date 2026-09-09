"""Project native heap objects onto selectable LabVIEW components.

The complete XML object tree is retained for inspection. Only known cosmetic
objects are omitted from the canvas. Borrowed visual properties keep their
original owner, locator and serialization format; edits use an explicit list.
"""
from __future__ import annotations

import re
from typing import Any

COSMETIC_CLASSES = {
    "image", "cosm", "subcosm", "multicosm", "bigmulticosm", "texthair",
    "fontrun", "annex", "numlabel", "scale", "grid", "tableattribute",
    "storagerowcol", "clstrobj", "keymaplist", "propiteminfo", "eventspec",
    "attachment", "dynlink", "polyselector",
}
ROOT_CLASSES = {"ohext", "supc", "srn", "diag", "pane", "conpane"}
LOGICAL_CLASSES = {"fpdco", "bdconstdco"}
WIDGET_CLASSES = {
    "stdnum", "stdstring", "stdbool", "stdslide", "stdknob", "stdring",
    "stdpath", "stdrefnum", "stdclust", "indarr", "tablecontrol",
}
NATIVE_KINDS = {
    **dict.fromkeys(WIDGET_CLASSES | {"fpdco"}, "control"),
    "bdconstdco": "constant",
    **dict.fromkeys({"prim", "nmux", "abuild", "aindx", "lcnt", "lmax", "ltst"}, "function"),
    **dict.fromkeys({"iuse", "dyniuse", "polyiuse", "propnode", "propitem"}, "subvi"),
    **dict.fromkeys({"forloop", "whileloop", "eventstruct"}, "structure"),
    **dict.fromkeys({"lptun", "innerlptun", "seltun", "parm", "overridableparm",
                     "iusedco", "polyiusedco", "nmxdco", "abuilddco", "aidco",
                     "eventdyndco", "eventdatanode", "eventtimeout"}, "connector"),
    **dict.fromkeys(ROOT_CLASSES, "container"),
    **dict.fromkeys(COSMETIC_CLASSES | {"label", "multilabel"}, "decoration"),
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def native_kind(class_key: str) -> str | None:
    return NATIVE_KINDS.get(class_key)


def primary_component(component: dict[str, Any], components: dict[str, dict[str, Any]]) -> bool:
    key = _key(component.get("class_name", ""))
    if component.get("role") != "component" or key in COSMETIC_CLASSES | ROOT_CLASSES:
        return False
    if key in LOGICAL_CLASSES:
        return True
    parent_id = component.get("parent_id")
    while parent_id and parent_id in components:
        parent = components[parent_id]
        parent_key = _key(parent.get("class_name", ""))
        if parent_key in LOGICAL_CLASSES and key in WIDGET_CLASSES | {"label", "multilabel"}:
            return False
        if parent_key in COSMETIC_CLASSES or parent_key in {"label", "multilabel"}:
            return False
        parent_id = parent.get("parent_id")
    return True


def enrich_native_components(
    components: dict[str, dict[str, Any]], properties: dict[str, dict[str, Any]],
) -> None:
    """Join fPDCO/bDConstDCO to its ddo, label and explicitly owned text record."""
    for component in sorted(components.values(), key=lambda item: -item["depth"]):
        key = _key(component["class_name"])
        children = [components[child_id] for child_id in component["children"]]
        own_props = [properties[prop_id] for prop_id in component["property_ids"]]
        component["presentation_property_ids"] = []
        if key == "texthair":
            text = next((prop for prop in own_props if prop["field_name"] == "text"), None)
            if text:
                component["name"] = str(text["parsed"])
                component["presentation_property_ids"] = [text["id"]]
        elif key in {"label", "multilabel"}:
            text = next((child for child in children if _key(child["class_name"]) == "texthair"), None)
            if text:
                component["name"] = text["name"]
                component["presentation_property_ids"] = list(text["presentation_property_ids"])
        elif key in WIDGET_CLASSES:
            labels = [child for child in children if _key(child["class_name"]) == "label"]
            if labels:
                label = labels[0]
                component["name"] = label["name"]
                component["presentation_property_ids"] = list(label["presentation_property_ids"])
        elif key in LOGICAL_CLASSES:
            visual = next((child for child in children if _key(child["tag"]) == "ddo"), None)
            if not visual:
                continue
            component["widget"] = visual["class_name"]
            if visual["bounds"] is not None and component["bounds"] is None:
                component["bounds"] = dict(visual["bounds"])
            if visual["name"] not in {visual["tag"], visual["class_name"]}:
                component["name"] = visual["name"]
            # No arbitrary descendant editing: only direct visual scalars and
            # the main label text are explicitly delegated to the logical DCO.
            component["presentation_property_ids"] = list(dict.fromkeys([
                *[prop_id for prop_id in visual["property_ids"] if properties[prop_id]["editable"]],
                *visual["presentation_property_ids"],
            ]))
            component["editable_property_count"] += sum(
                bool(properties[prop_id]["editable"])
                for prop_id in component["presentation_property_ids"]
            )
