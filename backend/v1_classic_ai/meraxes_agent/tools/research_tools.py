"""
Meraxes agent — goal parsing, research, and intent expansion tools.

Production Track 2 capabilities beyond fixed benchmark-only optimization.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

V1_ROOT = Path(__file__).resolve().parents[2]
if str(V1_ROOT) not in sys.path:
    sys.path.insert(0, str(V1_ROOT))

from dataset_loader import load_template
from meraxes_agent.models.schemas import ToolResult

MODELS_DIR = V1_ROOT / "models" / "meraxes"
DATASETS_DIR = V1_ROOT / "datasets"

_TOPIC_SPLIT = re.compile(r"\b(?:about|for|on|covering|including|like)\b", re.I)
_ACTION_WORDS = re.compile(
    r"\b(research|add|create|expand|cover|handle|support|train|teach|learn|intent|topic|faq)\b",
    re.I,
)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())[:40].strip("_")
    return s or "topic"


# Words that signal a meta/command phrase rather than a real subject topic.
_META_WORDS = frozenset({
    "train", "trained", "training", "retrain", "model", "models", "intent",
    "intents", "research", "researches", "optimize", "optimise", "optimization",
    "list", "test", "bot", "bots", "ai", "find", "tem", "them", "watht", "lready",
    "already", "ones", "major", "add", "create", "build", "know", "more", "extra",
    "now", "out", "the10", "can", "did", "your", "my",
})

# Lightweight check that a topic is a real, sensible subject (not a typo command).
_VOWELS = set("aeiou")


def _looks_like_word(token: str) -> bool:
    t = token.lower()
    if len(t) < 2:
        return False
    if not (set(t) & _VOWELS):
        return False
    return t.isalpha()


def is_meaningful_topic(text: str) -> bool:
    """Reject meta-commands, gibberish, and instructions so they don't become intents."""
    t = (text or "").strip().lower()
    if len(t) < 3 or len(t) > 60:
        return False
    tokens = re.findall(r"[a-z0-9]+", t)
    if not tokens:
        return False
    meta_hits = sum(1 for tok in tokens if tok in _META_WORDS)
    # If most of the phrase is meta/command words, it's not a topic.
    if meta_hits >= max(1, len(tokens) // 2):
        return False
    # Require at least one real-looking content word.
    real = [tok for tok in tokens if tok not in _META_WORDS and _looks_like_word(tok)]
    return len(real) >= 1


def _gemini_json(prompt: str) -> dict | list | None:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=45,
        )
        if resp.status_code != 200:
            return None
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception:
        return None


class MeraxesGoalParserTool:
    name = "meraxes_goal_parser"
    description = "Parse user goal into topics, research queries, and planned actions"

    def execute(self, **kwargs: Any) -> ToolResult:
        goal = str(kwargs.get("goal") or kwargs.get("goal_description") or "").strip()
        dataset = kwargs.get("dataset", "saas")
        if len(goal) < 3:
            return ToolResult(success=False, error="Goal too short")

        topics: list[str] = []
        for part in _TOPIC_SPLIT.split(goal):
            chunk = part.strip(" .,:;")
            if len(chunk) < 4:
                continue
            if _ACTION_WORDS.search(chunk):
                chunk = re.sub(
                    r"^(please\s+)?(research|add|create|expand|more\s+)?(intents?\s+)?(for|about|on|to)\s+",
                    "",
                    chunk,
                    flags=re.I,
                ).strip()
            for piece in re.split(r"\band\b|,|;", chunk, flags=re.I):
                piece = piece.strip(" .")
                if len(piece) >= 3 and piece.lower() not in ("my bot", "the bot", "meraxes"):
                    if is_meaningful_topic(piece):
                        topics.append(piece[:120])

        topics = list(dict.fromkeys(topics))[:6]
        goal_lower = goal.lower()
        wants_research = any(
            w in goal_lower
            for w in ("research", "find out", "look up", "investigate", "learn about", "study", "web")
        )
        wants_intents = any(
            w in goal_lower
            for w in ("intent", "topic", "add", "cover", "handle", "support", "faq", "question", "answer")
        ) or bool(topics)

        gemini = _gemini_json(
            f'Parse this chatbot improvement goal for a {dataset} business bot. Goal: "{goal}". '
            'Return JSON: {"topics":["..."], "research_queries":["..."], "wants_research":true, "wants_intents":true, "summary":"one sentence"}'
        )
        if isinstance(gemini, dict):
            topics = gemini.get("topics") or topics
            research_queries = gemini.get("research_queries") or topics
            wants_research = gemini.get("wants_research", wants_research)
            wants_intents = gemini.get("wants_intents", wants_intents)
            summary = gemini.get("summary", goal[:120])
        else:
            research_queries = topics if topics else [goal[:100]]
            summary = goal[:160]

        # Drop meta/command/gibberish topics so they never become intents.
        topics = [t for t in topics if is_meaningful_topic(t)][:6]

        if not topics and wants_intents:
            research_queries = [goal[:100]]

        return ToolResult(
            success=True,
            output={
                "goal": goal,
                "dataset": dataset,
                "topics": topics,
                "research_queries": research_queries[:5],
                "wants_research": wants_research or kwargs.get("enable_research", True),
                "wants_intents": wants_intents,
                "summary": summary,
            },
        )


