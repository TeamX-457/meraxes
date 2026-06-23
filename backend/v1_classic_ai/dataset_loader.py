"""Load business templates and bot-specific datasets."""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATASETS_DIR = BASE_DIR / "datasets"
BOTS_DIR = BASE_DIR / "bots"


def list_business_templates() -> list[dict]:
    templates = []
    for path in sorted(DATASETS_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        templates.append({
            "id": data["id"],
            "name": data["name"],
            "description": data.get("description", ""),
            "suggested_customer_questions": data.get("suggested_customer_questions", []),
            "intent_count": len(data.get("intents", [])),
        })
    return templates


def load_template(template_id: str) -> dict:
    path = DATASETS_DIR / f"{template_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown business template: {template_id}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_bot_dataset(bot_id: str) -> dict | None:
    path = BOTS_DIR / f"{bot_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_bot_dataset(bot_id: str, data: dict) -> None:
    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = BOTS_DIR / f"{bot_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def build_training_pairs(intents: list[dict]) -> tuple[list[str], list[str]]:
    """Expand intents into (sentence, label) pairs."""
    sentences, labels = [], []
    for intent in intents:
        tag = intent["tag"]
        for pattern in intent.get("patterns", []):
            sentences.append(pattern)
            labels.append(tag)
    return sentences, labels


def cap_intents_for_training(intents: list[dict], max_intents: int = 15, max_patterns: int = 8) -> list[dict]:
    """Reduce dataset size for fast CPU training — uses existing data only."""
    capped = []
    for intent in intents[:max_intents]:
        capped.append({
            **intent,
            "patterns": intent.get("patterns", [])[:max_patterns],
            "responses": intent.get("responses", [])[:3],
        })
    return capped


def flatten_faq(intents: list[dict]) -> list[dict]:
    """FAQ entries for semantic matching: one row per pattern."""
    faq = []
    for intent in intents:
        for pattern in intent.get("patterns", []):
            for response in intent.get("responses", []):
                faq.append({
                    "question": pattern,
                    "answer": response,
                    "tag": intent["tag"],
                })
    return faq


def merge_custom_qa(intents: list[dict], custom_qa: list[dict]) -> list[dict]:
    """Append user-defined Q&A as intents."""
    merged = list(intents)
    for i, item in enumerate(custom_qa):
        q = item.get("question", "").strip()
        a = item.get("answer", "").strip()
        if not q or not a:
            continue
        merged.append({
            "tag": f"custom_{i}",
            "patterns": [q.lower()],
            "responses": [a],
        })
    return merged
