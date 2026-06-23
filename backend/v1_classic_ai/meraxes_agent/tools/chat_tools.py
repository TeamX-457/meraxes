"""Tools the Meraxes chat agent can invoke (Copilot-style)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from database import create_bot, get_bot, list_bots
from dataset_loader import load_template, merge_custom_qa
from meraxes_agent.knowledge import gather_knowledge

V1_ROOT = Path(__file__).resolve().parents[2]
_SKIP_TAGS = frozenset({"greeting", "thanks", "goodbye", "name", "set_name", "status"})


def _load_intents(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("intents", [])
    except Exception:
        return []


def tool_session_snapshot(session: dict) -> dict[str, Any]:
    bot_id = session.get("bot_id")
    bot = get_bot(bot_id) if bot_id else None
    dataset = (bot or {}).get("business_id") or session.get("dataset") or "saas"
    bots = list_bots()
    return {
        "active_bot": bot,
        "dataset": dataset,
        "bot_count": len(bots),
        "bot_names": [b["name"] for b in bots[:8]],
    }


_SKIP_NAMES = frozenset({
    "a", "an", "the", "my", "me", "it", "bot", "for", "new", "then", "please", "ok", "okay",
})


def _extract_create_params(message: str, history: list[dict]) -> dict[str, str | None]:
    """Pull bot name + industry module from the message and recent chat."""
    ctx_parts = [message]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant"):
            ctx_parts.append(h.get("content", ""))
    combined = " ".join(ctx_parts)

    name: str | None = None
    for pat in (
        r"(?:name\s+it|named|call\s+it)\s+['\"]?([A-Za-z][\w-]*)['\"]?",
        r"\bcreate\s+(?:a\s+)?(?:new\s+)?bot\s+(?:for\s+me\s+)?(?:and\s+)?(?:name\s+it\s+)?['\"]?([A-Za-z][\w-]*)['\"]?",
        r"\bcreate\s+['\"]?([A-Za-z][\w-]*)['\"]?\s+then\b",
        r"\b(?:bot\s+)?named\s+['\"]?([A-Za-z][\w-]*)['\"]?",
    ):
        m = re.search(pat, combined, re.I)
        if m and m.group(1).lower() not in _SKIP_NAMES:
            name = m.group(1)
            break

    business_id = "general"
    if re.search(r"\b(e[\s-]?commerce|ecormece|online\s+store|retail|shop(?:ping)?)\b", combined, re.I):
        business_id = "ecommerce"
    elif re.search(r"\b(finance|banking)\b", combined, re.I):
        business_id = "finance"
    elif re.search(r"\bsaas\b", combined, re.I):
        business_id = "saas"
    elif re.search(r"\bhealthcare\b", combined, re.I):
        business_id = "healthcare"

    return {"name": name, "business_id": business_id}


def tool_create_bot(message: str, history: list[dict]) -> dict[str, Any]:
    """Actually create and train a new bot in the database."""
    params = _extract_create_params(message, history)
    name = params.get("name")
    if not name:
        return {"created": False, "error": "missing_name", "business_id": params.get("business_id")}

    business_id = params.get("business_id") or "general"
    try:
        template = load_template(business_id)
    except FileNotFoundError:
        business_id = "general"
        template = load_template(business_id)

    for b in list_bots():
        if b["name"].lower() == name.lower():
            return {
                "created": False,
                "error": "exists",
                "existing": {"name": b["name"], "bot_id": b["bot_id"], "business_id": b["business_id"]},
            }

    import threading

    bot = create_bot(name, business_id, "hybrid")

    def _train_in_background() -> None:
        try:
            from engine import get_engine

            b = get_bot(bot["bot_id"])
            if not b:
                return
            eng = get_engine(b)
            eng.intents = merge_custom_qa(template.get("intents", []), [])
            eng.train()
        except Exception:
            pass

    threading.Thread(
        target=_train_in_background,
        daemon=True,
        name=f"meraxes-train-{bot['bot_id']}",
    ).start()

    return {
        "created": True,
        "bot_id": bot["bot_id"],
        "name": bot["name"],
        "business_id": business_id,
        "business_name": template.get("name", business_id),
        "description": template.get("description", ""),
        "sample_questions": (template.get("suggested_customer_questions") or [])[:5],
        "intent_count": len(template.get("intents", [])),
        "training_in_background": True,
    }


def tool_list_bots() -> dict[str, Any]:
    bots = list_bots()
    return {
        "bots": [
            {
                "name": b["name"],
                "bot_id": b["bot_id"],
                "business_id": b["business_id"],
                "model_type": b["model_type"],
            }
            for b in bots
        ],
        "count": len(bots),
    }


def tool_list_intents(session: dict, limit: int = 10) -> dict[str, Any]:
    bot_id = session.get("bot_id")
    bot = get_bot(bot_id) if bot_id else None
    dataset = (bot or {}).get("business_id") or session.get("dataset") or "saas"

    template = load_template(dataset)
    template_tags = {i["tag"] for i in template.get("intents", [])}
    meraxes = _load_intents(V1_ROOT / "models" / "meraxes" / dataset / "intents.json")
    bot_file = _load_intents(V1_ROOT / "bots" / bot_id / "intents.json") if bot_id else []

    by_tag: dict[str, dict] = {}
    agent_tags: set[str] = set()

    for intent in template.get("intents", []):
        by_tag[intent["tag"]] = intent

    meraxes_tags = {i["tag"] for i in meraxes}
    for intent in meraxes:
        tag = intent["tag"]
        by_tag[tag] = intent
        if tag not in template_tags or tag.startswith("user_"):
            agent_tags.add(tag)
    for tag in meraxes_tags - template_tags:
        agent_tags.add(tag)
    for intent in bot_file:
        by_tag[intent["tag"]] = intent

    def _pack(intent: dict) -> dict:
        patterns = intent.get("patterns") or []
        sample = next((str(p) for p in patterns if p and len(str(p)) < 80), intent.get("tag", ""))
        return {
            "tag": intent["tag"],
            "sample_phrase": sample,
            "response_preview": (intent.get("responses") or [""])[0][:120],
        }

    agent_added = [_pack(by_tag[t]) for t in agent_tags if t in by_tag]
    built_in = [
        _pack(i) for i in by_tag.values()
        if i["tag"] not in agent_tags and i["tag"] not in _SKIP_TAGS
    ][: max(limit, 5)]

    return {
        "bot_name": bot["name"] if bot else None,
        "dataset": dataset,
        "total": len(by_tag),
        "agent_added": agent_added[:limit],
        "built_in_sample": built_in[:limit],
    }


def tool_bot_overview(session: dict, target_name: str | None = None) -> dict[str, Any]:
    """Factual snapshot of a specific bot: what it's built on, what it can answer.

    Reads the real config (business template, intents, custom Q&A) so the agent
    answers 'what is my bot about' from data, not by guessing from the name.
    """
    bots = list_bots()
    bot = None
    if target_name:
        tl = target_name.lower()
        bot = next((b for b in bots if tl in b["name"].lower()), None)
    if not bot and session.get("bot_id"):
        bot = get_bot(session["bot_id"])
    if not bot and bots:
        bot = bots[0]
    if not bot:
        return {"found": False, "bot_names": [b["name"] for b in bots]}

    bot_id = bot["bot_id"]
    dataset = bot.get("business_id") or "saas"
    try:
        template = load_template(dataset)
        biz_name = template.get("name", dataset)
        biz_desc = template.get("description", "")
        sample_qs = (template.get("suggested_customer_questions") or [])[:6]
        template_intents = template.get("intents", [])
    except Exception:
        biz_name, biz_desc, sample_qs, template_intents = dataset, "", [], []

    meraxes = _load_intents(V1_ROOT / "models" / "meraxes" / dataset / "intents.json")
    bot_file = _load_intents(V1_ROOT / "bots" / bot_id / "intents.json")

    by_tag: dict[str, dict] = {}
    for intent in template_intents:
        by_tag[intent["tag"]] = intent
    for intent in meraxes:
        by_tag[intent["tag"]] = intent
    for intent in bot_file:
        by_tag[intent["tag"]] = intent

    topic_tags = [t for t in by_tag if t not in _SKIP_TAGS]
    readable_topics = [t.replace("_", " ") for t in topic_tags[:12]]
    custom_qa = bot.get("custom_qa") or []

    return {
        "found": True,
        "bot_name": bot["name"],
        "business_template": biz_name,
        "business_id": dataset,
        "business_description": biz_desc,
        "model_type": bot.get("model_type"),
        "total_intents": len(by_tag),
        "topic_count": len(topic_tags),
        "top_topics": readable_topics,
        "custom_qa_count": len(custom_qa),
        "custom_qa_sample": [q.get("question", "") for q in custom_qa[:4]],
        "sample_questions": sample_qs,
    }


def tool_research(message: str, dataset: str, *, fast: bool = True) -> dict[str, Any]:
    k = gather_knowledge(message, dataset=dataset, enable_research=True, fast=fast)
    return {
        "brief": k.get("brief", "")[:2000],
        "sources": k.get("source_names", []),
        "answer_draft": k.get("synthesized_answer", ""),
    }


def tool_website_context(session: dict) -> dict[str, Any]:
    snap = tool_session_snapshot(session)
    dataset = snap["dataset"]
    try:
        t = load_template(dataset)
        ctx = {
            "business_name": t.get("name", dataset),
            "description": t.get("description", ""),
            "sample_questions": (t.get("suggested_customer_questions") or [])[:6],
        }
    except Exception:
        ctx = {"business_name": dataset, "description": "", "sample_questions": []}

    bot = snap.get("active_bot")
    if bot:
        ctx["bot_name"] = bot["name"]
        ctx["custom_qa"] = bot.get("custom_qa") or []
    return ctx
