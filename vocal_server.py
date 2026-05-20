#!/usr/bin/env python3
"""
Chatbot Factory - Serveur Vocal
================================
Reçoit des appels via Twilio, transcrit la voix en texte (Whisper),
fait répondre l'agent LLM, et vocalise la réponse (Edge TTS).

Flow:
  1. Client appelle → Twilio reçoit l'appel
  2. Twilio envoie le stream audio au webhook /voice
  3. Whisper transcrit l'audio en texte
  4. L'agent LLM génère une réponse
  5. Edge TTS vocalise la réponse
  6. Twilio joue la réponse au client

Dépendances:
    pip install whisper edge-tts fastapi uvicorn twilio python-dotenv

Usage:
    python vocal_server.py
"""

import os
import io
import json
import logging
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vocal_server")

# ─── Configuration ────────────────────────────────────────────────────────────

# LLM
LLM_BACKEND = os.getenv("LLM_BACKEND", "openrouter")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# Whisper
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")  # tiny, base, small, medium, large

# TTS
TTS_VOICE_FR = os.getenv("TTS_VOICE_FR", "fr-FR-HenriNeural")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-US-GuyNeural")

# Serveur
PORT = int(os.getenv("PORT", 8000))

# ─── Initialisation ───────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory — Serveur Vocal")

# Charger Whisper (lazy loading)
whisper_model = None

def get_whisper_model():
    """Charge le modèle Whisper au premier appel."""
    global whisper_model
    if whisper_model is None:
        import whisper
        logger.info(f"Chargement du modèle Whisper: {WHISPER_MODEL}...")
        whisper_model = whisper.load_model(WHISPER_MODEL)
        logger.info("Whisper chargé!")
    return whisper_model

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es l'assistant vocal de **{company_name}**. Tu réponds au téléphone.

## Règles importantes
- Sois **concis** : 2-3 phrases maximum par réponse
- Parle de façon **naturelle et chaleureuse**, comme une vraie réceptionniste
- Si tu ne sais pas, propose de transférer à un humain
- Réponds dans la **langue utilisée par le client** (français ou anglais)
- Ne donne jamais de diagnostic médical

## Informations sur l'entreprise
{company_info}

## Ton style
- Chaleureux et professionnel
- Rassurant
- Efficace"""

# ─── Fonctions LLM ────────────────────────────────────────────────────────────

def call_llm(messages: list[dict], language: str = "fr") -> str:
    """Appeler le LLM via API REST."""
    import urllib.request

    if LLM_BACKEND == "openrouter":
        api_key = OPENROUTER_API_KEY
        model = OPENROUTER_MODEL
        url = "https://openrouter.ai/api/v1/chat/completions"
    else:
        return "Bonjour ! Je suis l'assistant. Comment puis-je vous aider?"

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
        return "Désolé, une erreur s'est produite. Veuillez réessayer."


async def text_to_speech(text: str, language: str = "fr") -> bytes:
    """Convertir du texte en voix via Edge TTS."""
    import edge_tts

    voice = TTS_VOICE_FR if language == "fr" else TTS_VOICE_EN

    communicate = edge_tts.Communicate(text, voice)

    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    return audio_data


def speech_to_text(audio_data: bytes, language: str = "fr") -> str:
    """Transcrire de la voix en texte via Whisper."""
    model = get_whisper_model()

    # Sauvegarder l'audio dans un fichier temporaire
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_data)
        temp_path = f.name

    try:
        result = model.transcribe(temp_path, language=language)
        return result["text"].strip()
    finally:
        os.unlink(temp_path)


# ─── Sessions ─────────────────────────────────────────────────────────────────

call_sessions: dict[str, dict] = {}


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "vocal_server", "timestamp": datetime.now().isoformat()}


@app.post("/voice")
async def voice_webhook(request: Request):
    """
    Webhook Twilio pour les appels entrants.
    Twilio envoie une requête POST avec les détails de l'appel.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    from_number = form_data.get("From", "unknown")
    to_number = form_data.get("To", "unknown")

    logger.info(f"Appel entrant de {from_number} vers {to_number} (SID: {call_sid})")

    # Créer ou récupérer la session
    if call_sid not in call_sessions:
        call_sessions[call_sid] = {
            "from": from_number,
            "to": to_number,
            "history": [],
            "language": "fr",
            "started_at": datetime.now().isoformat(),
        }

    # Message d'accueil
    greeting = (
        "Bonjour ! Bienvenue à la Clinique Dentaire Sourire. "
        "Je suis votre assistant virtuel. Comment puis-je vous aider aujourd'hui ?"
    )

    # Générer l'audio de bienvenue
    try:
        audio_data = await text_to_speech(greeting, "fr")
        # Sauvegarder l'audio pour Twilio
        audio_path = f"/tmp/greeting_{call_sid}.mp3"
        with open(audio_path, "wb") as f:
            f.write(audio_data)
    except Exception as e:
        logger.error(f"Erreur TTS: {e}")
        audio_path = None

    # Réponse TwiML (Twilio Markup Language)
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="fr-FR">{greeting}</Say>
    <Gather input="speech" language="fr-FR" action="/voice/respond" timeout="5">
        <Say voice="alice" language="fr-FR">Je vous écoute.</Say>
    </Gather>
