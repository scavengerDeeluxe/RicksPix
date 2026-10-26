#!/usr/bin/env python3
"""Second-pass local privacy/publication classification for Rick's Pix.

Reads catalog.jsonl and its 1280px previews. Writes a separate resumable
publication-decisions.jsonl; never alters photographs or the original catalog.
Requires a local Ollama model (qwen3-vl:8b-instruct by default).
"""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import requests

PROMPT = """You are reviewing one photograph for a PUBLIC historical photography archive.
The collection contains landscapes, wildlife, documentary scenes, and private family life.

Classify PUBLIC SUITABILITY independently of artistic or technical quality.

Return ONLY valid JSON:
{
  "decision": "public | documentary | family | review",
  "confidence": 0.0,
  "contains_people": false,
  "private_context": false,
  "reason": "One short factual explanation",
  "possible_rick_portrait": false
}

Decision rules:
- public: nature, architecture, wildlife, ordinary objects, public places, no private personal context.
- documentary: public-facing work, maintenance workers, street scenes, public events, people in a clearly documentary setting, without apparent intimate/private context.
- family: birthdays, Christmas gift opening, family gatherings, domestic celebrations, posed family portraits, and other private personal memories.
- review: ambiguous situations, children, intimate moments, medical content, private homes, uncertain people-centered photos, or any image you cannot classify confidently.
- If uncertain between public/documentary and family, choose review.
- Never infer a specific person's identity from appearance. You do NOT know what Rick looks like.
- If a photo could be of Rick, choose review. possible_rick_portrait only means a possible photographer portrait that needs HUMAN verification.
- A maintenance worker on a snowy tower is documentary, not automatically family.
- No personal names, identities, or guesses about relationships.
- Do not treat a high quality score as justification for publication.
- confidence between 0 and 1; use less than 0.85 if uncertain.
"""

VALID = {"public", "documentary", "family", "review"}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    base = Path(os.environ.get("LOCALAPPDATA", ".")) / "RicksPicksCatalog"
    ap.add_argument("--catalog", default=str(base / "catalog.jsonl"))
    ap.add_argument("--output", default=str(base / "publication-decisions.jsonl"))
    ap.add_argument("--limit", type=int, default=100, help="New photographs to classify (0=all)")
    ap.add_argument("--model", default="qwen3-vl:8b-instruct")
    args = ap.parse_args()
    catalog, output = Path(args.catalog), Path(args.output)
    if not catalog.is_file():
        ap.error(f"Catalog not found: {catalog}")
    existing = set()
    if output.is_file():
        for line in output.read_text(encoding="utf-8-sig").splitlines():
            try:
                d = json.loads(line)
                if d.get("id"):
                    existing.add(str(d["id"]))
            except ValueError:
                pass
    processed = held = failures = 0
    with catalog.open(encoding="utf-8-sig") as source, output.open("a", encoding="utf-8") as dest:
        for n, line in enumerate(source, 1):
            try:
                item = json.loads(line)
                pid = str(item["id"])
                if pid in existing:
                    continue
                preview = Path(item["preview"])
                if not preview.is_file():
                    raise FileNotFoundError(preview)
                image = base64.b64encode(preview.read_bytes()).decode("ascii")
                payload = {
                    "model": args.model, "stream": False, "format": "json",
                    "options": {"temperature": 0.0, "num_ctx": 8192},
                    "messages": [{"role": "user", "content": PROMPT, "images": [image]}]
                }
                resp = requests.post("http://127.0.0.1:11434/api/chat", json=payload, timeout=300)
                resp.raise_for_status()
                answer = json.loads(resp.json()["message"]["content"])
                decision = str(answer.get("decision", "review")).lower().strip()
                if decision not in VALID:
                    decision = "review"
                try:
                    confidence = max(0.0, min(1.0, float(answer.get("confidence", 0))))
                except (TypeError, ValueError):
                    confidence = 0.0
                private = answer.get("private_context") is not False
                people = answer.get("contains_people") is not False
                # Conservative gate: no low-confidence or private-context auto-public decisions.
                if private or confidence < 0.85 or (people and decision == "public"):
                    decision = "review"
                result = {
                    "id": pid, "decision": decision, "confidence": confidence,
                    "contains_people": people, "private_context": private,
                    "possible_rick_portrait": bool(answer.get("possible_rick_portrait", False)),
                    "reason": str(answer.get("reason", ""))[:500],
                    "source": "local_ai", "model": args.model
                }
                dest.write(json.dumps(result, ensure_ascii=False) + "\n")
                dest.flush()
                existing.add(pid)
                processed += 1
                if decision not in {"public", "documentary"}:
                    held += 1
                print(f"[{processed}] {decision.upper():12} {item.get('relative_path',pid)} — {result['reason']}")
                if args.limit and processed >= args.limit:
                    break
            except Exception as exc:
                failures += 1
                print(f"FAILED line {n}: {exc}", file=sys.stderr)
                if failures >= 10:
                    break
    print(f"Classified: {processed}, held for privacy/review: {held}, failures: {failures}")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
