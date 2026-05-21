# Chatbot Factory — Agent Texte
# Déployé sur Render (512 MB RAM)
#
# Endpoints:
#   POST /chat      — Chat texte avec le LLM
#   GET  /health    — Health check
#   GET  /          — Status

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ─── ENV ──────────────────────────────────────────────────────────────────────

ENV_FILE = Path(__file__).with_name(".env.vocal")
if not ENV_FILE.exists():
    ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot_factory")

# ─── Config LLM ───────────────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]

PORT = int(os.getenv("PORT", 8000))

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory — Agent Texte")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es l'assistant virtuel de démonstration de Chatbot Factory.
Tu es en mode test — les intégrations complètes (Google Sheets, Calendrier, CRM) seront ajoutées bientôt.

Pour l'instant, tu peux :
- Expliquer ce que fait Chatbot Factory
- Répondre aux questions sur le projet
- Guider les utilisateurs

Ton ton est professionnel mais accessible, en français."""

# ─── Sessions ─────────────────────────────────────────────────────────────────

sessions: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return PlainTextResponse("Chatbot Factory is running. Try /health or /chat")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "Chatbot Factory — Texte",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id

    if session_id not in sessions:
        sessions[session_id] = []

    history = sessions[session_id]
    history.append({"role": "user", "content": request.message})

    # Construire les messages avec le system prompt
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-10:])

    response_text = call_llm(messages, "fr")

    history.append({"role": "assistant", "content": response_text})
    sessions[session_id] = history[-10:]

    return ChatResponse(response=response_text, session_id=session_id)


# ─── LLM ─────────────────────────────────────────────────────────────────────

def call_llm(messages: list[dict], language: str = "fr") -> str:
    import urllib.request

    backend = (LLM_BACKEND or "").strip().lower()

    # Mode auto: essaie OpenAI d'abord, sinon OpenRouter
    if backend == "auto":
        backend = "openai" if OPENAI_API_KEY else "openrouter"

    if backend == "openrouter":
        api_key = OPENROUTER_API_KEY
        model = OPENROUTER_MODEL
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    elif backend == "openai":
        api_key = OPENAI_API_KEY
        model = OPENAI_MODEL
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    else:
        if language == "fr":
            return "Bonjour ! Je suis votre assistant. Comment puis-je vous aider ?"
        return "Hello! I'm your assistant. How can I help you?"

    if not api_key:
        if language == "fr":
            return "⚠️ Clé API non configurée pour le backend LLM choisi."
        return "⚠️ The API key is missing for the selected LLM backend."

    payload_dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }
    if backend == "openai":
        payload_dict["max_completion_tokens"] = 200
    else:
        payload_dict["max_tokens"] = 200

    payload = json.dumps(payload_dict).encode()
    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        body_text = ""
        if hasattr(e, "read"):
            try:
                body_text = e.read().decode(errors="replace")
            except Exception:
                body_text = ""
        logger.error(f"Erreur LLM: {e} body={body_text}")
        if language == "fr":
            if body_text:
                return f"Désolé, erreur LLM: {body_text}"
            return "Désolé, une erreur s'est produite. Veuillez réessayer."
        else:
            if body_text:
                return f"Sorry, LLM error: {body_text}"
            return "Sorry, an error occurred. Please try again."


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Démarrage Chatbot Factory (Texte) sur le port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
