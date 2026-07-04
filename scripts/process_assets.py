"""Downscale captured PNGs to web-friendly JPEGs for the pitch deck."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets"

# name -> max width
APP_SHOTS = {
    "app_patients": 1600,
    "app_intake_gate": 1600,
    "app_overview": 1600,
    "app_history": 1600,
    "app_history_expanded": 1500,
    "app_history_overlay": 1500,
    "app_history_rois": 1600,
    "app_treatment": 1600,
}
CLOSEUPS = {
    "composite_v3_0518_pigmentation": 820,
    "face_v3_0518_roi": 820,
    "heat_v3_0518_pore": 820,
    "heat_v3_0518_pigmentation": 820,
    "heat_v1_0118_pigmentation": 820,
}


def convert(stem: str, max_w: int, quality: int) -> None:
    src = OUT / f"{stem}.png"
    if not src.exists():
        print(f"  skip (missing) {stem}")
        return
    im = Image.open(src).convert("RGB")
    if im.width > max_w:
        h = round(im.height * max_w / im.width)
        im = im.resize((max_w, h), Image.LANCZOS)
    dst = OUT / f"{stem}.jpg"
    im.save(dst, "JPEG", quality=quality, optimize=True)
    print(f"  {dst.name}  {im.width}x{im.height}  {dst.stat().st_size // 1024} KB")


def main() -> None:
    print("app screenshots:")
    for stem, w in APP_SHOTS.items():
        convert(stem, w, 88)
    print("close-ups:")
    for stem, w in CLOSEUPS.items():
        convert(stem, w, 86)
    total = sum(f.stat().st_size for f in OUT.glob("*.jpg"))
    print(f"\ntotal jpg: {total // 1024} KB across {len(list(OUT.glob('*.jpg')))} files")


if __name__ == "__main__":
    main()