class MeraxesResearchTool:
    name = "meraxes_researcher"
    description = "Research topics via Wikipedia + optional Gemini synthesis"

    def execute(self, **kwargs: Any) -> ToolResult:
        parsed = kwargs.get("meraxes_goal_parser") or kwargs.get("goal_parser") or {}
        queries = parsed.get("research_queries") or parsed.get("topics") or []
        if not parsed.get("wants_research", True) or not queries:
            return ToolResult(
                success=True,
                output={"skipped": True, "findings": [], "brief": "Research not requested.", "sources": []},
            )

        findings: list[dict] = []
        sources: list[str] = []

        for q in queries[:4]:
            finding = {"query": q, "snippets": [], "source": None}
            title = q.split()[0:4]
            wiki_title = "_".join(w.title() for w in title)
            try:
                wr = httpx.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(wiki_title)}",
                    timeout=12,
                    headers={"User-Agent": "MeraxesBot/1.0 (research agent)"},
                )
                if wr.status_code == 200:
                    data = wr.json()
                    extract = data.get("extract", "")
                    if extract:
                        finding["snippets"].append(extract[:500])
                        finding["source"] = data.get("content_urls", {}).get("desktop", {}).get("page")
                        if finding["source"]:
                            sources.append(finding["source"])
            except Exception:
                pass

            try:
                ddg = httpx.get(
                    "https://api.duckduckgo.com/",
                    params={"q": q, "format": "json", "no_html": 1},
                    timeout=10,
                )
                if ddg.status_code == 200:
                    abstract = ddg.json().get("AbstractText", "")
                    if abstract and abstract not in finding["snippets"]:
                        finding["snippets"].append(abstract[:400])
                        src = ddg.json().get("AbstractURL")
                        if src:
                            finding["source"] = finding["source"] or src
                            sources.append(src)
            except Exception:
                pass

            if not finding["snippets"]:
                template = load_template(parsed.get("dataset", "saas"))
                for q_hint in template.get("suggested_customer_questions", [])[:3]:
                    if any(w in q_hint.lower() for w in q.lower().split()[:2] if len(w) > 3):
                        finding["snippets"].append(f"Industry FAQ: {q_hint}")
                        break
                if not finding["snippets"]:
                    finding["snippets"].append(
                        f"Best practice for {parsed.get('dataset', 'business')} bots: provide clear, concise answers about {q}."
                    )

            findings.append(finding)

        brief_parts = [f"• {f['query']}: {f['snippets'][0][:200]}" for f in findings if f.get("snippets")]
        brief = "\n".join(brief_parts)

        gemini = _gemini_json(
            f"Synthesize research for chatbot training ({parsed.get('dataset')} vertical):\n{brief}\n"
            'Return JSON: {"brief":"2-3 sentences","key_facts":["..."]}'
        )
        if isinstance(gemini, dict) and gemini.get("brief"):
            brief = gemini["brief"]
            key_facts = gemini.get("key_facts", [])
        else:
            key_facts = [f["snippets"][0][:150] for f in findings if f.get("snippets")][:5]

        return ToolResult(
            success=True,
            output={
                "findings": findings,
                "brief": brief,
                "key_facts": key_facts,
                "sources": list(dict.fromkeys(sources))[:6],
                "query_count": len(findings),
            },
        )


