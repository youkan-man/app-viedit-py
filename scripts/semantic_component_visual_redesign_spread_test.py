from __future__ import annotations

import semantic_component_visual_redesign_test as base


_original_model = base.model


def spread_model():
    """Place visual families far enough apart to exercise overview LOD at 1920px."""
    value = _original_model()
    by_id = {item["id"]: item for item in value["vi"]["objects"]}

    # The semantic-visual assertions are independent of automatic layout. A
    # deliberately wide fixture makes the Overview command actually zoom out
    # on every supported viewport instead of remaining at normal LOD on a
    # 1920-pixel display.
    by_id["projection-structure"]["bounds"].update(
        {"x": 1500, "y": 340, "width": 330, "height": 225}
    )
    by_id["visual-block-generic"]["bounds"].update(
        {"x": 1260, "y": 475, "width": 105, "height": 72}
    )
    by_id["visual-block-string-constant"]["bounds"].update(
        {"x": 1030, "y": 470, "width": 150, "height": 54}
    )
    return value


base.model = spread_model


if __name__ == "__main__":
    raise SystemExit(base.main())
