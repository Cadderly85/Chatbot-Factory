import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import json, urllib.request

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SYSTEM_PROMPT = "Tu es l'assistant de Clinique Dentaire Sourire a Montreal. Services: Nettoyage 150-250$, Blanchiment 400-600$, Orthodontie, Implants. Tel: (514) 555-0123. Sois chaleureux et concis."

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
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": req.message}]
    
    # Essayer OpenRouter
    key = os.getenv("OPENROUTER_API_KEY", "")
    if key:
        try:
            payload = json.dumps({"model": "openrouter/owl-alpha", "messages": msgs, "temperature": 0.7, "max_tokens": 500}).encode()
            request = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=payload,
                                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return {"response": result["choices"][0]["message"]["content"], "session_id": req.session_id, "transferred": False}
        except Exception as e:
            pass
    
    # Essayer OpenAI
    key = os.getenv("OPENAI_API_KEY", "")
    if key:
        try:
            payload = json.dumps({"model": "gpt-5.4-mini", "messages": msgs, "temperature": 0.7, "max_completion_tokens": 500}).encode()
            request = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload,
                                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                return {"response": result["choices"][0]["message"]["content"], "session_id": req.session_id, "transferred": False}
        except Exception as e:
            pass
    
    return {"response": "Bonjour! Je suis l'assistant de la Clinique Dentaire Sourire. Comment puis-je vous aider? (LLM indisponible - demo mode)", "session_id": req.session_id, "transferred": False}