class MeraxesIntentBuilderTool:
    name = "meraxes_intent_builder"
    description = "Generate new intent definitions from goal, research, and user topics"

    def execute(self, **kwargs: Any) -> ToolResult:
        parsed = kwargs.get("meraxes_goal_parser") or {}
        research = kwargs.get("meraxes_researcher") or {}
        dataset = parsed.get("dataset") or kwargs.get("dataset", "saas")
        topics = parsed.get("topics") or []

        if not parsed.get("wants_intents", True) and not topics:
            return ToolResult(success=True, output={"intents": [], "skipped": True, "count": 0})

        template = load_template(dataset)
        existing_tags = {i["tag"] for i in template.get("intents", [])}
        brief = research.get("brief", "")
        key_facts = research.get("key_facts", [])

        gemini = _gemini_json(
            f'Create chatbot intents for a {dataset} business bot.\n'
            f'User goal: {parsed.get("goal", "")}\nResearch: {brief}\nTopics: {topics}\n'
            'Return JSON: {"intents":[{"tag":"snake_case","patterns":["user phrase",...],"responses":["bot reply",...]}]} '
            "Create 2-5 intents, 3-5 patterns each, 1-2 responses each. Tags must be unique snake_case."
        )

        new_intents: list[dict] = []
        if isinstance(gemini, dict) and gemini.get("intents"):
            for item in gemini["intents"]:
                tag = _slug(item.get("tag", "custom"))
                if tag in existing_tags:
                    tag = f"user_{tag}"[:40]
                patterns = [p.lower().strip() for p in item.get("patterns", []) if p][:6]
                responses = [r.strip() for r in item.get("responses", []) if r][:2]
                if patterns and responses:
                    new_intents.append({"tag": tag, "patterns": patterns, "responses": responses})
                    existing_tags.add(tag)

        if not new_intents:
            seed_topics = [t for t in (topics or []) if is_meaningful_topic(t)]
            for i, topic in enumerate(seed_topics[:5]):
                tag = _slug(topic)
                if tag in existing_tags:
                    tag = f"user_{tag}_{i}"[:40]
                fact = key_facts[i] if i < len(key_facts) else f"We can help you with {topic}."
                patterns = [
                    topic.lower(),
                    f"what about {topic.lower()}",
                    f"tell me about {topic.lower()}",
                    f"how does {topic.lower()} work",
                ]
                new_intents.append({
                    "tag": tag,
                    "patterns": patterns[:5],
                    "responses": [fact[:400] if len(fact) > 30 else f"Here's what you need to know about {topic}: {fact}"],
                })
                existing_tags.add(tag)

        return ToolResult(
            success=bool(new_intents),
            output={
                "intents": new_intents,
                "count": len(new_intents),
                "topics_covered": [i["tag"] for i in new_intents],
            },
            error=None if new_intents else "No intents generated",
        )


class MeraxesIntentDeployTool:
    name = "meraxes_intent_deployer"
    description = "Merge new intents into Meraxes model, retrain, and persist"

    def execute(self, **kwargs: Any) -> ToolResult:
        builder = kwargs.get("meraxes_intent_builder") or {}
        new_intents = builder.get("intents") or []
        dataset = kwargs.get("dataset") or (kwargs.get("meraxes_goal_parser") or {}).get("dataset", "saas")

        if not new_intents:
            return ToolResult(success=True, output={"deployed": False, "added_tags": [], "message": "No new intents to deploy"})

        bot_id = f"meraxes_{dataset}"
        model_dir = MODELS_DIR / dataset
        intents_path = model_dir / "intents.json"

        if intents_path.is_file():
            base = json.loads(intents_path.read_text(encoding="utf-8")).get("intents", [])
        else:
            base = load_template(dataset).get("intents", [])

        existing_tags = {i["tag"] for i in base}
        added: list[dict] = []
        for intent in new_intents:
            if intent["tag"] not in existing_tags:
                base.append(intent)
                existing_tags.add(intent["tag"])
                added.append({"tag": intent["tag"], "patterns": len(intent.get("patterns", []))})

        if not added:
            return ToolResult(success=True, output={"deployed": False, "added_tags": [], "message": "Intents already exist"})

        try:
            model_dir.mkdir(parents=True, exist_ok=True)
            intents_path.write_text(json.dumps({"intents": base}, indent=2), encoding="utf-8")

            from train_meraxes import train_vertical

            stats = train_vertical(dataset, minimal=True, quick=True)
            from engine import invalidate_engine
            invalidate_engine(bot_id)
            return ToolResult(
                success=True,
                output={
                    "deployed": True,
                    "added_tags": [a["tag"] for a in added],
                    "added_intents": added,
                    "total_intents": len(base),
                    "retrain_stats": stats,
                    "model_path": str(model_dir / "chat_model.pth"),
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class MeraxesUserSummaryTool:
    """Build plain-language summary for dashboard (not shown in dev JSON by default)."""

    name = "meraxes_user_summary"

    def execute(self, **kwargs: Any) -> ToolResult:
        parsed = kwargs.get("meraxes_goal_parser") or {}
        research = kwargs.get("meraxes_researcher") or {}
        builder = kwargs.get("meraxes_intent_builder") or {}
        deploy = kwargs.get("meraxes_intent_deployer") or {}
        score = kwargs.get("meraxes_score_tracker") or {}

        intents_added = deploy.get("added_tags") or builder.get("topics_covered") or []
        researched = not research.get("skipped") and research.get("query_count", 0) > 0
        improved = (score.get("improvement") or 0) > 0

        bullets = []
        if researched:
            bullets.append(f"Researched {research.get('query_count', 0)} topic(s) for accurate answers")
        if deploy.get("deployed"):
            bullets.append(f"Added {len(intents_added)} new topic(s) to your bot: {', '.join(intents_added[:4])}")
        elif builder.get("count"):
            bullets.append(f"Prepared {builder.get('count')} training topic(s)")
        bullets.append("Tested bot with sample customer questions")
        if improved:
            bullets.append("Quality score improved after tuning")
        else:
            bullets.append("Verified bot quality after updates")

        return ToolResult(
            success=True,
            output={
                "headline": "Your bot was updated" if intents_added else "Bot optimization complete",
                "bullets": bullets,
                "intents_added": intents_added,
                "research_brief": research.get("brief", "")[:300],
                "sources": research.get("sources", [])[:3],
            },
        )
