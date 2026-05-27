#!/usr/bin/env python3
"""
Chatbot Factory - Agent Combine Texte + Vocal
===============================================
FastAPI agent avec endpoints:
  POST /chat                         - Chat texte
  GET  /health                       - Health check
  POST /vocal/transcribe-and-respond - Chat vocal (Whisper + TTS)
  GET  /vocal/health                 - Health check vocal
  WS   /vocal/ws                     - WebSocket vocal temps reel
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# ─── Base de connaissances ───────────────────────────────────────────────────

KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []

try:
    with open(KB_DIR / "knowledge.json", "r", encoding="utf-8") as f:
        knowledge_docs = json.load(f)
    print(f"OK: Base de connaissances chargee: {len(knowledge_docs)} documents")
except:
    logger.warning("knowledge.json non trouve")

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es l'assistant virtuel de **Clinique Dentaire Sourire**, une clinique dentaire a Montreal.

## Ton style
- Chaleureux et accessible
- Concis mais complet (1-3 phrases max)
- Toujours en francais
- Termine par une question ou appel a l'action

## Services offerts
- Nettoyage dentaire et examen complet (150$-250$)
- Blanchiment dentaire (400$-600$)
- Orthodontie (broches et Invisalign)
- Implants dentaires
- Soins d'urgence dentaire
- Dentisterie esthetique (facettes, couronnes)

## Informations pratiques
- Adresse : 1234 Rue Saint-Jean, Montreal, QC H2X 1Y5
- Telephone : (514) 555-0123
- Courriel : info@cliniquesourire.ca
- Horaires : Lundi au vendredi 8h-18h, Samedi 9h-14h

## Regles importantes
- Ne JAMAIS donner de diagnostic medical
- Ne JAMAIS recommander un traitement specifique
- Pour les questions complexes, proposer de transferer a un humain"""

# ─── Configuration LLM ──────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")


def call_llm(messages):
    """Appeler le LLM via API REST avec fallback."""
    import urllib.request

    backend = (LLM_BACKEND or "").strip().lower()

    def candidates():
        if backend == "auto":
            ordered = []
            if os.getenv("OPENROUTER_API_KEY", ""):
                ordered.append(("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"),
                                "https://openrouter.ai/api/v1/chat/completions", os.getenv("OPENROUTER_API_KEY", "")))
            if os.getenv("OPENAI_API_KEY", ""):
                ordered.append(("openai", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
                                "https://api.openai.com/v1/chat/completions", os.getenv("OPENAI_API_KEY", "")))
            if not ordered:
                ordered = [
                    ("openrouter", "openrouter/owl-alpha", "https://openrouter.ai/api/v1/chat/completions", ""),
                    ("openai", "gpt-5.4-mini", "https://api.openai.com/v1/chat/completions", ""),
                ]
            return ordered
        return []

    for backend_name, model, url, api_key in candidates():
        if not api_key:
            continue
        payload_dict = {"model": model, "messages": messages, "temperature": 0.7}
        if backend_name == "openai":
            payload_dict["max_completion_tokens"] = 500
        else:
            payload_dict["max_tokens"] = 500

        payload = json.dumps(payload_dict).encode()
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=payload, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Erreur LLM {backend_name}: {e}")
            continue

    return "Desole, une erreur s'est produite. Veuillez reessayer ou nous appeler au (514) 555-0123."


def search_knowledge(query):
    """Recherche simple dans la base de connaissances."""
    if not knowledge_docs:
        return ""
    query_lower = query.lower()
    results = []
    for doc in knowledge_docs:
        content = doc.get("content", "").lower()
        title = doc.get("title", "").lower()
        score = sum(1 for word in query_lower.split() if word in content or word in title)
        if score > 0:
            results.append((score, doc["content"]))
    results.sort(reverse=True, key=lambda x: x[0])
    if results:
        return "\n\n".join(r[1] for r in results[:3])
    return ""


# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory - Clinique Dentaire Sourire")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

sessions = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str
    session_id: str
    transferred: bool = False


# ─── Endpoints Texte ─────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return PlainTextResponse("Chatbot Factory - Agent Texte + Vocal. /chat (POST), /vocal/transcribe-and-respond (POST)")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "Clinique Dentaire Sourire",
        "timestamp": datetime.now().isoformat(),
        "docs": len(knowledge_docs),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id

    if session_id not in sessions:
        sessions[session_id] = []

    chat_history = sessions[session_id]
    context = search_knowledge(request.message)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"Informations pertinentes:\n\n{context}"})
    for msg in chat_history[-10:]:
        messages.append(msg)
    messages.append({"role": "user", "content": request.message})

    response_text = call_llm(messages)

    chat_history.append({"role": "user", "content": request.message})
    chat_history.append({"role": "assistant", "content": response_text})
    sessions[session_id] = chat_history[-20:]

    transfer_keywords = ["transferer", "humain", "parler a quelqu'un", "transfer", "human"]
    transferred = any(kw in response_text.lower() for kw in transfer_keywords)

    return ChatResponse(response=response_text, session_id=session_id, transferred=transferred)


