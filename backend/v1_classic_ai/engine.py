"""Chat engines: intent classifier, FAQ matcher, and hybrid."""
import json
import pickle
import random
import re
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from dataset_loader import (
    build_training_pairs,
    cap_intents_for_training,
    flatten_faq,
    load_bot_dataset,
    load_template,
    merge_custom_qa,
    save_bot_dataset,
)
from config import EMBEDDER_MODEL, MERAXES_MODELS_DIR

try:
    from vector_store import add_memory, search_memory
except Exception:  # vector store optional — degrade gracefully
    def add_memory(text: str, bot_id: str = "global") -> None:  # type: ignore
        return None

    def search_memory(query: str, k: int = 3, bot_id: str = "global") -> list[str]:  # type: ignore
        return []

BASE_DIR = Path(__file__).resolve().parent
MODEL_TYPES = {
    "intent": {
        "id": "intent",
        "name": "Intent Classifier",
        "description": "Fast neural model trained on your Q&A patterns. Best for structured support flows.",
        "embed_snippet": "intent",
    },
    "faq": {
        "id": "faq",
        "name": "FAQ Matcher",
        "description": "Semantic similarity against your question list. Great when customers ask in many ways.",
        "embed_snippet": "faq",
    },
    "hybrid": {
        "id": "hybrid",
        "name": "Hybrid (Recommended)",
        "description": "FAQ match first, then intent classifier. Best balance for website chatbots.",
        "embed_snippet": "hybrid",
    },
}


def clean_text(text: str) -> str:
    text = text.lower()
    return re.sub(r"[^a-z0-9\s]", "", text)


