#!/usr/bin/env python3
"""Add exact Russian caption and carousel badge overlays to generated post photos.

Requires ImageMagick 6 (`convert` and `identify`). Each source image is named like
п1-ф1.jpg beside its matching п1-ф1.txt prompt. JPEG comment metadata makes the
operation idempotent, so already-rendered assets are safely skipped.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MARKER = "vk-post-overlay-v1"


def run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, text=True, capture_output=True)
    return result.stdout.strip()


def image_size(path: Path) -> tuple[int, int]:
    raw = run(["identify", "-format", "%w %h", str(path)])
    width, height = (int(value) for value in raw.split())
    return width, height


def is_rendered(path: Path) -> bool:
    comment = run(["identify", "-format", "%c", str(path)])
    return MARKER in comment


def render(prompt_file: Path, image_file: Path) -> None:
    content = prompt_file.read_text(encoding="utf-8")
    title_match = re.search(r"(?m)^ТЕКСТ НА КАРТИНКЕ: «(.*)»\s*$", content)
    if not title_match:
        raise ValueError(f"No Russian image title in {prompt_file}")
    title = title_match.group(1).strip()
    swipe = bool(re.search(r"(?m)^ЛИСТАЙ: да\s*$", content))

    width, height = image_size(image_file)
    margin_x = round(width * 0.04)
    panel_width = width - 2 * margin_x
    panel_height = round(height * (0.137 if swipe else 0.145))
    panel_y = round(height * (0.714 if swipe else 0.792))
    panel_x2 = width - margin_x
    panel_y2 = min(height - 1, panel_y + panel_height)
    corner = max(16, round(width * 0.025))

    caption_width = max(300, panel_width - round(width * 0.125))
    caption_height = max(72, panel_height - round(height * 0.02))
    caption_x = (width - caption_width) // 2
    caption_y = panel_y + (panel_height - caption_height) // 2
    font_size = max(28, round(width * 0.043))

    command = [
        "convert", str(image_file),
        "-fill", "rgba(0,0,0,0.60)",
        "-draw", f"roundrectangle {margin_x},{panel_y} {panel_x2},{panel_y2} {corner},{corner}",
        "(",
        "-background", "none", "-fill", "white", "-font", str(FONT),
        "-pointsize", str(font_size), "-size", f"{caption_width}x{caption_height}",
        "-gravity", "center", f"caption:{title}",
        ")",
        "-gravity", "north", "-geometry", f"+{caption_x}+{caption_y}",
        "-compose", "over", "-composite",
    ]

    if swipe:
        badge_width = round(width * 0.235)
        badge_height = round(height * 0.07)
        badge_corner = badge_height // 2
        badge_font = max(20, round(width * 0.026))
        badge = [
            "(", "-size", f"{badge_width}x{badge_height}", "xc:none",
            "-fill", "rgba(0,0,0,0.72)",
            "-draw", f"roundrectangle 0,0 {badge_width - 1},{badge_height - 1} {badge_corner},{badge_corner}",
            "-font", str(FONT), "-pointsize", str(badge_font), "-fill", "white",
            "-gravity", "center", "-annotate", "+0+0", "ЛИСТАЙ →", ")",
            "-gravity", "southeast",
            "-geometry", f"+{round(width * 0.039)}+{round(height * 0.041)}",
            "-compose", "over", "-composite",
        ]
        command.extend(badge)

    with tempfile.NamedTemporaryFile(suffix=".jpg", dir=image_file.parent, delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        command.extend([
            "-strip", "-set", "comment", MARKER,
            "-sampling-factor", "4:2:0", "-quality", "84", str(temp_path),
        ])
        run(command)
        temp_path.replace(image_file)
    finally:
        temp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "communities", nargs="*", type=Path, default=[Path("сообщества")],
        help="community folder(s), or the communities root (default: сообщества)",
    )
    args = parser.parse_args()
    if not shutil.which("convert") or not shutil.which("identify"):
        parser.error("ImageMagick is required (convert and identify were not found)")
    if not FONT.is_file():
        parser.error(f"Cyrillic bold font was not found: {FONT}")

    processed = skipped = missing = 0
    failures: list[str] = []
    prompt_files: set[Path] = set()
    for community in args.communities:
        if community.name == "сообщества":
            prompt_files.update(community.glob("*/день-*/картинки/п*-ф*.txt"))
        else:
            prompt_files.update(community.glob("день-*/картинки/п*-ф*.txt"))

    for prompt_file in sorted(prompt_files):
        image_file = prompt_file.with_suffix(".jpg")
        if not image_file.is_file():
            missing += 1
            continue
        try:
            if is_rendered(image_file):
                skipped += 1
                continue
            render(prompt_file, image_file)
            processed += 1
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            failures.append(f"{image_file}: {error}")

    print(f"Rendered: {processed}; already rendered: {skipped}; missing JPGs: {missing}")
    if failures:
        print("Failures:")
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
