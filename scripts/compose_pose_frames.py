"""Generate click gesture frames from the supplied pose references."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


POSE_ROOT = Path(__file__).resolve().parents[1] / "assets" / "poses"
CELL_SIZE = (192, 208)

# Hold the user-approved tilt, then let the gesture finish on its own and
# restore standing. Keeping standing out of the gesture sequence avoids an
# extra transitional redraw before the final pose.
HEAD_TILT_PHASES = (
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
)


def load_cell(name: str) -> Image.Image:
    image = Image.open(POSE_ROOT / name).convert("RGBA")
    if image.size == CELL_SIZE:
        return image
    canvas = Image.new("RGBA", CELL_SIZE, (0, 0, 0, 0))
    left = (CELL_SIZE[0] - image.width) // 2
    top = CELL_SIZE[1] - image.height
    canvas.alpha_composite(image, (left, top))
    return canvas


def generate_head_tilt() -> None:
    for stale in POSE_ROOT.glob("head-tilt_*.png"):
        stale.unlink()
    for index, name in enumerate(HEAD_TILT_PHASES):
        cell = load_cell(name)
        cell.save(POSE_ROOT / f"head-tilt_{index}.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--head-tilt",
        action="store_true",
        help="generate the click head-tilt frames",
    )
    args = parser.parse_args()
    if args.head_tilt:
        generate_head_tilt()
    else:
        raise SystemExit("Choose --head-tilt.")


if __name__ == "__main__":
    main()
