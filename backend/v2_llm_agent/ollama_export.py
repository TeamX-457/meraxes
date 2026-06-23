"""
Build Ollama Modelfile from V2 cloud chat export (ollama_finetune.jsonl).

Creates a custom local model with system prompt + few-shot examples learned
from external API chats. Run `ollama create` when AUTO_BUILD_OLLAMA=true.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from v2_llm_agent.config import (
    AUTO_BUILD_OLLAMA,
    OLLAMA_BASE_MODEL,
    OLLAMA_CUSTOM_MODEL,
)

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent / "data"
FINETUNE_PATH = _DATA / "ollama_finetune.jsonl"
MODELFILE_PATH = _DATA / "Modelfile.nova"
MAX_EXAMPLES = 30
MAX_MSG_CHARS = 1200


def _escape_modelfile(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _trim(text: str, limit: int = MAX_MSG_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def load_examples(limit: int = MAX_EXAMPLES) -> list[dict]:
    if not FINETUNE_PATH.exists():
        return []
    rows: list[dict] = []
    for line in FINETUNE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def build_modelfile(examples: list[dict] | None = None) -> str:
    examples = examples if examples is not None else load_examples()
    n = len(examples)
    lines = [
        f"FROM {OLLAMA_BASE_MODEL}",
        "",
        "# Nova AI — learned from V2 cloud API chats",
        f"# Examples: {n}",
        'SYSTEM """You are Nova AI, a helpful assistant trained on real conversations.',
        "Answer clearly and match the tone of the examples below when relevant.",
        'Stay accurate; say when you are unsure."""',
        "",
    ]
    for ex in examples:
        for msg in ex.get("messages", []):
            role = msg.get("role", "")
            content = _trim(str(msg.get("content", "")))
            if not content or role not in ("user", "assistant"):
                continue
            lines.append(f'MESSAGE {role} "{_escape_modelfile(content)}"')
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_modelfile() -> Path:
    _DATA.mkdir(parents=True, exist_ok=True)
    content = build_modelfile()
    MODELFILE_PATH.write_text(content, encoding="utf-8")
    return MODELFILE_PATH


def ollama_available() -> bool:
    return shutil.which("ollama") is not None


def run_ollama_create() -> dict:
    path = write_modelfile()
    if not ollama_available():
        return {
            "ok": False,
            "error": "ollama not in PATH — install from https://ollama.com",
            "modelfile": str(path),
            "model": OLLAMA_CUSTOM_MODEL,
        }
    try:
        proc = subprocess.run(
            ["ollama", "create", OLLAMA_CUSTOM_MODEL, "-f", str(path)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode == 0:
            return {
                "ok": True,
                "model": OLLAMA_CUSTOM_MODEL,
                "modelfile": str(path),
                "message": (proc.stdout or "Model created").strip()[-300:],
            }
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "ollama create failed")[-500:],
            "modelfile": str(path),
            "model": OLLAMA_CUSTOM_MODEL,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ollama create timed out", "modelfile": str(path)}
    except Exception as e:
        return {"ok": False, "error": str(e), "modelfile": str(path)}


def maybe_auto_build() -> None:
    if not AUTO_BUILD_OLLAMA:
        return
    if not load_examples():
        return
    result = run_ollama_create()
    if result.get("ok"):
        logger.info("Ollama model built: %s", OLLAMA_CUSTOM_MODEL)
    else:
        logger.warning("Ollama auto-build skipped: %s", result.get("error"))


def export_status() -> dict:
    examples = load_examples(limit=99999)
    full_count = 0
    if FINETUNE_PATH.exists():
        full_count = sum(1 for ln in FINETUNE_PATH.read_text(encoding="utf-8").splitlines() if ln.strip())
    return {
        "finetune_examples": full_count,
        "modelfile_examples": len(examples),
        "modelfile_path": str(MODELFILE_PATH) if MODELFILE_PATH.exists() else None,
        "base_model": OLLAMA_BASE_MODEL,
        "custom_model": OLLAMA_CUSTOM_MODEL,
        "auto_build": AUTO_BUILD_OLLAMA,
        "ollama_cli": ollama_available(),
    }
