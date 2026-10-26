#!/usr/bin/env python3
"""Publish Rick's Pix JSONL catalog to Cloudflare R2 + D1.

By default this is a read-only dry run. Use --publish to upload/upsert.
Source originals are NEVER opened or modified; only pre-generated previews
and JSONL metadata are read. Requires: pip install -r tools/requirements.txt
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from io import BytesIO

import boto3
import requests
from PIL import Image, ImageOps

DATABASE_ID = "f0c828b2-983e-4bc3-b62d-c60f888e9175"
BUCKET = "rickspix"
SQL = """
INSERT INTO photos
(id,source_path,title,description,category,subcategory,captured_at,season,
 camera_make,camera_model,image_key,thumb_key,quality_score,ai_metadata,exif_metadata,published)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
ON CONFLICT(id) DO UPDATE SET
 title=excluded.title,description=excluded.description,category=excluded.category,
 subcategory=excluded.subcategory,captured_at=excluded.captured_at,
 season=excluded.season,camera_make=excluded.camera_make,
 camera_model=excluded.camera_model,image_key=excluded.image_key,
 thumb_key=excluded.thumb_key,quality_score=excluded.quality_score,
 ai_metadata=excluded.ai_metadata,exif_metadata=excluded.exif_metadata,
 published=1
"""

def env_required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing environment variable {name}")
    return value

def checkpoint_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS completed (id TEXT PRIMARY KEY, completed_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    return conn

def metadata(record):
    exif = record.get("exif") or {}
    camera = record.get("camera") or {}
    capture = record.get("capture") or {}
    a = record.get("analysis") or {}
    date = (capture.get("datetime_original") or exif.get("ExifIFD:DateTimeOriginal")
            or exif.get("EXIF:DateTimeOriginal") or exif.get("DateTimeOriginal"))
    if isinstance(date, str) and len(date) >= 19:
        date = date[:19].replace(":", "-", 2).replace(" ", "T")
    else:
        date = None
    q = a.get("quality") or {}
    score = q.get("overall")
    try:
        score = int(score)
        if not 1 <= score <= 10:
            score = None
    except (TypeError, ValueError):
        score = None
    return [
        str(record["id"]),
        str(record.get("relative_path") or record.get("filename") or record["id"]),
        str(a.get("title") or Path(record.get("filename", "")).stem or "Untitled"),
        str(a.get("description") or ""),
        str(a.get("primary_category") or "Uncategorized"),
        a.get("subcategory"),
        date,
        a.get("season"),
        camera.get("make") or exif.get("EXIF:Make") or exif.get("IFD0:Make"),
        camera.get("model") or exif.get("EXIF:Model") or exif.get("IFD0:Model"),
        f"photos/{record['id']}.jpg",
        f"thumbs/{record['id']}.jpg",
        score,
        json.dumps(a, ensure_ascii=False),
        json.dumps(exif, ensure_ascii=False),
    ]

def thumbnail(path):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((460, 460), Image.Resampling.LANCZOS)
        out = BytesIO()
        im.convert("RGB").save(out, "JPEG", quality=83, optimize=True)
        return out.getvalue()

def d1_query(session, endpoint, sql, params):
    response = session.post(endpoint, json={"sql": sql, "params": [
        "" if p is None else str(p) for p in params
    ]}, timeout=40)
    response.raise_for_status()
    result = response.json()
    if not result.get("success") or any(not item.get("success", False) for item in result.get("result", [])):
        raise RuntimeError(f"D1 rejected query: {result.get('errors') or result.get('result')}")
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=str(Path(os.environ.get("LOCALAPPDATA", ".")) / "RicksPicksCatalog" / "catalog.jsonl"))
    parser.add_argument("--state", default=None, help="Local checkpoint SQLite; defaults next to catalog")
    parser.add_argument("--limit", type=int, default=0, help="Limit new successful photos (0=all)")
    parser.add_argument("--publish", action="store_true", help="Actually upload to R2 and write D1")
    args = parser.parse_args()
    catalog = Path(args.catalog)
    if not catalog.is_file():
        parser.error(f"Catalog not found: {catalog}")
    if not args.publish:
        print("DRY RUN: no uploads or database writes. Add --publish when ready.")

    state_path = Path(args.state) if args.state else catalog.parent / "publish-state.sqlite3"
    state = checkpoint_db(state_path) if args.publish else None
    s3 = session = endpoint = None
    if args.publish:
        account = env_required("CLOUDFLARE_ACCOUNT_ID")
        api_token = env_required("CLOUDFLARE_D1_API_TOKEN")
        s3 = boto3.client(
            "s3", endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            region_name="auto", aws_access_key_id=env_required("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=env_required("R2_SECRET_ACCESS_KEY"))
        session = requests.Session()
        session.headers.update({"Authorization": f"Bearer {api_token}"})
        endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{DATABASE_ID}/query"

    successes = skipped = failed = 0
    with catalog.open("r", encoding="utf-8-sig") as f:
        for line_num, line in enumerate(f, 1):
            try:
                record = json.loads(line)
                photo_id = str(record["id"])
                if state and state.execute("SELECT 1 FROM completed WHERE id=?", (photo_id,)).fetchone():
                    skipped += 1
                    continue
                preview = Path(record["preview"])
                if not preview.is_file():
                    raise FileNotFoundError(f"Missing preview: {preview}")
                params = metadata(record)
                if args.publish:
                    s3.upload_file(str(preview), BUCKET, params[10], ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "public, max-age=31536000, immutable"})
                    s3.put_object(Bucket=BUCKET, Key=params[11], Body=thumbnail(preview), ContentType="image/jpeg", CacheControl="public, max-age=31536000, immutable")
                    d1_query(session, endpoint, SQL, params)
                    state.execute("INSERT OR IGNORE INTO completed(id) VALUES (?)", (photo_id,))
                    state.commit()
                successes += 1
                print(f"[{successes}] {'PUBLISHED' if args.publish else 'READY'} {record.get('relative_path', photo_id)}")
                if args.limit and successes >= args.limit:
                    break
            except Exception as exc:
                failed += 1
                print(f"FAILED line {line_num}: {exc}", file=sys.stderr)
    if state:
        state.close()
    print(f"Finished: {successes} successful, {skipped} previously published, {failed} failed")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
