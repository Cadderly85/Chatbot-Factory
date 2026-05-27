#!/usr/bin/env python3
"""Chatbot Factory - Agent Texte + Vocal (Whisper API OpenAI)"""

import os, json, logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

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

app = FastAPI(title="Chatbot Factory")
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

# ─── Vocal ──────────────────────────────────────────────────────────────────

@app.get("/vocal/health")
async def vh():
    return {"status": "ok", "whisper": "api-openai" if os.getenv("OPENAI_API_KEY") else "none"}

@app.post("/vocal/transcribe-and-respond")
async def vocal_ep(audio: UploadFile = File(...), language: str = Form("fr"), session_id: str = Form("default")):
    import urllib.request, tempfile, os

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {"transcription": "", "response": "Vocal non disponible.", "audio_base64": "", "language": language}

    suffix = ".webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lower()
        if ext in (".wav", ".mp3", ".ogg"): suffix = ext

    data = await audio.read()

    # Whisper API OpenAI
    boundary = "----CF"
    body = f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a{suffix}\"\r\nContent-Type: audio/{suffix[1:]}\r\n\r\n".encode() + data + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-1\r\n--{boundary}--\r\n".encode()

    try:
        req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            transcription = result.get("text", "").strip()
    except Exception as e:
        return {"transcription": "", "response": f"Erreur: {str(e)[:80]}", "audio_base64": "", "language": language}

    if not transcription:
        return {"transcription": "", "response": "Je n'ai pas compris.", "audio_base64": "", "language": language}

    # Reponse LLM
    msgs = [{"role": "system", "content": "Assistant vocal clinique dentaire. Tres court (1-2 phrases). Francais."},
            {"role": "user", "content": transcription}]
    response_text = call_llm(msgs)

    # TTS edge-tts
    audio_b64 = ""
    try:
        import edge_tts, asyncio
        voice = "fr-FR-HenriNeural" if language == "fr" else "en-US-GuyNeural"
        tmp2 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp2.close()
        asyncio.run(edge_tts.Communicate(response_text, voice).save(tmp2.name))
        with open(tmp2.name, "rb") as f:
            audio_b64 = __import__("base64").b64encode(f.read()).decode()
        os.unlink(tmp2.name)
    except:
        pass

    return {"transcription": transcription, "response": response_text, "audio_base64": audio_b64, "language": language}

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
