#!/usr/bin/env python3
"""Chatbot Factory - Agent Texte pour HF Space (vocal cote client via Web Speech API)"""

import os, json, logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
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
    logger.warning(f"KB non chargee: {e}")

# ─── System prompt ───────────────────────────────────────────────────────────

def load_system_prompt() -> str:
    p = Path(__file__).parent / "system_prompt.md"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    # Fallback
    return (
        "Tu es l'assistant de Clinique Dentaire Sourire à Montréal. "
        "Services: Nettoyage 150-250$, Blanchiment 400-600$, Orthodontie, Implants. "
        "Tel: (514) 555-0123. "
        "Chaleureux, concis (1-3 phrases), français. "
        "Jamais de diagnostic médical. Si hors sujet, propose de transférer à un humain."
    )

SYSTEM_PROMPT = load_system_prompt()

# ─── Recherche dans la base de connaissances ──────────────────────────────────

def search_knowledge(query: str, max_chars: int = 2000) -> str:
    if not knowledge_docs:
        return ""
    query_lower = query.lower()
    qwords = [w for w in query_lower.split() if len(w) > 2]
    scored = []
    for doc in knowledge_docs:
        text = json.dumps(doc, ensure_ascii=False).lower()
        score = sum(1 for w in qwords if w in text)
        if score > 0:
            scored.append((score, doc.get("text", json.dumps(doc, ensure_ascii=False))))
    scored.sort(key=lambda x: x[0], reverse=True)
    result_parts = []
    total = 0
    for _, text in scored:
        total += len(text)
        if total > max_chars:
            break
        result_parts.append(text)
    return "\n---\n".join(result_parts)

# ─── LLM avec fallback ────────────────────────────────────────────────────────

def call_llm(messages: list) -> str:
    import urllib.request

    candidates = []
    backend = os.getenv("LLM_BACKEND", "auto")

    if backend in ("auto", "openrouter"):
        key = os.getenv("OPENROUTER_API_KEY", "")
        model = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
        if key:
            candidates.append(("openrouter", model, "https://openrouter.ai/api/v1/chat/completions", key))

    if backend in ("auto", "openai"):
        key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        if key:
            candidates.append(("openai", model, "https://api.openai.com/v1/chat/completions", key))

    if not candidates:
        logger.error("Aucune clé API LLM configurée")
        return "Je suis désolé, le service est temporairement indisponible."

    for name, model, url, key in candidates:
        if not key:
            continue
        payload = {"model": model, "messages": messages, "temperature": 0.7}
        if name == "openai":
            payload["max_completion_tokens"] = 500
        else:
            payload["max_tokens"] = 500

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning(f"LLM {name} a échoué: {e}, essai suivant...")

    return "Je suis désolé, le service est temporairement indisponible."

# ─── FastAPI App ─────────────────────────────────────────────────────────────

app = FastAPI(title="Chatbot Factory")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
sessions: dict[str, list] = {}


class ChatReq(BaseModel):
    message: str
    session_id: str = "default"


@app.get("/")
async def root():
    return PlainTextResponse("OK — Chatbot Factory")


@app.get("/health")
async def health():
    return {"status": "ok", "kb_loaded": len(knowledge_docs) > 0}


@app.post("/chat")
async def chat(req: ChatReq):
    sid = req.session_id
    if sid not in sessions:
        sessions[sid] = []
    hist = sessions[sid]

    # Recherche contextuelle
    ctx = search_knowledge(req.message)
    context_msg = ""
    if ctx:
        context_msg = f"\n\nInformations pertinentes trouvées:\n{ctx}"

    # Construction des messages
    msgs = [{"role": "system", "content": SYSTEM_PROMPT + context_msg}]
    # Historique (10 derniers)
    for m in hist[-10:]:
        msgs.append(m)
    msgs.append({"role": "user", "content": req.message})

    # Appel LLM
    response_text = call_llm(msgs)

    # Sauvegarde session
    hist.append({"role": "user", "content": req.message})
    hist.append({"role": "assistant", "content": response_text})
    sessions[sid] = hist[-20:]

    transferred = any(w in response_text.lower() for w in ["transférer", "transferer", "humain", "dentiste"])

    return {
        "response": response_text,
        "session_id": sid,
        "transferred": transferred,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
