"""Generate longitudinal demo photo sets via Nano Banana Pro (Gemini 3 Pro Image).

For each demo patient, generate three visit photos with maintained identity but
visibly different skin condition (so the longitudinal radar chart shows real
progression in the demo video).

Requires the GEMINI_API_KEY environment variable. If unset, prints instructions
and exits without making API calls.

Usage:
    GEMINI_API_KEY=... uv run python scripts/generate_demo_photos.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

NANO_BANANA_SCRIPT = Path.home() / ".claude/skills/nano-banana-pro/scripts/generate_image.py"

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "demo_photos"

# (filename, prompt, optional input-image filename to edit from)
DEMO_SHOTS: list[tuple[str, str, str | None]] = [
    (
        "patient1_visit1_baseline.jpg",
        (
            "Frontal medical-aesthetic clinic intake photo of an Asian woman in her early 30s, "
            "neutral expression, soft natural daylight, clean light-grey background, "
            "1024x1024 portrait. She has visible melasma — symmetric brown pigmentation "
            "patches across both cheeks, typical of post-pregnancy hyperpigmentation. "
            "Clinic-style sharpness, no makeup, no jewelry, no text, no watermark."
        ),
        None,
    ),
    (
        "patient1_visit2_midway.jpg",
        (
            "Edit the previous photo to show the same woman 4 weeks into pigmentation "
            "treatment. The melasma patches on the cheeks should be noticeably faded — "
            "lighter in colour and smaller in extent — while keeping the same face shape, "
            "hair, lighting, and background completely identical."
        ),
        "patient1_visit1_baseline.jpg",
    ),
    (
        "patient1_visit3_final.jpg",
        (
            "Edit the previous photo to show the same woman 8 weeks into treatment. The "
            "melasma should be mostly cleared, with only a faint residual unevenness. "
            "Keep face shape, hair, lighting, and background identical."
        ),
        "patient1_visit2_midway.jpg",
    ),
    (
        "patient2_visit1_baseline.jpg",
        (
            "Frontal medical-aesthetic clinic intake photo of an Asian woman in her mid 40s, "
            "neutral expression, soft natural daylight, clean light-grey background, "
            "1024x1024 portrait. She has visible horizontal forehead lines, mild crow's feet, "
            "and slight nasolabial folds. No makeup, no jewelry, no text, no watermark."
        ),
        None,
    ),
    (
        "patient2_visit2_midway.jpg",
        (
            "Edit the previous photo to keep the same identity but shoot it under WARM "
            "TUNGSTEN lighting from the upper-left, with a slightly orange colour cast — "
            "this deliberately mismatches the clinic's standard daylight balance. Soften "
            "the forehead lines slightly (4-week treatment progress) but keep the lighting "
            "deliberately off-spec so the consistency gate will flag it."
        ),
        "patient2_visit1_baseline.jpg",
    ),
    (
        "patient2_visit3_final.jpg",
        (
            "Edit the previous photo to return to neutral daylight (same as visit 1). The "
            "forehead lines and crow's feet should now be significantly softer (8 weeks of "
            "treatment). Keep face shape, hair, and background identical."
        ),
        "patient2_visit2_midway.jpg",
    ),
]


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY environment variable is not set.")
        print()
        print("To obtain a key, sign up at https://aistudio.google.com/")
        print("Then run:")
        print("    export GEMINI_API_KEY=your_key_here")
        print("    uv run python scripts/generate_demo_photos.py")
        return 1

    if not NANO_BANANA_SCRIPT.exists():
        print(f"ERROR: nano-banana-pro skill not found at {NANO_BANANA_SCRIPT}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, prompt, input_image in DEMO_SHOTS:
        output_path = OUTPUT_DIR / filename
        cmd = [
            "uv", "run", str(NANO_BANANA_SCRIPT),
            "--prompt", prompt,
            "--filename", str(output_path),
            "--resolution", "1K",
        ]
        if input_image:
            cmd.extend(["--input-image", str(OUTPUT_DIR / input_image)])

        print(f"\n>>> Generating {filename}{' (edit-mode)' if input_image else ''}")
        result = subprocess.run(cmd, capture_output=False)
        if result.returncode != 0:
            print(f"FAILED generating {filename}")
            return result.returncode
    print(f"\nDone. {len(DEMO_SHOTS)} photos saved under {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
