#!/usr/bin/env python3
"""Rick's Pix: classify for public suitability, then publish approved photographs.

Run:
    python tools/process_and_publish.py

Runs against the existing local catalog.jsonl. Safe to rerun: both stages
resume from checkpoints, and the publisher upserts photo records.
Family, ambiguous and unclassified photos remain unpublished.
"""
import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REQUIRED = (
    ("CLOUDFLARE_ACCOUNT_ID", "Cloudflare Account ID", False),
    ("R2_ACCESS_KEY_ID", "R2 Access Key ID", False),
    ("R2_SECRET_ACCESS_KEY", "R2 Secret Access Key", True),
    ("CLOUDFLARE_D1_API_TOKEN", "Cloudflare D1 API token", True),
)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    catalog_default = Path(os.environ.get("LOCALAPPDATA", ".")) / "RicksPicksCatalog" / "catalog.jsonl"
    parser.add_argument("--source", default=r"G:\\My Drive\\RicksPicks\\ss\\2017",\n                        help="Photo source directory, searched recursively")\n    parser.add_argument("--ingest-limit", type=int, default=0,\n                        help="New photographs to add to catalog (0 = all)")\n    parser.add_argument("--catalog", default=str(catalog_default),
                        help="Path to the original AI catalog.jsonl")
    parser.add_argument("--classify-limit", type=int, default=0,
                        help="New photos to classify in this run (0 = all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify, then preview publishing without uploading anything")
    args = parser.parse_args()

    catalog = Path(args.catalog).expanduser().resolve()
    if not catalog.is_file():
        print(f"ERROR: Catalog not found: {catalog}", file=sys.stderr)
        return 2

    if args.classify_limit < 0:
        parser.error("--classify-limit must be zero or greater")

    env = os.environ.copy()
    if not args.dry_run:
        print("Cloudflare upload credentials are only held for this run; nothing is saved.")
        for name, label, secret in REQUIRED:
            if not env.get(name):
                value = getpass.getpass(label + ": ") if secret else input(label + ": ")
                if not value.strip():
                    print(f"ERROR: Missing {label}", file=sys.stderr)
                    return 2
                env[name] = value.strip()

    ingestion = [\n        sys.executable, str(HERE / "catalog_new_photos.py"),\n        "--source", str(Path(args.source).expanduser()),\n        "--catalog", str(catalog),\n        "--limit", str(args.ingest_limit),\n    ]\n    classification = [
        sys.executable, str(HERE / "classify_publication.py"),
        "--catalog", str(catalog),
        "--output", str(catalog.parent / "publication-decisions.jsonl"),
        "--limit", str(args.classify_limit),
    ]
    publish = [
        sys.executable, str(HERE / "publish_catalog.py"),
        "--catalog", str(catalog),
    ]
    if not args.dry_run:
        publish.append("--publish")

    try:
        print("\n=== 1/2: Classifying unpublished/uncategorized photographs ===", flush=True)
        subprocess.run(classification, env=env, check=True)
        print("\n=== 2/2: Publishing eligible photographs to R2 + D1 ===", flush=True)
        subprocess.run(publish, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"\nStopped: stage returned exit code {exc.returncode}. Run the same command after fixing the error; completed work is retained.", file=sys.stderr)
        return exc.returncode or 1
    except KeyboardInterrupt:
        print("\nInterrupted. Run the same command later to resume.", file=sys.stderr)
        return 130
    finally:
        for name, _, _ in REQUIRED:
            if name not in os.environ:
                env.pop(name, None)

    print("\nComplete. Public/documentary photos are published; family/review photos were held.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
