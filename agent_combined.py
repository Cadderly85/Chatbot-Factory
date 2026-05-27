#!/usr/bin/env python3
"""
Chatbot Factory - Agent Combine Texte + Vocal
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# ─── Base de connaissances ───────────────────────────────────────────────────

KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []

try:
    kb_path = KB_DIR / "knowledge.json"
    if kb_path.exists():
        with open(kb_path, "r", encoding="utf-8") as f:
            knowledge_docs = json.load(f)
        logger.info(f"KB chargee: {len(knowledge_docs)} docs")
except Exception as e:
    logger.warning(f"KB non trouvee: {e}")

# ─── System Prompt ───────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es l'assistant virtuel de Clinique Dentaire Sourire, une clinique dentaire a Montreal.

Ton style: chaleureux, concis (1-3 phrases), toujours en francais.

Services: Nettoyage (150-250$), Blanchiment (400-600$), Orthodontie, Implants, Soins d'urgence, Esthetique.

Info: 1234 Rue Saint-Jean, Montreal. Tel: (514) 555-0123. Lun-Ven 8h-18h, Sam 9h-14h.

Regles: Jamais de diagnostic medical. Proposer un humain si complexe."""

# ─── LLM ─────────────────────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")


def call_llm(messages):
    import urllib.request

    backend = (LLM_BACKEND or "").strip().lower()
    ordered = []
    if backend in ("auto", "openrouter"):
        key = os.getenv("OPENROUTER_API_KEY", "")
        if key:
            ordered.append(("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"),
                            "https://openrouter.ai/api/v1/chat/completions", key))
    if backend in ("auto", "openai"):
        key = os.getenv("OPENAI_API_KEY", "")
        if key:
            ordered.append(("openai", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
                            "https://api.openai.com/v1/chat/completions", key))
    if not ordered:
        ordered = [("openrouter", "openrouter/owl-alpha", "https://openrouter.ai/api/v1/chat/completions", os.getenv("OPENROUTER_API_KEY", ""))]

    for name, model, url, key in ordered:
        if not key:
            continue
        payload = {"model": model, "messages": messages, "temperature": 0.7,
                   "max_tokens": 500 if name != "openai" else None}
        if name == "openai":
            payload["max_completion_tokens"] = 500
            del payload["max_tokens"]
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM {name}: {e}")
            continue
    return "Desole, erreur. Reessappelez (514) 555-0123."


def search_knowledge(query):
    if not knowledge_docs:
        return ""
    ql = query.lower()
    results = []
    for doc in knowledge_docs:
        c = doc.get("content", "").lower()
        t = doc.get("title", "").lower()
        score = sum(1 for w in ql.split() if w in c or w in t)
        if score > 0:
            results.append((score, doc["content"]))
    results.sort(reverse=True, key=lambda x: x[0])
    return "\n\n".join(r[1] for r in results[:3]) if results else ""


# ─── App ─────────────────────────────────────────────────────────────────────

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
    return {"status": "ok", "agent": "Clinique Dentaire Sourire",
            "timestamp": datetime.now().isoformat(), "docs": len(knowledge_docs)}


@app.post("/chat")
async def chat(req: ChatReq):
    sid = req.session_id
    if sid not in sessions:
        sessions[sid] = []
    hist = sessions[sid]
    ctx = search_knowledge(req.message)
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if ctx:
        msgs.append({"role": "system", "content": f"Contexte:\n{ctx}"})
    for m in hist[-10:]:
        msgs.append(m)
    msgs.append({"role": "user", "content": req.message})
    resp = call_llm(msgs)
    hist.append({"role": "user", "content": req.message})
    hist.append({"role": "assistant", "content": resp})
    sessions[sid] = hist[-20:]
    transferred = any(kw in resp.lower() for kw in ["transferer", "humain", "transfer"])
    return {"response": resp, "session_id": sid, "transferred": transferred}


# ─── Vocal (si Whisper + edge-tts disponibles) ──────────────────────────────

whisper_model = None
vocal_available = False

try:
    import whisper
    import edge_tts
    vocal_available = True
    logger.info("Vocal disponible (whisper + edge-tts)")
except ImportError:
    logger.info("Vocal non disponible (whisper/edge-tts non installes)")


@app.get("/vocal/health")
async def vocal_health():
    return {"status": "ok", "vocal_available": vocal_available, "whisper_loaded": whisper_model is not None}


@app.post("/vocal/transcribe-and-respond")
async def vocal_endpoint(audio: UploadFile = File(...), language: str = Form("fr"), session_id: str = Form("default")):
    if not vocal_available:
        return {"transcription": "", "response": "Vocal non disponible. Utilisez le chat texte.", "audio_base64": "", "language": language}

    import tempfile, base64

    # Whisper lazy load
    global whisper_model
    if whisper_model is None:
        logger.info("Chargement Whisper...")
        whisper_model = whisper.load_model("base")
        logger.info("Whisper OK")

    suffix = ".webm"
    if audio.filename:
        ext = Path(audio.filename).suffix.lower()
        if ext in (".wav", ".mp3", ".ogg"):
            suffix = ext

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(await audio.read())
        tmp.close()

        result = whisper_model.transcribe(tmp.name)
        transcription = result.get("text", "").strip()

        if not transcription:
            return {"transcription": "", "response": "Je n'ai pas compris. Pouvez-vous repeter?", "audio_base64": "", "language": language}

        # LLM
        prompt = "Tu es l'assistant vocal d'une clinique dentaire. Tres court (1-2 phrases). Chaleureux. Francais."
        msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": transcription}]
        response_text = call_llm(msgs)

        # TTS
        audio_b64 = ""
        try:
            import asyncio
            voice = "fr-FR-HenriNeural" if language == "fr" else "en-US-GuyNeural"
            proc = edge_tts.Communicate(response_text, voice)
            tts_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tts_tmp.close()
            asyncio.run(proc.save(tts_tmp.name))
            with open(tts_tmp.name, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            os.unlink(tts_tmp.name)
        except Exception as e:
            logger.error(f"TTS: {e}")

        return {"transcription": transcription, "response": response_text, "audio_base64": audio_b64, "language": language}
    finally:
        try:
            os.unlink(tmp.name)
        except:
            pass


@app.websocket("/vocal/ws")
async def vocal_ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_bytes()
            await websocket.send_json({"type": "response", "text": "Vocal WebSocket disponible. Utilisez POST /vocal/transcribe-and-respond."})
    except:
        pass


# Ne pas utiliser __main__ - HF lance via uvicorn
# if __name__ == "__main__":
#     import uvicorn
#     port = int(os.getenv("PORT", 7860))
#     uvicorn.run(app, host="0.0.0.0", port=port)
