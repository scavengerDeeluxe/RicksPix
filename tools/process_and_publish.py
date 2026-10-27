#!/usr/bin/env python3
"""Rick's Pix: discover, catalog, screen and publish photographs.

A NEW photo gets one Ollama analysis for both description and publication status.
Existing catalog entries lacking a decision get a one-time backfill classification.
Runs are resumable and never modify original image files.
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
    base = Path(os.environ.get("LOCALAPPDATA", ".")) / "RicksPicksCatalog"
    parser.add_argument("--source", default="G:/My Drive/RicksPicks/ss",
                        help="Photo source folder, recursively scanned")
    parser.add_argument("--catalog", default=str(base / "catalog.jsonl"))
    parser.add_argument("--ingest-limit", type=int, default=0,
                        help="Number of new photos to add (0 = all)")
    parser.add_argument("--classify-limit", type=int, default=0,
                        help="Legacy catalog decisions to backfill (0 = all)")
    parser.add_argument("--model", default="qwen3-vl:8b-instruct")
    parser.add_argument("--dry-run", action="store_true",
                        help="Create local catalog/decisions but do not upload")
    args = parser.parse_args()
    if args.ingest_limit < 0 or args.classify_limit < 0:
        parser.error("Limits must be zero or greater")
    catalog = Path(args.catalog).expanduser().resolve()
    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        parser.error(f"Photo source folder not found: {source}")

    env = os.environ.copy()
    if not args.dry_run:
        print("Cloudflare credentials are used only for this process and are not saved.")
        for name, label, secret in REQUIRED:
            if not env.get(name):
                value = getpass.getpass(label + ": ") if secret else input(label + ": ")
                if not value.strip():
                    parser.error(f"Missing {label}")
                env[name] = value.strip()

    ingestion = [
        sys.executable, str(HERE / "catalog_new_photos.py"),
        "--source", str(source), "--catalog", str(catalog),
        "--model", args.model, "--limit", str(args.ingest_limit),
    ]
    legacy = [
        sys.executable, str(HERE / "classify_publication.py"),
        "--catalog", str(catalog),
        "--output", str(catalog.parent / "publication-decisions.jsonl"),
        "--model", args.model, "--limit", str(args.classify_limit),
    ]
    publish = [
        sys.executable, str(HERE / "publish_catalog.py"),
        "--catalog", str(catalog),
    ]
    if not args.dry_run:
        publish.append("--publish")

    try:
        print("\n=== 1/3: Discover + catalog + decide suitability (one AI call/photo) ===", flush=True)
        subprocess.run(ingestion, env=env, check=True)
        print("\n=== 2/3: One-time screening for previously cataloged photographs ===", flush=True)
        subprocess.run(legacy, env=env, check=True)
        print("\n=== 3/3: Publish approved photographs to Cloudflare ===", flush=True)
        subprocess.run(publish, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"Stage failed with exit code {exc.returncode}. Rerun to resume.", file=sys.stderr)
        return exc.returncode or 1
    except KeyboardInterrupt:
        print("Interrupted. Rerun to resume.", file=sys.stderr)
        return 130
    finally:
        for name, _, _ in REQUIRED:
            if name not in os.environ:
                env.pop(name, None)

    print("\nDone: approved public/documentary photos published; family/review held.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
