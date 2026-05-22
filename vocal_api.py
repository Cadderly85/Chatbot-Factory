#!/usr/bin/env python3
"""
Chatbot Factory — Serveur Vocal HF
===================================
Backend de production du widget vocal pour Hugging Face Spaces.

Flux:
  widget GitHub Pages → /vocal/transcribe-and-respond → Whisper → LLM auto
  → Edge TTS → réponse audio

Endpoints:
  POST /vocal/transcribe-and-respond — Audio → texte + audio
  GET  /vocal/health                 — Health check
  WS   /vocal/ws                     — Streaming temps réel

Variables clés:
  LLM_BACKEND=auto
  OPENROUTER_MODEL=openrouter/owl-alpha
  OPENAI_MODEL=gpt-5.4-mini
  ALLOWED_ORIGINS=https://cadderly85.github.io
"""

import os
import io
import json
import base64
import logging
import traceback
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

ENV_FILE = Path(__file__).with_name(".env.vocal")
if not ENV_FILE.exists():
    ENV_FILE = Path(__file__).with_name(".env")
load_dotenv(ENV_FILE)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vocal_api")

# ─── Configuration ────────────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
TTS_VOICE_FR = os.getenv("TTS_VOICE_FR", "fr-FR-HenriNeural")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-US-GuyNeural")
PORT = int(os.getenv("PORT", 8001))
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory — Vocal API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Whisper (lazy loading) ───────────────────────────────────────────────────

whisper_model = None

def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        import whisper
        logger.info(f"Chargement Whisper: {WHISPER_MODEL}...")
        whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper charge!")
    return whisper_model

# ─── Sessions ─────────────────────────────────────────────────────────────────

sessions: dict[str, list[dict]] = {}

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/vocal/health")
async def health():
    return {"status": "ok", "service": "vocal_api", "timestamp": datetime.now().isoformat()}


@app.get("/")
async def root():
    return PlainTextResponse("Chatbot Factory vocal API is running. Try /vocal/health")


@app.post("/vocal/transcribe-and-respond")
async def transcribe_and_respond(
    audio: UploadFile = File(...),
    language: str = Form("fr"),
    session_id: str = Form("default"),
):
    """
    Reçoit un fichier audio, transcrit avec Whisper,
    fait répondre le LLM, et renvoie la réponse texte + audio.
    """
    logger.info(f"Recu: {audio.filename}, langue: {language}")

    audio_path = None
    try:
        # 1. Sauvegarder l'audio
        audio_data = await audio.read()
        suffix = ".webm"
        if audio.filename and audio.filename.endswith(".wav"):
            suffix = ".wav"
        elif audio.filename and audio.filename.endswith(".mp3"):
            suffix = ".mp3"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_data)
            audio_path = f.name

        # 2. Transcrire avec Whisper
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

        # 3. Récupérer l'historique
        if session_id not in sessions:
            sessions[session_id] = []
        history = sessions[session_id]

        # 4. Appeler le LLM
        messages = [
            {"role": "system", "content": get_system_prompt(lang)}
        ]
        for msg in history[-10:]:
            messages.append(msg)
        messages.append({"role": "user", "content": transcription})

        response_text = call_llm(messages, lang)
        logger.info(f"Reponse LLM: {response_text}")

        # 5. Sauvegarder l'historique
        history.append({"role": "user", "content": transcription})
        history.append({"role": "assistant", "content": response_text})
        sessions[session_id] = history[-20:]

        # 6. Générer l'audio de la réponse (TTS)
        audio_base64 = await generate_tts(response_text, lang)

        return JSONResponse({
            "transcription": transcription,
            "response": response_text,
            "audio_base64": audio_base64,
            "language": lang,
        })

    except Exception as e:
        logger.error("Erreur dans /vocal/transcribe-and-respond\n%s", traceback.format_exc())
        return JSONResponse(status_code=500, content={"detail": str(e), "type": e.__class__.__name__})
    finally:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)


