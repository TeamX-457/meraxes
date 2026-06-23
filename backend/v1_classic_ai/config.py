"""Meraxes v1 platform configuration."""

import os

PRODUCT_NAME = "Meraxes"
PRODUCT_TAGLINE = "Embeddable business chatbot platform with trainable intent models"
PORT = int(os.getenv("V1_PORT", "8005"))
HOST = os.getenv("V1_HOST", "0.0.0.0")
PUBLIC_URL = os.getenv("V1_PUBLIC_URL", f"http://127.0.0.1:{PORT}")

# Trained Meraxes models (one folder per business vertical)
MERAXES_MODELS_DIR = os.getenv("MERAXES_MODELS_DIR", "models/meraxes")

# Agent optimizer API (Track 2)
MERAXES_AGENT_PORT = int(os.getenv("MERAXES_AGENT_PORT", "8030"))

# Embedding model — ~90MB one-time download from HuggingFace on first train/run
EMBEDDER_MODEL = os.getenv("MERAXES_EMBEDDER", "all-MiniLM-L6-v2")
