from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = Path(
    os.getenv(
        "BUILD_ARTIFACT_DIR",
        str(ROOT / "artifacts" / "readable-diagram-density"),
    )
)
COLUMNS = 3
CELL_WIDTH = 440
CELL_HEIGHT = 300
LABEL_HEIGHT = 32


def image_paths() -> list[Path]:
    preferred = ("basic", "medium", "huge-overview")
    resolutions = ("1365x768", "1440x900", "1920x1080")
    result: list[Path] = []
    for resolution in resolutions:
        for kind in preferred:
            path = ARTIFACTS / f"readable-{kind}-{resolution}.png"
            if path.exists():
                result.append(path)
    return result


def render_sheet(paths: list[Path]) -> Path:
    if not paths:
        raise FileNotFoundError(f"no readable diagram screenshots in {ARTIFACTS}")
    rows = (len(paths) + COLUMNS - 1) // COLUMNS
    sheet = Image.new(
        "RGB",
        (COLUMNS * CELL_WIDTH, rows * CELL_HEIGHT),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((CELL_WIDTH - 16, CELL_HEIGHT - LABEL_HEIGHT - 16))
        column = index % COLUMNS
        row = index // COLUMNS
        left = column * CELL_WIDTH + (CELL_WIDTH - image.width) // 2
        top = row * CELL_HEIGHT + LABEL_HEIGHT
        sheet.paste(image, (left, top))
        draw.text(
            (column * CELL_WIDTH + 8, row * CELL_HEIGHT + 8),
            path.stem,
            fill="black",
        )
    output = ARTIFACTS / "readable-diagram-contact-sheet.jpg"
    sheet.save(output, quality=42, optimize=True)
    return output


def emit(path: Path) -> None:
    data = path.read_bytes()
    encoded = base64.b64encode(data).decode("ascii")
    print(f"READABLE_CONTACT_SHEET_SHA256={hashlib.sha256(data).hexdigest()}")
    print(f"READABLE_CONTACT_SHEET_BYTES={len(data)}")
    for offset in range(0, len(encoded), 3000):
        print(
            f"READABLE_CONTACT_SHEET_B64_{offset // 3000:03d}="
            + encoded[offset : offset + 3000]
        )


def main() -> int:
    output = render_sheet(image_paths())
    emit(output)
    print(f"READABLE_CONTACT_SHEET_PATH={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
