"""Generate click gesture frames from the supplied pose references."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


POSE_ROOT = Path(__file__).resolve().parents[1] / "assets" / "poses"
SPRITE_PATH = POSE_ROOT.parent / "spritesheet.png"
CELL_SIZE = (192, 208)

# Every gesture starts and finishes on the same standing frame.
HEAD_TILT_PHASES = (
    "standing",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "standing",
)

HEAD_STRETCH_PHASES = (
    "standing",
    "peek_1.png",
    "peek_2.png",
    "peek_3.png",
    "peek_2.png",
    "peek_1.png",
    "standing",
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


def load_standing_cell() -> Image.Image:
    """Use the exact frame rendered while idle so gesture starts do not jump."""
    sheet = Image.open(SPRITE_PATH).convert("RGBA")
    return sheet.crop((0, 0, CELL_SIZE[0], CELL_SIZE[1]))


def generate_pose(name: str, phases: tuple[str, ...]) -> None:
    for stale in POSE_ROOT.glob(f"{name}_*.png"):
        stale.unlink()
    for index, source in enumerate(phases):
        cell = load_standing_cell() if source == "standing" else load_cell(source)
        cell.save(POSE_ROOT / f"{name}_{index}.png")


def generate_gestures() -> None:
    generate_pose("head-tilt", HEAD_TILT_PHASES)
    generate_pose("head-stretch", HEAD_STRETCH_PHASES)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--head-tilt",
        action="store_true",
        help="generate the click head-tilt frames",
    )
    parser.add_argument(
        "--head-stretch",
        action="store_true",
        help="generate the click head-stretch frames",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="generate every click gesture",
    )
    args = parser.parse_args()
    if args.all:
        generate_gestures()
    elif args.head_tilt:
        generate_pose("head-tilt", HEAD_TILT_PHASES)
    elif args.head_stretch:
        generate_pose("head-stretch", HEAD_STRETCH_PHASES)
    else:
        raise SystemExit("Choose --head-tilt, --head-stretch, or --all.")


if __name__ == "__main__":
    main()
