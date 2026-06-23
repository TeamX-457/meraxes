"""Retrain every bot from latest business templates (run after build_all_datasets.py)."""
from database import init_db, list_bots
from dataset_loader import load_template, merge_custom_qa
from engine import get_engine, invalidate_engine

init_db()
for bot in list_bots():
    print(f"Training {bot['name']} ({bot['business_id']})...")
    invalidate_engine(bot["bot_id"])
    engine = get_engine(bot)
    engine.intents = merge_custom_qa(
        load_template(bot["business_id"])["intents"],
        bot.get("custom_qa", []),
    )
    stats = engine.train()
    print(f"  -> {stats}")