@app.websocket("/vocal/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket pour le streaming vocal en temps réel.
    Reçoit des chunks audio, transcrit, et répond.
    """
    await websocket.accept()
    logger.info("WebSocket connecté")

    session_id = f"ws_{datetime.now().timestamp()}"
    if session_id not in sessions:
        sessions[session_id] = []

    try:
        while True:
            # Recevoir un chunk audio
            data = await websocket.receive_bytes()

            # Sauvegarder temporairement
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(data)
                temp_path = f.name

            try:
                # Transcrire
                model = get_whisper_model()
                result = model.transcribe(temp_path, language="fr")
                transcription = result["text"].strip()

                if transcription:
                    await websocket.send_json({
                        "type": "transcription",
                        "text": transcription,
                    })

                    # Répondre
                    history = sessions[session_id]
                    messages = [{"role": "system", "content": get_system_prompt("fr")}]
                    for msg in history[-10:]:
                        messages.append(msg)
                    messages.append({"role": "user", "content": transcription})

                    response_text = call_llm(messages, "fr")

                    history.append({"role": "user", "content": transcription})
                    history.append({"role": "assistant", "content": response_text})
                    sessions[session_id] = history[-20:]

                    # Générer TTS
                    audio_base64 = await generate_tts(response_text, "fr")

                    await websocket.send_json({
                        "type": "response",
                        "text": response_text,
                        "audio_base64": audio_base64,
                    })

            finally:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.unlink(temp_path)

    except WebSocketDisconnect:
        logger.info("WebSocket déconnecté")
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}")
        await websocket.close()


# ─── Fonctions ────────────────────────────────────────────────────────────────

def get_system_prompt(language: str) -> str:
    if language == "fr":
        return """Tu es l'assistant vocal d'une clinique dentaire. Tu réponds comme une vraie personne au téléphone.

Règles:
- Réponses TRÈS COURTES: 1 à 2 phrases maximum
- Ton chaleureux, naturel et professionnel
- Si la demande est floue, pose UNE question simple
- Si tu ne sais pas, propose de transférer à un humain
- Ne donne jamais de diagnostic médical
- Réponds en français clair et simple
- Parle comme un assistant de clinique, pas comme un robot

Tu aides surtout pour: rendez-vous, horaires, services, coordonnées, et orientation."""
    else:
        return """You are the voice assistant for a dental clinic. Speak like a real person on the phone.

Rules:
- VERY SHORT answers: 1 to 2 sentences maximum
- Warm, natural, professional tone
- If the request is unclear, ask ONE simple question
- If you don't know, offer to transfer to a human
- Never give medical diagnoses
- Answer in clear, simple English
- Sound like a clinic assistant, not a robot

You mainly help with appointments, opening hours, services, contact info, and routing."""


def call_llm(messages: list[dict], language: str = "fr") -> str:
    import urllib.request

    backend = (LLM_BACKEND or "").strip().lower()

    def candidates():
        if backend == "auto":
            ordered = []
            if OPENROUTER_API_KEY:
                ordered.append(("openrouter", OPENROUTER_MODEL, "https://openrouter.ai/api/v1/chat/completions", OPENROUTER_API_KEY))
            if OPENAI_API_KEY:
                ordered.append(("openai", OPENAI_MODEL, "https://api.openai.com/v1/chat/completions", OPENAI_API_KEY))
            if not ordered:
                ordered = [
                    ("openrouter", OPENROUTER_MODEL, "https://openrouter.ai/api/v1/chat/completions", OPENROUTER_API_KEY),
                    ("openai", OPENAI_MODEL, "https://api.openai.com/v1/chat/completions", OPENAI_API_KEY),
                ]
            return ordered
        if backend == "openrouter":
            return [("openrouter", OPENROUTER_MODEL, "https://openrouter.ai/api/v1/chat/completions", OPENROUTER_API_KEY)]
        if backend == "openai":
            return [("openai", OPENAI_MODEL, "https://api.openai.com/v1/chat/completions", OPENAI_API_KEY)]
        return []

    for backend_name, model, url, api_key in candidates():
        if not api_key:
            continue

        payload_dict = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
        }
        if backend_name == "openai":
            payload_dict["max_completion_tokens"] = 200
        else:
            payload_dict["max_tokens"] = 200

        payload = json.dumps(payload_dict).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

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
            logger.error(f"Erreur LLM {backend_name}: {e} body={body_text}")
            continue

    return "Désolé, je n'ai pas pu joindre le modèle de réponse. Veuillez réessayer."



async def generate_tts(text: str, language: str = "fr") -> str:
    """Génère l'audio TTS et renvoie en base64."""
    import edge_tts

    voice = TTS_VOICE_FR if language == "fr" else TTS_VOICE_EN

    communicate = edge_tts.Communicate(text, voice)

    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    return base64.b64encode(audio_data).decode()


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Demarrage API vocale sur le port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
