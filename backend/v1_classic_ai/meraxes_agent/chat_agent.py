"""
Meraxes chat agent — Copilot/Cursor-style planner + tools + natural synthesis.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from meraxes_agent.llm_bridge import chat_with_router
from meraxes_agent.tools.chat_tools import (
    tool_bot_overview,
    tool_list_bots,
    tool_list_intents,
    tool_research,
    tool_session_snapshot,
    tool_website_context,
)

# ─── Planning (LLM or heuristic fallback) ───────────────────────────────────

_PLAN_TOOLS = frozenset({
    "research", "list_intents", "list_bots", "bot_overview", "create_bot",
    "run_optimizer", "test_bot", "describe_business", "none",
})

_HEURISTIC_LIST = re.compile(
    r"\b(list|show|display|give\s+me|name)\b.*\b(intents?|topics?|subjects?)\b"
    r"|\b(intents?|topics?).*\b(list|show|added|already)\b"
    r"|\bmajor\s+intents?\b",
    re.I,
)
_HEURISTIC_BOTS = re.compile(
    r"\b(list|show)\b.*\bbots\b|\bwhat\s+bots\b|\bmy\s+bots\b|\bhow\s+many\s+bots\b",
    re.I,
)
_HEURISTIC_BOT_ABOUT = re.compile(
    r"\b(what\s+(is|does|can)|tell\s+me\s+about|describe|explain|info\s+(on|about)|"
    r"purpose\s+of|details?\s+(on|about))\b.*\b(bot|model|chatbot|assistant)\b"
    r"|\bwhat'?s\s+my\s+bot\b|\bwhat\s+(is|are)\s+my\s+bots?\s+about\b"
    r"|\bhow\s+does\s+(my|the)\s+bot\b",
    re.I,
)
_HEURISTIC_TEST = re.compile(
    r"\b(test|try|check|qa|evaluate|see\s+how)\b.*\b(bot|model|it)\b"
    r"|\btest\s+(my|the|it)\b|\bask\s+(my|the)\s+bot\b|\brun\s+a\s+test\b",
    re.I,
)
_HEURISTIC_BUSINESS = re.compile(
    r"\b(my\s+business\s+is|this\s+is\s+my\s+business|we\s+are\s+a|we're\s+a|"
    r"my\s+company|train\s+(my\s+)?bot\s+(based\s+on|on)\s+(this|my))\b",
    re.I,
)
_HEURISTIC_TRAIN = re.compile(
    r"\b(train|retrain|optimize|optimise|fine[\s-]?tune|tune\s+(it|the|my)|"
    r"add\s+intent|research\s+and\s+train|improve\s+(the\s+|my\s+)?bot|quality\s+lab)\b",
    re.I,
)
_HEURISTIC_CONFIRM = re.compile(
    r"^(yes|yeah|yep|yup|sure|ok|okay|go\s+ahead|do\s+it|proceed|please\s+do|"
    r"go\s+on|continue|sounds?\s+good|let'?s\s+do\s+it|fine\s+tune\s+it|"
    r"go\s+ahead\s+and\b.*)\b",
    re.I,
)
_PROPOSAL_HINT = re.compile(
    r"\b(fine[\s-]?tune|train|optimi|add\s+intent|i can add|i'?ll add|would you like me to|"
    r"let me know if you'?d like|proceed with)\b",
    re.I,
)
_HEURISTIC_CREATE = re.compile(
    r"\b(create|make|set\s+up)\b.*\b(?:bot|chatbot|assistant)\b"
    r"|\bcreate\s+(?:a\s+)?(?:new\s+)?bot\b"
    r"|\b(?:name\s+it|named|call\s+it)\s+['\"]?\w+['\"]?"
    r"|\bcreate\s+\w+\s+then\b",
    re.I,
)
_CREATE_PROPOSAL = re.compile(
    r"\b(i can help you create|create a new bot|let'?s create|name it|named)\b",
    re.I,
)
_HEURISTIC_KNOWLEDGE = re.compile(
    r"^(what|who|how|why|explain|define|tell me about)\b", re.I
)


async def _llm_plan(message: str, history: list[dict], snapshot: dict) -> dict | None:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    recent = "\n".join(
        f"{m['role']}: {m['content'][:200]}"
        for m in history[-6:]
    )
    bot_line = ""
    if snapshot.get("active_bot"):
        b = snapshot["active_bot"]
        bot_line = f"Active bot: {b['name']} ({b['business_id']})"

    prompt = f"""You route requests for Meraxes AI (chatbot platform agent like Copilot).

