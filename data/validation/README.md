# Validation datasets

External, real-world datasets for **offline validation and tuning** of the two
core features — the Photo-Consistency Gate and the 5-metric scoring engine —
against independent ground truth. This replaces the earlier calibration on just
5 reference faces in `data/test_images/`.

> **Real-person pixels never enter git** (repo non-negotiable §5). This folder's
> `.gitignore` block tracks only the reproducible bits — download/sampling
> scripts, ID/URL manifests, license notes, and (under `results/`) the aggregate
> CSV/PNG the validation scripts emit. Images, masks, and the large FFHQ
> metadata JSON stay local. Anyone can rebuild the pixels by re-running the
> fetch scripts below.

## What each dataset validates

| Dataset | Ground truth | Validates | Script |
|---|---|---|---|
| **FFHQ-Wrinkle** | 1,000 hand-drawn wrinkle masks | `wrinkle_raw` ranking + Sobel cutoff | `scripts/validation/validate_wrinkle_ffhq.py` |
| **ACNE04** | 1,457 dermatologist severity grades (0–3) | `erythema_raw` / texture rise with severity (known-groups) | `scripts/validation/validate_severity_acne04.py` |
| **SCIN** | Self-reported Fitzpatrick skin type | Gate YCrCb skin check for dark-skin bias (LIMITATIONS §4) | `scripts/validation/validate_skintone_bias_scin.py` |

All three scripts import the **production** `facetrack` functions (no
re-implementation), resize inputs to `NORMALIZED_FACE_WIDTH_PX = 512` to match
the deployed pipeline, and write results under `<dataset>/results/`.

```bash
uv run python scripts/validation/validate_wrinkle_ffhq.py
uv run python scripts/validation/validate_severity_acne04.py
uv run python scripts/validation/validate_skintone_bias_scin.py
```

---

## FFHQ-Wrinkle — `ffhq_wrinkle/`

- **Source**: Kim et al., *"A Facial Wrinkle Detection Dataset"* — masks:
  https://github.com/labhai/ffhq-wrinkle-dataset ; images: the official FFHQ
  `images1024x1024` set (NVlabs), streamed losslessly from the
  `gaunernst/ffhq-1024-wds` WebDataset mirror on Hugging Face.
- **License**: FFHQ-Wrinkle masks & FFHQ images are **CC BY-NC-SA 4.0**
  (non-commercial; attribution via paper citation). Fine for offline research
  validation; do **not** ship these pixels in a product.
- **Contents (local only)**: `manual_wrinkle_masks/*.png` (1,000 masks, IDs
  00001–21035, 1024×1024 grayscale) + `images/*.webp` (the matching FFHQ faces).
- **Tracked**: `ffhq_manual_ids_urls.csv` (mask ID → official FFHQ Drive URL +
  md5), `stream_extract_ffhq.py` (streams only the needed shards and keeps only
  the masked IDs — no 90 GB full download), `stream_extract_ffhq.py` is
  resumable.

Re-fetch:
```bash
cd data/validation/ffhq_wrinkle
bash <(curl -sL https://raw.githubusercontent.com/labhai/ffhq-wrinkle-dataset/main/download_ffhq_wrinkle.sh)  # masks → ./data, then move to ./manual_wrinkle_masks
python stream_extract_ffhq.py    # matching FFHQ images (needs ffhq_manual_ids_urls.csv)
```

## ACNE04 — `acne04/`

- **Source**: Wu et al., *"Joint Acne Image Grading and Counting via Label
  Distribution Learning"*, ICCV 2019. Watermark-cleaned mirror:
  `ManuelHettich/acne04` on Hugging Face. Original:
  https://github.com/xpwu95/LDL
- **License**: free for **academic use**; other uses require contacting the
  author (xpwu95@163.com).
- **Contents (local only)**: `acne{0,1,2,3}_1024/*.jpg` — faces bucketed by
  Hayashi severity grade (0 = mild … 3 = very severe), ~99/100/99/96 images.
- Grade folders = the known-groups labels; no separate manifest needed.

Re-fetch:
```bash
uv run --with 'huggingface_hub[cli]' hf download ManuelHettich/acne04 \
  --repo-type dataset --include 'acne0_1024/*' 'acne1_1024/*' 'acne2_1024/*' 'acne3_1024/*' \
  --local-dir data/validation/acne04
```

## SCIN — `scin/`

- **Source**: Ward et al., *SCIN (Skin Condition Image Network)*,
  Google Research × Stanford. Public GCS bucket `dx-scin-public-data`
  (no auth). https://github.com/google-research-datasets/scin
- **License**: *SCIN Data Use License* (CC BY 4.0-style, research use).
- **Contents**: `scin_cases.csv` + `scin_labels.csv` (metadata, **tracked**) and
  a Fitzpatrick-stratified image sample under `images/` (local only, ~360 imgs,
  ≤60 per FST1–FST6, head/neck preferred; darker types over-sampled so the bias
  test has power).
- **Tracked**: the two metadata CSVs, `sample_download_scin.py`,
  `scin_sample_manifest.csv` (the exact sampled case IDs → files).

Re-fetch:
```bash
cd data/validation/scin
curl -O https://storage.googleapis.com/dx-scin-public-data/dataset/scin_cases.csv
curl -O https://storage.googleapis.com/dx-scin-public-data/dataset/scin_labels.csv
python sample_download_scin.py
```

---

## Not included (and why)

- **Melasma/MASI, rosacea CEA graded image sets** — no public version exists
  (all live inside clinics behind VISIA units). Confirmed absent; do not re-search.
- **Kesty SkinAnalysis** (3,662 imgs graded on pigmentation + redness + wrinkles
  — the closest 1:1 to our 5 metrics) — available **on request** only. Email
  drkesty@stpeteskinandlaser.com to obtain; drop it in `kesty/` when it arrives.
