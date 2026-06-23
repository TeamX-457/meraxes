# Multi-LLM API Router

Production FastAPI gateway: Gemini, Groq, Together, OpenRouter, xAI Grok, OpenAI.

## Run (local — not on the public internet until you deploy)

```bat
start-router.bat
```

### Docker

```bat
docker-start.bat
```

Or manually:

```bat
cd AImodel\llm_router
docker compose up --build -d
docker compose logs -f
```

UI: http://127.0.0.1:8020  
OpenAI-compatible: `http://127.0.0.1:8020/v1/chat/completions`

### Test it works

1. Browser: open http://127.0.0.1:8020 — chat UI
2. Health: http://127.0.0.1:8020/health — should show `"status":"ok"`
3. PowerShell:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8020/health
   Invoke-RestMethod http://127.0.0.1:8020/api/chat -Method POST -ContentType "application/json" -Body '{"messages":[{"role":"user","content":"Say hi in one sentence"}],"task":"fast"}'
   ```

## Cursor / CLI

```json
{
  "openai.baseUrl": "http://127.0.0.1:8020/v1",
  "openai.apiKey": "router-local"
}
```

## Routing

| Task | Primary providers |
|------|-------------------|
| fast | Groq → Gemini |
| long | Gemini → OpenRouter |
| reasoning | OpenRouter → OpenAI → xAI |
| cheap | Together → OpenRouter → Groq |

Copy `.env.example` to `.env` and add keys. Never commit `.env`.