# ─── Endpoints Vocaux ────────────────────────────────────────────────────────

whisper_model = None


def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        import whisper
        model_name = os.getenv("WHISPER_MODEL", "base")
        logger.info(f"Chargement Whisper: {model_name}")
        whisper_model = whisper.load_model(model_name)
        logger.info("Whisper charge")
    return whisper_model


def get_vocal_system_prompt(language: str = "fr") -> str:
    if language == "fr":
        return """Tu es l'assistant vocal d'une clinique dentaire. Tu reponds comme une vraie personne au telephone.
Regles:
- Reponses TRES COURTES: 1 a 2 phrases maximum
- Chaleureux, naturel et professionnel
- Si la demande est floue, pose UNE question simple
- Ne donne jamais de diagnostic medical
- Repons en francais clair et simple
- Parle comme un assistant de clinique, pas comme un robot
Tu aides surtout pour: rendez-vous, horaires, services, coordonnees, et orientation."""
    else:
        return """You are the voice assistant for a dental clinic. Speak like a real person on the phone.
Rules:
- VERY SHORT answers: 1 to 2 sentences maximum
- Warm, natural, professional tone
- If unclear, ask ONE simple question
- Never give medical diagnoses
- Answer in clear, simple English
- Sound like a clinic assistant, not a robot"""


@app.get("/vocal/health")
async def vocal_health():
    return {
        "status": "ok",
        "service": "vocal_api",
        "whisper_loaded": whisper_model is not None,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/vocal/transcribe-and-respond")
async def transcribe_and_respond(
    audio: UploadFile = File(...),
    language: str = Form("fr"),
    session_id: str = Form("default"),
):
    """Transcrit l'audio avec Whisper, repond via LLM, et renvoie l'audio TTS."""
    import tempfile
    import base64

    suffix = ".webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lower()
        if ext in (".wav", ".mp3", ".ogg", ".m4a"):
            suffix = ext

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await audio.read()
        tmp_file.write(content)
        tmp_file.close()

        model = get_whisper_model()
        result = model.transcribe(tmp_file.name, language=language if language in ("fr", "en") else None)
        transcription = result.get("text", "").strip()

        if not transcription:
            return {"transcription": "", "response": "Je n'ai pas bien compris. Pouvez-vous repeter?", "audio_base64": "", "language": language}

        system_prompt = get_vocal_system_prompt(language)
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": transcription}]

        vocal_sessions = sessions.setdefault(f"vocal_{session_id}", [])
        for msg in vocal_sessions[-6:]:
            messages.insert(1, msg)

        response_text = call_llm(messages)

        vocal_sessions.append({"role": "user", "content": transcription})
        vocal_sessions.append({"role": "assistant", "content": response_text})
        sessions[f"vocal_{session_id}"] = vocal_sessions[-10:]

        audio_base64 = ""
        try:
            import asyncio
            voice_fr = os.getenv("TTS_VOICE_FR", "fr-FR-HenriNeural")
            voice_en = os.getenv("TTS_VOICE_EN", "en-US-GuyNeural")
            voice = voice_fr if language == "fr" else voice_en

            proc = edge_tts.Communicate(response_text, voice)
            tts_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tts_tmp.close()
            asyncio.run(proc.save(tts_tmp.name))
            with open(tts_tmp.name, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode()
            os.unlink(tts_tmp.name)
        except Exception as e:
            logger.error(f"Erreur TTS: {e}")

        return {"transcription": transcription, "response": response_text, "audio_base64": audio_base64, "language": language}

    finally:
        try:
            os.unlink(tmp_file.name)
        except:
            pass


@app.websocket("/vocal/ws")
async def websocket_endpoint(websocket: WebSocket):
    import base64
    import tempfile

    await websocket.accept()
    ws_session_id = f"ws_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        while True:
            data = await websocket.receive_bytes()
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
            tmp_file.write(data)
            tmp_file.close()

            try:
                model = get_whisper_model()
                result = model.transcribe(tmp_file.name, language="fr")
                transcription = result.get("text", "").strip()

                await websocket.send_json({"type": "transcription", "text": transcription})

                if transcription:
                    system_prompt = get_vocal_system_prompt("fr")
                    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": transcription}]
                    response_text = call_llm(messages)

                    audio_base64 = ""
                    try:
                        import asyncio
                        proc = edge_tts.Communicate(response_text, os.getenv("TTS_VOICE_FR", "fr-FR-HenriNeural"))
                        tts_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                        tts_tmp.close()
                        asyncio.run(proc.save(tts_tmp.name))
                        with open(tts_tmp.name, "rb") as f:
                            audio_base64 = base64.b64encode(f.read()).decode()
                        os.unlink(tts_tmp.name)
                    except:
                        pass

                    await websocket.send_json({"type": "response", "text": response_text, "audio_base64": audio_base64})
            finally:
                try:
                    os.unlink(tmp_file.name)
                except:
                    pass
    except:
        pass


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
