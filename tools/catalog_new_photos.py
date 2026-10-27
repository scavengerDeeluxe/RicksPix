#!/usr/bin/env python3
"""Discover original photos and catalog each with ONE vision-model call.

Each successful analysis appends BOTH catalog.jsonl and publication-decisions.jsonl.
No source image is modified. Safe to resume after interruption.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp", ".heic", ".heif"}
MODEL = "qwen3-vl:8b-instruct"

PROMPT = """You are an archivist preparing a public exhibition of Rick's photography.
Look at the photograph ONCE and provide its artistic description, objective quality,
AND suitability for the public exhibition. Return exactly one JSON object with:
{
 "title": "Brief evocative but factual title",
 "description": "1-3 sentences describing what is visibly happening",
 "primary_category": "Landscape | Wildlife | Dachshunds | Pets | Nature | People | Documentary | Architecture | Objects | Other",
 "subcategory": "Short specific subject",
 "season": "Winter | Spring | Summer | Fall | Unknown",
 "quality": {"overall": 1, "sharpness": 1, "exposure": 1, "composition": 1,
             "reason": "One short practical comment"},
 "publication": {"decision": "public | documentary | family | review",
                 "confidence": 0.0, "contains_people": false,
                 "private_context": false, "possible_rick_portrait": false,
                 "reason": "Brief explanation"}
}
Important category rules:
- Wildlife is for WILD animals only: wolves, lynx, moose, foxes, deer, birds, etc.
- Rick photographed many pet dachshunds. Any identifiable dachshund,
  doxie, or wiener dog belongs in the separate Dachshunds category,
  NEVER Wildlife. This includes dachshunds outdoors or in snow.
- Other domestic dogs, cats, and pets belong in Pets, NOT Wildlife.
- Categorization is independent of public suitability; do not suppress
  a pet photo just because it features Rick's dogs.
Quality scores must be integers from 1 to 10: 1 severely defective, 5 acceptable,
10 exceptional. Consider blur, exposure, noise, composition; judge the photograph,
NOT whether the subject is personally interesting.
Publication categories:
- public: landscapes, wildlife, architecture, everyday objects, etc. with no family context.
- documentary: people working, public events, ordinary street life, maintenance workers
  in winter weather, and other documentary subjects.
- family: domestic gatherings, Christmas gift opening, birthdays, celebrations,
  posed family portraits, or other purely family-oriented photographs.
- review: uncertain/private scenes, children, intimate situations, possible photos
  of the photographer Rick. You cannot identify Rick from an image. Never guess
  identity or relationships. Any potential Rick portrait requires a human decision.
