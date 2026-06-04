#!/usr/bin/env python3
"""
Chatbot Factory — App combinée pour HF Spaces
Endpoints texte + vocal (Whisper lazy-load, fallback gracieux)
"""

import os
import io
import json
import base64
import logging
import tempfile
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

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
app._maybe_disable_swagger()

# ─── KB + System Prompt ──────────────────────────────────────────────────────

KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []
try:
    kb_path = KB_DIR / "knowledge.json"
    if kb_path.exists():
        with open(kb_path, "r", encoding="utf-8") as f:
            knowledge_docs = json.load(f)
except Exception:
    pass

# ─── Sessions ─────────────────────────────────────────────────────────────────

sessions_vocal: dict[str, list[dict]] = {}
sessions_text: dict[str, list[dict]] = {}

# ─── LLM helper ──────────────────────────────────────────────────────────────

def call_llm(messages: list[dict]) -> str:
    backend = LLM_BACKEND.lower()
    import httpx

    if backend in ("auto", "openrouter") and OPENROUTER_API_KEY:
        try:
            with httpx.Client(timeout=60) as c:
                r = c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                    json={"model": OPENROUTER_MODEL, "messages": messages, "max_tokens": 500},
                )
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenRouter failed: {e}")

    if backend in ("auto", "openai") and OPENAI_API_KEY:
        try:
            with httpx.Client(timeout=60) as c:
                r = c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={"model": OPENAI_MODEL, "messages": messages, "max_tokens": 500},
                )
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"OpenAI failed: {e}")

    if backend in ("auto", "groq") and GROQ_API_KEY:
        try:
            with httpx.Client(timeout=60) as c:
                r = c.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
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
    history = sessions_text.get(sid, [])
    history.append({"role": "user", "content": req.message})

    system_prompt = (
        "Tu es un assistant virtuel pour une entreprise. "
        "Réponds de manière concise et utile en français. "
        "Si tu ne connais pas la réponse, dis-le honnêtement."
    )
    messages = [{"role": "system", "content": system_prompt}] + history
    response = call_llm(messages)

    history.append({"role": "assistant", "content": response})
    if len(history) > 20:
        history = history[-20:]
    sessions_text[sid] = history

    return {"response": response, "session_id": sid, "transferred": False}


# ══════════════════════════════════════════════════════════════════════════════
#  SERVEUR VOCAL (Whisper lazy-load)
# ══════════════════════════════════════════════════════════════════════════════

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
            if audio.filename.endswith(".wav"): suffix = ".wav"
            elif audio.filename.endswith(".mp3"): suffix = ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_data)
            audio_path = f.name

        logger.info(f"Recu: {audio.filename} ({len(audio_data)} bytes)")

        # Whisper lazy-load
        try:
            import whisper
        except ImportError:
            return JSONResponse(
                {"error": "Whisper n'est pas installé sur ce serveur. Utilisez la transcription côté client (Web Speech API)."},
                status_code=501,
            )

        model = whisper.load_model(WHISPER_MODEL)
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

        # LLM
        if session_id not in sessions_vocal:
            sessions_vocal[session_id] = []
        history = sessions_vocal[session_id]
        history.append({"role": "user", "content": transcription})

        system_prompt = "Tu es un assistant virtuel. Réponds de manière concise en français."
        messages = [{"role": "system", "content": system_prompt}] + history
        response_text = call_llm(messages)

        history.append({"role": "assistant", "content": response_text})
        if len(history) > 20:
            sessions_vocal[session_id] = history[-20:]

        # TTS
        audio_b64 = None
        try:
            import edge_tts
            voice = TTS_VOICE_FR if lang == "fr" else TTS_VOICE_EN
            communicate = edge_tts.Communicate(response_text, voice)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            await communicate.save(tmp_path)
            with open(tmp_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            os.unlink(tmp_path)
        except Exception as e:
            logger.warning(f"TTS echoue: {e}")

        return JSONResponse({
            "transcription": transcription,
            "response": response_text,
            "audio_base64": audio_b64,
        })

    except Exception as e:
        logger.error(f"Erreur: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)
