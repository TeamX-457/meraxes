# Nova / Meraxes — Track 2 Agent Optimizer

**Product:** Meraxes v1 (trainable embeddable chatbots)  
**Agent:** `meraxes_v1_quality_lab`  
**Track:** Optimize (Existing Agents)

The Track 2 agent lives in **`v1_classic_ai/meraxes_agent/`** and optimizes **Meraxes v1** models only.  
**v2_llm_agent** (Nova chatbot) is unchanged.

## Architecture

```
Goal → Train Meraxes model → Benchmark (existing datasets)
     → Run v1 BotEngine → Score → Detect failures
     → Retrain with custom Q&A → Re-run → Measure improvement
```

## Trained models location

```
v1_classic_ai/models/meraxes/
├── saas/chat_model.pth
├── ecommerce/chat_model.pth
├── general/chat_model.pth
├── healthcare/chat_model.pth
├── finance/chat_model.pth
└── manifest.json
```

## Commands

```powershell
# Train all Meraxes models (uses existing datasets)
cd learn/AImodel/v1_classic_ai
python train_meraxes.py --all --quick

# Meraxes v1 chatbot platform (port 8005)
uvicorn main:app --port 8005

# Agent optimizer API (port 8030)
uvicorn meraxes_agent.main:app --port 8030
```

## API

```http
POST /agents/optimize
POST /agents/train?dataset=saas&quick=true
POST /agents/train-all?quick=true
GET  /health
```

## Data usage

- **No new datasets downloaded** — uses `v1_classic_ai/datasets/*.json`
- **One-time ~90MB download:** `all-MiniLM-L6-v2` embedding model from HuggingFace (first train/run only)
- Training is local PyTorch on CPU — no cloud API costs

## v2 unchanged

`v2_llm_agent/` remains the Nova LLM chatbot — not modified by this agent.
