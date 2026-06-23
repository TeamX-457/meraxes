# Image generation options (Nova V2)

## Best for your PC (no local load)

| Option | Cost | PC load | Quality |
|--------|------|---------|---------|
| **OpenAI DALL-E** (already configured) | ~$0.04/image | None | Excellent |
| Groq / Gemini | Text only — no images | None | N/A |

Your `.env` already has `IMAGE_PROVIDER=openai` — **use this daily**. No WebUI, no Colab.

---

## Free GPU (Google Colab)

Local SD on CPU is slow because diffusion needs a GPU. There is no glitch to fix that on CPU.

**Colab gives you a free T4 GPU** for ~hours per session:

1. Open `AImodel/docs/colab-sd-gpu.ipynb` in [Google Colab](https://colab.research.google.com)
2. Runtime → Change runtime type → **GPU**
3. Run all cells
4. Copy the `SD_WEBUI_URL=...` line into `v2_llm_agent/.env`
5. Set `IMAGE_PROVIDER=openai,sd-webui` (DALL-E first, Colab SD as backup)
6. Restart V2

Colab downsides: session expires, URL changes each run, not for production.

---

## Jupyter in VS Code

VS Code Jupyter uses **your PC's hardware** — same CPU problem as WebUI unless you connect to a **remote** GPU kernel (Colab, RunPod, etc.).

---

## Local WebUI (only if offline)

- `generator\START-IMAGES-LIGHT.bat` — 384px, 12 steps (still slow on CPU)
- Needs NVIDIA GPU + remove `--use-cpu all` in `webui-user.bat` for real speed

---

## Can V1 generate images?

No. V1 is text-only (intents/FAQ). Images = DALL-E, Colab SD, or a real GPU.

---

## Recommended setup

```
IMAGE_PROVIDER=openai
```

Ask Nova V2: *create an image of a sports car* — done in ~10 seconds, PC stays cool.
