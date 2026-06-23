"""
Expand seed phrases into 100–200 training patterns per intent.

Designed for sentence-transformer + softmax intent models (MiniLM 384-d):
- More paraphrases per class improves recall on website chat queries
- 12–20 intents × 150 patterns ≈ 1.8k–3k FAQ rows (good for hybrid FAQ + classifier)
"""
from __future__ import annotations

# Default target per intent (user asked 100+; 150 balances quality and train time)
DEFAULT_TARGET = 150
MAX_TARGET = 200

_PREFIXES = (
    "",
    "how do i ",
    "how can i ",
    "how to ",
    "what is ",
    "what are ",
    "what's ",
    "whats ",
    "where is ",
    "where are ",
    "when is ",
    "when can i ",
    "when do i ",
    "can i ",
    "can you ",
    "do you ",
    "does your ",
    "is there ",
    "are there ",
    "i need ",
    "i want ",
    "i would like ",
    "help me ",
    "help with ",
    "question about ",
    "info about ",
    "information on ",
    "information about ",
    "tell me about ",
    "tell me ",
    "explain ",
    "need help with ",
    "assistance with ",
    "support for ",
    "looking for ",
    "asking about ",
    "regarding ",
    "about ",
    "details on ",
    "details about ",
    "learn about ",
    "guide to ",
    "steps for ",
    "process for ",
    "options for ",
)

_SUFFIXES = (
    "",
    " please",
    " help",
    " info",
    " information",
    " details",
    " question",
    " support",
    " options",
    " policy",
    " process",
    " today",
    " now",
    " online",
    " on website",
)

_ALT_QUESTION = (
    "can you help with {s}",
    "could you explain {s}",
    "i have a question about {s}",
    "quick question about {s}",
    "need info on {s}",
    "what do i do about {s}",
    "what should i know about {s}",
    "any info on {s}",
    "clarify {s}",
    "more about {s}",
)


def _norm(s: str) -> str:
    s = " ".join(s.lower().strip().split())
    return s


def expand_patterns(
    seeds: list[str],
    *,
    target: int = DEFAULT_TARGET,
    extra_templates: list[str] | None = None,
) -> list[str]:
    """Grow unique lowercase patterns from seed phrases up to `target` (cap 200)."""
    target = min(max(target, 50), MAX_TARGET)
    out: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        p = _norm(raw)
        if not p or len(p) < 2 or p in seen:
            return
        seen.add(p)
        out.append(p)

    for seed in seeds:
        s = _norm(seed)
        if not s:
            continue
        add(s)
        for pre in _PREFIXES:
            add(f"{pre}{s}")
        for suf in _SUFFIXES:
            if suf:
                add(f"{s}{suf}")
        for pre in _PREFIXES:
            for suf in _SUFFIXES:
                if pre or suf:
                    add(f"{pre}{s}{suf}")
        for tpl in _ALT_QUESTION:
            add(tpl.format(s=s))
        if extra_templates:
            for tpl in extra_templates:
                if "{s}" in tpl:
                    add(tpl.format(s=s))
                else:
                    add(f"{tpl} {s}")

    # Pair seeds for compound queries (e.g. "shipping" + "international")
    if len(out) < target and len(seeds) >= 2:
        for i, a in enumerate(seeds[:12]):
            for b in seeds[i + 1 : i + 8]:
                a, b = _norm(a), _norm(b)
                add(f"{a} and {b}")
                add(f"{a} or {b}")
                add(f"{a} for {b}")

    return out[:target]


def intent(
    tag: str,
    seeds: list[str],
    responses: list[str],
    *,
    target: int = DEFAULT_TARGET,
    extra_templates: list[str] | None = None,
) -> dict:
    return {
        "tag": tag,
        "patterns": expand_patterns(seeds, target=target, extra_templates=extra_templates),
        "responses": responses,
    }


def build_dataset(
    *,
    id: str,
    name: str,
    description: str,
    suggested: list[str],
    intents: list[dict],
    pattern_target: int = DEFAULT_TARGET,
) -> dict:
    built = []
    for spec in intents:
        if "patterns" in spec and len(spec["patterns"]) >= pattern_target:
            built.append(spec)
            continue
        built.append(
            intent(
                spec["tag"],
                spec["seeds"],
                spec["responses"],
                target=pattern_target,
                extra_templates=spec.get("extra_templates"),
            )
        )
    return {
        "id": id,
        "name": name,
        "description": description,
        "suggested_customer_questions": suggested,
        "intents": built,
    }
