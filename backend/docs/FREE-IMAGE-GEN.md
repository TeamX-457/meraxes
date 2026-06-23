# Free image generation (no money needed)

## Best option — already wired in V2

**Pollinations.ai** — free, no API key, no credit card.

In `v2_llm_agent/.env`:
```env
IMAGE_PROVIDER=pollinations
```

Restart V2 → ask Nova: *create an image of a sports car*

- Your PC does almost nothing
- Costs **$0**
- Tag in chat: `pollinations · flux`

---

## What costs money (skip if broke)

| Thing | Cost |
|-------|------|
| Custom Cloudflare domain | ~$10/year |
| OpenAI DALL-E | ~$0.04 per image |
| ngrok paid static URL | ~$8/month |
| RunPod / GPU rental | few $/month |

---

## Free Colab GPU (optional, more work)

1. Google Colab free → GPU runtime
2. Run `docs/colab-sd-gpu.ipynb`
3. Use **free ngrok** or **trycloudflare** tunnel

**Catch:** URL changes every session — paste new URL into `.env` each time you start Colab.

No domain needed. No payment.

---

## Do NOT use on your PC

`generator\START-IMAGES.bat` on CPU-only = slow + melts CPU. Use Pollinations instead.

---

## V1 cannot generate images

V1 is text-only. Free images = V2 + Pollinations or Colab.
