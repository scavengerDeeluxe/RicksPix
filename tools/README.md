# One-command processing

From the repository root, after `pip install -r tools/requirements.txt`:

```powershell
python tools/process_and_publish.py
```

The command prompts for missing Cloudflare credentials, runs local Ollama classification on all remaining records, and publishes only eligible public/documentary photographs. It resumes both stages safely on subsequent runs. It does **not** create the original descriptive catalog; it consumes the existing `catalog.jsonl` and previews.

To test without publishing:

```powershell
python tools/process_and_publish.py --classify-limit 25 --dry-run
```

Note: You must still run the original photo cataloger on newly recovered directories before they can enter this pipeline.

---

# Privacy gate before bulk publication

Run this second-pass local classifier after the AI catalog exists:

```powershell
py tools/classify_publication.py --limit 100
```

It writes `%LOCALAPPDATA%\RicksPicksCatalog\publication-decisions.jsonl` without changing the originals or `catalog.jsonl`. Repeat with `--limit 0` after reviewing the pilot.

The publisher now **holds all unclassified photos**. It only publishes AI classifications `public` or `documentary` when confidence is at least 0.85 and there is no detected private context. Family gatherings, children, private settings, and ambiguous portraits are held.

Rick is an intentional exception, **but identity requires human confirmation**. To approve a known photograph of Rick, add a JSONL record to `publication-overrides.jsonl` next to the catalog, using the actual catalog ID:

```json
{"id":"REAL_PHOTO_ID","decision":"rick_approved","source":"human","reason":"Confirmed by family"}
```

Never treat a model's guess that someone is Rick as sufficient. Overrides must be made after visually checking the image. These records are not uploaded publicly; only approved images and metadata are.

Previously published photos are not unpublished by this local change. Review the existing five separately if needed.

---

# Publish the local AI catalog

Read-only dry run by default. The importer uses the existing JSONL and preview
JPEGs under `%LOCALAPPDATA%\RicksPicksCatalog`. It never opens or changes original images.

Install dependencies:

```powershell
py -m pip install -r tools/requirements.txt
py tools/publish_catalog.py --limit 5
```

For actual publishing, set these environment variables in your local session:
- `CLOUDFLARE_ACCOUNT_ID` — 32-character Cloudflare account ID
- `CLOUDFLARE_D1_API_TOKEN` — Cloudflare API token with D1 Write for this account
- `R2_ACCESS_KEY_ID` — R2 S3 access key for bucket `rickspix`
- `R2_SECRET_ACCESS_KEY` — matching R2 secret

Then begin with five images:

```powershell
py tools/publish_catalog.py --limit 5 --publish
```

After checking the published gallery, run without `--limit`.
State is tracked in `publish-state.sqlite3` next to the JSONL file.
Successfully published IDs are not repeated. Failed lines are retried on the next run.
The D1 operation uses an idempotent upsert.

The public gallery previews are **not full-resolution originals**.
The generated 1280-pixel analysis JPEG doubles as the viewing image,
with a smaller 460-pixel thumbnail. Publish only images you want public.

Cloudflare API documentation:
https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/
https://developers.cloudflare.com/r2/examples/aws/boto3/
