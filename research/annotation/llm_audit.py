"""AI-assisted label audit (NOT a human second annotator).

Gives the blind sheet to a model that was not used in any experiment, with the
same instructions a human annotator gets (annotation/README.md), and writes its
answers to out/llm_sheet.csv in the sheet's format. Score it with

    python research\\annotation\\score.py --sheet research\\annotation\\out\\llm_sheet.csv --out llm_agreement.json

then review every disagreement by hand: each is either a model error or a label
error. Resumable: rows already answered are kept.

    python research\\annotation\\llm_audit.py --model gemini-3.5-flash
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import BACKEND_DIR  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"

SYSTEM = """You are annotating a benchmark of Data Processing Agreements (DPAs) under India's DPDP Act and the GDPR.
For ONE contract and ONE requirement, answer with exactly one label:

NONE      Nothing is wrong: some clause satisfies the requirement, or the requirement does not apply to
          this contract (e.g. children's-data rules for a contract whose processing involves no children's data).
VIOLATES  A clause goes against the requirement (e.g. allows 7 days to report a breach when 72 hours is required).
GAP       The requirement is mandatory AND nothing in the contract deals with it.

Rules:
- Judge the WHOLE contract. A clause about something else is not a violation.
- A later clause that says "notwithstanding..." or "amends clause N" replaces what it amends; judge the contract as amended.
- If the requirement is not mandatory, silence is NONE, never GAP.
- A requirement may describe duties of the Company (Data Fiduciary); the contract does not have to restate them."""


SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": ["NONE", "VIOLATES", "GAP"]}, "reason": {"type": "string"}},
    "required": ["label", "reason"],
}
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def gemini_key() -> str:
    # Direct REST call: the app's client stalled in a rate-limit cooldown with a single account.
    for line in (BACKEND_DIR / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEYS="):
            return line.split("=", 1)[1].strip().strip('"').split(",")[0].strip()
    sys.exit("GEMINI_API_KEYS not set in backend/.env")


async def ask(client: httpx.AsyncClient, model: str, key: str, prompt: str) -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": SCHEMA},
    }
    r = await client.post(URL.format(model), json=body, headers={"x-goog-api-key": key}, timeout=90)
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return json.loads("".join(p.get("text", "") for p in parts))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.5-flash")
    ap.add_argument("--out", default="llm_sheet.csv", help="file name under annotation/out/")
    args = ap.parse_args()

    out_path = OUT / args.out
    rows = list(csv.DictReader(open(OUT / "sheet.csv", encoding="utf-8-sig")))
    done = {}
    if out_path.exists():
        done = {r["item"]: r for r in csv.DictReader(open(out_path, encoding="utf-8-sig")) if r["your_label"]}

    key = gemini_key()
    client = httpx.AsyncClient()

    for i, r in enumerate(rows, 1):
        if r["item"] in done:
            r.update(done[r["item"]])
            continue
        contract = (OUT / r["contract"]).read_text(encoding="utf-8")
        prompt = (
            f"CONTRACT:\n{contract}\n\nREQUIREMENT:\n{r['requirement']}\n\n"
            f"Mandatory: {r['mandatory']}\n\nAnswer with the label and a one-sentence reason."
        )
        for attempt in range(3):
            try:
                a = await ask(client, args.model, key, prompt)
                r["your_label"], r["notes"] = a["label"], a["reason"]
                break
            except Exception as e:  # quota or transient error: wait and retry, else leave blank
                print(f"{r['item']}: {type(e).__name__}: {str(e)[:120]}", flush=True)
                await asyncio.sleep(20 * (attempt + 1))
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows[:i] + [x for x in rows[i:] if x["item"] in done])
        print(f"{i}/{len(rows)} {r['item']} {r['your_label']}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