Do not treat family images as public merely because they are technically excellent.
When uncertain, choose review and confidence below 0.85.
Do not mention these classification rules in the image's public description.
Only output JSON, no markdown.
"""

def json_lines(path):
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8-sig") as stream:
        for line in stream:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value
            except ValueError:
                continue

def photo_paths(source):
    for directory, dirs, files in os.walk(source):
        dirs[:] = [d for d in dirs if not d.startswith("._") and d not in {"$RECYCLE.BIN", "System Volume Information"}]
        for name in sorted(files):
            if name.startswith("._") or name.startswith(".") or name.lower() in {"thumbs.db", ".ds_store"}:
                continue
            candidate = Path(directory) / name
            if candidate.suffix.lower() in EXTENSIONS:
                yield candidate

def exif_data(path):
    # ExifTool retains Sony/GoPro maker notes, capture time, camera, lens and GPS.
    try:
        proc = subprocess.run(
            ["exiftool", "-json", "-G1", "-a", "-n", "-charset", "filename=utf8", str(path)],
            check=True, capture_output=True, text=True, timeout=45)
        values = json.loads(proc.stdout)
        if values:
            info = values[0]
            for key in list(info):
                if key.startswith(("File:", "System:", "ExifTool:")) or key == "SourceFile":
                    info.pop(key, None)
            return info
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        pass
    return {}

def preview_photo(path, target):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        if im.mode != "RGB":
            im = im.convert("RGB")
        # Avoid writing half-complete previews after interruption.
        temp = target.with_suffix(".tmp")
        try:
            im.save(temp, format="JPEG", quality=87, optimize=True)
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()

def normalize_score(value):
    try:
        return min(10, max(1, int(round(float(value)))))
    except (ValueError, TypeError, OverflowError):
        return None

def normalize_analysis(raw, model):
    if not isinstance(raw, dict):
        raise ValueError("Ollama result is not a JSON object")
    quality = raw.get("quality") if isinstance(raw.get("quality"), dict) else {}
    publication = raw.get("publication") if isinstance(raw.get("publication"), dict) else {}
    for field in ("overall", "sharpness", "exposure", "composition"):
        quality[field] = normalize_score(quality.get(field))
    quality["reason"] = str(quality.get("reason") or "")[:300]
    valid = {"public", "documentary", "family", "review"}
    kind = str(publication.get("decision") or "review").lower().strip()
    if kind not in valid:
        kind = "review"
    try:
        confidence = max(0.0, min(1.0, float(publication.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    people = publication.get("contains_people") is not False
    private = publication.get("private_context") is not False
    portrait = publication.get("possible_rick_portrait") is True
    if private or portrait or confidence < 0.85 or (kind == "public" and people):
        kind = "review"
    decision = {
        "decision": kind, "confidence": confidence, "contains_people": people,
        "private_context": private, "possible_rick_portrait": portrait,
        "reason": str(publication.get("reason") or "")[:500],
        "source": "local_ai", "model": model
    }
    analysis = {
        "title": str(raw.get("title") or "")[:180],
        "description": str(raw.get("description") or "")[:1400],
        "primary_category": category,
        "subcategory": str(raw.get("subcategory") or "")[:100],
        "season": str(raw.get("season") or "Unknown")[:30],
        "quality": quality
    }
    return analysis, decision

def infer_camera(exif):
    def get(*keys):
        return next((exif[k] for k in keys if exif.get(k)), None)
    return (
        {"make": get("IFD0:Make", "EXIF:Make", "QuickTime:Make"),
         "model": get("IFD0:Model", "EXIF:Model", "QuickTime:Model")},
        {"datetime_original": get("ExifIFD:DateTimeOriginal", "EXIF:DateTimeOriginal",
                                  "QuickTime:CreationDate", "IFD0:DateTime")}
    )

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    base = Path(os.environ.get("LOCALAPPDATA", ".")) / "RicksPicksCatalog"
    ap.add_argument("--source", required=True, help="Original photo directory (recursive)")
    ap.add_argument("--catalog", default=str(base / "catalog.jsonl"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=0, help="New images to catalog, 0=all")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434/api/chat")
    args = ap.parse_args()
    source = Path(args.source).expanduser().resolve()
    catalog = Path(args.catalog).expanduser().resolve()
    if not source.is_dir():
        ap.error(f"Photo source directory does not exist: {source}")
    if args.limit < 0:
        ap.error("--limit cannot be negative")
    catalog.parent.mkdir(parents=True, exist_ok=True)
    decisions_path = catalog.parent / "publication-decisions.jsonl"
    previews = catalog.parent / "previews"
    previews.mkdir(parents=True, exist_ok=True)
    known_ids = set()
    known_paths = set()
    for item in json_lines(catalog):
        if item.get("id"):
            known_ids.add(str(item["id"]))
        if item.get("relative_path"):
            known_paths.add(str(item["relative_path"]).replace("\\", "/").casefold())
    count = skipped = failed = 0
    with requests.Session() as session, catalog.open("a", encoding="utf-8") as out, decisions_path.open("a", encoding="utf-8") as decisions:
        for path in photo_paths(source):
            relative = path.relative_to(source).as_posix()
            # Existing catalog entries were generated by an earlier cataloger: skip
            # those even when their ID hashing algorithm differs.
            if relative.casefold() in known_paths:
                skipped += 1
                continue
            # Stable within this source directory, including across reruns.
            identifier = hashlib.sha256((str(source).casefold() + "/" + relative.casefold()).encode("utf-8")).hexdigest()[:32]
            if identifier in known_ids:
                skipped += 1
                continue
            preview = previews / (identifier + ".jpg")
            try:
                if not preview.is_file():
                    preview_photo(path, preview)
                encoded = base64.b64encode(preview.read_bytes()).decode("ascii")
                payload = {
                    "model": args.model, "stream": False, "format": "json",
                    "options": {"temperature": 0, "num_ctx": 8192},
                    "messages": [{"role": "user", "content": PROMPT, "images": [encoded]}]
                }
                response = session.post(args.ollama, json=payload, timeout=360)
                response.raise_for_status()
                raw = json.loads(response.json()["message"]["content"])
                analysis, decision = normalize_analysis(raw, args.model)
                exif = exif_data(path)
                camera, capture = infer_camera(exif)
                record = {
                    "id": identifier, "filename": path.name, "relative_path": relative,
                    "source": str(path), "preview": str(preview.resolve()),
                    "camera": camera, "capture": capture, "exif": exif,
                    "analysis": analysis
                }
                decision["id"] = identifier
                # Write the publication decision before catalog so interruption never
                # leaves a new record requiring a second vision pass.
                decisions.write(json.dumps(decision, ensure_ascii=False, default=str) + "\n")
                decisions.flush()
                out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                out.flush()
                known_ids.add(identifier)
                known_paths.add(relative.casefold())
                count += 1
                print(f"[{count}] {decision['decision'].upper():12} Q{analysis['quality']['overall'] or '?'} {relative} — {analysis['description']}", flush=True)
                if args.limit and count >= args.limit:
                    break
            except (OSError, UnidentifiedImageError, ValueError, KeyError, requests.RequestException) as exc:
                failed += 1
                print(f"FAILED {relative}: {exc}", file=sys.stderr, flush=True)
                if failed >= 20:
                    print("Stopping at 20 failures; rerun after investigating.", file=sys.stderr)
                    break
    print(f"New catalog entries: {count}; existing skipped: {skipped}; failures: {failed}")
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
