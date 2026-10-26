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
