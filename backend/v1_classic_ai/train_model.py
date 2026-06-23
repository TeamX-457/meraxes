"""Train classifier from a business template. Usage: py train_model.py [business_id]"""
import sys

from dataset_loader import build_training_pairs, load_template, merge_custom_qa
from engine import BotEngine


def main():
    business_id = sys.argv[1] if len(sys.argv) > 1 else "general"
    template = load_template(business_id)
    intents = template["intents"]
    engine = BotEngine("default", business_id, "hybrid", [])
    engine.intents = intents
    stats = engine.train()
    print(f"Trained {business_id}: {stats}")


if __name__ == "__main__":
    main()
