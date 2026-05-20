#!/usr/bin/env python3
"""
Agent Conversationnel — Clinique Dentaire Sourire
Version allégée pour Render (pas de dépendances lourdes)
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
LLM_BACKEND = os.getenv("LLM_BACKEND", "openrouter")

def call_llm(messages):
    """Appeler le LLM via API REST (pas de dépendance lourde)."""
    import urllib.request
    import urllib.parse
    
    if LLM_BACKEND == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        model = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-flash:free")
        url = "https://openrouter.ai/api/v1/chat/completions"
    elif LLM_BACKEND == "groq":
        api_key = os.getenv("GROQ_API_KEY", "")
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        url = "https://api.groq.com/openai/v1/chat/completions"
    else:
        # Fallback : réponse simple sans LLM
        return "Bonjour ! Je suis l'agent de démonstration de Clinique Dentaire Sourire. Comment puis-je vous aider aujourd'hui ?"
    
    if not api_key:
        return "⚠️ Clé API LLM non configurée. Veuillez contacter l'administrateur."
    
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 500,
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
        return f"Désolé, une erreur s'est produite. Veuillez réessayer ou nous appeler au (514) 555-0123."

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
