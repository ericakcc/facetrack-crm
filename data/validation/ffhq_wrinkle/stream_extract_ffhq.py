"""Stream FFHQ-1024 WebDataset shards and keep only the manually-masked IDs.

Streams each needed shard from gaunernst/ffhq-1024-wds (lossless WebP
transcodes of the official images1024x1024 set) and extracts only the
members whose FFHQ ID has a manual wrinkle mask. Resumable: already
extracted images are skipped, fully-covered shards are not re-streamed.
"""

import csv
import sys
import tarfile
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
SHARD_URL = "https://huggingface.co/datasets/gaunernst/ffhq-1024-wds/resolve/main/{:05d}.tar"
OUT_DIR = BASE / "images"


def load_wanted_ids(csv_path: Path) -> set[int]:
    """Read the FFHQ IDs that have manual wrinkle masks."""
    with csv_path.open() as f:
        return {int(row["ffhq_id"]) for row in csv.DictReader(f)}


def main() -> None:
    wanted = load_wanted_ids(BASE / "ffhq_manual_ids_urls.csv")
    OUT_DIR.mkdir(exist_ok=True)
    have = {int(p.stem) for p in OUT_DIR.glob("*.webp")}
    todo = wanted - have
    print(f"wanted={len(wanted)} have={len(have)} todo={len(todo)}", flush=True)

    shards = sorted({i // 1000 for i in todo})
    for shard in shards:
        shard_ids = {i for i in todo if i // 1000 == shard}
        url = SHARD_URL.format(shard * 1000)
        print(f"shard {shard:05d}: need {len(shard_ids)} images", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "ffhq-wrinkle-validation"})
        with (
            urllib.request.urlopen(req, timeout=120) as resp,
            tarfile.open(fileobj=resp, mode="r|") as tar,
        ):
            found = 0
            for member in tar:
                stem = Path(member.name).stem
                if not stem.isdigit() or int(stem) not in shard_ids:
                    continue
                fobj = tar.extractfile(member)
                if fobj is None:
                    continue
                (OUT_DIR / f"{int(stem):05d}.webp").write_bytes(fobj.read())
                found += 1
                if found == len(shard_ids):
                    break  # got everything from this shard, stop streaming it
        print(f"shard {shard:05d}: extracted {found}/{len(shard_ids)}", flush=True)

    n = len(list(OUT_DIR.glob("*.webp")))
    print(f"done: {n}/{len(wanted)} images in {OUT_DIR}", flush=True)
    if n < len(wanted):
        sys.exit(1)


if __name__ == "__main__":
    main()
