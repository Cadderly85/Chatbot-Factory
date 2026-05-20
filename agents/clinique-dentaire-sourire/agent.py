#!/usr/bin/env python3
"""
Agent Conversationnel — Clinique Dentaire Sourire
Généré automatiquement par Chatbot Factory
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
logger = logging.getLogger("clinique_dentaire_sourire_agent")

# Configuration
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_base"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")

if LLM_BACKEND == "ollama":
    from langchain_community.chat_models import ChatOllama
    llm = ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"), base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
elif LLM_BACKEND == "groq":
    from langchain_groq import ChatGroq
    llm = ChatGroq(model=os.getenv("GROQ_MODEL", "llama-3.1-70b-versatile"))
elif LLM_BACKEND == "openrouter":
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        model=os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct:free"),
    )

# Base de connaissances (RAG)
logger.info("Chargement de la base de connaissances...")
try:
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectorstore = Chroma(
        persist_directory=str(KNOWLEDGE_DIR / "chroma"),
        embedding_function=embeddings,
    )
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    logger.info(f"✅ Base chargée : {vectorstore._collection.count()} documents")
except Exception as e:
    logger.warning(f"⚠️ Base de connaissances non disponible: {e}")
    retriever = None

# System Prompt
SYSTEM_PROMPT = """# Agent Conversationnel — Clinique Dentaire Sourire

## Identité
Tu es l'assistant virtuel de **Clinique Dentaire Sourire**, une entreprise du secteur **Santé / Clinique médicale / Dentaire**.
Ton ton est **chaleureux et accessible**.
Valeurs : bienveillance, expertise, confort, confiance

## Services offerts
- Nettoyage dentaire
- Blanchiment
- Orthodontie
- Implants
- Soins d'urgence
- Dentisterie esthétique

## Langue
Tu réponds toujours en français.

## Tes responsabilités
1. Répondre aux questions des clients sur les services, horaires, politiques, etc.
2. Qualifier les leads : obtenir le nom, courriel et raison de la demande.
3. Transférer à un humain pour les demandes complexes ou urgentes.

## Règles de comportement
- Sois concis mais complet.
- Ne jamais inventer d'informations. Si tu ne sais pas, dis-le.
- Ne jamais donner de diagnostic médical.
- Toujours terminer par une question ou une suggestion.
"""

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

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id
    if session_id not in sessions:
        sessions[session_id] = []

    chat_history = sessions[session_id]

    context = ""
    if retriever:
        try:
            docs = retriever.get_relevant_documents(request.message)
            context = "\n\n".join(doc.page_content for doc in docs)
        except:
            pass

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        messages.append({"role": "system", "content": f"Informations pertinentes:\n\n{context}"})

    for msg in chat_history[-10:]:
        messages.append(msg)
    messages.append({"role": "user", "content": request.message})

    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    langchain_messages = []
    for m in messages:
        if m["role"] == "system":
            langchain_messages.append(SystemMessage(content=m["content"]))
        elif m["role"] == "user":
            langchain_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            langchain_messages.append(AIMessage(content=m["content"]))

    result = llm.invoke(langchain_messages)
    response_text = result.content

    chat_history.append({"role": "user", "content": request.message})
    chat_history.append({"role": "assistant", "content": response_text})
    sessions[session_id] = chat_history[-20:]

    transfer_keywords = ["transférer", "humain", "parler à quelqu'un", "transfer", "human"]
    transferred = any(kw in response_text.lower() for kw in transfer_keywords)

    return ChatResponse(response=response_text, session_id=session_id, transferred=transferred)

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "Clinique Dentaire Sourire"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
