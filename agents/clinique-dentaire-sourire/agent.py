#!/usr/bin/env python3
"""
Agent Conversationnel — Clinique Dentaire Sourire
Version Render légère, avec fallback LLM auto.

Ordre LLM:
  1) OpenRouter (openrouter/owl-alpha)
  2) OpenAI (gpt-5.4-mini)
  3) Groq (si configuré)
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# Charger la base de connaissances en mémoire (pas de ChromaDB)
KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []

try:
    with open(KB_DIR / "knowledge.json", "r", encoding="utf-8") as f:
        knowledge_docs = json.load(f)
    print(f"✅ Base de connaissances chargée: {len(knowledge_docs)} documents")
except:
    logger.warning("⚠️ knowledge.json non trouvé")

# System Prompt
SYSTEM_PROMPT = """Tu es l'assistant virtuel de **Clinique Dentaire Sourire**, une clinique dentaire à Montréal.

## Ton style
- Chaleureux et accessible
- Concis mais complet
- Toujours en français

## Services offerts
- Nettoyage dentaire et examen complet (150$-250$)
- Blanchiment dentaire (400$-600$)
- Orthodontie (broches et Invisalign)
- Implants dentaires
- Soins d'urgence dentaire
- Dentisterie esthétique (facettes, couronnes)

## Informations pratiques
- Adresse : 1234 Rue Saint-Jean, Montréal, QC H2X 1Y5
- Téléphone : (514) 555-0123
- Courriel : info@cliniquesourire.ca
- Horaires : Lundi au vendredi 8h-18h, Samedi 9h-14h

## Règles importantes
- Ne JAMAIS donner de diagnostic médical
- Ne JAMAIS recommander un traitement spécifique
- Pour les questions complexes, proposer de transférer à un humain
- Toujours terminer par une question ou un appel à l'action"""

# Configuration LLM
LLM_BACKEND = os.getenv("LLM_BACKEND", "auto")

def call_llm(messages):
    """Appeler le LLM via API REST avec fallback OpenRouter -> OpenAI -> Groq."""
    import urllib.request
    import urllib.parse

    backend = (LLM_BACKEND or "").strip().lower()

    def candidates():
        if backend == "auto":
            ordered = []
            if os.getenv("OPENROUTER_API_KEY", ""):
                ordered.append(("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"), "https://openrouter.ai/api/v1/chat/completions", os.getenv("OPENROUTER_API_KEY", "")))
            if os.getenv("OPENAI_API_KEY", ""):
                ordered.append(("openai", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"), "https://api.openai.com/v1/chat/completions", os.getenv("OPENAI_API_KEY", "")))
            if os.getenv("GROQ_API_KEY", ""):
                ordered.append(("groq", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"), "https://api.groq.com/openai/v1/chat/completions", os.getenv("GROQ_API_KEY", "")))
            if not ordered:
                ordered = [
                    ("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"), "https://openrouter.ai/api/v1/chat/completions", os.getenv("OPENROUTER_API_KEY", "")),
                    ("openai", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"), "https://api.openai.com/v1/chat/completions", os.getenv("OPENAI_API_KEY", "")),
                    ("groq", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"), "https://api.groq.com/openai/v1/chat/completions", os.getenv("GROQ_API_KEY", "")),
                ]
            return ordered
        if backend == "openrouter":
            return [("openrouter", os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"), "https://openrouter.ai/api/v1/chat/completions", os.getenv("OPENROUTER_API_KEY", ""))]
        if backend == "openai":
            return [("openai", os.getenv("OPENAI_MODEL", "gpt-5.4-mini"), "https://api.openai.com/v1/chat/completions", os.getenv("OPENAI_API_KEY", ""))]
        if backend == "groq":
            return [("groq", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"), "https://api.groq.com/openai/v1/chat/completions", os.getenv("GROQ_API_KEY", ""))]
        return []

    for backend_name, model, url, api_key in candidates():
        if not api_key:
            continue

        payload_dict = {
            "model": model,
            "messages": messages,
            "temperature": 0.7,
        }
        if backend_name == "openai":
            payload_dict["max_completion_tokens"] = 500
        else:
            payload_dict["max_tokens"] = 500

        payload = json.dumps(payload_dict).encode()
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
            body_text = ""
            if hasattr(e, "read"):
                try:
                    body_text = e.read().decode(errors="replace")
                except Exception:
                    body_text = ""
            logger.error(f"Erreur LLM {backend_name}: {e} body={body_text}")
            continue

    return f"Désolé, je n'ai pas pu joindre le modèle de réponse. Veuillez réessayer ou nous appeler au (514) 555-0123."

# FastAPI
app = FastAPI(title="Agent — Clinique Dentaire Sourire")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

sessions = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str
    transferred: bool = False

def search_knowledge(query):
    """Recherche simple dans la base de connaissances."""
    if not knowledge_docs:
        return ""
    
    query_lower = query.lower()
    results = []
    
    for doc in knowledge_docs:
        content = doc.get("content", "").lower()
        title = doc.get("title", "").lower()
        
        # Score simple : nombre de mots de la requête trouvés
        score = sum(1 for word in query_lower.split() if word in content or word in title)
        if score > 0:
            results.append((score, doc["content"]))
    
    results.sort(reverse=True, key=lambda x: x[0])
    
    if results:
        return "\n\n".join(r[1] for r in results[:3])
    return ""

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id
    
    if session_id not in sessions:
        sessions[session_id] = []
    
    chat_history = sessions[session_id]
    
    # Rechercher dans la base de connaissances
    context = search_knowledge(request.message)
    
    # Construire les messages
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if context:
        messages.append({"role": "system", "content": f"Informations pertinentes:\n\n{context}"})
    
    for msg in chat_history[-10:]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": request.message})
    
    # Appeler le LLM
    response_text = call_llm(messages)
    
    chat_history.append({"role": "user", "content": request.message})
    chat_history.append({"role": "assistant", "content": response_text})
    sessions[session_id] = chat_history[-20:]
    
    transfer_keywords = ["transférer", "humain", "parler à quelqu'un", "transfer", "human"]
    transferred = any(kw in response_text.lower() for kw in transfer_keywords)
    
    return ChatResponse(
        response=response_text,
        session_id=session_id,
        transferred=transferred
    )

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "Clinique Dentaire Sourire",
        "timestamp": datetime.now().isoformat(),
        "docs": len(knowledge_docs),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
