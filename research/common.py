"""Shared helpers for the "Silence Is Not Violation" research harness.

The harness lives outside the PactScan app (``research/``) and imports the
app's own code from ``backend/`` — so the deployed Detect / Horizon-Scanning
functions are what get measured, not re-implementations of them. Nothing
here changes the app.

Run every script with the backend's virtualenv, from the repo root:

    backend\\venv\\Scripts\\python.exe research\\<script>.py ...

The backend's ``.env`` is read from ``backend\\`` (pydantic-settings resolves
``env_file=".env"`` against the working directory), so ``use_backend_env()``
switches into that folder before ``app.config`` is first imported.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

RESEARCH_DIR = Path(__file__).resolve().parent
REPO_DIR = RESEARCH_DIR.parent
BACKEND_DIR = REPO_DIR / "backend"
BENCHMARK_DIR = RESEARCH_DIR / "benchmark"
BENCHMARK_FILE = BENCHMARK_DIR / "out" / "benchmark.json"
RUNS_DIR = RESEARCH_DIR / "runs"
RESULTS_DIR = RESEARCH_DIR / "results"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(RESEARCH_DIR) not in sys.path:
    sys.path.insert(0, str(RESEARCH_DIR))


def use_backend_env() -> None:
    """Make ``backend\\.env`` the settings source (must run before app.config loads)."""
    os.chdir(BACKEND_DIR)


# --------------------------------------------------------------------------- #
# JSON / JSONL
# --------------------------------------------------------------------------- #
def load_benchmark(path: Path = BENCHMARK_FILE) -> dict:
    if not path.exists():
        raise SystemExit(f"{path} not found — run research\\build_benchmark.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# Model pinning (Known Issues §3, §10.10–10.14)
# --------------------------------------------------------------------------- #
def pin_model(provider: str, model: str, cache_dir: Path) -> None:
    """Restrict the LLM client to exactly ONE model, with a cache private to this run.

    The app normally falls back across providers / accounts / model tiers when a
    free quota runs out (Known Issues §10.10–10.11), which would silently mix
    models inside one experiment. Here the attempt plan holds a single model (it
    may still rotate API keys of the same account list — same model). The cache
    directory is per run, so repeat runs never reuse each other's answers
    (Known Issues §3) while calls repeated *within* a run are free.
    """
    from app.config import settings

    if provider == "groq":
        settings.llm_provider_order = "groq"
        settings.groq_model_tiers_raw = model
    elif provider == "gemini":
        settings.llm_provider_order = "gemini"
        for i in range(1, 8):
            setattr(settings, f"gemini_model_tier_{i}", model)
    else:
        raise SystemExit(f"Unknown provider {provider!r} (use groq or gemini).")
    settings.llm_cache_enabled = True
    settings.llm_cache_dir = str(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Offline fake model (dry runs only — never used for reported numbers)
# --------------------------------------------------------------------------- #
_NEGATIVE_MARKERS = (
    "without", "discretion", "indefinitely", "no obligation", "not be subject",
    "any country", "any purpose", "fifty thousand", "within thirty (30) days after",
    "fifteen (15)", "ten (10) business days", "twelve (12) months after",
    "one hundred and eighty", "sole discretion", "conclusive", "for its own purposes",
)


def install_fake_llm() -> None:
    """Replace the LLM + embedding calls with a deterministic keyword heuristic so
    every script can be exercised end to end with zero API calls. Its answers
    are meaningless as research results — it exists to test the plumbing."""
    import re

    from app.llm import client as llm
    from app.models.clause import BatchNLIItem, BatchNLIResult, NLIResult

    def _label(clause: str, requirement: str) -> tuple[str, str]:
        c, r = clause.lower(), requirement.lower()
        req_words = {w for w in re.findall(r"[a-z]{6,}", r)}
        overlap = sum(1 for w in req_words if w in c)
        if overlap < 2:
            return "NEUTRAL", "high"
        if any(m in c for m in _NEGATIVE_MARKERS):
            return "CONTRADICTS", "high"
        return "ENTAILS", "high"

    async def fake_structured(prompt, schema, system_prompt=None):
        if schema is BatchNLIResult:
            clause = prompt.split("REQUIREMENTS:")[0]
            items = []
            for req_id, text in re.findall(r"- requirement_id='([^']+)': (.*)", prompt):
                label, conf = _label(clause, text)
                items.append(BatchNLIItem(requirement_id=req_id, label=label, explanation="fake", confidence=conf))
            return BatchNLIResult(results=items)
        if schema is NLIResult:
            clause = prompt.split("NEW/AMENDED REGULATION REQUIREMENT:")[0]
            req = prompt.split("NEW/AMENDED REGULATION REQUIREMENT:")[-1]
            label, conf = _label(clause, req)
            return NLIResult(label=label, explanation="fake", confidence=conf)
        raise NotImplementedError(f"fake LLM has no answer for schema {schema.__name__}")

    async def fake_embedding(text: str) -> list[float]:
        words = re.findall(r"[a-z]{4,}", text.lower())
        vec = [0.0] * 64
        for w in words:
            vec[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1.0
        return vec

    llm.generate_structured = fake_structured
    llm.generate_embedding = fake_embedding
