"""
Silent training pipeline: V2 external API chats → V1 intent/custom_qa + local export.

After each successful V2 reply from a cloud provider:
  1. Queue Q&A for V1 intent retrain (background subprocess)
  2. Append to Ollama fine-tune JSONL (for future local training)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from v2_llm_agent.config import (
    EXPORT_LOCAL_FINETUNE,
    OLLAMA_REBUILD_EVERY_N,
    SILENT_V1_TRAINING,
    V1_TRAIN_BOT_ID,
    V1_TRAIN_EVERY_N,
    V1_TRAIN_MIN_ANSWER_LEN,
    V1_TRAIN_MIN_QUESTION_LEN,
)

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent / "data"
_DATA.mkdir(parents=True, exist_ok=True)
QUEUE_PATH = _DATA / "v1_train_queue.jsonl"
FINETUNE_PATH = _DATA / "ollama_finetune.jsonl"
STATS_PATH = _DATA / "training_stats.json"

_AIMODEL = Path(__file__).resolve().parent.parent
_V1_TRAIN_SCRIPT = _AIMODEL / "v1_classic_ai" / "train_from_v2_queue.py"

_lock = threading.Lock()
_queued_since_train = 0
_train_timer: threading.Timer | None = None
_stats = {"queued": 0, "applied": 0, "last_train": None, "last_error": None, "last_ollama_build": None}
_finetune_since_build = 0
_ollama_timer: threading.Timer | None = None


def _load_stats() -> None:
    global _stats
    if STATS_PATH.exists():
        try:
            _stats.update(json.loads(STATS_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass


def _save_stats() -> None:
    STATS_PATH.write_text(json.dumps(_stats, indent=2), encoding="utf-8")


def _normalize(q: str) -> str:
    return " ".join(q.lower().strip().split())


def _should_learn(question: str, answer: str, provider: str) -> bool:
    if not SILENT_V1_TRAINING:
        return False
    if provider in ("cache", "none", "", "sd-webui"):
        return False
    q, a = question.strip(), answer.strip()
    if len(q) < V1_TRAIN_MIN_QUESTION_LEN or len(a) < V1_TRAIN_MIN_ANSWER_LEN:
        return False
    if a.lower().startswith("request failed") or "cannot reach server" in a.lower():
        return False
    # Skip text-LLM refusals for image tasks (wrong training signal)
    if "don't have the capability to directly create images" in a.lower():
        return False
    if "create images" in q.lower() or "draw " in q.lower() or "picture of" in q.lower():
        return False
    return True


def _append_jsonl(path: Path, record: dict) -> None:
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _schedule_v1_train(delay_sec: float = 45.0) -> None:
    global _train_timer

    def _run():
        _trigger_v1_train()

    with _lock:
        if _train_timer:
            _train_timer.cancel()
        _train_timer = threading.Timer(delay_sec, _run)
        _train_timer.daemon = True
        _train_timer.start()


def _trigger_v1_train() -> None:
    if not _V1_TRAIN_SCRIPT.exists():
        _stats["last_error"] = "train script missing"
        _save_stats()
        return
    python = sys.executable
    env = {**os.environ, "V1_TRAIN_BOT_ID": V1_TRAIN_BOT_ID or ""}
    try:
        proc = subprocess.run(
            [python, str(_V1_TRAIN_SCRIPT)],
            cwd=str(_AIMODEL),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode == 0:
            _stats["last_train"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _stats["last_error"] = None
            try:
                out = json.loads((proc.stdout or "").strip().splitlines()[-1])
                _stats["applied"] = _stats.get("applied", 0) + int(out.get("added", 0))
                _stats["v1_bot_id"] = out.get("bot_id")
            except Exception:
                pass
            logger.info("Silent V1 train OK: %s", (proc.stdout or "")[-200:])
        else:
            _stats["last_error"] = (proc.stderr or proc.stdout or "train failed")[-500:]
            logger.warning("Silent V1 train failed: %s", _stats["last_error"])
    except Exception as e:
        _stats["last_error"] = str(e)
        logger.exception("Silent V1 train subprocess error")
    _save_stats()


def _schedule_ollama_build(delay_sec: float = 60.0) -> None:
    global _ollama_timer

    def _run():
        _trigger_ollama_build()

    with _lock:
        if _ollama_timer:
            _ollama_timer.cancel()
        _ollama_timer = threading.Timer(delay_sec, _run)
        _ollama_timer.daemon = True
        _ollama_timer.start()


def _trigger_ollama_build() -> None:
    try:
        from v2_llm_agent.ollama_export import run_ollama_create, write_modelfile

        from v2_llm_agent.config import AUTO_BUILD_OLLAMA

        if AUTO_BUILD_OLLAMA:
            result = run_ollama_create()
        else:
            write_modelfile()
            result = {"ok": True, "message": "Modelfile updated"}
        if result.get("ok"):
            _stats["last_ollama_build"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            _stats["last_ollama_error"] = None
        else:
            _stats["last_ollama_error"] = result.get("error")
    except Exception as e:
        _stats["last_ollama_error"] = str(e)
        logger.exception("Ollama export failed")
    _save_stats()


def record_chat_for_training(
    question: str,
    answer: str,
    provider: str,
    model: str,
) -> None:
    """Call after every successful V2 /chat — non-blocking."""
    if not _should_learn(question, answer, provider):
        return

    record = {
        "question": question.strip(),
        "answer": answer.strip(),
        "provider": provider,
        "model": model,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    _append_jsonl(QUEUE_PATH, record)
    _stats["queued"] = _stats.get("queued", 0) + 1
    _save_stats()

    if EXPORT_LOCAL_FINETUNE:
        _append_jsonl(
            FINETUNE_PATH,
            {
                "messages": [
                    {"role": "user", "content": question.strip()},
                    {"role": "assistant", "content": answer.strip()},
                ],
                "provider": provider,
            },
        )
        global _finetune_since_build
        with _lock:
            _finetune_since_build += 1
            fn = _finetune_since_build
        if fn >= OLLAMA_REBUILD_EVERY_N:
            with _lock:
                _finetune_since_build = 0
            threading.Thread(target=_trigger_ollama_build, name="ollama-export", daemon=True).start()
        else:
            _schedule_ollama_build()

    global _queued_since_train
    with _lock:
        _queued_since_train += 1
        n = _queued_since_train

    if n >= V1_TRAIN_EVERY_N:
        with _lock:
            _queued_since_train = 0
        threading.Thread(target=_trigger_v1_train, name="v1-silent-train", daemon=True).start()
    else:
        _schedule_v1_train()


def run_v1_train_now() -> None:
    """Public entry for manual /api/training/run-v1."""
    _trigger_v1_train()


def run_ollama_build_now(force_create: bool = False) -> dict:
    """Public entry for manual Ollama Modelfile / model build."""
    from v2_llm_agent.ollama_export import export_status, run_ollama_create, write_modelfile

    if force_create:
        result = run_ollama_create()
    else:
        path = write_modelfile()
        result = {"ok": True, "modelfile": str(path), "message": "Modelfile written"}
    if result.get("ok"):
        _stats["last_ollama_build"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _stats["last_ollama_error"] = None
    else:
        _stats["last_ollama_error"] = result.get("error")
    _save_stats()
    return {**result, **export_status()}


def get_training_status() -> dict:
    _load_stats()
    pending = 0
    if QUEUE_PATH.exists():
        with open(QUEUE_PATH, encoding="utf-8") as f:
            pending = sum(1 for line in f if line.strip())
    finetune_count = 0
    if FINETUNE_PATH.exists():
        with open(FINETUNE_PATH, encoding="utf-8") as f:
            finetune_count = sum(1 for line in f if line.strip())
    ollama = {}
    try:
        from v2_llm_agent.ollama_export import export_status
        ollama = export_status()
    except Exception:
        pass
    return {
        "silent_v1_enabled": SILENT_V1_TRAINING,
        "export_finetune": EXPORT_LOCAL_FINETUNE,
        "v1_bot_id": V1_TRAIN_BOT_ID or _stats.get("v1_bot_id") or "auto-first-bot",
        "train_every_n": V1_TRAIN_EVERY_N,
        "ollama_rebuild_every_n": OLLAMA_REBUILD_EVERY_N,
        "queue_pending": pending,
        "finetune_examples": finetune_count,
        "ollama": ollama,
        **_stats,
    }


_load_stats()
