"""
Multi-source knowledge for Meraxes agent chat.

Sources: Wikipedia, DuckDuckGo, website FAQ context, Gemini synthesis.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import quote

import httpx

from dataset_loader import load_template
from meraxes_agent.tools.research_tools import _gemini_json

_STOP_WORDS = frozenset({
    "what", "when", "where", "which", "how", "does", "your", "about", "there",
    "this", "that", "with", "from", "have", "they", "will", "would", "could",
    "should", "the", "are", "for", "you", "can", "not", "and", "our", "any",
})


def _extract_search_terms(message: str) -> list[str]:
    msg = message.strip()
    terms = [msg[:120]]
    clean = _clean_wiki_query(msg)
    if clean.lower() != msg.lower()[: len(clean)].lower():
        terms.append(clean[:100])
    for chunk in re.split(r"\b(?:about|on|for|regarding)\b", msg, flags=re.I):
        chunk = chunk.strip(" ?.")
        if len(chunk) >= 4 and chunk.lower() not in {t.lower() for t in terms}:
            terms.append(chunk[:100])
    return terms[:4]


def _clean_wiki_query(query: str) -> str:
    q = query.strip().rstrip("?.!")
    for prefix in ("what is ", "what are ", "who is ", "tell me about ", "explain ", "define "):
        if q.lower().startswith(prefix):
            q = q[len(prefix):].strip()
            break
    return q or query.strip()


def _title_variants(query: str) -> list[str]:
    clean = _clean_wiki_query(query)
    variants = [clean, clean.replace(" ", "_")]
    if "ecommerce" in clean.lower() or "e commerce" in clean.lower():
        variants.extend(["E-commerce", "Electronic commerce"])
    if "saas" in clean.lower():
        variants.extend(["Software as a service", "SaaS"])
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _wikipedia_summary(title: str) -> dict | None:
    try:
        r = httpx.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
            timeout=12,
            headers={"User-Agent": "MeraxesBot/1.0"},
        )
        if r.status_code == 200:
            d = r.json()
            extract = d.get("extract", "")
            if extract and "may refer to" not in extract.lower()[:80]:
                return {
                    "source": "wikipedia",
                    "title": d.get("title", title),
                    "text": extract[:700],
                    "url": d.get("content_urls", {}).get("desktop", {}).get("page"),
                }
    except Exception:
        pass
    return None


def _wikipedia_search(query: str) -> dict | None:
    clean = _clean_wiki_query(query)
    for title in _title_variants(clean):
        hit = _wikipedia_summary(title)
        if hit:
            return hit
    try:
        r = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": clean, "limit": 1, "format": "json"},
            timeout=10,
            headers={"User-Agent": "MeraxesBot/1.0"},
        )
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1 and data[1]:
                return _wikipedia_summary(data[1][0])
    except Exception:
        pass
    return None


def _duckduckgo(query: str) -> dict | None:
    try:
        r = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            text = d.get("AbstractText") or ""
            if text:
                return {"source": "duckduckgo", "title": query, "text": text[:600], "url": d.get("AbstractURL")}
            related = d.get("RelatedTopics") or []
            snippets = []
            for item in related[:4]:
                if isinstance(item, dict) and item.get("Text"):
                    snippets.append(item["Text"][:220])
            if snippets:
                return {"source": "duckduckgo", "title": query, "text": " ".join(snippets)[:600], "url": None}
    except Exception:
        pass
    return None


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in _STOP_WORDS}


def _website_faq_hits(dataset: str, message: str) -> list[dict]:
    """Match user message to actual FAQ/intent answers — not loose keyword overlap."""
    try:
        template = load_template(dataset)
    except Exception:
        return []

    msg_kw = _keywords(message)
    if not msg_kw:
        return []

    hits: list[tuple[int, dict]] = []
    for intent in template.get("intents", []):
        patterns = intent.get("patterns") or []
        responses = intent.get("responses") or []
        if not responses:
            continue
        pat_kw: set[str] = set()
        for p in patterns[:20]:
            pat_kw |= _keywords(str(p))
        overlap = len(msg_kw & pat_kw)
        if overlap >= 2 or (overlap >= 1 and len(msg_kw) <= 2):
            hits.append((overlap, {
                "source": "website_faq",
                "title": intent.get("tag", "faq"),
                "text": responses[0][:400],
                "url": None,
            }))

    hits.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in hits[:2]]


def synthesize_local_answer(message: str, hits: list[dict]) -> str:
    """Build a conversational answer from web research without an LLM."""
    web = [h for h in hits if h.get("source") in ("wikipedia", "duckduckgo", "research_agent")]
    faq = [h for h in hits if h.get("source") == "website_faq"]

    if web:
        primary = web[0]
        title = primary.get("title", "")
        body = primary.get("text", "").strip()
        if body:
            if title and title.lower() not in message.lower():
                answer = f"{title}: {body}"
            else:
                answer = body
            if len(web) > 1 and web[1].get("text"):
                extra = web[1]["text"][:200].strip()
                if extra and extra not in body:
                    answer += f"\n\nAlso: {extra}"
            return answer[:1200]

    if faq:
        return faq[0].get("text", "")

    return ""


def gather_knowledge(
    message: str,
    dataset: str = "saas",
    *,
    enable_research: bool = True,
    fast: bool = False,
) -> dict[str, Any]:
    """Collect facts from multiple sources. fast=True uses parallel lookups with short timeouts."""
    if not enable_research:
        return {
            "hits": [],
            "sources": [],
            "source_names": [],
            "brief": "",
            "synthesized_answer": "",
            "citations": [],
        }

    terms = _extract_search_terms(message)[:2 if fast else 4]
    hits: list[dict] = []
    urls: list[str] = []
    timeout = 6 if fast else 12

    def _fetch_wiki(term: str) -> dict | None:
        return _wikipedia_search(term)

    def _fetch_ddg(term: str) -> dict | None:
        return _duckduckgo(term)

    with ThreadPoolExecutor(max_workers=min(6, len(terms) * 2) or 2) as pool:
        futures = []
        for term in terms:
            futures.append(pool.submit(_fetch_wiki, term))
            futures.append(pool.submit(_fetch_ddg, term))
        try:
            for fut in as_completed(futures, timeout=timeout):
                try:
                    result = fut.result()
                except Exception:
                    continue
                if result and result.get("text") and not any(
                    h.get("text") == result["text"] for h in hits
                ):
                    hits.append(result)
                    if result.get("url"):
                        urls.append(result["url"])
        except Exception:
            pass

    if not fast and len(message) < 100:
        for faq in _website_faq_hits(dataset, message):
            hits.append(faq)

    combined = "\n\n".join(
        f"[{h['source']}] {h.get('title', '')}: {h['text']}"
        for h in hits if h.get("text")
    )

    synthesized = ""
    citations: list[str] = []
    if not fast and (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        gemini = _gemini_json(
            f"You are a helpful website assistant. User asked: {message}\n\n"
            f"Sources:\n{combined[:3500]}\n\n"
            'Return JSON: {"answer":"direct conversational answer in 2-5 sentences using the sources",'
            '"citations":["source names used"]}'
        )
        if isinstance(gemini, dict) and gemini.get("answer"):
            synthesized = gemini["answer"]
            citations = gemini.get("citations") or []

    if not synthesized:
        synthesized = synthesize_local_answer(message, hits)

    return {
        "hits": hits,
        "sources": list(dict.fromkeys(urls))[:8],
        "source_names": list(dict.fromkeys(h.get("source", "") for h in hits if h.get("source"))),
        "brief": combined[:2500],
        "synthesized_answer": synthesized,
        "citations": citations,
    }
