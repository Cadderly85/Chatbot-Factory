#!/usr/bin/env python3
"""Chatbot Factory - Agent Texte uniquement (vocal gerer cote client)"""

import os, json, logging
from datetime import datetime
from fastapi import FastAPI
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 7860)))
