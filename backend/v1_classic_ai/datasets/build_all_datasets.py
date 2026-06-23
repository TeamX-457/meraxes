"""

Regenerate all V1 business template JSON files.



Each vertical has 55–70+ intents × N patterns (default 100).



Run from AImodel folder:

  ml-env\\Scripts\\python.exe v1_classic_ai\\datasets\\build_all_datasets.py

  ml-env\\Scripts\\python.exe v1_classic_ai\\datasets\\build_all_datasets.py --target 120

"""

from __future__ import annotations



import argparse

import json

from pathlib import Path



from pattern_engine import DEFAULT_TARGET, build_dataset, intent

from intent_catalog import CATALOG



DIR = Path(__file__).parent



SUGGESTED = {

    "general": [

        "What are your opening hours?",

        "How can I contact support?",

        "Do you offer refunds?",

        "How much does it cost?",

        "What products do you sell?",

        "How do I create an account?",

        "Do you have a mobile app?",

    ],

    "ecommerce": [

        "Where is my order?",

        "What is your return policy?",

        "Do you ship internationally?",

        "Is this item in stock?",

        "Do you have a discount code?",

        "Can I change my shipping address?",

        "How do I exchange a size?",

    ],

    "saas": [

        "How much does your plan cost?",

        "Is there a free trial?",

        "How do I integrate your API?",

        "Do you offer SSO?",

        "How do I cancel my subscription?",

        "What is your uptime SLA?",

        "How do I export my data?",

    ],

    "finance": [

        "What are your loan interest rates?",

        "How do I open a savings account?",

        "Is my money FDIC insured?",

        "How do I reset my online banking password?",

        "What documents do I need for a mortgage?",

        "How do I dispute a charge?",

        "Where is the nearest branch?",

    ],

    "healthcare": [

        "How do I book an appointment?",

        "Do you accept my insurance?",

        "What are your clinic hours?",

        "How do I get prescription refills?",

        "Is telehealth available?",

        "How do I access test results?",

        "What if I have an emergency?",

    ],

}



META = {

    "general": ("General Business", "Default assistant for any small business website — 55+ intent topics."),

    "ecommerce": ("E-Commerce & Retail", "Online stores and retail — 60+ shopping & order intents."),

    "saas": ("SaaS & Software", "B2B software and subscriptions — 65+ product & API intents."),

    "finance": ("Finance & Banking", "Banks, lenders, and fintech — 60+ banking intents."),

    "healthcare": ("Healthcare & Clinics", "Clinics and telehealth — 60+ patient care intents."),

}





def build_vertical(key: str, target: int) -> dict:

    name, desc = META[key]

    specs = CATALOG[key]()

    built_intents = []

    for spec in specs:

        built_intents.append(

            intent(spec["tag"], spec["seeds"], spec["responses"], target=target)

        )

    return {

        "id": key,

        "name": name,

        "description": desc,

        "suggested_customer_questions": SUGGESTED[key],

        "intents": built_intents,

    }





def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(

        "--target",

        type=int,

        default=100,

        help=f"Patterns per intent (50–200, default 100 for large catalogs)",

    )

    args = parser.parse_args()

    target = min(max(args.target, 50), 200)



    print(f"Building templates: ~{target} patterns × 55–70 intents each...\n")

    for key in CATALOG:

        data = build_vertical(key, target)

        path = DIR / f"{key}.json"

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        n_intents = len(data["intents"])

        n_patterns = sum(len(i["patterns"]) for i in data["intents"])

        per = [len(i["patterns"]) for i in data["intents"]]

        print(

            f"  {key}.json — {n_intents} intents, {n_patterns:,} patterns "

            f"(min={min(per)}, max={max(per)})"

        )

    print("\nDone. Run retrain_all_bots.py or restart V1 to apply.")





if __name__ == "__main__":

    main()

