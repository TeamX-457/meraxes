# Stable Diffusion via Colab + Cloudflare (fixed domain)

Use a **Cloudflare domain + Tunnel** so Nova V2 always calls the same URL — no random ngrok links.

---

## How it fits together

```
Nova V2 (your PC)  ──HTTPS──►  sd-api.YOURDOMAIN.com  ──Cloudflare Tunnel──►  Colab GPU (SD WebUI :7860)
VS Code / scripts  ──same URL──►
```

- **Domain stays the same forever** (`sd-api.yourdomain.com`)
- **Colab still restarts** when the session ends (~90 min idle on free) — you re-run the notebook, tunnel reconnects, **same domain works again**
- **Not 24/7** unless you keep restarting Colab or move to RunPod/Vast.ai

---

## One-time setup (~20 min)

### 1. Domain on Cloudflare
1. Buy a domain (Cloudflare Registrar ~$10/yr, or transfer existing).
2. DNS must use **Cloudflare nameservers** (orange cloud).

### 2. Cloudflare Tunnel (fixed hostname)
1. Cloudflare Dashboard → **Zero Trust** (free) → **Networks** → **Tunnels**.
2. **Create a tunnel** → name it `colab-sd`.
3. Install connector — for Colab we use **token in notebook** (see notebook cell), not install on PC.
4. **Public Hostname**:
   - Subdomain: `sd-api` (or whatever you want)
   - Domain: `yourdomain.com`
   - Service: `http://localhost:7860`
5. Copy the **tunnel token** (starts with `eyJ...`).

### 3. Colab notebook
1. Open `AImodel/docs/colab-sd-cloudflare.ipynb` in Google Colab.
2. Runtime → **GPU**.
3. Paste your tunnel token in the config cell.
4. Run all cells — SD WebUI starts + cloudflared connects.

### 4. Nova V2 `.env` (set once, never change URL)

```env
ENABLE_IMAGE_GEN=true
IMAGE_PROVIDER=openai,sd-webui
SD_WEBUI_URL=https://sd-api.yourdomain.com
SD_IMAGE_STEPS=20
SD_IMAGE_SIZE=512
```

Restart V2: `AImodel\restart-v2.bat`

---

## Calling from VS Code or your project

Same HTTP API as always — fixed base URL:

```python
import requests

API = "https://sd-api.yourdomain.com/sdapi/v1/txt2img"
r = requests.post(API, json={
    "prompt": "sports car, photorealistic",
    "steps": 20,
    "width": 512,
    "height": 512,
})
# save r.json()["images"][0] as base64 PNG
```

Nova V2 does this automatically when you ask for an image (after DALL-E if `IMAGE_PROVIDER=openai,sd-webui`).

---

## Colab session workflow (each time)

1. Open Colab notebook → Run all (GPU + SD + tunnel).
2. Wait ~3 min for model load.
3. Test: open `https://sd-api.yourdomain.com` in browser (may show WebUI or API).
4. Use Nova V2 or VS Code — **URL unchanged**.

When Colab disconnects: re-run notebook. Domain still works.

---

## Cloudflare vs ngrok

| | ngrok free | Cloudflare Tunnel |
|--|------------|-------------------|
| URL | Random each time | **Fixed subdomain** |
| Cost | Free | Free (need domain ~$10/yr) |
| Colab | Works | Works |
| 24/7 | No | No (Colab limit) |

---

## Training?

- **Fine-tune SD on Colab:** possible in same notebook (LoRA) — heavy, session limits apply.
- **Train V1 to generate images:** not possible — V1 is text-only. V1 can only *route* “I want an image” to V2/API.

---

## Still easiest for daily use

**DALL-E** (`IMAGE_PROVIDER=openai`) — no Colab, no tunnel, no session restarts.

Use **Cloudflare + Colab** when you want **free GPU** + **your own domain** + **same URL in code**.
