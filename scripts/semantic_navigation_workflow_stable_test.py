from __future__ import annotations

import semantic_navigation_workflow_test as workflow_test
from playwright.sync_api import Page


def stable_set_view_and_select(
    page: Page,
    object_id: str,
    box: dict[str, float],
) -> None:
    """Model a user selection followed by a deliberate pan/zoom operation.

    The original fixture used a fixed 120 ms timer. On a fast, wide viewport the
    next selection could begin before the previous Surface restore had consumed
    that timer, so the test itself wrote B's box into C's history entry. Wait for
    the editor and density runtimes to become idle, then apply the requested box
    synchronously and observe two stable animation frames.
    """
    target_surface = page.evaluate(
        """id => window.VISemanticEditor.S.objects.get(id)?.surface
          || 'block-diagram'""",
        object_id,
    )
    page.wait_for_function(
        """() => Boolean(
          window.VINavigationHistoryStability?.ready
          && window.VICanvasDensity?.ready
          && window.VISemanticEditor?.S?.vi
        )"""
    )
    page.evaluate(
        "id => window.VISemanticEditor.select(id, true)",
        object_id,
    )
    page.wait_for_function(
        """({id, surface}) => {
          const S = window.VISemanticEditor.S;
          const D = window.VICanvasDensity?.runtime;
          const H = window.VINavigationHistoryStability?.runtime;
          return S.selected === id
            && S.surface === surface
            && !D?.pendingSurface
            && !D?.scheduled
            && !D?.applying
            && !H?.settling;
        }""",
        {"id": object_id, "surface": target_surface},
    )
    page.evaluate(
        "box => window.VICanvasDensity.applyBox(box, 'manual')",
        box,
    )
    page.wait_for_function(
        """box => {
          const S = window.VISemanticEditor.S;
          const D = window.VICanvasDensity?.runtime;
          const close = key => Math.abs(Number(S.box?.[key]) - Number(box[key])) <= 0.05;
          return ['x', 'y', 'width', 'height'].every(close)
            && !D?.pendingSurface
            && !D?.scheduled
            && !D?.applying;
        }""",
        box,
    )
    page.wait_for_timeout(48)
    page.wait_for_function(
        """box => {
          const S = window.VISemanticEditor.S;
          return ['x', 'y', 'width', 'height'].every(
            key => Math.abs(Number(S.box?.[key]) - Number(box[key])) <= 0.05
          );
        }""",
        box,
    )


def main() -> int:
    workflow_test.set_view_and_select = stable_set_view_and_select
    return workflow_test.main()


if __name__ == "__main__":
    raise SystemExit(main())
