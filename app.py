#!/usr/bin/env python3
"""
Chatbot Factory — App combinée pour HF Spaces
==============================================
Point d'entrée unique qui sert :
  - L'agent texte (POST /chat)
  - Le serveur vocal (POST /vocal/transcribe-and-respond)
  - Health check (GET /vocal/health)
"""

import os
import io
import json
import base64
import logging
import tempfile
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# ─── Env ──────────────────────────────────────────────────────────────────────

env_candidates = [
    Path(__file__).with_name(".env.vocal"),
    Path(__file__).with_name(".env"),
]
for p in env_candidates:
    if p.exists():
        load_dotenv(p)
        break

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chatbot_factory")

# ─── Config ───────────────────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
TTS_VOICE_FR = os.getenv("TTS_VOICE_FR", "fr-FR-HenriNeural")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-US-GuyNeural")
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── KB ───────────────────────────────────────────────────────────────────────

KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []

try:
    kb_path = KB_DIR / "knowledge.json"
    if kb_path.exists():
        with open(kb_path, "r", encoding="utf-8") as f:
            knowledge_docs = json.load(f)
        logger.info(f"KB chargee: {len(knowledge_docs)} docs")
except Exception as e:
    logger.warning(f"KB non chargee: {e}")

# ─── Sessions (texte) ────────────────────────────────────────────────────────

from collections import defaultdict
from time import time as _time

sessions_vocal: dict[str, list[dict]] = {}
sessions_text: dict[str, list[dict]] = defaultdict(list)

# ─── System prompt (texte) ───────────────────────────────────────────────────

system_prompt = (
    "Tu es un assistant virtuel pour une entreprise. "
    "Réponds de manière concise et utile en français. "
    "Si tu ne connais pas la réponse, dis-le honnêtement."
)

# ─── LLM helper ──────────────────────────────────────────────────────────────

def call_llm(messages: list[dict]) -> str:
    """Appelle le LLM avec fallback auto → OpenRouter → OpenAI → Groq."""
    backend = LLM_BACKEND.lower()

    # OpenRouter
    if backend in ("auto", "openrouter") and (OPENROUTER_API_KEY or OPENAI_API_KEY):
        try:
            import httpx
            api_key = OPENROUTER_API_KEY or OPENAI_API_KEY
            model = OPENROUTER_MODEL if OPENROUTER_API_KEY else OPENAI_MODEL
            with httpx.Client(timeout=60) as c:
                r = c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "max_tokens": 500},
                )
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenRouter failed: {e}")

    # OpenAI direct
    if backend in ("auto", "openai") and OPENAI_API_KEY:
        try:
            import httpx
            with httpx.Client(timeout=60) as c:
                r = c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"model": OPENAI_MODEL, "messages": messages, "max_tokens": 500},
                )
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI failed: {e}")

    # Groq
    if backend in ("auto", "groq") and GROQ_API_KEY:
        try:
            import httpx
            with httpx.Client(timeout=60) as c:
                r = c.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": 500},
                )
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"Groq failed: {e}")

    return "Je suis désolé, je ne peux pas répondre pour le moment. Veuillez réessayer plus tard."


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT TEXTE
# ══════════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

@app.get("/")
async def root():
    return PlainTextResponse("OK — Chatbot Factory")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "chatbot_factory", "timestamp": datetime.now().isoformat()}

@app.post("/chat")
async def chat(req: ChatRequest):
    sid = req.session_id
    history = sessions_text[sid]
    history.append({"role": "user", "content": req.message})

    messages = [{"role": "system", "content": system_prompt}] + history
    response = call_llm(messages)

    history.append({"role": "assistant", "content": response})
    # Trim history to last 20 messages
    if len(history) > 20:
        sessions_text[sid] = history[-20:]

    return {"response": response, "session_id": sid}


# ══════════════════════════════════════════════════════════════════════════════
#  SERVEUR VOCAL
# ══════════════════════════════════════════════════════════════════════════════

whisper_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        import whisper
        logger.info(f"Chargement Whisper: {WHISPER_MODEL}...")
        whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper charge!")
    return whisper_model


@app.get("/vocal/health")
async def vocal_health():
    return {"status": "ok", "service": "vocal_api", "timestamp": datetime.now().isoformat()}


@app.post("/vocal/transcribe-and-respond")
async def transcribe_and_respond(
    audio: UploadFile = File(...),
    language: str = Form("fr"),
    session_id: str = Form("default"),
):
    audio_path = None
    try:
        audio_data = await audio.read()
        suffix = ".webm"
        if audio.filename:
            if audio.filename.endswith(".wav"):
                suffix = ".wav"
            elif audio.filename.endswith(".mp3"):
                suffix = ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_data)
            audio_path = f.name

        logger.info(f"Recu: {audio.filename} ({len(audio_data)} bytes), langue: {language}")

        # 1. Whisper transcription
        model = get_whisper_model()
        lang = "fr" if language.startswith("fr") else "en"
        result = model.transcribe(audio_path, language=lang)
        transcription = result["text"].strip()
        logger.info(f"Transcription: {transcription}")

        if not transcription:
            return JSONResponse({
                "transcription": "",
                "response": "Je n'ai pas bien compris. Pouvez-vous répéter ?",
                "audio_base64": None,
            })

        # 2. LLM response
        if session_id not in sessions_vocal:
            sessions_vocal[session_id] = []
        history = sessions_vocal[session_id]
        history.append({"role": "user", "content": transcription})

        messages = [{"role": "system", "content": system_prompt}] + history
        response_text = call_llm(messages)

        history.append({"role": "assistant", "content": response_text})
        if len(history) > 20:
            sessions_vocal[session_id] = history[-20:]

        # 3. TTS
        audio_b64 = None
        try:
            import edge_tts
            voice = TTS_VOICE_FR if lang == "fr" else TTS_VOICE_EN
            communicate = edge_tts.Communicate(response_text, voice)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            await communicate.save(tmp_path)
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
            audio_b64 = base64.b64encode(audio_bytes).decode()
            os.unlink(tmp_path)
            logger.info(f"TTS genere: {len(audio_bytes)} bytes")
        except Exception as e:
            logger.warning(f"TTS echoue: {e}")

        return JSONResponse({
            "transcription": transcription,
            "response": response_text,
            "audio_base64": audio_b64,
        })

    except Exception as e:
        logger.error(f"Erreur: {e}")
        return JSONResponse(
            {"error": str(e), "detail": "Internal server error"},
            status_code=500,
        )
    finally:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)


@app.websocket("/vocal/ws")
async def vocal_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            # Minimal WS handler — just acknowledge
            await websocket.send_json({"status": "received"})
    except WebSocketDisconnect:
        pass