Session: {bot_line or 'No bot selected'}, dataset={snapshot.get('dataset')}, bots={snapshot.get('bot_names')}

Recent chat:
{recent or '(new chat)'}

User now says: {message}

Tools (pick exactly 1):
- research — factual/web questions about the WORLD (what is X, explain Y) — NOT about their own bot
- bot_overview — user asks what THEIR bot is about / what it does / what it can answer (e.g. "what is my aboki bot about")
- list_intents — user wants to SEE topics/intents to test, not train
- list_bots — user wants their bot list
- create_bot — user wants to CREATE/MAKE a new bot (e.g. "create a bot named Kal for ecommerce", "ok create Kal then")
- test_bot — user wants to TEST/TRY their bot: agent asks the bot real questions live and shows answers, fixing failures
- describe_business — user describes their business and wants the bot trained on it (e.g. "my business is X, train my bot on that")
- run_optimizer — user explicitly wants training/optimization/add intents (no business description given)
- none — greeting, follow-up, advice, embed help, general chat using context only

Rules:
- "what is my bot about" / "what does the X bot do" / "what can my bot answer" → bot_overview (NOT research — never guess from the bot's name)
- "create a bot named X" / "create Kal for ecommerce" / "ok create Kal then" → create_bot (actually creates it — NOT just advice)
- "list intents" / "what did you add" → list_intents (NOT run_optimizer)
- "test my bot" / "try it" / "ask it questions" → test_bot
- "my business is..." / "train on my business" → describe_business
- "fine tune" / "tune it" / "improve the bot" → run_optimizer
- If the user gives a short confirmation ("go ahead", "yes", "do it", "proceed") AND your previous message proposed training/fine-tuning → run_optimizer
- Only run_optimizer when user says train/optimize/fine-tune WITHOUT describing their business

Return JSON only:
{{"tools":["name"],"limit":10,"reason":"brief"}}"""

    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
            },
            timeout=20,
        )
        if r.status_code != 200:
            return None
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        plan = json.loads(text)
        tools = [t for t in plan.get("tools", ["none"]) if t in _PLAN_TOOLS]
        if not tools:
            tools = ["none"]
        plan["tools"] = tools[:2]
        return plan
    except Exception:
        return None


def _heuristic_plan(message: str, history: list[dict]) -> dict:
    last_assistant = next(
        (h["content"] for h in reversed(history) if h.get("role") == "assistant"), ""
    )
    if _HEURISTIC_LIST.search(message):
        return {"tools": ["list_intents"], "limit": 10, "reason": "user asked to list intents"}
    if _HEURISTIC_CREATE.search(message):
        return {"tools": ["create_bot"], "limit": 10, "reason": "user asked to create a bot"}
    if _HEURISTIC_CONFIRM.match(message.strip()) and (
        _CREATE_PROPOSAL.search(last_assistant) or re.search(r"\bcreate\s+\w+\s+then\b", message, re.I)
    ):
        return {"tools": ["create_bot"], "limit": 10, "reason": "user confirmed bot creation"}
    if _HEURISTIC_BOT_ABOUT.search(message):
        return {"tools": ["bot_overview"], "limit": 10, "reason": "user asked what their bot is about"}
    if _HEURISTIC_BOTS.search(message):
        return {"tools": ["list_bots"], "limit": 10, "reason": "user asked about bots"}
    if _HEURISTIC_TEST.search(message) or re.search(r"\bcan\s+(my|the)\s+bot\b", message, re.I):
        return {"tools": ["test_bot"], "limit": 10, "reason": "user wants to test the bot"}
    if _HEURISTIC_BUSINESS.search(message):
        return {"tools": ["describe_business"], "limit": 10, "reason": "user described business to train on"}
    if _HEURISTIC_TRAIN.search(message) and not _HEURISTIC_LIST.search(message):
        return {"tools": ["run_optimizer"], "limit": 10, "reason": "user requested training"}
    # Confirmation ("go ahead", "yes do it") right after the agent proposed fine-tuning.
    if _HEURISTIC_CONFIRM.match(message.strip()) and _PROPOSAL_HINT.search(last_assistant):
        return {"tools": ["run_optimizer"], "limit": 10, "reason": "user confirmed proposed training"}
    if _HEURISTIC_KNOWLEDGE.search(message.strip()):
        return {"tools": ["research"], "limit": 10, "reason": "factual question"}
    return {"tools": ["none"], "limit": 10, "reason": "general conversation"}


_PLATFORM_TOOLS = frozenset({
    "list_intents", "list_bots", "bot_overview", "create_bot",
    "test_bot", "describe_business", "run_optimizer",
})


async def plan_turn(message: str, history: list[dict], snapshot: dict) -> dict:
    heuristic = _heuristic_plan(message, history)
    # Platform actions (your bots, training, testing) must use real data — not LLM guesses.
    if heuristic.get("tools", ["none"])[0] in _PLATFORM_TOOLS:
        return heuristic
    plan = await _llm_plan(message, history, snapshot)
    if plan and heuristic.get("tools") == ["bot_overview"]:
        return heuristic  # never let the LLM guess what a bot does from its name
    return plan or heuristic


# ─── Synthesis (natural reply from tool outputs) ─────────────────────────────

async def _synthesize_with_llm(
    message: str,
    history: list[dict],
    plan: dict,
    tool_results: dict[str, Any],
    *,
    router_first: bool = False,
) -> str | None:
    ctx_blob = json.dumps(tool_results, indent=0)[:6000]
    recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in history[-8:])
    system = (
        "You are Meraxes AI — an expert agent for a chatbot platform (like Cursor/Copilot).\n"
        "Write ONE helpful reply to the user. Be natural, specific, and non-repetitive.\n"
        "Use the tool results below — do not invent data.\n"
        "CRITICAL: Never guess what a bot does from its NAME. If bot_overview is present, "
        "describe the bot strictly from that data (business_template, top_topics, intents, custom Q&A).\n"
        "If bot_overview: explain what the bot is built for, how many topics/intents it has, "
        "the main topics it can answer, and suggest a couple of sample questions to try.\n"
        "If list_intents: present topics clearly with example phrases to test.\n"
        "If run_optimizer started: confirm what you're doing for THEIR bot by name; don't use generic boilerplate.\n"
        "If test_bot started: tell them to watch the live test popup where you ask the bot questions and fix failures.\n"
        "If describe_business started: confirm you're training their bot on their business; mention the live training panel.\n"
        "If research: answer the question directly using the research draft.\n"
        "Keep it concise but complete. No JSON. No markdown headers unless listing items."
    )
    user_block = (
        f"Plan: {plan.get('reason', '')}\n\n"
        f"Recent chat:\n{recent}\n\n"
        f"User: {message}\n\n"
        f"Tool results:\n{ctx_blob}"
    )
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user_block}]

    if router_first:
        routed = await chat_with_router(msgs, task="auto", max_tokens=1000)
        if routed and routed.get("content"):
            return routed["content"].strip()

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            r = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": system + "\n\n" + user_block}]}], "generationConfig": {"temperature": 0.6}},
                timeout=35,
            )
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception:
            pass

    if not router_first:
        routed = await chat_with_router(msgs, task="auto", max_tokens=1000)
        if routed and routed.get("content"):
            return routed["content"].strip()
    return None


def _fallback_synthesize(message: str, plan: dict, tool_results: dict[str, Any]) -> str:
    """Structured fallback when no LLM — still uses real tool data, not identical templates."""
    parts: list[str] = []

    if "test_bot" in tool_results:
        tb = tool_results["test_bot"]
        bot = tb.get("bot_name") or "your bot"
        parts.append(
            f"Opening the live test for {bot}. Watch the popup — I'll ask it real customer "
            f"questions, show each answer, and automatically fix any it gets wrong."
        )

    if "describe_business" in tool_results:
        db = tool_results["describe_business"]
        bot = db.get("bot_name") or "your bot"
        parts.append(
            f"Got it — I'll fine-tune {bot} on your business now. Watch the live panel: "
            f"I'll ask it real customer questions, and for any it answers wrong I'll research "
            f"the correct answer, add it, and re-index the bot live. Fixes show on the left, "
            f"the re-index on the right."
        )

    if "run_optimizer" in tool_results:
        opt = tool_results["run_optimizer"]
        bot = opt.get("bot_name") or "your bot"
        parts.append(
            f"On it — training {bot} ({opt.get('dataset', 'your industry')}) in two phases. "
            f"Phase 1: quality lab adds real new intents. Phase 2: I interview the bot with "
            f"customer questions and auto-fix every weak answer. Watch the popup — conversation "
            f"on top, fixes left, optimization right."
        )

    if "list_intents" in tool_results:
        li = tool_results["list_intents"]
        name = li.get("bot_name") or li.get("dataset", "model")
        parts.append(f"Intents for {name} ({li.get('total', 0)} total):")
        if li.get("agent_added"):
            parts.append("Agent-added (test these first):")
            for i, item in enumerate(li["agent_added"], 1):
                parts.append(f"  {i}. {item['tag']} — \"{item.get('sample_phrase', '')}\"")
        if li.get("built_in_sample"):
            parts.append("Built-in samples:")
            for item in li["built_in_sample"][:6]:
                parts.append(f"  • {item['tag']} — \"{item.get('sample_phrase', '')}\"")

    if "bot_overview" in tool_results:
        bo = tool_results["bot_overview"]
        if not bo.get("found"):
            parts.append(
                "You don't have a bot selected yet. Pick one in the dropdown above the chat, "
                + (f"or choose from: {', '.join(bo.get('bot_names', []))}." if bo.get("bot_names") else "or create one first.")
            )
        else:
            desc = bo.get("business_description") or ""
            line = (
                f"{bo['bot_name']} is a {bo.get('business_template', bo.get('business_id'))} "
                f"chatbot ({bo.get('model_type', 'ai')} model)."
            )
            if desc:
                line += f" {desc}"
            parts.append(line)
            parts.append(
                f"It currently knows {bo.get('topic_count', 0)} topics "
                f"({bo.get('total_intents', 0)} intents total)"
                + (f" plus {bo['custom_qa_count']} custom Q&A answers." if bo.get("custom_qa_count") else ".")
            )
            if bo.get("top_topics"):
                parts.append("Main things it can answer: " + ", ".join(bo["top_topics"][:10]) + ".")
            if bo.get("sample_questions"):
                parts.append("Try asking it: " + "; ".join(f'"{q}"' for q in bo["sample_questions"][:4]))

    if "create_bot" in tool_results:
        cb = tool_results["create_bot"]
        if not cb.get("created"):
            if cb.get("error") == "missing_name":
                parts.append(
                    "I can create the bot — tell me the name and industry. "
                    'For example: "Create a bot named Kal for ecommerce".'
                )
            elif cb.get("error") == "exists":
                ex = cb.get("existing", {})
                parts.append(
                    f"{ex.get('name')} already exists (ID: {ex.get('bot_id')}, {ex.get('business_id')}) — "
                    f"I've selected it in the dropdown. Open Test chat to try it, or ask me to fine-tune it."
                )
        else:
            parts.append(
                f"Done — created {cb['name']} ({cb.get('business_name')}) and trained it "
                f"with {cb.get('intent_count', 0)} intents. Bot ID: {cb['bot_id']}."
            )
            if cb.get("description"):
                parts.append(cb["description"])
            if cb.get("sample_questions"):
                parts.append(
                    "Try in Test chat: "
                    + "; ".join(f'"{q}"' for q in cb["sample_questions"][:4])
                )
            parts.append(f"{cb['name']} is now selected in the dropdown above the chat.")
            if cb.get("training_in_background"):
                parts.append(
                    "Model training is running in the background (1–2 min) — "
                    "the bot is ready to select and test right away."
                )

    if "list_bots" in tool_results:
        lb = tool_results["list_bots"]
        if not lb.get("count"):
            parts.append("You have no bots yet — create one under Create bot.")
        else:
            parts.append(f"You have {lb['count']} bot(s):")
            for b in lb.get("bots", []):
                parts.append(f"  • {b['name']} — {b['business_id']} ({b['model_type']})")

    if "research" in tool_results:
        draft = tool_results["research"].get("answer_draft") or tool_results["research"].get("brief", "")
        if draft:
            parts.append(draft[:900])
        else:
            parts.append("I couldn't find much on that topic — try rephrasing or enable Research.")

    if "website" in tool_results and not parts:
        w = tool_results["website"]
        parts.append(
            f"I'm here to help with {w.get('business_name', 'your site')}. "
            f"Ask me anything about your bot, training, or customer questions."
        )

    if not parts:
        parts.append(
            "I'm Meraxes AI — I can answer questions, list your bot's intents, train new topics, "
            "and help embed chat on your site. What would you like to do?"
        )
    return "\n\n".join(parts)


async def synthesize_reply(
    message: str,
    history: list[dict],
    plan: dict,
    tool_results: dict[str, Any],
    *,
    prefer_fallback: bool = False,
) -> tuple[str, str]:
    # For actions (test/train), use the deterministic reply so we describe EXACTLY
    # what the job does — the LLM tends to invent fake outcomes ("added 20 intents").
    if prefer_fallback:
        return _fallback_synthesize(message, plan, tool_results), "agent"
    text = await _synthesize_with_llm(message, history, plan, tool_results, router_first=True)
    if text:
        return text, "ai"
    return _fallback_synthesize(message, plan, tool_results), "agent"


async def execute_tools(
    plan: dict,
    session: dict,
    message: str,
    *,
    history: list[dict] | None = None,
    enable_research: bool,
    start_optimizer_fn,
    start_test_fn=None,
    start_create_fn=None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run planned tools. Returns (tool_results, side_effects like action_job)."""
    results: dict[str, Any] = {}
    side: dict[str, Any] = {"action_started": False}

    snap = tool_session_snapshot(session)
    dataset = snap["dataset"]
    bot_name = snap.get("active_bot", {}).get("name") if snap.get("active_bot") else None
    if not bot_name:
        low = message.lower()
        bot_name = next((n for n in snap.get("bot_names", []) if n and n.lower() in low), None)

    for tool in plan.get("tools", ["none"]):
        if tool == "none":
            results["website"] = tool_website_context(session)
        elif tool == "research" and enable_research:
            results["research"] = tool_research(message, dataset, fast=len(message) > 50)
        elif tool == "list_intents":
            results["list_intents"] = tool_list_intents(session, limit=plan.get("limit", 10))
        elif tool == "list_bots":
            results["list_bots"] = tool_list_bots()
        elif tool == "create_bot" and start_create_fn:
            t = start_create_fn(session, message, history or [])
            if t.get("immediate"):
                if t.get("exists"):
                    ex = t["exists"]
                    results["create_bot"] = {"created": False, "error": "exists", "existing": ex}
                    side["created_bot_id"] = ex["bot_id"]
                else:
                    results["create_bot"] = {"created": False, "error": t.get("error", "missing_name")}
            else:
                results["create_bot"] = {
                    "started": True,
                    "bot_name": t.get("bot_name"),
                    "dataset": t.get("dataset"),
                    "job_id": t.get("action_job_id"),
                }
                side["action_started"] = True
                side["action_kind"] = "create"
                side["action_job_id"] = t.get("action_job_id")
        elif tool == "bot_overview":
            # Resolve a bot name mentioned in the message, else use the active bot.
            target = None
            low = message.lower()
            for name in snap.get("bot_names", []):
                if name and name.lower() in low:
                    target = name
                    break
            results["bot_overview"] = tool_bot_overview(session, target)
        elif tool == "test_bot" and start_test_fn:
            t = start_test_fn(session, message)
            results["test_bot"] = {
                "bot_name": bot_name,
                "job_id": t.get("action_job_id"),
                "started": True,
            }
            side["action_started"] = True
            side["action_kind"] = "test"
            side["action_job_id"] = t.get("action_job_id")
        elif tool == "describe_business":
            opt = start_optimizer_fn(session, message, message)
            job_id = opt.get("action_job_id")
            results["describe_business"] = {
                "bot_name": bot_name or opt.get("bot_name"),
                "dataset": opt.get("dataset", dataset),
                "job_id": job_id,
            }
            side["action_started"] = True
            side["action_kind"] = "train"
            side["action_job_id"] = job_id
        elif tool == "run_optimizer":
            opt = start_optimizer_fn(session, message)
            job_id = opt.get("action_job_id")
            results["run_optimizer"] = {
                "bot_name": bot_name or opt.get("bot_name"),
                "dataset": opt.get("dataset", dataset),
                "job_id": job_id,
                "other_bots": snap.get("bot_names", [])[1:4],
            }
            side["action_started"] = True
            side["action_kind"] = "train"
            side["action_job_id"] = job_id

    if not results:
        results["website"] = tool_website_context(session)

    return results, side
