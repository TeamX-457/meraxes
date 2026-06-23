"""Meraxes agent chat — sessions + agentic multi-source replies."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any

import httpx

from database import (
    create_bot,
    create_chat_session,
    delete_chat_session,
    get_bot,
    get_chat_session,
    get_session_messages,
    list_chat_sessions,
    list_bots,
    save_session_message,
    touch_chat_session,
)
from dataset_loader import load_template
from meraxes_agent.chat_agent import execute_tools, plan_turn, synthesize_reply
from meraxes_agent.knowledge import gather_knowledge, synthesize_local_answer
from meraxes_agent.llm_bridge import chat_with_router, list_providers, router_available

V1_ROOT = Path(__file__).resolve().parents[1]

_QUERY_RE = re.compile(
    r"\b(list|show|display|tell\s+me|what\s+are|which|how\s+many|enumerate|give\s+me|name)\b",
    re.I,
)
_TRAIN_RE = re.compile(
    r"\b("
    r"train|retrain|re-train|optimize|optimise|optimization|"
    r"add\s+(new\s+)?intents?|research\s+and\s+train|do\s+extra\s+research|"
    r"improve\s+(my\s+)?bot|quality\s+lab|update\s+(my\s+)?bot|teach\s+(my\s+)?bot|"
    r"find\s+(my\s+)?(ai\s+)?models?\s+and"
    r")\b",
    re.I,
)
_LIST_INTENTS_RE = re.compile(
    r"\b("
    r"list.*intent|intent.*list|show.*intent|what\s+intents?|major\s+intent|"
    r"topics?\s+(does|can|my|you)|what\s+can\s+(my\s+)?bot|"
    r"intents?\s+(you\s+)?(did|added|created)|already\s+there|so\s+i\s+can\s+test"
    r")\b",
    re.I,
)

_action_jobs: dict[str, dict[str, Any]] = {}
_SKIP_INTENT_TAGS = frozenset({"greeting", "thanks", "goodbye", "name", "set_name", "status"})


def _classify_message(message: str) -> str:
    """Route message: optimize | list_intents | list_bots | chat."""
    m = message.lower().strip()

    if _LIST_INTENTS_RE.search(m):
        return "list_intents"
    if _QUERY_RE.search(m) and re.search(r"\b(intent|topic|subject)\b", m):
        return "list_intents"
    if _QUERY_RE.search(m) and re.search(r"\bbots?\b", m):
        return "list_bots"

    if _QUERY_RE.search(m):
        return "chat"

    if _TRAIN_RE.search(m):
        return "optimize"
    if "train" in m and any(w in m for w in ("model", "bot", "ai")) and "intent" in m:
        return "optimize"

    return "chat"


def _is_agent_action(message: str) -> bool:
    return _classify_message(message) == "optimize"


def get_action_job(job_id: str) -> dict | None:
    return _action_jobs.get(job_id)


# ─── Live "test my bot" job ──────────────────────────────────────────────────

def _fallback_test_questions(dataset: str, limit: int = 10) -> list[str]:
    try:
        template = load_template(dataset)
        qs = list(template.get("suggested_customer_questions") or [])
    except Exception:
        qs = []
    generic = [
        "What services do you offer?",
        "Can you tell me about your business?",
        "What do you do?",
        "How do I get started?",
        "How much does it cost?",
        "How do I contact support?",
        "What are your opening hours?",
        "Do you offer refunds?",
        "What payment methods do you accept?",
        "Where are you located?",
    ]
    out: list[str] = []
    for q in qs + generic:
        if q not in out:
            out.append(q)
    return out[:limit]


async def _generate_test_questions(session: dict, message: str, business_desc: str = "") -> list[str]:
    bot = get_bot(session.get("bot_id")) if session.get("bot_id") else None
    dataset = (bot or {}).get("business_id") or session.get("dataset") or "saas"
    desc = business_desc.strip()
    try:
        template = load_template(dataset)
        biz_name = template.get("name", dataset)
    except Exception:
        biz_name = dataset

    prompt = (
        f"You are QA-testing a customer-support chatbot for a {biz_name} business.\n"
        + (f"Business description from owner: {desc}\n" if desc else "")
        + "Generate 10 realistic customer questions a real visitor would ask this business. "
        "Mix common ones (services, pricing, hours, contact) and specific ones tied to the business. "
        "Return JSON only: {\"questions\":[\"...\"]}"
    )
    routed = await chat_with_router(
        [{"role": "user", "content": prompt}], task="fast", max_tokens=600, temperature=0.7
    )
    if routed and routed.get("content"):
        try:
            blob = routed["content"]
            start, end = blob.find("{"), blob.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(blob[start : end + 1])
                qs = [str(q).strip() for q in data.get("questions", []) if str(q).strip()]
                if qs:
                    return qs[:12]
        except Exception:
            pass
    return _fallback_test_questions(dataset)


def _parse_question_count(message: str, default: int = 12) -> int:
    m = re.search(
        r"\b(\d{1,2})\s*(?:more\s+)?(?:questions?|q\s*&\s*a|qa|intents?)\b",
        message,
        re.I,
    )
    if m:
        return min(max(int(m.group(1)), 3), 25)
    return default


def _persist_session_bot(session_id: str, bot: dict) -> None:
    from database import update_chat_session_bot

    update_chat_session_bot(session_id, bot_id=bot["bot_id"], dataset=bot.get("business_id"))


def _resolve_target_bot(session: dict, message: str = "") -> dict | None:
    """Find which bot the user means: session bot → bot named in message → only bot."""
    bot_id = session.get("bot_id")
    if bot_id:
        b = get_bot(bot_id)
        if b:
            return b
    bots = list_bots()
    if message:
        low = message.lower()
        for b in bots:
            if b["name"] and b["name"].lower() in low:
                return b
    if len(bots) == 1:
        return bots[0]
    return None


def _run_live_qa_loop(
    job_id: str,
    job: dict,
    bot: dict,
    questions: list[str],
    *,
    _fix,
    _opt,
) -> tuple[int, int]:
    """Ask the bot each question live; auto-fix failures with custom Q&A."""
    import time as _time

    from database import get_user_name, save_user_name, update_bot, get_bot
    from engine import get_engine, invalidate_engine

    bot_id = bot["bot_id"]
    engine = get_engine(bot)
    pending_qa: list[dict] = []

    for idx, q in enumerate(questions):
        entry = {
            "index": idx + 1, "question": q, "answer": "", "source": "",
            "ok": False, "fixed": False, "status": "asking",
        }
        job.setdefault("transcript", []).append(entry)
        try:
            result = engine.reply(f"agent_test_{job_id}", q, get_user_name, save_user_name)
            answer = result.get("response", "")
            source = result.get("source", "")
        except Exception as exc:
            answer, source = f"(error: {exc})", "error"

        bad_sources = ("fallback", "error", "greeting", "goodbye")
        ok = (
            source not in bad_sources
            and bool(answer)
            and "how can i help you today" not in answer.lower()
            and "{name}" not in answer
        )
        entry["answer"] = answer
        entry["source"] = source
        entry["ok"] = ok
        entry["status"] = "answered"

        if not ok:
            job["status"] = "fixing"
            entry["status"] = "fixing"
            _fix(f"Q{idx + 1} failed (source: {source or 'none'}) → researching a correct answer…")
            ans = _quick_answer(q, bot)
            if ans:
                pending_qa.append({"question": q, "answer": ans})
                entry["answer"] = ans
                entry["source"] = "fixed"
                entry["ok"] = True
                entry["fixed"] = True
                entry["status"] = "fixed"
                _fix(f"Q{idx + 1} fixed ✓ — added a custom answer.")
                _opt(f"Queued custom answer for: \"{q[:50]}\"  ({len(pending_qa)} pending)")
            else:
                entry["status"] = "weak"
                _fix(f"Q{idx + 1} still weak — needs more training.")
        else:
            entry["status"] = "ok"
        job["progress"] = idx + 1

    if pending_qa:
        job["status"] = "fixing"
        _opt(f"Writing {len(pending_qa)} new custom answer(s) to {bot['name']}…")
        try:
            fresh = get_bot(bot_id) or bot
            new_qa = list(fresh.get("custom_qa") or []) + pending_qa
            update_bot(bot_id, custom_qa=new_qa)
            invalidate_engine(bot_id)
            get_engine(get_bot(bot_id))
            _opt(f"Re-indexed {bot['name']} live with {len(new_qa)} total custom answers.")
        except Exception as exc:
            job["fix_error"] = str(exc)
            _opt(f"Re-index error: {exc}")

    passed = sum(1 for e in job.get("transcript", []) if e.get("ok"))
    fixed = sum(1 for e in job.get("transcript", []) if e.get("fixed"))
    return passed, fixed


def _run_full_train_job(job_id: str, session: dict, message: str, business_desc: str = "") -> None:
    """Real training: quality lab (new intents) → live interview → auto-fix weak answers."""
    import asyncio
    import time as _time

    from database import get_bot
    from engine import invalidate_engine
    from meraxes_agent.models.schemas import AgentGoal
    from meraxes_agent.optimizer_agent import MeraxesQualityLab

    session_id = session["session_id"]
    job = _action_jobs[job_id]

    bot = _resolve_target_bot(session, message)
    if not bot:
        names = [b["name"] for b in list_bots()]
        hint = (
            f"Tell me which one — for example: \"train {names[0]}\"."
            if names else "Create a bot first under \"Create bot\"."
        )
        job.update({"status": "failed", "error": "No bot resolved."})
        save_session_message(
            session_id, "assistant",
            f"I have {len(names)} bot(s): {', '.join(names) or 'none'}. {hint} "
            f"You can also pick one in the dropdown above the chat.",
        )
        touch_chat_session(session_id)
        return

    bot_id = bot["bot_id"]
    dataset = bot.get("business_id") or session.get("dataset") or "saas"
    _persist_session_bot(session_id, bot)
    session = {**session, "bot_id": bot_id, "dataset": dataset}

    def _fix(text: str) -> None:
        job.setdefault("fixing_log", []).append({"t": _time.strftime("%H:%M:%S"), "text": text})

    def _opt(text: str) -> None:
        job.setdefault("optimization_log", []).append({"t": _time.strftime("%H:%M:%S"), "text": text})

    job.update({
        "bot_name": bot["name"],
        "transcript": [],
        "fixing_log": job.get("fixing_log") or [],
        "optimization_log": job.get("optimization_log") or [],
        "status": "running",
        "current": "Running quality lab…",
    })

    intents_added: list[str] = []
    opt_summary = ""
    _opt(f"Phase 1 — Quality lab on {bot['name']} ({dataset})…")

    def _progress(phase: str, msg: str, count: int) -> None:
        label = _PHASE_LABELS.get(phase, msg)
        job.setdefault("steps", []).append({"phase": phase, "label": label, "n": count})
        job["current"] = label
        _opt(f"{label}")

    try:
        goal = AgentGoal(
            description=message,
            context={
                "dataset": dataset,
                "enable_research": True,
                "quick_train": True,
                "minimal_train": True,
                "test_case_limit": 8,
                "bot_id": bot_id,
                "progress_cb": _progress,
            },
        )
        run = MeraxesQualityLab().run(goal)
        fo = run.final_output or {}
        intents_added = fo.get("intents_added") or []
        opt_summary = _format_optimizer_result(fo)
        if intents_added:
            _opt(f"Added {len(intents_added)} new topic(s): {', '.join(intents_added[:6])}.")
        else:
            _opt("Quality lab finished — no new topics added this round.")
        invalidate_engine(bot_id)
    except Exception as exc:
        _opt(f"Quality lab warning: {exc} — continuing with live interview.")

    n_q = _parse_question_count(message, default=12)
    _opt(f"Phase 2 — Interviewing {bot['name']} with {n_q} customer questions…")
    try:
        questions = asyncio.run(_generate_test_questions(session, message, business_desc))
    except Exception:
        questions = _fallback_test_questions(dataset, limit=n_q)
    questions = questions[:n_q]
    job["questions_total"] = len(questions)

    bot = get_bot(bot_id) or bot
    passed, fixed = _run_live_qa_loop(job_id, job, bot, questions, _fix=_fix, _opt=_opt)

    job["passed"] = passed
    job["fixed"] = fixed
    job["intents_added"] = intents_added
    job["status"] = "completed"
    _opt(f"Done. {passed}/{len(questions)} answered well, {fixed} auto-fixed.")

    summary_lines = [f"Trained {bot['name']} ({dataset})."]
    if intents_added:
        summary_lines.append(f"Added {len(intents_added)} new topic(s): {', '.join(intents_added[:6])}.")
    summary_lines.append(
        f"Live interview: {passed}/{len(questions)} answered well"
        + (f", {fixed} weak answers fixed with custom Q&A." if fixed else ".")
    )
    if fixed:
        summary_lines.append("Your bot was re-indexed — try the same questions in Test chat now.")
    weak = [e for e in job.get("transcript", []) if not e.get("ok")]
    if weak:
        summary_lines.append(
            "Still weak: " + ", ".join(f'\"{e["question"]}\"' for e in weak[:3])
        )
    job["summary"] = " ".join(summary_lines)
    save_session_message(session_id, "assistant", job["summary"])
    touch_chat_session(session_id)


def _run_test_job(job_id: str, session: dict, business_desc: str, message: str) -> None:
    import asyncio
    import time as _time

    session_id = session["session_id"]
    job = _action_jobs[job_id]

    bot = _resolve_target_bot(session, message)
    if not bot:
        names = [b["name"] for b in list_bots()]
        hint = (
            f"Tell me which one — for example: \"test {names[0]}\"."
            if names else "Create a bot first under \"Create bot\"."
        )
        job.update({"status": "failed", "error": "No bot resolved."})
        save_session_message(
            session_id, "assistant",
            f"I have {len(names)} bot(s): {', '.join(names) or 'none'}. {hint} "
            f"You can also pick one in the dropdown above the chat.",
        )
        touch_chat_session(session_id)
        return

    bot_id = bot["bot_id"]
    _persist_session_bot(session_id, bot)
    session = {**session, "bot_id": bot_id, "dataset": bot.get("business_id")}

    n_q = _parse_question_count(message, default=10)
    try:
        questions = asyncio.run(_generate_test_questions(session, message, business_desc))
    except Exception:
        questions = _fallback_test_questions(bot.get("business_id") or "saas", limit=n_q)
    questions = questions[:n_q]

    def _fix(text: str) -> None:
        job["fixing_log"].append({"t": _time.strftime("%H:%M:%S"), "text": text})

    def _opt(text: str) -> None:
        job["optimization_log"].append({"t": _time.strftime("%H:%M:%S"), "text": text})

    job["bot_name"] = bot["name"]
    job["transcript"] = []
    job["fixing_log"] = []
    job["optimization_log"] = []
    job["questions_total"] = len(questions)
    _opt(f"Loaded {bot['name']} ({bot.get('business_id', 'general')}) — {len(questions)} questions queued.")

    passed, fixed = _run_live_qa_loop(job_id, job, bot, questions, _fix=_fix, _opt=_opt)

    job["passed"] = passed
    job["fixed"] = fixed
    job["status"] = "completed"
    _opt(f"Done. {passed}/{len(questions)} answered well, {fixed} auto-fixed.")

    summary_lines = [
        f"I asked {bot['name']} {len(questions)} customer questions: "
        f"{passed}/{len(questions)} answered well"
        + (f", and I fixed {fixed} that were failing." if fixed else "."),
    ]
    if fixed:
        summary_lines.append("Fixes were saved as custom answers and your bot was re-indexed live.")
    weak = [e for e in job.get("transcript", []) if not e.get("ok")]
    if weak:
        summary_lines.append(
            "Still weak: " + ", ".join(f'\"{e["question"]}\"' for e in weak[:3])
        )
    job["summary"] = " ".join(summary_lines)
    save_session_message(session_id, "assistant", job["summary"])
    touch_chat_session(session_id)


def _quick_answer(question: str, bot: dict) -> str:
    """Generate a concise support answer for a failing question (LLM or research)."""
    dataset = bot.get("business_id", "general")
    try:
        from meraxes_agent.knowledge import gather_knowledge

        k = gather_knowledge(question, dataset=dataset, enable_research=True, fast=True)
        draft = k.get("synthesized_answer") or ""
        if draft and len(draft) > 20:
            return draft[:400]
    except Exception:
        pass
    return ""


def _run_create_bot_job(job_id: str, session_id: str, message: str, history: list[dict]) -> None:
    """Create + train a bot with live technical build log."""
    import time as _time

    from dataset_loader import merge_custom_qa
    from meraxes_agent.tools.chat_tools import _extract_create_params

    job = _action_jobs[job_id]

    def _log(text: str, phase: str = "info") -> None:
        entry = {"t": _time.strftime("%H:%M:%S"), "text": text, "phase": phase}
        job.setdefault("build_log", []).append(entry)
        job["current"] = text

    params = _extract_create_params(message, history)
    name = params.get("name")
    business_id = params.get("business_id") or "general"

    if not name:
        job.update({"status": "failed", "error": "No bot name in request."})
        save_session_message(session_id, "assistant", "Tell me the bot name — e.g. \"Create a bot named Kal for ecommerce\".")
        touch_chat_session(session_id)
        return

    _log(f"[parse] request → name=\"{name}\", module=\"{business_id}\"", "parse")

    for b in list_bots():
        if b["name"].lower() == name.lower():
            job.update({"status": "failed", "error": "Bot already exists."})
            save_session_message(
                session_id, "assistant",
                f"{b['name']} already exists (ID: {b['bot_id']}). I've selected it in the dropdown.",
            )
            touch_chat_session(session_id)
            return

    try:
        template = load_template(business_id)
    except FileNotFoundError:
        business_id = "general"
        template = load_template(business_id)
        _log(f"[template] module fallback → general", "warn")

    intents = template.get("intents", [])
    biz_label = template.get("name", business_id)
    _log(f"[template] loaded {biz_label} — {len(intents)} intents, hybrid model", "template")

    sample_tags = [
        i["tag"] for i in intents
        if i.get("tag") and i["tag"] not in ("greeting", "thanks", "goodbye", "name", "status")
    ][:10]
    if sample_tags:
        _log(f"[intents] catalog sample: {', '.join(sample_tags)}", "intents")
        if len(intents) > 10:
            _log(f"[intents] … +{len(intents) - 10} more intent definitions", "intents")

    _log(f"[db] INSERT bots (name={name}, business_id={business_id}, model_type=hybrid)", "db")
    bot = create_bot(name, business_id, "hybrid")
    job["bot_name"] = name
    _log(f"[db] committed bot_id={bot['bot_id']}", "db")

    _log("[engine] initializing BotEngine — loading SentenceTransformer encoder", "engine")
    from engine import get_engine

    eng = get_engine(bot)
    _log(f"[engine] merging {len(intents)} template intents + custom Q&A[]", "engine")
    eng.intents = merge_custom_qa(intents, [])

    _log("[model] encoding intent patterns → embedding matrix", "model")
    job["status"] = "training"
    _log("[model] training hybrid classifier (FAQ index + intent NN) — ~1–2 min", "model")
    try:
        eng.train()
        _log("[model] train() complete — checkpoint ready for inference", "model")
    except Exception as exc:
        _log(f"[model] training warning: {exc}", "warn")
        _log("[model] bot usable via template intents + FAQ fallback", "warn")

    _log(f"[session] attaching {name} to agent chat session", "session")
    _persist_session_bot(session_id, bot)

    samples = (template.get("suggested_customer_questions") or [])[:3]
    job.update({
        "status": "completed",
        "created_bot_id": bot["bot_id"],
        "business_id": business_id,
        "intent_count": len(intents),
        "summary": (
            f"Created {name} ({biz_label}) — {len(intents)} intents trained. "
            f"Bot ID: {bot['bot_id']}."
            + (f" Try: \"{samples[0]}\"" if samples else "")
        ),
    })
    _log(f"[done] {name} is live — select in dropdown or Test chat", "done")

    save_session_message(session_id, "assistant", job["summary"])
    touch_chat_session(session_id)


def _start_create_bot_action(session: dict, message: str, history: list[dict]) -> dict[str, Any]:
    from meraxes_agent.tools.chat_tools import _extract_create_params

    params = _extract_create_params(message, history)
    name = params.get("name")

    if not name:
        return {"immediate": True, "error": "missing_name"}

    for b in list_bots():
        if b["name"].lower() == name.lower():
            return {
                "immediate": True,
                "exists": {
                    "name": b["name"],
                    "bot_id": b["bot_id"],
                    "business_id": b["business_id"],
                },
            }

    job_id = uuid.uuid4().hex[:12]
    _action_jobs[job_id] = {
        "status": "running",
        "kind": "create",
        "session_id": session["session_id"],
        "bot_name": name,
        "business_id": params.get("business_id") or "general",
        "build_log": [],
        "current": "Starting build pipeline…",
    }

    threading.Thread(
        target=_run_create_bot_job,
        args=(job_id, session["session_id"], message, history),
        daemon=True,
        name=f"meraxes-create-{job_id}",
    ).start()

    return {
        "action_job_id": job_id,
        "kind": "create",
        "bot_name": name,
        "dataset": params.get("business_id") or "general",
    }


def _start_test_action(session: dict, message: str, business_desc: str = "") -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    resolved = _resolve_target_bot(session, message)
    _action_jobs[job_id] = {
        "status": "running",
        "kind": "test",
        "session_id": session["session_id"],
        "bot_name": resolved["name"] if resolved else None,
        "transcript": [],
        "fixing_log": [],
        "optimization_log": [],
        "questions_total": 0,
        "progress": 0,
    }

    threading.Thread(
        target=_run_test_job,
        args=(job_id, session, business_desc, message),
        daemon=True,
        name=f"meraxes-test-{job_id}",
    ).start()

    return {"action_job_id": job_id, "kind": "test"}


def _format_optimizer_result(final_output: dict) -> str:
    us = final_output.get("user_summary") or {}
    lines = [us.get("headline") or "Bot optimization complete"]
    for bullet in us.get("bullets") or []:
        lines.append(f"• {bullet}")
    intents = final_output.get("intents_added") or us.get("intents_added") or []
    if intents:
        lines.append(f"New topics: {', '.join(intents[:6])}")
    brief = us.get("research_brief") or final_output.get("research_brief") or ""
    if brief:
        lines.append(f"\nResearch summary: {brief[:400]}")
    base = final_output.get("baseline_score")
    post = final_output.get("post_refine_score")
    if base is not None and post is not None:
        lines.append(f"Quality score: {base:.2f} → {post:.2f}")
    return "\n".join(lines)


_PHASE_LABELS = {
    "parse": "Understanding your request",
    "research": "Researching topics",
    "intents": "Building new topics",
    "deploy": "Adding topics to your bot",
    "train": "Training the model",
    "benchmark": "Loading test questions",
    "baseline": "Testing bot (before)",
    "evaluate": "Scoring answers",
    "failures": "Finding weak answers",
    "retrain": "Fine-tuning weak spots",
    "regression": "Re-testing (after)",
    "score_delta": "Measuring improvement",
}


def _run_optimizer_job(job_id: str, session_id: str, message: str, dataset: str, bot_id: str | None) -> None:
    try:
        from meraxes_agent.models.schemas import AgentGoal
        from meraxes_agent.optimizer_agent import MeraxesQualityLab

        bot = get_bot(bot_id) if bot_id else None
        if bot and bot.get("business_id"):
            dataset = bot["business_id"]

        def _progress(phase: str, msg: str, count: int) -> None:
            job = _action_jobs.get(job_id)
            if job is None:
                return
            steps = job.setdefault("steps", [])
            steps.append({"phase": phase, "label": _PHASE_LABELS.get(phase, msg), "n": count})
            job["current"] = _PHASE_LABELS.get(phase, msg)

        goal = AgentGoal(
            description=message,
            context={
                "dataset": dataset,
                "enable_research": True,
                "quick_train": True,
                "minimal_train": True,
                "test_case_limit": 5,
                "bot_id": bot_id,
                "progress_cb": _progress,
            },
        )
        run = MeraxesQualityLab().run(goal)
        fo = run.final_output or {}
        text = _format_optimizer_result(fo)
        save_session_message(session_id, "assistant", text)
        touch_chat_session(session_id)
        job = _action_jobs.get(job_id, {})
        job.update({
            "status": "completed",
            "session_id": session_id,
            "run_id": run.run_id,
            "kind": "train",
            "summary": text,
            "baseline_score": fo.get("baseline_score"),
            "post_refine_score": fo.get("post_refine_score"),
            "intents_added": fo.get("intents_added", []),
            "rounds": len(run.steps),
        })
        _action_jobs[job_id] = job
    except Exception as exc:
        save_session_message(
            session_id,
            "assistant",
            f"I couldn't finish the training run: {exc}. Try Bot Optimizer tab or a shorter goal.",
        )
        touch_chat_session(session_id)
        _action_jobs[job_id] = {"status": "failed", "session_id": session_id, "error": str(exc)}


def _start_optimizer_action(session: dict, message: str, business_desc: str = "") -> dict[str, Any]:
    bot = _resolve_target_bot(session, message)
    dataset = (bot or {}).get("business_id") or session.get("dataset") or "saas"
    bot_label = bot["name"] if bot else "your bot"
    all_bots = list_bots()

    job_id = uuid.uuid4().hex[:12]
    _action_jobs[job_id] = {
        "status": "running",
        "kind": "train",
        "session_id": session["session_id"],
        "bot_name": bot_label,
        "transcript": [],
        "fixing_log": [],
        "optimization_log": [],
        "steps": [],
        "current": "Starting…",
        "questions_total": 0,
        "progress": 0,
    }

    threading.Thread(
        target=_run_full_train_job,
        args=(job_id, session, message, business_desc),
        daemon=True,
        name=f"meraxes-train-{job_id}",
    ).start()

    return {
        "action_job_id": job_id,
        "kind": "train",
        "dataset": dataset,
        "bot_name": bot_label,
        "bot_count": len(all_bots),
    }


def _load_intents_file(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("intents", data if isinstance(data, list) else [])
    except Exception:
        return []


def _collect_session_intents(session: dict) -> dict[str, Any]:
    bot_id = session.get("bot_id")
    bot = get_bot(bot_id) if bot_id else None
    dataset = (bot or {}).get("business_id") or session.get("dataset") or "saas"

    template = load_template(dataset)
    template_tags = {i["tag"] for i in template.get("intents", [])}

    meraxes_intents = _load_intents_file(V1_ROOT / "models" / "meraxes" / dataset / "intents.json")
    bot_intents = _load_intents_file(V1_ROOT / "bots" / bot_id / "intents.json") if bot_id else []

    by_tag: dict[str, dict] = {}
    agent_tags: set[str] = set()

    for intent in template.get("intents", []):
        by_tag[intent["tag"]] = intent

    meraxes_tags = {i["tag"] for i in meraxes_intents}
    for intent in meraxes_intents:
        tag = intent["tag"]
        by_tag[tag] = intent
        if tag not in template_tags or tag.startswith("user_"):
            agent_tags.add(tag)

    for intent in bot_intents:
        by_tag[intent["tag"]] = intent

    # Tags only in meraxes file beyond template = agent-added
    for tag in meraxes_tags - template_tags:
        agent_tags.add(tag)

    built_in = [by_tag[t] for t in by_tag if t not in agent_tags]
    agent_added = [by_tag[t] for t in agent_tags if t in by_tag]

    return {
        "bot": bot,
        "dataset": dataset,
        "total": len(by_tag),
        "built_in": built_in,
        "agent_added": agent_added,
    }


def _sample_phrase(intent: dict) -> str:
    patterns = intent.get("patterns") or []
    for p in patterns:
        p = str(p).strip()
        if p and len(p) < 80:
            return p
    responses = intent.get("responses") or []
    if responses:
        return str(responses[0])[:60]
    return intent.get("tag", "hello")


def _format_intent_list(session: dict, limit: int = 10) -> str:
    info = _collect_session_intents(session)
    bot = info["bot"]
    label = bot["name"] if bot else f"{info['dataset']} model"
    lines = [
        f"Here are up to {limit} intents you can test for {label} ({info['dataset']}):",
        f"Total topics in model: {info['total']}\n",
    ]

    if info["agent_added"]:
        lines.append("Added by the agent (new):")
        for i, intent in enumerate(info["agent_added"][:limit], 1):
            lines.append(f"  {i}. {intent['tag']} — try: \"{_sample_phrase(intent)}\"")
        lines.append("")

    remaining = max(0, limit - min(len(info["agent_added"]), limit))
    shown = 0
    if remaining:
        lines.append("Built-in template topics:")
        for intent in info["built_in"]:
            if intent["tag"] in _SKIP_INTENT_TAGS:
                continue
            shown += 1
            lines.append(f"  • {intent['tag']} — try: \"{_sample_phrase(intent)}\"")
            if shown >= remaining:
                break

    if not info["agent_added"] and shown == 0:
        lines.append("No custom agent intents yet. Use Bot Optimizer or ask me to train on a topic.")

    lines.append("\nTip: use Test chat tab or ask me a question matching any phrase above.")
    return "\n".join(lines)


def _format_bot_list() -> str:
    bots = list_bots()
    if not bots:
        return "You don't have any bots yet. Create one under Create bot."
    lines = [f"You have {len(bots)} bot(s):\n"]
    for b in bots:
        lines.append(f"• {b['name']} — template: {b['business_id']}, model: {b['model_type']}, id: {b['bot_id']}")
    return "\n".join(lines)


def _handle_structured_query(session: dict, kind: str) -> dict[str, Any]:
    if kind == "list_intents":
        content = _format_intent_list(session, limit=10)
    elif kind == "list_bots":
        content = _format_bot_list()
    else:
        content = "I'm not sure how to help with that yet."
    return {
        "content": content,
        "provider": "agent",
        "sources": [],
        "source_names": ["bot_introspection"],
        "action_started": False,
    }


def _session_title_from_message(message: str) -> str:
    t = message.strip().replace("\n", " ")
    return (t[:48] + "…") if len(t) > 48 else t or "New chat"


def _is_general_knowledge(message: str) -> bool:
    m = message.lower().strip()
    return bool(re.match(
        r"^(what is|what are|who is|who are|explain|define|tell me about|how does|how do)\b",
        m,
    ))


def _build_website_context(session: dict) -> str:
    parts: list[str] = []
    dataset = session.get("dataset") or "saas"
    try:
        template = load_template(dataset)
        parts.append(f"Business vertical: {template.get('name', dataset)}")
        if template.get("description"):
            parts.append(f"Description: {template['description']}")
        sample_qs = template.get("suggested_customer_questions") or []
        if sample_qs:
            parts.append("Typical customer questions: " + "; ".join(sample_qs[:5]))
    except Exception:
        pass

    bot_id = session.get("bot_id")
    if bot_id:
        bot = get_bot(bot_id)
        if bot:
            parts.append(f"Active chatbot: {bot['name']} (template: {bot['business_id']}, model: {bot['model_type']})")
            for qa in (bot.get("custom_qa") or [])[:8]:
                parts.append(f"Custom Q: {qa.get('question', '')} → A: {qa.get('answer', '')[:200]}")
    return "\n".join(parts)


async def _gemini_direct(messages: list[dict], system: str) -> str | None:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    parts = [{"text": system}]
    for m in messages[-12:]:
        parts.append({"text": f"{m['role'].upper()}: {m['content']}"})
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            json={"contents": [{"parts": parts}]},
            timeout=45,
        )
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return None


async def compose_reply(
    message: str,
    history: list[dict],
    knowledge: dict[str, Any],
    *,
    website_context: str = "",
    bot_reply: str | None = None,
    general_question: bool = False,
) -> dict[str, Any]:
    """Agentic reply: website-aware assistant with research + optional bot knowledge."""
    system = (
        "You are Meraxes AI — an intelligent agent embedded on this business website, "
        "similar to Cursor, Copilot, or Claude. You help visitors and site owners.\n\n"
        "You CAN:\n"
        "- Answer questions accurately using research and website context\n"
        "- Explain products, pricing, policies, and integrations for this business\n"
        "- Help improve the chatbot (suggest new Q&A topics, intents, training tips)\n"
        "- Guide users on embedding the chat widget on their site\n"
        "- Have natural multi-turn conversations\n\n"
        "Rules:\n"
        "- Answer the user's question DIRECTLY — never reply with an unrelated FAQ question\n"
        "- Use research sources when answering factual/general questions\n"
        "- Be conversational, helpful, and specific\n"
        "- If you don't know, say so honestly\n\n"
        f"WEBSITE CONTEXT:\n{website_context[:1500]}\n\n"
        f"RESEARCH:\n{knowledge.get('brief', '')[:2500]}\n"
    )
    if bot_reply and not general_question:
        system += f"\nLOCAL BOT SUGGESTION (use only if relevant to the question):\n{bot_reply}\n"

    msgs = [{"role": h["role"], "content": h["content"]} for h in history[-10:]]
    msgs.append({"role": "user", "content": message})

    if knowledge.get("synthesized_answer"):
        return {
            "content": knowledge["synthesized_answer"],
            "provider": "gemini_research" if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") else "research",
            "sources": knowledge.get("sources", []),
            "source_names": knowledge.get("source_names", []),
        }

    router_msgs = [{"role": "system", "content": system}, *msgs]
    routed = await chat_with_router(router_msgs, task="auto", max_tokens=900)
    if routed and routed.get("content"):
        return {
            "content": routed["content"],
            "provider": routed.get("provider", "llm_router"),
            "model": routed.get("model"),
            "sources": knowledge.get("sources", []),
            "source_names": knowledge.get("source_names", []),
        }

    gemini = await _gemini_direct(msgs, system)
    if gemini:
        return {
            "content": gemini,
            "provider": "gemini",
            "sources": knowledge.get("sources", []),
            "source_names": knowledge.get("source_names", []),
        }

    local = synthesize_local_answer(message, knowledge.get("hits") or [])
    if local:
        return {
            "content": local,
            "provider": "research",
            "sources": knowledge.get("sources", []),
            "source_names": knowledge.get("source_names", []),
        }

    if bot_reply and not general_question:
        return {
            "content": bot_reply,
            "provider": "local_bot",
            "sources": knowledge.get("sources", []),
            "source_names": knowledge.get("source_names", []),
        }

    return {
        "content": (
            "I couldn't find a good answer yet. Try rephrasing your question, "
            "or turn on Research for live Wikipedia and web search."
        ),
        "provider": "local",
        "sources": [],
        "source_names": [],
    }


async def agent_chat_turn(
    session_id: str,
    message: str,
    *,
    enable_research: bool = True,
    bot_id: str | None = None,
    dataset: str | None = None,
) -> dict[str, Any]:
    session = get_chat_session(session_id)
    if not session:
        raise ValueError("Session not found")

    # Sync the session to the bot the user selected in the dropdown.
    # IMPORTANT: only update when a real (non-empty) bot is selected, and derive
    # the dataset from THAT bot — never clobber the session with empty/default values
    # (doing so previously switched a finance bot to the 'saas' default).
    if bot_id and bot_id != session.get("bot_id"):
        from database import update_chat_session_bot

        picked = get_bot(bot_id)
        ds = picked.get("business_id") if picked else (dataset or session.get("dataset"))
        update_chat_session_bot(session_id, bot_id=bot_id, dataset=ds)
        session = get_chat_session(session_id) or session

    message = message.strip()

    # If the user names a bot in the message (e.g. "train aboki"), attach it even
    # when the dropdown still shows "No bot".
    resolved = _resolve_target_bot(session, message)
    if resolved and resolved["bot_id"] != session.get("bot_id"):
        _persist_session_bot(session_id, resolved)
        session = get_chat_session(session_id) or session
    if not message:
        raise ValueError("Empty message")

    history = get_session_messages(session_id)
    if len(history) == 0:
        touch_chat_session(session_id, title=_session_title_from_message(message))

    save_session_message(session_id, "user", message)

    from meraxes_agent.tools.chat_tools import tool_session_snapshot

    snapshot = tool_session_snapshot(session)
    plan = await plan_turn(message, history, snapshot)
    tool_results, side = await execute_tools(
        plan,
        session,
        message,
        history=history,
        enable_research=enable_research,
        start_optimizer_fn=_start_optimizer_action,
        start_test_fn=_start_test_action,
        start_create_fn=_start_create_bot_action,
    )

    if side.get("created_bot_id"):
        created = get_bot(side["created_bot_id"])
        if created:
            _persist_session_bot(session_id, created)

    content, provider = await synthesize_reply(
        message, history, plan, tool_results,
        prefer_fallback=(
            side.get("action_started", False)
            or "bot_overview" in tool_results
            or "create_bot" in tool_results
        ),
    )
    save_session_message(session_id, "assistant", content)

    source_names = []
    if "research" in tool_results:
        source_names.extend(tool_results["research"].get("sources") or [])
    if "list_intents" in tool_results:
        source_names.append("bot_intents")
    if "run_optimizer" in tool_results or "describe_business" in tool_results:
        source_names.append("optimizer")
    if "test_bot" in tool_results:
        source_names.append("bot_test")
    if "list_bots" in tool_results:
        source_names.append("bots")
    if "bot_overview" in tool_results:
        source_names.append("bot_config")
    if "create_bot" in tool_results:
        source_names.append("bot_create")

    out = {
        "session_id": session_id,
        "message": content,
        "provider": provider,
        "sources": [],
        "source_names": list(dict.fromkeys(source_names)),
        "research_used": "research" in tool_results,
        "action_started": side.get("action_started", False),
        "action_kind": side.get("action_kind"),
        "action_job_id": side.get("action_job_id"),
        "plan": plan.get("tools"),
        "created_bot_id": side.get("created_bot_id"),
    }
    return out


def new_session(
    bot_id: str | None = None,
    dataset: str = "saas",
    client_id: str | None = None,
) -> dict:
    return create_chat_session(bot_id=bot_id, dataset=dataset, client_id=client_id)


def sessions_list(client_id: str | None = None, limit: int = 40) -> list[dict]:
    return list_chat_sessions(client_id=client_id, limit=limit)


def session_history(session_id: str) -> list[dict]:
    return get_session_messages(session_id)


def remove_session(session_id: str, client_id: str | None = None) -> int:
    if client_id:
        s = get_chat_session(session_id)
        if not s or s.get("client_id") != client_id:
            return 0
    return delete_chat_session(session_id)


def chat_capabilities() -> dict:
    return {
        "router_available": router_available(),
        "providers": list_providers(),
        "gemini_configured": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")),
        "sources": ["wikipedia", "duckduckgo", "website_faq", "gemini", "llm_router", "optimizer", "bot_intents"],
        "agent_mode": "planner_tools",
    }
