# Meraxes — AI Backend

The Python backend for the Meraxes platform. It bundles **four FastAPI services** that together provide trainable embeddable chatbots, an LLM chat agent with memory and image generation, a multi-provider LLM gateway, and an autonomous optimizer agent.

This document is the single source of truth for running, configuring, extending, and deploying the backend. If you only read one section, read [Quick Start](#3-quick-start).

> **Repository note:** the entire Python backend lives under the `backend/` folder of the `TeamX-457/meraxes` repo. The web frontend lives in sibling folders/branches. All paths in this document are **relative to `backend/`** unless stated otherwise.

---

## Table of contents

1. [What this is](#1-what-this-is)
2. [Architecture](#2-architecture)
3. [Quick start](#3-quick-start)
4. [Configuration & secrets](#4-configuration--secrets)
5. [Service reference](#5-service-reference)
   - [5.1 Meraxes v1 — Chatbot Platform (`:8005`)](#51-meraxes-v1--chatbot-platform-8005)
   - [5.2 Meraxes Agent — Quality Lab / Track 2 (`:8030` or mounted)](#52-meraxes-agent--quality-lab-track-2-8030-or-mounted)
   - [5.3 Nova v2 — LLM Agent (`:8006`)](#53-nova-v2--llm-agent-8006)
   - [5.4 Multi-LLM Router (`:8020`)](#54-multi-llm-router-8020)
   - [5.5 agent_platform (compatibility shim)](#55-agent_platform-compatibility-shim)
6. [Core concepts](#6-core-concepts)
7. [Training guide](#7-training-guide)
8. [Data, models & databases](#8-data-models--databases)
9. [Deployment](#9-deployment)
10. [Troubleshooting](#10-troubleshooting)
11. [Contributing & dev workflow](#11-contributing--dev-workflow)
12. [Security](#12-security)

---

## 1. What this is

Meraxes is two generations of chatbot tech plus the infrastructure to run them:

| Generation | Name | What it does | How it answers |
|-----------|------|--------------|----------------|
| **v1** | **Meraxes** | Trainable, embeddable website chatbots. Pick a business vertical (SaaS, e‑commerce, healthcare, finance, general), train a small neural intent model on Q&A, and drop a `<script>` widget onto any site. | Local PyTorch intent classifier + semantic FAQ matcher. **No API keys, no cloud.** |
| **v2** | **Nova** | A full LLM chat agent with long‑term memory, conversation history, and image generation. | Calls real LLMs (OpenAI/Groq/Gemini/OpenRouter) or local Ollama, with automatic fallback. |

Two supporting services tie them together:

- **Multi‑LLM Router** — one OpenAI‑compatible endpoint that routes/falls back across six providers, with caching, rate limiting and usage tracking. Nova uses it internally; you can also point Cursor/Cline/any OpenAI client at it.
- **Meraxes Agent (Quality Lab)** — an autonomous "Track 2" optimizer that trains a v1 model, benchmarks it, finds failing intents, researches + adds new Q&A, retrains, and measures the improvement.

There's also a **silent training loop**: when Nova (v2) answers via a cloud LLM, it quietly turns those Q&A pairs into v1 intents and into an Ollama fine‑tune export — so the cheap local v1 bot keeps getting smarter from the expensive v2 traffic.

---

## 2. Architecture

```
                              ┌───────────────────────────────────────────┐
                              │  Web frontend (other repo folders/branches)│
                              └───────────────┬───────────────────────────┘
                                              │ HTTP / embed <script>
        ┌─────────────────────────────────────┼──────────────────────────────────┐
        │                                     │                                   │
┌───────▼────────┐   ┌────────────────┐  ┌────▼──────────────┐   ┌────────────────▼─────┐
│ Meraxes v1      │   │ Meraxes Agent  │  │ Nova v2            │   │ Multi-LLM Router      │
│ :8005           │   │ :8030 (or      │  │ :8006              │   │ :8020                 │
│ chatbot platform│   │  mounted on    │  │ LLM chat + memory  │   │ OpenAI-compatible     │
│ + embed widget  │   │  :8005)        │  │ + image gen        │   │ gateway + cache       │
└───────┬─────────┘   └───────┬────────┘  └────┬───────────────┘   └────────┬──────────────┘
        │                     │                │  embedded router          │
        │ PyTorch intent      │ trains/benchmk │  (in-process) ────────────┘
        │ + FAISS FAQ         │ v1 models      │
        ▼                     ▼                ▼
   SQLite + .pth models   models/meraxes/   SQLite + FAISS memory
                                              │ silent training
                                              └──────────► writes new v1 intents + Ollama export
```

**Ports at a glance**

| Service | Default port | Entry point | Start script |
|---------|--------------|-------------|--------------|
| Meraxes v1 platform | `8005` | `v1_classic_ai/main.py` | `v1_classic_ai/start-v1.bat` / `start-meraxes.bat` |
| Meraxes Agent (standalone) | `8030` | `v1_classic_ai/meraxes_agent/main.py` | `v1_classic_ai/start-meraxes-agent.bat` |
| Nova v2 | `8006` | `v2_llm_agent/main.py` | `v2_llm_agent/start-v2.bat` / `start-v2-only.bat` |
| Multi‑LLM Router | `8020` | `llm_router/main.py` | `llm_router/start-router.bat` |

> The Meraxes Agent routes are **also mounted on the v1 app**, so running `:8005` alone gives you both the chatbot platform and the optimizer agent. Port `8030` is only needed if you want the agent on its own process.

**Repository layout**

```
backend/
├── README.md                  ← this file
├── requirements.txt           ← shared ML deps (torch, fastapi, sentence-transformers…)
├── run-all.bat                ← launches v1 + v2 + router in 3 windows
│
├── v1_classic_ai/             ← Meraxes v1 (chatbot platform)
│   ├── main.py                ← FastAPI app (:8005)
│   ├── engine.py              ← BotEngine: intent / faq / hybrid models
│   ├── dataset_loader.py      ← business templates + training-pair builder
│   ├── database.py            ← SQLite (bots, messages, users)
│   ├── vector_store.py        ← FAISS per-bot memory
│   ├── train_meraxes.py       ← CLI: train vertical models
│   ├── datasets/*.json        ← saas / ecommerce / healthcare / finance / general
│   ├── models/meraxes/        ← trained vertical models + manifest.json
│   ├── bots/                  ← per-bot trained artifacts (.pth, labels.pkl, intents.json)
│   ├── static/                ← dashboard.html, embed-widget.js, preview
│   └── meraxes_agent/         ← Track 2 optimizer agent
│       ├── routes.py          ← /agents/* optimize + train endpoints
│       ├── chat_routes.py     ← /agents/chat/* session endpoints
│       ├── optimizer_agent.py ← MeraxesQualityLab pipeline
│       └── tools/             ← research / chat / meraxes tools
│
├── v2_llm_agent/              ← Nova v2 (LLM agent)
│   ├── main.py                ← FastAPI app (:8006)
│   ├── config.py              ← tiers, providers, memory, image, training config
│   ├── llm_engine.py          ← provider calls + fallback
│   ├── router_bridge.py       ← uses embedded Multi-LLM Router
│   ├── memory.py              ← FAISS semantic memory (sentence-transformers)
│   ├── database.py            ← SQLite (sessions, messages, users)
│   ├── image_engine.py        ← Pollinations / DALL·E / SD-WebUI image gen
│   ├── silent_trainer.py      ← exports v2 chats → v1 intents + Ollama fine-tune
│   ├── prompts.py             ← system prompt / message builder
│   └── frontend/index.html    ← chat UI
│
├── llm_router/               ← Multi-LLM Router
│   ├── main.py                ← FastAPI app (:8020) + /v1/chat/completions
│   ├── config.py              ← pydantic-settings (providers, routing, cache, limits)
│   ├── schemas.py             ← ChatRequest / ChatResponse
│   ├── core/                  ← router.py, cache.py, fallback.py, usage.py, optimizer.py
│   ├── services/              ← one client per provider (openai, gemini, groq, …)
│   ├── Dockerfile, docker-compose.yml
│   └── frontend/index.html
│
├── agent_platform/           ← backward-compatible shim → meraxes_agent
├── docs/                     ← image-gen & Colab notes
└── kaggle/                   ← optional Kaggle env helpers
```

---

## 3. Quick start

### Prerequisites

- **Python 3.11** (the venv and pinned wheels target 3.11)
- **Windows** is the primary dev target (batch scripts provided). On macOS/Linux the same `uvicorn` commands work — see [Running without the batch scripts](#running-without-the-batch-scripts).
- Optional: **[Ollama](https://ollama.com)** for 100% local LLM mode (no API keys).
- Optional: **Docker** for the router.
- First run downloads a sentence‑transformer embedding model from HuggingFace (~90 MB for v1, ~400 MB for v2). This is one‑time and cached.

### Step 1 — Create the virtualenv and install dependencies

From the `backend/` folder:

```powershell
py -3.11 -m venv ml-env
ml-env\Scripts\activate

pip install -r requirements.txt
pip install -r v2_llm_agent\requirements.txt
pip install -r llm_router\requirements.txt
```

> The batch scripts expect the venv at `backend/ml-env/`. The venv is **gitignored** — every developer creates their own.

### Step 2 — Configure environment files (only needed for v2 / router)

v1 (Meraxes) needs **no keys**. Nova v2 and the Router use cloud LLMs, so copy the example env files and add **your own** keys:

```powershell
copy v2_llm_agent\.env.example v2_llm_agent\.env
copy llm_router\.env.example   llm_router\.env
```

Then edit each `.env`. See [Configuration & secrets](#4-configuration--secrets) for every variable and where to get each key. **`.env` files are gitignored — never commit them.**

> Want zero keys? Set `USE_OPENAI=false` in `v2_llm_agent\.env` and run Ollama locally. Nova then runs fully offline.

### Step 3 — Run

**Everything at once** (3 terminal windows):

```powershell
run-all.bat
```

**Or one service at a time:**

```powershell
# Meraxes v1 chatbot platform → http://127.0.0.1:8005
v1_classic_ai\start-meraxes.bat

# Nova v2 LLM agent → http://127.0.0.1:8006
v2_llm_agent\start-v2.bat

# Multi-LLM Router → http://127.0.0.1:8020
llm_router\start-router.bat

# Meraxes optimizer agent on its own port → http://127.0.0.1:8030
v1_classic_ai\start-meraxes-agent.bat
```

### Step 4 — Verify

```powershell
Invoke-RestMethod http://127.0.0.1:8005/api/health
Invoke-RestMethod http://127.0.0.1:8006/health
Invoke-RestMethod http://127.0.0.1:8020/health
```

Each FastAPI service also serves interactive Swagger docs at **`/docs`** (e.g. <http://127.0.0.1:8005/docs>).

### Running without the batch scripts

The `.bat` files just wrap `uvicorn`. The cross‑platform equivalents (run from `backend/`):

```bash
# v1
cd v1_classic_ai && uvicorn main:app --host 0.0.0.0 --port 8005

# v2 (note: run from backend/, module path includes the package)
uvicorn v2_llm_agent.main:app --host 0.0.0.0 --port 8006

# router
cd llm_router && uvicorn main:app --host 0.0.0.0 --port 8020

# agent (standalone)
cd v1_classic_ai && uvicorn meraxes_agent.main:app --host 0.0.0.0 --port 8030
```

---

## 4. Configuration & secrets

Each service loads its own `.env` from its own folder via `python-dotenv` / `pydantic-settings`. **Variables you don't set fall back to the defaults below.**

### Where to get API keys

| Provider | Free tier? | Get a key |
|----------|-----------|-----------|
| OpenAI | paid | <https://platform.openai.com/api-keys> |
| Groq | yes (fast) | <https://console.groq.com/keys> |
| Google Gemini | yes | <https://aistudio.google.com/apikey> |
| OpenRouter | yes (many models) | <https://openrouter.ai/keys> |
| Together | yes | <https://api.together.xyz/settings/api-keys> |
| xAI (Grok) | paid | <https://console.x.ai> |

You do **not** need all of them. One working key (Groq and Gemini have generous free tiers) is enough to run Nova and the Router.

### `v2_llm_agent/.env` (Nova)

| Variable | Default | Purpose |
|----------|---------|---------|
| `USE_OPENAI` | `auto` | `auto` = use cloud when a key exists; `false` = Ollama‑only; `true` = require cloud |
| `DEFAULT_MODEL_TIER` | `strong` (or `local` if no key) | Default tier: `strong` \| `fast` \| `local` |
| `LLM_PROVIDER_ORDER` | `openai,groq,openrouter,google,ollama` | Fallback order |
| `OPENAI_API_KEY` / `OPENAI_MODELS` | – / `gpt-4o,gpt-4o-mini` | OpenAI |
| `GROQ_API_KEY` / `GROQ_MODELS` | – / `llama-3.3-70b-versatile,llama-3.1-8b-instant` | Groq |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODELS` | – | OpenRouter |
| `GOOGLE_API_KEY` / `GOOGLE_MODELS` | – / `gemini-2.0-flash,gemini-1.5-flash` | Gemini |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | `http://localhost:11434` / `qwen2.5:7b` | Local Ollama |
| `USE_EMBEDDED_ROUTER` | `true` | Route through the in‑process Multi‑LLM Router |
| `USE_LLM_ROUTER` / `LLM_ROUTER_URL` | `false` / `http://127.0.0.1:8020/v1` | Use the external router on `:8020` instead |
| `EMBEDDING_MODEL` | `all-mpnet-base-v2` | Memory embedder |
| `MEMORY_TOP_K` / `MEMORY_SCORE_THRESHOLD` | `6` / `0.52` | Semantic memory retrieval |
| `SILENT_V1_TRAINING` | `true` | Turn cloud answers into v1 intents |
| `EXPORT_LOCAL_FINETUNE` | `true` | Append to Ollama fine‑tune dataset |
| `V1_TRAIN_EVERY_N` | `5` | Retrain v1 every N qualifying chats |
| `AUTO_BUILD_OLLAMA` / `OLLAMA_CUSTOM_MODEL` | `false` / `nova-v2-learned` | Auto‑build a local model from chats |
| `ENABLE_IMAGE_GEN` | `true` | Enable `/chat` image generation |
| `IMAGE_PROVIDER` | `pollinations,openai,sd-webui` | Image provider fallback order |
| `SD_WEBUI_URL` | `http://127.0.0.1:7860` | Local Stable Diffusion WebUI |
| `PORT` / `HOST` / `DEBUG` | `8006` / `0.0.0.0` / `false` | Server |

### `llm_router/.env` (Router)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENABLE_{OPENAI,GEMINI,GROQ,TOGETHER,OPENROUTER,XAI}` | `true` | Provider toggles |
| `{OPENAI,GOOGLE,GROQ,TOGETHER,OPENROUTER,XAI}_API_KEY` | – | Per‑provider keys |
| `PROVIDER_PRIORITY` | `groq,gemini,openrouter,together,xai,openai` | Default fallback order |
| `PARALLEL_ENABLED` / `PARALLEL_PROVIDERS` | `true` / `groq,gemini` | Race two providers, take the first to answer |
| `CACHE_ENABLED` / `CACHE_TTL_SECONDS` | `true` / `3600` | Response cache |
| `RATE_LIMIT_{provider}` | 30–60 | Per‑provider requests/min |
| `PORT` / `HOST` / `DEBUG` | `8020` / `0.0.0.0` / `false` | Server |

### `v1_classic_ai` (Meraxes) — env optional

v1 reads a few optional env vars (no `.env` file required):

| Variable | Default | Purpose |
|----------|---------|---------|
| `V1_PORT` / `V1_HOST` | `8005` / `0.0.0.0` | Server |
| `MERAXES_MODELS_DIR` | `models/meraxes` | Where trained vertical models live |
| `MERAXES_EMBEDDER` | `all-MiniLM-L6-v2` | Sentence‑transformer for FAQ/intent embeddings |
| `MERAXES_AGENT_PORT` | `8030` | Standalone optimizer agent port |

---

## 5. Service reference

All request/response shapes below are taken directly from the code. JSON field names are exact.

### 5.1 Meraxes v1 — Chatbot Platform (`:8005`)

The product surface: create bots from business templates, train them, add custom Q&A, and embed them on websites.

| Method | Path | Body / query | Description |
|--------|------|--------------|-------------|
| `GET` | `/` | – | Dashboard UI |
| `GET` | `/api/health` | – | Status + list of trained vertical models |
| `GET` | `/api/model-types` | – | The three engine types (`intent`, `faq`, `hybrid`) |
| `GET` | `/api/businesses` | – | Available business templates |
| `GET` | `/api/businesses/{id}` | – | One template (full intents) |
| `GET` | `/api/bots` | – | List bots |
| `POST` | `/api/bots` | `{name, business_id, model_type}` | Create + train a bot |
| `GET` | `/api/bots/{bot_id}` | – | Bot + its template |
| `PATCH` | `/api/bots/{bot_id}` | `{name?, business_id?, model_type?, custom_qa?}` | Update bot |
| `POST` | `/api/bots/{bot_id}/train` | – | Retrain bot |
| `POST` | `/api/bots/{bot_id}/custom-qa` | `{question, answer}` | Add a Q&A pair + retrain |
| `POST` | `/chat` | `{message, user_id?, bot_id?}` | Chat with a bot |
| `GET` | `/api/chat/history` | `?bot_id&user_id&limit` | Conversation history |
| `DELETE` | `/api/chat/history` | `?bot_id&user_id` | Clear history |
| `GET` | `/embed/{bot_id}.js` | – | The embeddable widget script |
| `GET` | `/api/bots/{bot_id}/embed-code` | – | Copy‑paste embed snippet |

**Chat example**

```bash
curl -X POST http://127.0.0.1:8005/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"do you offer refunds?","user_id":"guest","bot_id":"<id>"}'
```

```json
{ "response": "Yes — refunds within 30 days...", "source": "faq",
  "bot_id": "1a19be44", "model_type": "hybrid" }
```

`source` tells you which path answered: `faq`, `intent`, `faq+intent`, `rule`, or `fallback`.

**Model types** (`model_type`):

- **`intent`** — neural classifier; best for structured support flows.
- **`faq`** — semantic similarity against your question list; best when users phrase things many ways.
- **`hybrid`** (recommended) — FAQ match first, intent classifier as fallback.

**Embedding a bot on a website**

```html
<script src="http://127.0.0.1:8005/embed/<bot_id>.js" defer></script>
```

### 5.2 Meraxes Agent — Quality Lab (Track 2) (`:8030` or mounted)

The autonomous optimizer. Pipeline: **train → benchmark → run BotEngine → score → detect failures → research + add Q&A → retrain → measure improvement.** These routes are mounted on `:8005` and also available standalone on `:8030`.

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `GET` | `/agents/health` | – | Agent status + trained models |
| `POST` | `/agents/optimize` | see below | Run the full optimization pipeline |
| `POST` | `/agents/train` | `?dataset=saas&quick=true` | Train one vertical model |
| `GET` | `/agents/runs/{run_id}` | – | Full run log |
| `GET` | `/agents/chat/capabilities` | – | What the chat agent can do |
| `GET`/`POST` | `/agents/chat/sessions` | `{bot_id?, dataset, client_id?}` | List / create chat sessions |
| `GET`/`DELETE` | `/agents/chat/sessions/{id}` | – | Get / delete a session |
| `POST` | `/agents/chat/sessions/{id}/messages` | `{message, enable_research?, bot_id?, dataset?}` | Send a message (may run research) |
| `GET` | `/agents/chat/jobs/{job_id}` | – | Poll a long‑running action job |

**Optimize example**

```bash
curl -X POST http://127.0.0.1:8030/agents/optimize \
  -H "Content-Type: application/json" \
  -d '{"goal":"Improve SaaS bot billing answers","dataset":"saas","test_case_limit":6,"quick_train":true,"enable_research":true}'
```

The response includes `baseline_score`, `post_refine_score`, `improvement`, `intents_added`, `research_brief`, and a per‑step `tool_usage` trace.

**Datasets:** `saas`, `ecommerce`, `healthcare`, `finance`, `general`.

### 5.3 Nova v2 — LLM Agent (`:8006`)

LLM chat with memory, history, and image generation.

| Method | Path | Body / query | Description |
|--------|------|--------------|-------------|
| `GET` | `/` | – | Chat UI |
| `GET` | `/api/config` | – | Active tier, providers, image/router status |
| `POST` | `/chat` | `ChatRequest` (below) | Main chat endpoint |
| `GET` | `/api/chat/history` | `?user_id&limit` | History for one user/session |
| `GET` | `/api/chat/conversations` | `?limit` | List sessions |
| `DELETE` | `/api/chat/conversations/{user_id}` | – | Delete session + memories + images |
| `DELETE` | `/api/chat/messages/{msg_id}` | `?user_id` | Delete one turn |
| `DELETE` | `/api/chat/history` | `?user_id` | Clear current chat |
| `GET` | `/api/training/status` | – | Silent‑trainer queue status |
| `POST` | `/api/training/run-v1` | – | Flush queue → retrain v1 now |
| `POST` | `/api/training/build-ollama` | `{create_model}` | Build Ollama model from chats |
| `GET` | `/api/router/usage` | – | Embedded router usage snapshot |
| `GET` | `/health` | – | LLM + memory + router + image status |
| `GET` | `/memory/stats` | – | FAISS stats |
| `DELETE` | `/user/{user_id}` | – | Wipe a user's data |

**`ChatRequest`**

```jsonc
{
  "message": "Explain vector databases in 2 sentences",  // required, 1–4096 chars
  "user_id": "uuid",        // optional; auto-generated if omitted (= session id)
  "tier": "strong",         // strong | fast | local
  "task": "reasoning",      // optional: auto | fast | long | reasoning | cheap
  "stream": false
}
```

**`ChatResponse`**

```jsonc
{
  "reply": "...", "user_id": "...", "provider": "groq", "model": "llama-3.3-70b-versatile",
  "tier": "strong", "latency_ms": 812, "memory_hits": 2,
  "image_url": null, "user_message_id": 41
}
```

**What `/chat` does on each call** (see `v2_llm_agent/main.py`): image fast‑path if the message asks for an image → detect & store the user's name → semantic memory retrieval → load history → build prompt → call LLM (with fallback) → persist turn → store a memory → silent‑train v1.

**Image generation:** if the message looks like an image request and `ENABLE_IMAGE_GEN=true`, Nova generates an image via the `IMAGE_PROVIDER` chain (Pollinations → OpenAI DALL·E → local SD‑WebUI) and returns `image_url` pointing at `/static/generated/<hash>.png`.

### 5.4 Multi‑LLM Router (`:8020`)

A cost‑optimized gateway across six providers with caching, parallel racing, and an OpenAI‑compatible endpoint.

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `GET` | `/` | – | Chat UI |
| `GET` | `/health` | – | Providers + cache size |
| `GET` | `/api/config` | – | Priority, parallel, cache, task routing |
| `GET` | `/api/usage` | – | Per‑provider usage stats |
| `POST` | `/api/chat` | `ChatRequest` | Native chat endpoint |
| `POST` | `/v1/chat/completions` | OpenAI body | **OpenAI‑compatible** (use with Cursor/Cline/SDKs) |

**`ChatRequest`** (`llm_router/schemas.py`)

```jsonc
{
  "messages": [{"role":"user","content":"Say hi"}],
  "model": null,                 // optional explicit model
  "task": "auto",                // auto | fast | long | reasoning | cheap
  "provider": null,              // force a provider, else routed
  "temperature": 0.7,
  "max_tokens": null,
  "parallel": null,              // override PARALLEL_ENABLED for this call
  "use_cache": true
}
```

**`ChatResponse`** returns `content, provider, model, task, latency_ms, input_tokens, output_tokens, cached, fallbacks_used, parallel_winner`.

**Task routing**

| `task` | Primary providers (then fall back) |
|--------|------------------------------------|
| `fast` | Groq → Gemini |
| `long` | Gemini → OpenRouter |
| `reasoning` | OpenRouter → OpenAI → xAI |
| `cheap` | Together → OpenRouter → Groq |
| `auto` | inferred from prompt length / content |

**Use as an OpenAI drop‑in** (Cursor / any OpenAI SDK):

```json
{ "openai.baseUrl": "http://127.0.0.1:8020/v1", "openai.apiKey": "router-local" }
```

**Docker:**

```bash
cd llm_router
docker compose up --build -d
docker compose logs -f
```

### 5.5 agent_platform (compatibility shim)

`agent_platform/main.py` simply re‑exports the Meraxes agent app for older import paths. New code should target `v1_classic_ai/meraxes_agent`.

---

## 6. Core concepts

**The v1 hybrid engine (`v1_classic_ai/engine.py`).** Each bot is a `BotEngine`. Training expands intents into `(pattern, tag)` pairs, embeds them with a sentence‑transformer (`all-MiniLM-L6-v2`), and trains a small 3‑layer MLP (`ChatModel`, 384→128→64→tags) for 350–900 epochs depending on dataset size. At reply time, **hybrid** tries a cosine‑similarity FAQ match first (dynamic threshold by corpus size), then the intent classifier with a top‑2 margin check, then a graceful fallback. Hard‑coded rule matches handle greetings/thanks/name capture before the model runs.

**Tiers (v2).** `strong` (GPT‑4o / Qwen 14B class), `fast` (mini / 3B class), `local` (Ollama only). Each tier defines candidate models per provider plus temperature/context settings.

**Fallback & routing.** Both Nova and the Router try providers in priority order and fall through on error/rate‑limit. The Router can additionally **race** two providers in parallel and keep the first response (`PARALLEL_PROVIDERS`).

**Memory (FAISS).** Both v1 and v2 keep a vector store. v2's `memory.py` embeds Q&A pairs (`all-mpnet-base-v2`), retrieves the top‑K above a similarity threshold, and injects them into the prompt — giving Nova long‑term recall across sessions.

**Silent training.** When Nova answers via a cloud provider and the Q&A passes length/quality gates, `silent_trainer.py` queues it. Every `V1_TRAIN_EVERY_N` qualifying chats it (a) adds intents to a v1 bot and retrains it, and (b) appends to an Ollama fine‑tune `.jsonl`. Optionally it builds a local `nova-v2-learned` Ollama model.

---

## 7. Training guide

**Train Meraxes vertical models** (used by the agent and as demo defaults):

```powershell
cd v1_classic_ai
..\ml-env\Scripts\activate

python train_meraxes.py saas --minimal     # fastest, ~2–5 min
python train_meraxes.py --all --minimal     # all verticals
python train_meraxes.py saas --quick         # higher accuracy, slower on CPU
```

Outputs land in `v1_classic_ai/models/meraxes/<vertical>/` (`chat_model.pth`, `labels.pkl`, `intents.json`) and update `manifest.json`.

**Train a user bot** — via the API (`POST /api/bots/{bot_id}/train`) or automatically when you create a bot or add custom Q&A.

**Retrain v1 from v2 chats** — automatic via the silent trainer, or force it: `POST :8006/api/training/run-v1`.

> Training is **local CPU PyTorch** — no cloud cost. The only download is the one‑time embedding model.

---

## 8. Data, models & databases

| Path | What | Committed? |
|------|------|-----------|
| `v1_classic_ai/*.db`, `v2_llm_agent/data/agent.db` | SQLite (bots, sessions, messages, users) | ⚠️ currently tracked; see note |
| `v1_classic_ai/models/meraxes/**` | Trained vertical models | ✅ yes (so bots run without retraining) |
| `v1_classic_ai/bots/**` | Per‑bot artifacts | ✅ yes |
| `*/data/faiss*.index`, `memory/**` | FAISS vector stores | ✅ yes |
| `v2_llm_agent/static/generated/*.png` | Generated images | ✅ yes |
| `ml-env/`, `.env`, `.kaggle/` | venv + secrets | ❌ **gitignored** |

> **Note:** trained model binaries are intentionally committed so the app works out‑of‑the‑box. The `.db` files and generated images are runtime artifacts — if the team prefers a clean repo, add `*.db` and `static/generated/` to `.gitignore` and have each dev generate their own. Flag this in review.

---

## 9. Deployment

- **Local / dev:** the batch scripts or `uvicorn` commands above.
- **Router via Docker:** `llm_router/Dockerfile` + `docker-compose.yml` (`docker compose up --build -d`).
- **Production hardening (TODO before public exposure):**
  - CORS is currently `allow_origins=["*"]` on every service — lock this down to your real frontend origin.
  - Put services behind a reverse proxy (nginx/Caddy) with TLS.
  - Set `DEBUG=false` (default) so error bodies aren't leaked.
  - Provide real secrets via the host's secret manager / env, not `.env` files.
  - Consider moving SQLite → Postgres for concurrent writers.

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ERROR: ml-env not found` | Create the venv in `backend/` (Step 1). Scripts expect `backend/ml-env/`. |
| First request to v1/v2 hangs ~30–60 s | One‑time embedding‑model download from HuggingFace. Wait for "Uvicorn running…". |
| Nova returns 503 "All LLM providers failed" | No working key and Ollama not running. Add a key in `v2_llm_agent/.env` **or** start Ollama and set `USE_OPENAI=false`. |
| `requirements.txt` looks garbled / pip errors | The file is UTF‑16 encoded. If pip rejects it, re‑save as UTF‑8 or `pip install` the packages explicitly (fastapi, uvicorn, torch, sentence-transformers, faiss-cpu, scikit-learn, openai, python-dotenv). |
| Port already in use (8006) | `restart-v2.bat` kills the listener and restarts; or change `PORT` in `.env`. |
| Router shows a provider as down | Missing/invalid key, or `ENABLE_<PROVIDER>=false`. Check `GET :8020/health`. |
| Image generation fails | Pollinations needs internet; DALL·E needs `OPENAI_API_KEY`; SD‑WebUI needs the generator running on `:7860`. |

---

## 11. Contributing & dev workflow

1. **Branch from `main`** — don't commit directly. The backend lives on the `python-backend` branch; cut feature branches from there.
2. **Never commit secrets.** `.env`, `*.key`, `*.pem`, `.kaggle/`, and `access_token` are gitignored — keep it that way.
3. **Keep the venv out of git.** It's `ml-env/` and gitignored.
4. **Match existing style.** Services are plain FastAPI + Pydantic; config is centralized in each `config.py`. Add new env vars there with sensible defaults.
5. **Tests:** `agent_platform/tests/` and `v1_classic_ai/meraxes_agent/tests/` use pytest. Run `pytest` from `backend/`.
6. **Adding a router provider:** drop a client in `llm_router/services/`, register it in `core/router.py`, add its key/toggle to `config.py` and `.env.example`.
7. **Adding a v1 vertical:** add a `datasets/<name>.json` template (same shape as `saas.json`), then `python train_meraxes.py <name> --minimal`.
8. **Open a PR** into the backend branch with a clear description of the endpoints/behaviour changed.

---

## 12. Security

- **Secrets never go in the repo.** Each developer copies `*.env.example` → `.env` and supplies **their own** keys (see [§4](#4-configuration--secrets)). The code reads from `.env`, which git ignores. The committed `.env.example` files document *which* variables exist, with no real values.
- Keys are billed per account — a leaked key can be scraped and abused within minutes. If a key is ever committed, **rotate it immediately** (revoke at the provider, issue a new one).
- For shared/team keys, use a secrets manager (1Password, Doppler, Infisical, or GitHub Actions secrets for CI) — not a committed file.
- Before exposing any service publicly, tighten CORS and run behind TLS (see [Deployment](#9-deployment)).
