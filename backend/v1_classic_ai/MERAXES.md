# Meraxes v1 — Trainable Chatbot Platform

**Product name:** Meraxes  
**Location:** `learn/AImodel/v1_classic_ai/`  
**v2 chatbot (Nova):** unchanged in `v2_llm_agent/`

## Trained models (already in repo after training)

```
models/meraxes/
├── general/chat_model.pth
├── saas/chat_model.pth
├── ecommerce/chat_model.pth
└── manifest.json
```

## Train models (uses existing datasets — no new dataset download)

```powershell
cd learn\AImodel\v1_classic_ai
..\ml-env\Scripts\activate

# Fastest (~2-5 min per vertical, recommended)
python train_meraxes.py saas --minimal
python train_meraxes.py --all --minimal

# Higher accuracy (slower on CPU — can take 30+ min)
python train_meraxes.py saas --quick
```

## Run Meraxes

| Service | Command | Port |
|---------|---------|------|
| Meraxes v1 platform | `start-meraxes.bat` or `uvicorn main:app --port 8005` | 8005 |
| Agent optimizer (Track 2) | `start-meraxes-agent.bat` or `uvicorn meraxes_agent.main:app --port 8030` | 8030 |

## Agent optimizer API

```http
POST http://127.0.0.1:8030/agents/optimize
{
  "goal": "Improve Meraxes SaaS bot intent accuracy",
  "dataset": "saas",
  "test_case_limit": 4,
  "minimal_train": true
}
```

Pipeline: **train → benchmark → run BotEngine → score → detect failures → retrain with Q&A → re-run → measure improvement**

## Data / download note

| Item | Size | Required? |
|------|------|-----------|
| Existing JSON datasets (`datasets/*.json`) | Already local | Yes |
| `all-MiniLM-L6-v2` embedder (HuggingFace) | ~90 MB one-time | Yes, first train/run only |
| New external datasets | — | **Not needed** |

**No large dataset downloads required.** Only the ~90MB sentence-transformer model downloads once on first use.