</Response>"""

    return PlainTextResponse(twiml, media_type="application/xml")


@app.post("/voice/respond")
async def voice_respond(request: Request):
    """
    Traite la réponse vocale du client.
    Twilio envoie la transcription de la parole du client.
    """
    form_data = await request.form()
    call_sid = form_data.get("CallSid", "unknown")
    speech_result = form_data.get("SpeechResult", "")
    confidence = form_data.get("Confidence", "0")

    logger.info(f"Transcription: '{speech_result}' (confiance: {confidence})")

    if not speech_result:
        # Pas compris, redemander
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="fr-FR">Je n'ai pas bien compris. Pouvez-vous répéter ?</Say>
    <Gather input="speech" language="fr-FR" action="/voice/respond" timeout="5">
        <Say voice="alice" language="fr-FR">Je vous écoute.</Say>
    </Gather>
</Response>"""
        return PlainTextResponse(twiml, media_type="application/xml")

    # Détecter la langue
    language = detect_language(speech_result)

    # Récupérer la session
    session = call_sessions.get(call_sid, {"history": [], "language": language})
    session["language"] = language

    # Construire les messages pour le LLM
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(
            company_name="Clinique Dentaire Sourire",
            company_info="- Adresse: 1234 Rue Saint-Jean, Montréal\n- Tél: (514) 555-0123\n- Horaires: Lun-Ven 8h-18h"
        )}
    ]

    for msg in session["history"][-10:]:
        messages.append(msg)

    messages.append({"role": "user", "content": speech_result})

    # Appeler le LLM
    response_text = call_llm(messages, language)
    logger.info(f"Réponse LLM: {response_text}")

    # Sauvegarder dans l'historique
    session["history"].append({"role": "user", "content": speech_result})
    session["history"].append({"role": "assistant", "content": response_text})
    call_sessions[call_sid] = session

    # Générer l'audio de la réponse
    try:
        audio_data = await text_to_speech(response_text, language)
        audio_path = f"/tmp/response_{call_sid}.mp3"
        with open(audio_path, "wb") as f:
            f.write(audio_data)
        logger.info(f"Audio généré: {len(audio_data)} bytes")
    except Exception as e:
        logger.error(f"Erreur TTS: {e}")

    # Réponse TwiML
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="{'fr-FR' if language == 'fr' else 'en-US'}">{response_text}</Say>
    <Gather input="speech" language="{'fr-FR' if language == 'fr' else 'en-US'}" action="/voice/respond" timeout="5">
        <Say voice="alice" language="{'fr-FR' if language == 'fr' else 'en-US'}">Avez-vous autre chose à me demander ?</Say>
    </Gather>
    <Say voice="alice" language="{'fr-FR' if language == 'fr' else 'en-US'}">Merci de votre appel. Au revoir !</Say>
    <Hangup/>
</Response>"""

    return PlainTextResponse(twiml, media_type="application/xml")


@app.post("/voice/stream")
async def voice_stream(request: Request):
    """
    Endpoint pour le streaming audio en temps réel (Twilio Media Stream).
    Reçoit les chunks audio, les transcrit avec Whisper, et répond.
    """
    body = await request.body()
    # TODO: Implémenter le streaming audio temps réel
    return {"status": "ok"}


# ─── Utilitaires ──────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Détecte la langue du texte (français ou anglais)."""
    # Simple détection basée sur des mots-clés
    fr_words = ["bonjour", "merci", "oui", "non", "je", "vous", "est", "les", "des", "une", "pour", "avec"]
    en_words = ["hello", "thank", "yes", "no", "the", "is", "are", "you", "I", "we", "please", "can"]

    text_lower = text.lower()
    fr_score = sum(1 for w in fr_words if w in text_lower)
    en_score = sum(1 for w in en_words if w in text_lower)

    return "fr" if fr_score >= en_score else "en"


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Démarrage du serveur vocal sur le port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