class ChatModel(nn.Module):
    def __init__(self, input_size: int, hidden_size: int, output_size: int):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.35)
        self.fc2 = nn.Linear(hidden_size, hidden_size // 2)
        self.relu2 = nn.ReLU()
        self.dropout2 = nn.Dropout(0.25)
        self.fc3 = nn.Linear(hidden_size // 2, output_size)

    def forward(self, x):
        x = self.dropout(self.relu(self.fc1(x)))
        x = self.dropout2(self.relu2(self.fc2(x)))
        return self.fc3(x)


class BotEngine:
    def __init__(self, bot_id: str, business_id: str, model_type: str, custom_qa: list):
        self.bot_id = bot_id
        self.business_id = business_id
        self.model_type = model_type if model_type in MODEL_TYPES else "hybrid"
        self._embedder = None
        self._faq_embeddings = None
        self._faq_index_map = None

        if bot_id.startswith("meraxes_"):
            saved_intents = self._model_dir() / "intents.json"
            if saved_intents.is_file():
                with open(saved_intents, encoding="utf-8") as f:
                    data = json.load(f)
                self.intents = merge_custom_qa(data.get("intents", []), custom_qa)
            else:
                template = load_template(business_id)
                self.intents = merge_custom_qa(cap_intents_for_training(template["intents"], 8, 5), custom_qa)
        else:
            template = load_template(business_id)
            self.intents = merge_custom_qa(template["intents"], custom_qa)

        self.faq = flatten_faq(self.intents)
        self._load_classifier()

    @property
    def embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(EMBEDDER_MODEL)
        return self._embedder

    def _model_dir(self) -> Path:
        """Meraxes models live under models/meraxes/{business_id}/ for agent bots."""
        if self.bot_id.startswith("meraxes_"):
            d = BASE_DIR / MERAXES_MODELS_DIR / self.business_id
            d.mkdir(parents=True, exist_ok=True)
            return d
        d = BASE_DIR / "bots" / self.bot_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _bot_paths(self):
        d = self._model_dir()
        return d / "chat_model.pth", d / "labels.pkl", d / "intents.json"

    def _load_classifier(self):
        model_path, labels_path, intents_path = self._bot_paths()
        if not labels_path.exists():
            # Fallback legacy root model
            legacy_labels = BASE_DIR / "labels.pkl"
            if legacy_labels.exists():
                labels_path = legacy_labels
                model_path = BASE_DIR / "chat_model.pth"
            else:
                self.label_names = sorted({i["tag"] for i in self.intents})
                self.model = ChatModel(384, 128, max(len(self.label_names), 1))
                self.model.eval()
                self._refresh_faq_index()
                return

        with open(labels_path, "rb") as f:
            self.label_names = pickle.load(f)
        self.model = ChatModel(384, 128, len(self.label_names))
        if model_path.exists():
            try:
                try:
                    state = torch.load(model_path, map_location="cpu", weights_only=True)
                except TypeError:
                    state = torch.load(model_path, map_location="cpu")
                self.model.load_state_dict(state)
            except Exception:
                pass
        self.model.eval()
        self._refresh_faq_index()

    def _refresh_faq_index(self):
        if not self.faq:
            self._faq_embeddings = None
            return
        # Cap FAQ index to keep encoding + inference fast on CPU.
        # Meraxes quick models stay small; regular bots cap higher for coverage.
        cap = 300 if self.bot_id.startswith("meraxes_") else 700
        faq_subset = self.faq[:cap]
        questions = [clean_text(item["question"]) for item in faq_subset]
        self._faq_embeddings = self.embedder.encode(questions, convert_to_numpy=True, show_progress_bar=False)
        self._faq_index_map = faq_subset

    def train(self) -> dict:
        sentences, labels = build_training_pairs(self.intents)
        if len(sentences) < 2:
            raise ValueError("Need at least 2 training patterns")

        sentences = [clean_text(s) for s in sentences]
        label_names = sorted(set(labels))
        label_to_index = {l: i for i, l in enumerate(label_names)}
        y = np.array([label_to_index[l] for l in labels])

        X = self.embedder.encode(sentences)
        X = torch.tensor(np.array(X), dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.long)

        model = ChatModel(X.shape[1], 128, len(label_names))
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.008)

        n = len(sentences)
        if n > 8000:
            epochs = 900
        elif n > 4000:
            epochs = 750
        elif n > 1500:
            epochs = 600
        elif n > 500:
            epochs = 500
        else:
            epochs = 350
        for epoch in range(epochs):
            out = model(X)
            loss = criterion(out, y_t)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        bot_dir = self._model_dir()
        torch.save(model.state_dict(), bot_dir / "chat_model.pth")
        with open(bot_dir / "labels.pkl", "wb") as f:
            pickle.dump(label_names, f)
        with open(bot_dir / "intents.json", "w", encoding="utf-8") as f:
            json.dump({"intents": self.intents}, f, indent=2)

        save_bot_dataset(self.bot_id, {
            "bot_id": self.bot_id,
            "business_id": self.business_id,
            "intents": self.intents,
        })

        self.label_names = label_names
        self.model = model
        self.model.eval()
        self._refresh_faq_index()
        return {"patterns": len(sentences), "intents": len(label_names), "epochs": epochs}

    def _faq_threshold(self) -> float:
        n = len(self.faq) if self.faq else 0
        if n > 8000:
            return 0.58
        if n > 4000:
            return 0.62
        if n > 1500:
            return 0.65
        if n > 400:
            return 0.68
        return 0.72

    def _faq_reply(self, text: str, threshold: float | None = None) -> str | None:
        if threshold is None:
            threshold = self._faq_threshold()
        if self._faq_embeddings is None:
            return None
        q = clean_text(text)
        vec = self.embedder.encode([q], convert_to_numpy=True)
        sims = np.dot(self._faq_embeddings, vec.T).flatten() / (
            np.linalg.norm(self._faq_embeddings, axis=1) * np.linalg.norm(vec) + 1e-9
        )
        best = int(np.argmax(sims))
        if sims[best] >= threshold:
            faq_list = getattr(self, "_faq_index_map", None) or self.faq
            return faq_list[best]["answer"]
        return None

    def _intent_reply(self, text: str) -> tuple[str, float, bool]:
        memory = search_memory(text, bot_id=self.bot_id)
        context = " ".join(memory + [text])
        X = self.embedder.encode([context])
        X = torch.tensor(X, dtype=torch.float32)
        output = self.model(X)
        probs = torch.softmax(output, dim=1)
        confidence, pred = torch.max(probs, dim=1)
        conf = confidence.item()

        # Top-2 margin: ambiguous queries → let FAQ or fallback handle
        top2 = torch.topk(probs, k=min(2, probs.shape[1]), dim=1)
        margin = (top2.values[0][0] - top2.values[0][1]).item() if top2.values.shape[1] > 1 else 1.0
        ambiguous = margin < 0.12 and conf < 0.72

        intent_tag = self.label_names[pred.item()]
        for item in self.intents:
            if item["tag"] == intent_tag:
                return random.choice(item["responses"]), conf, ambiguous
        return "I don't understand that yet.", conf, True

    def reply(self, user_id: str, text: str, get_user_name, save_user_name) -> dict:
        raw = text.strip()
        cleaned = clean_text(raw)

        def _rule_match(tag: str, phrases: tuple[str, ...]) -> dict | None:
            # Word-boundary aware: avoid "sup" matching "support", "hi" matching "this".
            words = cleaned.split()
            wordset = set(words)
            short = len(words) <= 4
            matched = False
            for p in phrases:
                if cleaned == p:
                    matched = True
                    break
                if " " in p:
                    if cleaned.startswith(p + " ") or cleaned.endswith(" " + p) or f" {p} " in f" {cleaned} ":
                        matched = True
                        break
                elif p in wordset and short:
                    # single-word phrase must be a standalone word in a short message
                    matched = True
                    break
            if not matched:
                return None
            for intent in self.intents:
                if intent["tag"] == tag:
                    msg = random.choice(intent["responses"])
                    name = get_user_name(user_id)
                    msg = msg.replace("{name}", f" {name}" if name else "")
                    return {"response": msg, "source": tag}

        greetings = (
            "hello", "hi", "hey", "hiya", "howdy", "good morning", "good afternoon",
            "good evening", "greetings", "yo", "sup",
        )
        hit = _rule_match("greeting", greetings)
        if hit:
            return hit

        status_phrases = (
            "how are you", "how r u", "hows it going", "how is it going",
            "you ok", "are you ok", "how you doing", "how have you been",
        )
        hit = _rule_match("status", status_phrases)
        if hit:
            return hit

        thanks_phrases = (
            "thank you", "thanks", "thx", "much appreciated", "appreciate it",
            "cheers", "that helps", "helpful",
        )
        if any(cleaned == p or cleaned.startswith(p) for p in thanks_phrases):
            hit = _rule_match("thanks", thanks_phrases)
            if hit:
                return hit

        if "my name is" in cleaned or "call me" in cleaned:
            for phrase in ("my name is", "call me", "i am called"):
                if phrase in cleaned:
                    name = cleaned.split(phrase, 1)[-1].strip().title()
                    if name:
                        save_user_name(user_id, name)
                        return {"response": f"Nice to meet you, {name}!", "source": "rule"}

        user_name = get_user_name(user_id)
        response = None
        source = self.model_type

        if self.model_type in ("faq", "hybrid"):
            response = self._faq_reply(cleaned)
            if response:
                source = "faq"

        if response is None and self.model_type in ("intent", "hybrid"):
            response, conf, ambiguous = self._intent_reply(cleaned)
            source = "intent"
            if ambiguous or conf < 0.52:
                faq_retry = self._faq_reply(cleaned, threshold=self._faq_threshold() - 0.03)
                if faq_retry:
                    response = faq_retry
                    source = "faq+intent"
                elif conf < 0.48:
                    response = (
                        "I'm not sure about that. Try rephrasing, or ask about "
                        "hours, orders, billing, or contact support."
                    )
                    source = "fallback"

        if response:
            response = response.replace("{name}", f" {user_name}" if user_name else "")

        try:
            add_memory(cleaned, bot_id=self.bot_id)
        except Exception:
            pass
        return {"response": response, "source": source}


_engines: dict[str, BotEngine] = {}


def get_engine(bot: dict) -> BotEngine:
    bid = bot["bot_id"]
    if bid not in _engines:
        _engines[bid] = BotEngine(
            bid, bot["business_id"], bot["model_type"], bot.get("custom_qa", [])
        )
    return _engines[bid]


def invalidate_engine(bot_id: str) -> None:
    _engines.pop(bot_id, None)
