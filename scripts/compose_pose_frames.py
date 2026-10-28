"""Generate click gesture frames from the supplied pose references.

Wing poses stay as complete source drawings. Never cut out or rotate an
individual wing: that moves parts of the face and torso into the wing layer.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops


POSE_ROOT = Path(__file__).resolve().parents[1] / "assets" / "poses"
SPRITE_PATH = POSE_ROOT.parent / "spritesheet.png"
CELL_SIZE = (192, 208)
FRAME_SIZE = (320, 320)
FRAME_BASELINE = 274
FRAME_PADDING = 6

# All four gestures start and finish on the exact idle sprite. Each interior
# frame comes from one source pose only, so actions cannot bleed into others.
HEAD_TILT_PHASES = (
    "standing",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "peek_base.png",
    "standing",
)

WING_POSES = {
    "cheer": "cheer.png",
    "wave": "wave.png",
}
STRETCH_POSE = "stretch.png"

# Each source uses a different perspective. These factors normalize the
# apparent head size while scaling the complete drawing uniformly.
HEAD_SCALES = {
    "head-tilt": 0.993,
    "head-stretch": 0.862,
    "cheer": 1.823,
    "wave": 1.065,
}


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


def pose_cell(content: Image.Image, label: str = "pose") -> Image.Image:
    """Align visible pixels to the shared canvas and foot baseline."""
    bbox = content.getchannel("A").getbbox()
    if not bbox:
        return Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    content = content.crop(bbox)
    if content.height > FRAME_BASELINE - FRAME_PADDING:
        raise SystemExit(
            f"{label}: pose is {content.height}px tall and would be clipped"
        )
    if content.width > FRAME_SIZE[0] - FRAME_PADDING * 2:
        raise SystemExit(
            f"{label}: pose is {content.width}px wide and would be clipped"
        )
    canvas = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    left = (FRAME_SIZE[0] - content.width) // 2
    top = FRAME_BASELINE - content.height
    canvas.alpha_composite(content, (left, top))
    return canvas


def scaled_pose_cell(
    content: Image.Image,
    scale: float = 1.0,
    label: str = "pose",
) -> Image.Image:
    """Scale the complete drawing uniformly, then align it to the baseline."""
    if scale != 1.0:
        content = content.resize(
            (
                max(1, round(content.width * scale)),
                max(1, round(content.height * scale)),
            ),
            Image.Resampling.NEAREST,
        )
    return pose_cell(content, label)


def whole_pose_cell(name: str, scale: float = 1.0) -> Image.Image:
    """Scale a complete source drawing; never crop a wing into a layer."""
    source = load_cell(str(Path("sources") / name))
    return scaled_pose_cell(source, scale, name)


def generate_pose(name: str, frames: list[Image.Image]) -> None:
    for stale in POSE_ROOT.glob(f"{name}_*.png"):
        stale.unlink()
    for index, frame in enumerate(frames):
        frame.save(POSE_ROOT / f"{name}_{index}.png")
    print(f"{name}: {len(frames)} whole-pose frames")


def generate_gestures() -> None:
    standing = load_standing_cell()
    standing_pose = pose_cell(standing, "standing")
    generate_pose(
        "head-tilt",
        [
            standing_pose
            if source == "standing"
            else scaled_pose_cell(
                load_cell(source),
                HEAD_SCALES["head-tilt"],
                source,
            )
            for source in HEAD_TILT_PHASES
        ],
    )
    generate_pose(
        "head-stretch",
        [
            standing_pose,
            *(
                [whole_pose_cell(STRETCH_POSE, HEAD_SCALES["head-stretch"])]
                * 5
            ),
            standing_pose,
        ],
    )
    for name, source in WING_POSES.items():
        pose = whole_pose_cell(source, HEAD_SCALES[name])
        generate_pose(
            name,
            [standing_pose, *([pose] * 5), standing_pose],
        )


def main_yellow_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    """Return the largest connected yellow head region."""
    mask = {
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y))[3] > 200
        and image.getpixel((x, y))[0] > 180
        and image.getpixel((x, y))[1] > 145
        and image.getpixel((x, y))[2] < 150
    }
    components = []
    while mask:
        seed = mask.pop()
        queue = deque([seed])
        component = [seed]
        while queue:
            x, y = queue.popleft()
            for point in (
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ):
                if point in mask:
                    mask.remove(point)
                    queue.append(point)
                    component.append(point)
        components.append(component)
    component = max(components, key=len)
    return (
        min(x for x, _ in component),
        min(y for _, y in component),
        max(x for x, _ in component) + 1,
        max(y for _, y in component) + 1,
    )


def head_metric(name: str, frame_index: int) -> float:
    image = Image.open(POSE_ROOT / f"{name}_{frame_index}.png").convert("RGBA")
    left, top, right, bottom = main_yellow_bbox(image)
    return ((right - left) * (bottom - top)) ** 0.5


def verify_generated_frames() -> None:
    standing_image = Image.open(POSE_ROOT / "head-tilt_0.png").convert("RGBA")
    for name in ("head-tilt", "head-stretch", "cheer", "wave"):
        paths = sorted(POSE_ROOT.glob(f"{name}_*.png"))
        if len(paths) != 7:
            raise SystemExit(f"{name}: expected 7 frames, found {len(paths)}")
        frames = [Image.open(path).convert("RGBA") for path in paths]
        for path, frame in zip(paths, frames):
            if frame.size != FRAME_SIZE:
                raise SystemExit(f"{path.name}: expected {FRAME_SIZE}, got {frame.size}")
            bbox = frame.getchannel("A").getbbox()
            if not bbox:
                raise SystemExit(f"{path.name}: empty frame")
            left, top, right, bottom = bbox
            if (
                left < FRAME_PADDING
                or top < FRAME_PADDING
                or right > FRAME_SIZE[0] - FRAME_PADDING
                or bottom > FRAME_SIZE[1] - FRAME_PADDING
            ):
                raise SystemExit(f"{path.name}: content too close to canvas edge")
        if ImageChops.difference(frames[0], frames[-1]).getbbox() is not None:
            raise SystemExit(f"{name}: first and last frames differ")
        if ImageChops.difference(frames[0], standing_image).getbbox() is not None:
            raise SystemExit(f"{name}: first frame differs from standing")

    standing_metric = head_metric("head-tilt", 0)
    for name, index in (
        ("head-tilt", 1),
        ("head-stretch", 3),
        ("cheer", 1),
        ("wave", 1),
    ):
        ratio = head_metric(name, index) / standing_metric
        print(f"{name}: head scale ratio {ratio:.3f}")
        if not 0.94 <= ratio <= 1.06:
            raise SystemExit(
                f"{name}: head scale drift {ratio:.3f}; expected 0.94..1.06"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.parse_args()
    generate_gestures()
    verify_generated_frames()


if __name__ == "__main__":
    main()
