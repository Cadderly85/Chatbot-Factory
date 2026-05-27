#!/usr/bin/env python3
"""Chatbot Factory - Agent Combine Texte + Vocal (Whisper via API OpenAI)"""

import os, json, logging, tempfile, base64
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []
try:
    kb = KB_DIR / "knowledge.json"
    if kb.exists():
        with open(kb, "r", encoding="utf-8") as f:
            knowledge_docs = json.load(f)
except:
    pass

SYSTEM_PROMPT = "Tu es l'assistant de Clinique Dentaire Sourire a Montreal. Services: Nettoyage 150-250$, Blanchiment 400-600$, Orthodontie, Implants. Tel: (514) 555-0123. Chaleureux, concis, francais. Jamais de diagnostic medical."
LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")

def call_llm(messages):
    import urllib.request
    candidates = []
    if LLM_BACKEND in ("auto", "openrouter"):
        k = os.getenv("OPENROUTER_API_KEY", "")
        if k: candidates.append(("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"), "https://openrouter.ai/api/v1/chat/completions", k))
    if LLM_BACKEND in ("auto", "openai"):
        k = os.getenv("OPENAI_API_KEY", "")
        if k: candidates.append(("openai", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"), "https://api.openai.com/v1/chat/completions", k))
    if not candidates: candidates.append(("openrouter", "openrouter/owl-alpha", "https://openrouter.ai/api/v1/chat/completions", os.getenv("OPENROUTER_API_KEY", "")))
    for name, model, url, key in candidates:
        if not key: continue
        payload = {"model": model, "messages": messages, "temperature": 0.7}
        if name == "openai": payload["max_completion_tokens"] = 500
        else: payload["max_tokens"] = 500
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM {name}: {e}")
            continue
    return "Desole, erreur. Appelez (514) 555-0123."

app = FastAPI(title="Chatbot Factory - Texte + Vocal")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
sessions = {}

class ChatReq(BaseModel):
    message: str
    session_id: str = "default"

@app.get("/")
async def root():
    return PlainTextResponse("Chatbot Factory OK - Texte + Vocal")

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Clinique Dentaire Sourire", "timestamp": datetime.now().isoformat()}

@app.post("/chat")
async def chat(req: ChatReq):
    sid = req.session_id
    if sid not in sessions: sessions[sid] = []
    hist = sessions[sid]
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + hist[-10:] + [{"role": "user", "content": req.message}]
    resp = call_llm(msgs)
    hist.append({"role": "user", "content": req.message})
    hist.append({"role": "assistant", "content": resp})
    sessions[sid] = hist[-20:]
    transferred = any(kw in resp.lower() for kw in ["transferer", "humain", "transfer"])
    return {"response": resp, "session_id": sid, "transferred": transferred}

# ──────────────────────────────────────────────────────────────────────────────
# VOCAL — Whisper via API OpenAI (pas de dependance lourde)
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/vocal/health")
async def vh():
    has_openai = bool(os.getenv("OPENAI_API_KEY", ""))
    return {"status": "ok", "vocal_available": has_openai, "whisper": "api-openai" if has_openai else "unavailable"}

@app.post("/vocal/transcribe-and-respond")
async def vocal_ep(audio: UploadFile = File(...), language: str = Form("fr"), session_id: str = Form("default")):
    import urllib.request

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {"transcription": "", "response": "Vocal non disponible (pas de cle OpenAI).", "audio_base64": "", "language": language}

    # Sauvegarder l'audio en temp
    suffix = ".webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lower()
        if ext in (".wav", ".mp3", ".ogg"): suffix = ext

    audio_data = await audio.read()

    # 1. Transcrire avec Whisper API OpenAI
    try:
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="audio{suffix}"\r\n'
            f"Content-Type: audio/{suffix[1:]}\r\n\r\n"
        ).encode() + audio_data + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            transcription = result.get("text", "").strip()
    except Exception as e:
        logger.error(f"Whisper API: {e}")
        return {"transcription": "", "response": f"Erreur transcription: {str(e)[:100]}", "audio_base64": "", "language": language}

    if not transcription:
        return {"transcription": "", "response": "Je n'ai pas compris. Pouvez-vous repeter?", "audio_base64": "", "language": language}

    # 2. Repondre via LLM
    prompt = "Tu es l'assistant vocal d'une clinique dentaire. Tres court (1-2 phrases max). Chaleureux, naturel. Francais."
    msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": transcription}]
    response_text = call_llm(msgs)

    # 3. TTS avec edge-tts (leger, pas besoin de PyTorch)
    audio_b64 = ""
    try:
        import edge_tts
        import asyncio
        voice = "fr-FR-HenriNeural" if language == "fr" else "en-US-GuyNeural"
        comm = edge_tts.Communicate(response_text, voice)
        tts_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts_tmp.close()
        asyncio.run(comm.save(tts_tmp.name))
        with open(tts_tmp.name, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        os.unlink(tts_tmp.name)
    except ImportError:
        logger.warning("edge-tts non disponible")
    except Exception as e:
        logger.error(f"TTS: {e}")

    return {"transcription": transcription, "response": response_text, "audio_base64": audio_b64, "language": language}

@app.websocket("/vocal/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            await websocket.send_json({"type": "response", "text": "Utilisez POST /vocal/transcribe-and-respond"})
    except:
        pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    logger.info(f"Port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
