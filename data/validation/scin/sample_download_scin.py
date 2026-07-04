"""Stratified sample of SCIN images across Fitzpatrick skin types.

Purpose: probe the gate's YCrCb skin-visibility check for skin-tone bias
(LIMITATIONS §4) — does very dark skin (FST5/FST6) get falsely flagged as
occluded? We over-sample the darker types and prefer head/neck shots so the
images are face-relevant. Images stream from the public GCS bucket; nothing
here needs auth.
"""

import csv
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent
GCS = "https://storage.googleapis.com/dx-scin-public-data/{}"
PER_TYPE = 60  # target images per Fitzpatrick type
TYPES = ["FST1", "FST2", "FST3", "FST4", "FST5", "FST6"]
OUT = BASE / "images"


def build_sample() -> dict[str, list[dict]]:
    """Pick up to PER_TYPE cases per Fitzpatrick type, head/neck first."""
    cases = list(csv.DictReader((BASE / "scin_cases.csv").open()))
    by_type: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        fst = c["fitzpatrick_skin_type"]
        if fst in TYPES and c["image_1_path"]:
            by_type[fst].append(c)

    sample: dict[str, list[dict]] = {}
    for fst in TYPES:
        rows = by_type[fst]
        # deterministic order: head/neck first, then by case_id
        rows.sort(key=lambda r: (r.get("body_parts_head_or_neck") != "YES", r["case_id"]))
        sample[fst] = rows[:PER_TYPE]
    return sample


def main() -> None:
    OUT.mkdir(exist_ok=True)
    sample = build_sample()
    manifest_rows = []
    for fst in TYPES:
        rows = sample[fst]
        head = sum(1 for r in rows if r.get("body_parts_head_or_neck") == "YES")
        print(f"{fst}: {len(rows)} cases ({head} head/neck)", flush=True)
        for r in rows:
            src = r["image_1_path"]  # e.g. dataset/images/-123.png
            fname = f"{fst}_{r['case_id']}.png"
            dst = OUT / fname
            if not dst.exists():
                try:
                    urllib.request.urlretrieve(GCS.format(src), dst)
                except Exception as e:  # noqa: BLE001 - log and skip flaky fetches
                    print(f"  skip {r['case_id']}: {e}", flush=True)
                    continue
            manifest_rows.append(
                {
                    "fitzpatrick": fst,
                    "case_id": r["case_id"],
                    "file": fname,
                    "head_or_neck": r.get("body_parts_head_or_neck", ""),
                    "shot_type": r.get("image_1_shot_type", ""),
                }
            )

    with (BASE / "scin_sample_manifest.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["fitzpatrick", "case_id", "file", "head_or_neck", "shot_type"]
        )
        w.writeheader()
        w.writerows(manifest_rows)
    print(f"done: {len(manifest_rows)} images, manifest written", flush=True)


if __name__ == "__main__":
    main()
