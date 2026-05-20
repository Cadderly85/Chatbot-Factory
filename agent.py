# Chatbot Factory — Agent de test
# Version simplifiée pour déploiement initial sur Render

import os
import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Chatbot Factory — Agent de test")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """Tu es l'assistant virtuel de démonstration de Chatbot Factory.
Tu es en mode test — les intégrations complètes (Google Sheets, Calendrier, CRM) seront ajoutées bientôt.

Pour l'instant, tu peux :
- Expliquer ce que fait Chatbot Factory
- Répondre aux questions sur le projet
- Guider les utilisateurs

Ton ton est professionnel mais accessible, en français."""

sessions = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    session_id: str

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id

    if session_id not in sessions:
        sessions[session_id] = []

    history = sessions[session_id]
    history.append({"role": "user", "content": request.message})

    # Réponse de test simple
    response_text = (
        f"🤖 Bonjour ! Je suis l'agent de démonstration de Chatbot Factory.\n\n"
        f"Tu as dit : \"{request.message}\"\n\n"
        f"Pour l'instant je suis en mode test. Bientôt je pourrai :\n"
        f"• Répondre aux questions de tes clients 24/7\n"
        f"• Prendre des rendez-vous\n"
        f"• Qualifier des leads\n"
        f"• M'intégrer à ton CRM et ton calendrier\n\n"
        f"Reste à l'écoute pour la suite ! 🚀"
    )

    history.append({"role": "assistant", "content": response_text})
    sessions[session_id] = history[-10:]

    return ChatResponse(response=response_text, session_id=session_id)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agent": "Chatbot Factory — Test",
        "timestamp": datetime.now().isoformat(),
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
