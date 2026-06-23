"""
Meraxes model trainer — trains one model per business vertical.

Uses existing datasets only (no new downloads except ~90MB embedder on first run).

Usage:
    python train_meraxes.py              # train all verticals
    python train_meraxes.py saas       # train one vertical
    python train_meraxes.py --quick    # fewer epochs (faster, lower accuracy)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from dataset_loader import cap_intents_for_training, list_business_templates, load_template
from engine import BotEngine, invalidate_engine

MODELS_ROOT = BASE_DIR / "models" / "meraxes"
MANIFEST_PATH = MODELS_ROOT / "manifest.json"


def _cap_intents_for_training(intents: list[dict], max_intents: int = 15, max_patterns: int = 8) -> list[dict]:
    return cap_intents_for_training(intents, max_intents, max_patterns)


def train_vertical(business_id: str, quick: bool = False, minimal: bool = False) -> dict:
    bot_id = f"meraxes_{business_id}"
    template = load_template(business_id)
    engine = BotEngine(bot_id, business_id, "hybrid", [])

    saved_intents_path = MODELS_ROOT / business_id / "intents.json"
    if saved_intents_path.is_file():
        saved = json.loads(saved_intents_path.read_text(encoding="utf-8"))
        engine.intents = saved.get("intents", template["intents"])
    elif minimal:
        engine.intents = _cap_intents_for_training(template["intents"], max_intents=8, max_patterns=5)
    elif quick:
        engine.intents = _cap_intents_for_training(template["intents"], max_intents=15, max_patterns=8)
    else:
        engine.intents = template["intents"]

    if quick or minimal:
        def quick_train():
            from dataset_loader import build_training_pairs
            import numpy as np
            import pickle
            import torch
            import torch.nn as nn
            from engine import ChatModel, clean_text

            sentences, labels = build_training_pairs(engine.intents)
            if len(sentences) < 2:
                raise ValueError("Need at least 2 training patterns")

            sentences = [clean_text(s) for s in sentences]
            label_names = sorted(set(labels))
            label_to_index = {l: i for i, l in enumerate(label_names)}
            y = np.array([label_to_index[l] for l in labels])

            print(f"  Encoding {len(sentences)} patterns for {len(label_names)} intents...")
            X = engine.embedder.encode(sentences, show_progress_bar=False)
            X = torch.tensor(np.array(X), dtype=torch.float32)
            y_t = torch.tensor(y, dtype=torch.long)
            model = ChatModel(X.shape[1], 128, len(label_names))
            criterion = nn.CrossEntropyLoss()
            optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
            epochs = 30 if minimal else 60
            for _ in range(epochs):
                out = model(X)
                loss = criterion(out, y_t)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            bot_dir = engine._model_dir()
            torch.save(model.state_dict(), bot_dir / "chat_model.pth")
            with open(bot_dir / "labels.pkl", "wb") as f:
                pickle.dump(label_names, f)
            with open(bot_dir / "intents.json", "w", encoding="utf-8") as f:
                json.dump({"intents": engine.intents}, f, indent=2)

            engine.label_names = label_names
            engine.model = model
            engine.model.eval()
            engine._refresh_faq_index()
            return {
                "patterns": len(sentences),
                "intents": len(label_names),
                "epochs": epochs,
                "mode": "minimal" if minimal else "quick",
            }

        stats = quick_train()
    else:
        stats = engine.train()

    invalidate_engine(bot_id)
    stats["business_id"] = business_id
    stats["bot_id"] = bot_id
    stats["model_path"] = str(engine._model_dir() / "chat_model.pth")
    return stats


def train_all(quick: bool = False, minimal: bool = False) -> dict:
    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    results = {}
    for template in list_business_templates():
        bid = template["id"]
        print(f"Training Meraxes model: {bid}...")
        try:
            results[bid] = train_vertical(bid, quick=quick, minimal=minimal)
            print(f"  OK: {results[bid]}")
        except Exception as exc:
            results[bid] = {"error": str(exc)}
            print(f"  FAILED: {exc}")

    manifest = {
        "product": "Meraxes",
        "models": results,
        "embedder": "all-MiniLM-L6-v2",
        "note": "Trained from existing v1_classic_ai/datasets — no external dataset download",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return results


def main():
    parser = argparse.ArgumentParser(description="Train Meraxes v1 models")
    parser.add_argument("business_id", nargs="?", help="Business vertical (saas, general, etc.)")
    parser.add_argument("--quick", action="store_true", help="Fast training with capped intents")
    parser.add_argument("--minimal", action="store_true", help="Fastest demo training (~1-2 min per vertical)")
    parser.add_argument("--all", action="store_true", help="Train all verticals")
    args = parser.parse_args()

    if args.all or not args.business_id:
        train_all(quick=args.quick, minimal=args.minimal)
    else:
        stats = train_vertical(args.business_id, quick=args.quick, minimal=args.minimal)
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
