#!/usr/bin/env python3
"""
Chatbot Factory — Serveur Vocal API
=====================================
Reçoit l'audio du widget, transcrit avec Whisper,
fait répondre l'agent LLM, et renvoie la réponse audio (TTS).

Endpoints:
  POST /vocal/transcribe-and-respond — Reçoit audio → renvoie texte + audio
  GET  /vocal/health                 — Health check
  WS   /vocal/ws                     — WebSocket pour streaming temps réel

Dépendances:
    pip install openai-whisper edge-tts fastapi uvicorn python-dotenv
"""

import os
import io
import json
import base64
import logging
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vocal_api")

# ─── Configuration ────────────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "openrouter")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
TTS_VOICE_FR = os.getenv("TTS_VOICE_FR", "fr-FR-HenriNeural")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-US-GuyNeural")
PORT = int(os.getenv("PORT", 8001))

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory — Vocal API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    logger.info(f"Recu: {audio.filename} ({audio.size} bytes), langue: {language}")

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

    try:
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

    finally:
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
                os.unlink(temp_path)

    except WebSocketDisconnect:
        logger.info("WebSocket déconnecté")
    except Exception as e:
        logger.error(f"Erreur WebSocket: {e}")
        await websocket.close()


# ─── Fonctions ────────────────────────────────────────────────────────────────

def get_system_prompt(language: str) -> str:
    if language == "fr":
        return """Tu es l'assistant vocal d'une entreprise. Tu réponds au téléphone de façon naturelle.

Regles:
- Sois CONCIS: 2-3 phrases maximum
- Parle de façon NATURELLE et CHALEUREUSE
- Si tu ne sais pas, propose de transferer a un humain
- Reponds en FRANCAIS
- Ne donne jamais de diagnostic medical

Tu es un assistant professionnel et sympathique."""
    else:
        return """You are a voice assistant for a business. You answer the phone naturally.

Rules:
- Be CONCISE: 2-3 sentences maximum
- Speak in a NATURAL and WARM way
- If you don't know, suggest transferring to a human
- Answer in ENGLISH
- Never give medical diagnoses

You are a professional and friendly assistant."""


def call_llm(messages: list[dict], language: str = "fr") -> str:
    import urllib.request

    if LLM_BACKEND == "openrouter":
        api_key = OPENROUTER_API_KEY
        model = OPENROUTER_MODEL
        url = "https://openrouter.ai/api/v1/chat/completions"
    else:
        if language == "fr":
            return "Bonjour ! Je suis votre assistant. Comment puis-je vous aider ?"
        else:
            return "Hello! I'm your assistant. How can I help you?"

    if not api_key:
        return "⚠️ Clé API non configurée."

    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 200,
        "temperature": 0.7,
    }).encode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Erreur LLM: {e}")
        if language == "fr":
            return "Désolé, une erreur s'est produite. Veuillez réessayer."
        else:
            return "Sorry, an error occurred. Please try again."


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
