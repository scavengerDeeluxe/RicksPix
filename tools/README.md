# Rick's Pix: one command, one vision analysis per new photograph

From PowerShell in the RicksPix repository folder:

```powershell
git pull
python ./tools/process_and_publish.py
```

By default the script recursively scans `G:/My Drive/RicksPicks/ss/2017`. To scan the entire `ss` collection, specify `--source "G:/My Drive/RicksPicks/ss"`.

For each **new** source photograph:

1. Discover the file (ignore macOS `._` sidecars and non-images).
2. Create a 1280px JPEG preview without modifying the original.
3. Call local Ollama `qwen3-vl:8b-instruct` **once** to determine subject, title, caption, category, quality 1–10 and public/documentary/family/review suitability.
4. Append metadata to `catalog.jsonl` and the decision to `publication-decisions.jsonl`.
5. Publish eligible images to R2 and their metadata to Cloudflare D1.

Photos already in the catalog are skipped by the source scanner. Records from the earlier pilot lacking publication decisions receive **one legacy backfill** pass; newer photos never need that second pass. Previously classified photos are not reclassified. Uploads resume using `publish-state.sqlite3`.

Family, ambiguous, child-centered and private photos remain on local disk and are **not** automatically published. Photos of Rick may be manually approved after a human identifies him; the model never assumes who Rick is.

For a **known Rick** photograph, append the following to `publication-overrides.jsonl` next to `catalog.jsonl`:

```json
{"id":"ACTUAL_CATALOG_ID","decision":"rick_approved","source":"human","reason":"Verified by family"}
```

## Unattended, long-running scans

The driver requests that Windows stay awake while it runs (it does not block
manual restarts, forced Windows Update restarts, or power loss).

- Metadata errors are nonfatal; ExifTool is read as UTF-8 bytes rather than
  Windows CP1252, and bad EXIF is omitted without losing the photo.
- A corrupt image is logged and skipped; the next file is processed.
- Transient Ollama responses and D1 network/rate-limit errors are retried
  with increasing delays.
- Failed items from all stages append to
  `%LOCALAPPDATA%/RicksPicksCatalog/processing-errors.jsonl`.
- Resume with the same command after any interruption. Completed catalog IDs
  and published records are skipped.
- Systemic problems (missing source directory, bad credentials, disk full,
  machine shutdown) can still stop the run; review the log afterwards.

## Requirements

- Python 3 with `pip install -r tools/requirements.txt`.
- Ollama running at `http://127.0.0.1:11434` with `qwen3-vl:8b-instruct`.
- ExifTool on PATH to preserve rich Sony/GoPro metadata (the importer continues without it).
- Cloudflare credentials supplied by environment variables or entered when prompted:
  - `CLOUDFLARE_ACCOUNT_ID`
  - `CLOUDFLARE_D1_API_TOKEN`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`

A local preview of changes without Cloudflare uploads:

```powershell
python ./tools/process_and_publish.py --ingest-limit 10 --dry-run
```

The scripts never modify original photos. Only reduced-size gallery JPEGs are uploaded.

The standalone `classify_publication.py` and `publish_catalog.py` remain usable for troubleshooting/backfills.
