#!/usr/bin/env python3
"""Chatbot Factory - Agent Texte + Whisper installe a la volee"""

import os, json, logging, subprocess, sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

SYSTEM_PROMPT = "Tu es l'assistant de Clinique Dentaire Sourire a Montreal. Services: Nettoyage 150-250$, Blanchiment 400-600$, Orthodontie, Implants. Tel: (514) 555-0123. Chaleureux, concis, francais."

def call_llm(messages):
    import urllib.request
    key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 500}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
sessions = {}

class ChatReq(BaseModel):
    message: str
    session_id: str = "default"

@app.get("/") 
async def root():
    return PlainTextResponse("OK")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/chat")
async def chat(req: ChatReq):
    sid = req.session_id
    if sid not in sessions: sessions[sid] = []
    hist = sessions[sid]
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + hist[-10:] + [{"role": "user", "content": req.message}]
    resp = call_llm(msgs)
    hist += [{"role": "user", "content": req.message}, {"role": "assistant", "content": resp}]
    sessions[sid] = hist[-20:]
    return {"response": resp, "session_id": sid, "transferred": "transferer" in resp.lower()}

# ─── Vocal avec Whisper installe a la volee ──────────────────────────────────

_whisper_model = None

def ensure_whisper():
    """Installe Whisper si necessaire et charge le modele."""
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    try:
        import whisper
        logger.info("Whisper deja disponible, chargement...")
        _whisper_model = whisper.load_model("tiny")  # tiny = 75MB, beaucoup plus rapide
        return _whisper_model
    except ImportError:
        logger.info("Whisper non disponible, installation...")

    # Installer whisper + torch (CPU only, plus leger)
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--quiet",
            "openai-whisper"
        ], timeout=300)
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--quiet",
            "torch", "--index-url", "https://download.pytorch.org/whl/cpu"
        ], timeout=600)

        import whisper
        logger.info("Whisper installe! Chargement modele tiny...")
        _whisper_model = whisper.load_model("tiny")
        return _whisper_model
    except Exception as e:
        logger.error(f"Installation Whisper echouee: {e}")
        return None

@app.get("/vocal/health")
async def vh():
    has_whisper = False
    try:
        import whisper
        has_whisper = True
    except ImportError:
        pass
    return {"status": "ok", "whisper_available": has_whisper, "model_loaded": _whisper_model is not None}

@app.post("/vocal/transcribe-and-respond")
async def vocal_ep(audio: UploadFile = File(...), language: str = Form("fr"), session_id: str = Form("default")):
    import tempfile, os, base64

    model = ensure_whisper()
    if model is None:
        return {"transcription": "", "response": "Vocal non disponible. Whisper n'a pas pu etre installe.", "audio_base64": "", "language": language}

    # Sauvegarder l'audio
    suffix = ".webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lower()
        if ext in (".wav", ".mp3", ".ogg"): suffix = ext

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await audio.read())
        tmp.close()

        # Transcrire
        result = model.transcribe(tmp.name, language=language if language in ("fr", "en") else None)
        transcription = result.get("text", "").strip()

        if not transcription:
            return {"transcription": "", "response": "Je n'ai pas compris.", "audio_base64": "", "language": language}

        # Reponse LLM
        msgs = [{"role": "system", "content": "Assistant vocal clinique dentaire. Tres court (1-2 phrases). Francais."},
                {"role": "user", "content": transcription}]
        response_text = call_llm(msgs)

        # TTS edge-tts (leger, pas de PyTorch)
        audio_b64 = ""
        try:
            import edge_tts, asyncio
            voice = "fr-FR-HenriNeural" if language == "fr" else "en-US-GuyNeural"
            tts_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tts_tmp.close()
            asyncio.run(edge_tts.Communicate(response_text, voice).save(tts_tmp.name))
            with open(tts_tmp.name, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            os.unlink(tts_tmp.name)
        except:
            pass

        return {"transcription": transcription, "response": response_text, "audio_base64": audio_b64, "language": language}
    finally:
        try: os.unlink(tmp.name)
        except: pass

@app.websocket("/vocal/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.receive_bytes()
            await ws.send_json({"type": "error", "text": "Use POST"})
    except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 7860)))
