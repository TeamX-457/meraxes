"""
Apply V2 chat queue to V1 bot custom_qa and retrain intent model.

Run manually or invoked silently from V2 after external API chats:
  cd AImodel
  ml-env\\Scripts\\python.exe v1_classic_ai\\train_from_v2_queue.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

V1_DIR = Path(__file__).resolve().parent
AIMODEL = V1_DIR.parent
QUEUE = AIMODEL / "v2_llm_agent" / "data" / "v1_train_queue.jsonl"
PROCESSED = AIMODEL / "v2_llm_agent" / "data" / "v1_train_processed.jsonl"

sys.path.insert(0, str(V1_DIR))

from database import create_bot, get_bot, init_db, list_bots, update_bot  # noqa: E402
from dataset_loader import load_template, merge_custom_qa  # noqa: E402
from engine import get_engine, invalidate_engine  # noqa: E402


def _resolve_bot_id() -> str:
    bid = os.getenv("V1_TRAIN_BOT_ID", "").strip()
    if bid:
        bot = get_bot(bid)
        if bot:
            return bid
    bots = list_bots()
    if bots:
        return bots[0]["bot_id"]
    bot = create_bot("Nova Learned (V2)", "general", "hybrid")
    get_engine(bot).train()
    return bot["bot_id"]


def _norm(q: str) -> str:
    return " ".join(q.lower().strip().split())


def main() -> None:
    init_db()
    if not QUEUE.exists():
        print("No queue file — nothing to train.")
        return

    lines = QUEUE.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return

    pairs: list[dict] = []
    for line in lines:
        try:
            pairs.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    bot_id = _resolve_bot_id()
    bot = get_bot(bot_id)
    if not bot:
        print(f"Bot {bot_id} not found")
        sys.exit(1)

    existing = bot.get("custom_qa", [])
    seen = {_norm(x.get("question", "")) for x in existing}

    added = 0
    for p in pairs:
        q = p.get("question", "").strip()
        a = p.get("answer", "").strip()
        if not q or not a:
            continue
        nq = _norm(q)
        if nq in seen:
            continue
        seen.add(nq)
        existing.append({"question": q, "answer": a})
        added += 1

    if added == 0:
        QUEUE.unlink(missing_ok=True)
        print("No new pairs — queue cleared.")
        return

    bot = update_bot(bot_id, custom_qa=existing)
    invalidate_engine(bot_id)
    engine = get_engine(bot)
    engine.intents = merge_custom_qa(
        load_template(bot["business_id"])["intents"],
        bot.get("custom_qa", []),
    )
    stats = engine.train()

    with open(PROCESSED, "a", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    QUEUE.unlink(missing_ok=True)

    print(json.dumps({"bot_id": bot_id, "added": added, "train": stats}))


if __name__ == "__main__":
    main()
