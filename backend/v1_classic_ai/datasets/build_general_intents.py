"""Deprecated — use build_all_datasets.py for all templates."""
from build_all_datasets import general_dataset, main as build_all_main
from pattern_engine import DEFAULT_TARGET
from pathlib import Path
import json

OUT = Path(__file__).parent / "general.json"


def main() -> None:
    data = general_dataset(DEFAULT_TARGET)
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} — run build_all_datasets.py to refresh every template.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        build_all_main()
    else:
        main()
