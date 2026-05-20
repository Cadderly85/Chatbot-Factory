#!/usr/bin/env python3
"""
Chatbot Factory — Agent Generator
===================================
Lit les réponses client depuis un Google Sheet, scrape leur site web,
génère la base de connaissances, et produit un agent conversationnel
prêt à déployer.

Usage:
    python generate_agent.py --sheet-id <GOOGLE_SHEET_ID> --client-name <NOM>

Dépendances:
    pip install gspread google-auth requests beautifulsoup4 \
                langchain chromadb sentence-transformers \
                fastapi uvicorn pydantic python-dotenv
"""

import os
import re
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ─── Configuration ────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_agent")

# Chemins de sortie
OUTPUT_BASE = Path("generated_agents")
TEMPLATES_DIR = Path("templates")

# ─── ÉTAPE 1 — Lecture du Google Sheet ────────────────────────────────────────

def read_client_sheet(sheet_id: str) -> dict:
    """
    Lit les réponses du client depuis le Google Sheet d'onboarding.
    Retourne un dictionnaire structuré avec toutes les réponses.
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("Installe gspread: pip install gspread google-auth")
        raise

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    creds_path = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    gc = gspread.authorize(creds)

    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Toutes les lignes : question | réponse
    rows = worksheet.get_all_records()

    client_data = {
        "raw_responses": rows,
        "metadata": {},
        "services": [],
        "faq": [],
        "integrations": {},
        "branding": {},
    }

    # Parser les réponses en sections logiques
    for row in rows:
        question = str(row.get("Question", "")).strip().lower()
        reponse = str(row.get("Réponse", row.get("response", ""))).strip()

        if not reponse:
            continue

        # Métadonnées de base
        if any(kw in question for kw in ["nom", "entreprise", "company", "name"]):
            client_data["metadata"]["company_name"] = reponse
        elif any(kw in question for kw in ["secteur", "industrie", "domain", "industry"]):
            client_data["metadata"]["industry"] = reponse
        elif any(kw in question for kw in ["site web", "website", "url", "site internet"]):
            client_data["metadata"]["website"] = reponse
        elif any(kw in question for kw in ["courriel", "email", "contact"]):
            client_data["metadata"]["email"] = reponse
        elif any(kw in question for kw in ["téléphone", "phone", "tel"]):
            client_data["metadata"]["phone"] = reponse
        elif any(kw in question for kw in ["adresse", "address", "location"]):
            client_data["metadata"]["address"] = reponse

        # Services
        elif any(kw in question for kw in ["service", "produit", "product", "offre"]):
            client_data["services"].append(reponse)

        # FAQ
        elif any(kw in question for kw in ["faq", "question fréquente", "common question"]):
            if ":" in reponse or "?" in reponse:
                client_data["faq"].append(reponse)

        # Intégrations
        elif any(kw in question for kw in ["crm"]):
            client_data["integrations"]["crm"] = reponse
        elif any(kw in question for kw in ["calendrier", "calendly", "appointment", "booking"]):
            client_data["integrations"]["calendar"] = reponse
        elif any(kw in question for kw in ["canal", "channel", "messenger", "whatsapp"]):
            client_data["integrations"]["channels"] = reponse

        # Branding
        elif any(kw in question for kw in ["ton", "tone", "style", "personnalité"]):
            client_data["branding"]["tone"] = reponse
        elif any(kw in question for kw in ["bilingue", "bilingual", "langue", "language"]):
            client_data["branding"]["bilingual"] = reponse.lower() in ["oui", "yes", "true"]
        elif any(kw in question for kw in ["valeurs", "values"]):
            client_data["branding"]["values"] = reponse
        elif any(kw in question for kw in ["limites", "restrictions", "ne pas"]):
            client_data["branding"]["restrictions"] = reponse

    logger.info(f"✅ Données client lues : {client_data['metadata'].get('company_name', 'Inconnu')}")
    return client_data


# ─── ÉTAPE 2 — Scraping du site web ──────────────────────────────────────────

def scrape_website(url: str, max_pages: int = 30) -> list[dict]:
    """
    Scrape le site web du client et retourne une liste de documents.
    Chaque document = {"url": ..., "title": ..., "content": ...}
    """
    if not url.startswith("http"):
        url = f"https://{url}"

    logger.info(f"🔍 Scraping de {url} (max {max_pages} pages)...")

    documents = []
    visited = set()
    to_visit = [url]
    base_domain = re.match(r"https?://[^/]+", url).group()

    headers = {
        "User-Agent": "ChatbotFactory/1.0 (https://chatbotfactory.xyz)"
    }

    while to_visit and len(visited) < max_pages:
        current_url = to_visit.pop(0)
        if current_url in visited:
            continue

        try:
            resp = requests.get(current_url, headers=headers, timeout=10)
            resp.raise_for_status()
            visited.add(current_url)

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extraire le texte pertinent (pas les scripts, styles, nav, footer)
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title else current_url
            content = soup.get_text(separator="\n", strip=True)

            # Nettoyer les lignes vides multiples
            content = re.sub(r"\n{3,}", "\n\n", content)

            if len(content) > 100:  # Ignorer les pages vides
                documents.append({
                    "url": current_url,
                    "title": title,
                    "content": content[:8000],  # Limiter la taille
                })

            # Découvrir les liens internes
            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = requests.compat.urljoin(current_url, href)
                if full_url.startswith(base_domain) and full_url not in visited:
                    # Filtrer les URLs non pertinentes
                    if not any(ext in full_url for ext in [".pdf", ".jpg", ".png", ".css", ".js"]):
                        to_visit.append(full_url)

        except Exception as e:
            logger.warning(f"⚠️ Erreur scraping {current_url}: {e}")
            continue

    logger.info(f"✅ {len(documentes)} pages scrapées avec succès")
    return documents


# ─── ÉTAPE 3 — Création de la base de connaissances ──────────────────────────

def create_knowledge_base(client_data: dict, web_documents: list[dict], output_dir: Path) -> Path:
    """
    Crée la base de connaissance à partir des réponses client + site web.
    Retourne le chemin vers le fichier de connaissances.
    """
    kb_dir = output_dir / "knowledge_base"
    kb_dir.mkdir(parents=True, exist_ok=True)

    knowledge_chunks = []

    # 1. Informations de l'entreprise
    company = client_data["metadata"].get("company_name", "L'entreprise")
    industry = client_data["metadata"].get("industry", "")

    info_text = f"# À propos de {company}\n\n"
    info_text += f"Secteur : {industry}\n"
    if client_data["metadata"].get("address"):
        info_text += f"Adresse : {client_data['metadata']['address']}\n"
    if client_data["metadata"].get("phone"):
        info_text += f"Téléphone : {client_data['metadata']['phone']}\n"
    if client_data["metadata"].get("email"):
        info_text += f"Courriel : {client_data['metadata']['email']}\n"
    if client_data["metadata"].get("website"):
        info_text += f"Site web : {client_data['metadata']['website']}\n"

    knowledge_chunks.append({
        "source": "client_info",
        "title": f"Informations sur {company}",
        "content": info_text,
    })

    # 2. Services
    if client_data["services"]:
        services_text = f"# Services offerts par {company}\n\n"
        for service in client_data["services"]:
            services_text += f"- {service}\n"

        knowledge_chunks.append({
            "source": "services",
            "title": "Services",
            "content": services_text,
        })

    # 3. FAQ
    if client_data["faq"]:
        faq_text = "# Foire aux questions\n\n"
        for item in client_data["faq"]:
            faq_text += f"{item}\n\n"

        knowledge_chunks.append({
            "source": "faq",
            "title": "FAQ",
            "content": faq_text,
        })

    # 4. Contenu du site web
    for doc in web_documents:
        knowledge_chunks.append({
            "source": doc["url"],
            "title": doc["title"],
            "content": doc["content"],
        })

    # Sauvegarder en JSON
    kb_file = kb_dir / "knowledge.json"
    with open(kb_file, "w", encoding="utf-8") as f:
        json.dump(knowledge_chunks, f, ensure_ascii=False, indent=2)

    # Sauvegarder aussi en Markdown (plus facile à relire)
    md_file = kb_dir / "knowledge.md"
    with open(md_file, "w", encoding="utf-8") as f:
        for chunk in knowledge_chunks:
            f.write(f"## {chunk['title']}\n\n")
            f.write(f"*Source: {chunk['source']}*\n\n")
            f.write(f"{chunk['content']}\n\n---\n\n")

    logger.info(f"✅ Base de connaissances créée : {len(knowledge_chunks)} documents")
    return kb_file


# ─── ÉTAPE 4 — Génération du System Prompt ───────────────────────────────────

def generate_system_prompt(client_data: dict) -> str:
    """
    Génère le system prompt personnalisé pour l'agent.
    """
    company = client_data["metadata"].get("company_name", "notre entreprise")
    industry = client_data["metadata"].get("industry", "")
    tone = client_data["branding"].get("tone", "professionnel et accueillant")
    values = client_data["branding"].get("values", "")
    restrictions = client_data["branding"].get("restrictions", "")
    bilingual = client_data["branding"].get("bilingual", False)

    services_list = "\n".join(f"  - {s}" for s in client_data["services"]) if client_data["services"] else "  (à définir)"

    lang_instruction = (
        "Tu réponds dans la langue utilisée par le client (français ou anglais). "
        "Si le client écrit en français, réponds en français. S'il écrit en anglais, réponds en anglais."
        if bilingual else
        "Tu réponds toujours en français. Si le client écrit en anglais, réponds en français poliment."
    )

    restrictions_section = ""
    if restrictions:
        restrictions_section = f"""
## 🚫 Restrictions
{restrictions}
Tu ne dois JAMAIS fournir d'informations sur ces sujets. Si le client demande, poliment redirige vers un humain.
"""

    prompt = f"""# Agent Conversationnel — {company}

## 🎭 Identité
Tu es l'assistant virtuel de **{company}**, une entreprise du secteur **{industry}**.
Ton ton est **{tone}**.
{"Valeurs de l'entreprise : " + values if values else ""}

## 📋 Services offerts
{services_list}

## 🗣️ Langue
{lang_instruction}

## 📚 Connaissances
Tu as accès à une base de connaissances sur {company}. Utilise-la pour répondre aux questions.
Si tu ne trouves pas la réponse dans la base de connaissances, dis honnêtement que tu ne sais pas et propose de transférer à un humain.

## 🎯 Tes responsabilités
1. **Répondre aux questions** des clients sur les services, horaires, politiques, etc.
2. **Qualifier les leads** : obtenir le nom, courriel et raison de la demande.
3. **Prendre des rendez-vous** quand c'est demandé (utiliser l'outil book_appointment).
4. **Transférer à un humain** pour les demandes complexes, urgentes ou hors de ton champ de compétence.
5. **Journaliser chaque conversation** (utiliser l'outil log_conversation).

## ⚡ Règles de comportement
- Sois concis mais complet. Pas de paragraphes de 20 lignes.
- Utilise des emojis avec modération pour rendre la conversation agréable.
- Ne jamais inventer d'informations. Si tu ne sais pas, dis-le.
- Toujours terminer par une question ou une suggestion pour garder la conversation vivante.
- Si le client semble frustré ou confus, propose immédiatement de transférer à un humain.
{restrictions_section}
## 🔄 Transfert humain
Quand tu transfères à un humain :
1. Résume la demande du client en 2-3 phrases.
2. Indique les informations de contact déjà collectées (nom, courriel, téléphone).
3. Dis au client : « Je vous transfère à un membre de notre équipe. Un instant s'il vous plaît. »
"""
    logger.info("✅ System prompt généré")
    return prompt


# ─── ÉTAPE 5 — Génération du code de l'agent ─────────────────────────────────

def generate_agent_code(client_data: dict, system_prompt: str, output_dir: Path) -> Path:
    """
    Génère le code Python de l'agent (FastAPI léger, compatible Render 512MB).
    Pas de ChromaDB, pas de LangChain lourd — API REST directe.
    """
    company_slug = slugify(client_data["metadata"].get("company_name", "agent"))
    company_name = client_data["metadata"].get("company_name", "Client")
    has_calendar = bool(client_data["integrations"].get("calendar"))
    has_crm = bool(client_data["integrations"].get("crm"))

    # Construire la section connaissances pour le system prompt
    kb_section = ""
    if client_data.get("services"):
        kb_section += "\n## Services offerts\n"
        for s in client_data["services"]:
            kb_section += f"- {s}\n"
    if client_data.get("faq"):
        kb_section += "\n## FAQ\n"
        for f in client_data["faq"]:
            kb_section += f"{f}\n"

    # Construire les infos de contact
    contact_info = ""
    meta = client_data["metadata"]
    if meta.get("address"):
        contact_info += f"\n- Adresse : {meta['address']}"
    if meta.get("phone"):
        contact_info += f"\n- Téléphone : {meta['phone']}"
    if meta.get("email"):
        contact_info += f"\n- Courriel : {meta['email']}"

    agent_code = f'''#!/usr/bin/env python3
"""
Agent Conversationnel — {company_name}
Généré automatiquement par Chatbot Factory le {datetime.now().strftime("%Y-%m-%d %H:%M")}
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
logger = logging.getLogger("{company_slug}_agent")

# ─── Base de connaissances ──────────────────────────────────────────────────

KB_DIR = Path(__file__).parent / "knowledge_base"
knowledge_docs = []

try:
    with open(KB_DIR / "knowledge.json", "r", encoding="utf-8") as f:
        knowledge_docs = json.load(f)
    logger.info(f"✅ Base de connaissances chargée: {{len(knowledge_docs)}} documents")
except Exception as e:
    logger.warning(f"⚠️ knowledge.json non trouvé: {{e}}")

# ─── System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """{system_prompt}"""

# ─── Configuration LLM ─────────────────────────────────────────────────────

LLM_BACKEND = os.getenv("LLM_BACKEND", "openrouter")


def call_llm(messages):
    """Appeler le LLM via API REST (pas de dépendance lourde)."""
    import urllib.request

    if LLM_BACKEND == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        model = os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha")
        url = "https://openrouter.ai/api/v1/chat/completions"
    elif LLM_BACKEND == "groq":
        api_key = os.getenv("GROQ_API_KEY", "")
        model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        url = "https://api.groq.com/openai/v1/chat/completions"
    else:
        return "Bonjour ! Je suis l'agent de démonstration. Comment puis-je vous aider?"

    if not api_key:
        return "⚠️ Clé API LLM non configurée. Veuillez contacter l'administrateur."

    payload = json.dumps({{
        "model": model,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7,
    }}).encode()

    headers = {{
        "Authorization": f"Bearer {{api_key}}",
        "Content-Type": "application/json",
    }}

    req = urllib.request.Request(url, data=payload, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Erreur LLM: {{e}}")
        return "Désolé, une erreur s'est produite. Veuillez réessayer ou nous appeler."
'''

    # Ajouter les outils Google Sheets si configuré
    agent_code += '''

# ─── Google Sheets ──────────────────────────────────────────────────────────

def log_conversation(session_id: str, user_message: str, bot_response: str, transferred: bool = False):
    """Journalise la conversation dans Google Sheets."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "")

    if not spreadsheet_id or not Path(creds_path).exists():
        return

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(spreadsheet_id).worksheet("Conversations")
        sheet.append_row([
            datetime.now().isoformat(),
            session_id,
            user_message[:500],
            bot_response[:500],
            "OUI" if transferred else "NON",
        ])
    except Exception as e:
        logger.error(f"Erreur log conversation: {e}")


def log_lead(name: str, email: str, phone: str, interest: str, source: str = "chatbot"):
    """Enregistre un lead dans Google Sheets."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
    spreadsheet_id = os.getenv("SPREADSHEET_ID", "")

    if not spreadsheet_id or not Path(creds_path).exists():
        return

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(spreadsheet_id).worksheet("Leads")
        sheet.append_row([
            datetime.now().isoformat(),
            name, email, phone, interest, source,
        ])
        logger.info(f"✅ Lead enregistré: {name} ({email})")
    except Exception as e:
        logger.error(f"Erreur log lead: {e}")
'''

    # Ajouter l'outil de calendrier si nécessaire
    if has_calendar:
        agent_code += '''
# ─── Calendrier ─────────────────────────────────────────────────────────────

def book_appointment(name: str, email: str, date: str, time: str,
                     service: str = "", notes: str = "") -> str:
    """Créer un rendez-vous via Cal.com API."""
    import requests

    cal_api_key = os.getenv("CAL_COM_API_KEY", "")
    cal_event_type_id = os.getenv("CAL_COM_EVENT_TYPE_ID", "")

    if not cal_api_key:
        return "Le système de rendez-vous n'est pas encore configuré. Un membre de l'équipe vous contactera."

    try:
        from datetime import datetime as dt
        start_dt = dt.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")

        resp = requests.post(
            "https://api.cal.com/v1/bookings",
            headers={"Authorization": f"Bearer {cal_api_key}"},
            json={
                "eventTypeId": int(cal_event_type_id),
                "start": start_dt.isoformat(),
                "responses": {"name": name, "email": email, "notes": notes},
                "metadata": {"service": service, "source": "chatbot"},
            },
            timeout=15,
        )

        if resp.status_code in (200, 201):
            return f"✅ Rendez-vous confirmé pour {name} le {date} à {time}."
        else:
            return "⚠️ Il y a eu un problème. Un membre de l'équipe vous contactera."
    except Exception as e:
        logger.error(f"Erreur book_appointment: {e}")
        return "⚠️ Impossible de prendre le rendez-vous en ce moment. Veuillez nous appeler directement."
'''

    # Ajouter l'outil CRM si nécessaire
    if has_crm:
        crm_name = client_data["integrations"].get("crm", "").lower()
        if "hubspot" in crm_name:
            agent_code += '''
# ─── CRM (HubSpot) ──────────────────────────────────────────────────────────

def create_crm_contact(name: str, email: str, phone: str = "", notes: str = ""):
    """Créer un contact dans HubSpot."""
    import requests

    hubspot_key = os.getenv("HUBSPOT_API_KEY", "")
    if not hubspot_key:
        return

    try:
        requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers={"Authorization": f"Bearer {hubspot_key}", "Content-Type": "application/json"},
            json={"properties": {"email": email, "firstname": name, "phone": phone, "notes": notes}},
            timeout=10,
        )
        logger.info(f"✅ Contact HubSpot créé: {email}")
    except Exception as e:
        logger.error(f"Erreur HubSpot: {e}")
'''
        else:
            agent_code += f'''
# ─── CRM ────────────────────────────────────────────────────────────────────

def create_crm_contact(name: str, email: str, phone: str = "", notes: str = ""):
    """Créer un contact dans le CRM ({client_data["integrations"].get("crm", "non configuré")})."""
    logger.info(f"CRM contact: {name} ({email}) - INTÉGRATION À COMPLÉTER")
'''

    # ── FastAPI App ─────────────────────────────────────────────────────────
    agent_code += f'''

# ─── FastAPI Application ────────────────────────────────────────────────────

app = FastAPI(title="Agent — {company_name}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sessions = {{}}


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
        score = sum(1 for word in query_lower.split() if word in content or word in title)
        if score > 0:
            results.append((score, doc["content"]))

    results.sort(reverse=True, key=lambda x: x[0])

    if results:
        return "\\n\\n".join(r[1] for r in results[:3])
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
    messages = [{{"role": "system", "content": SYSTEM_PROMPT}}]

    if context:
        messages.append({{"role": "system", "content": f"Informations pertinentes:\\n\\n{{context}}"}})

    for msg in chat_history[-10:]:
        messages.append(msg)

    messages.append({{"role": "user", "content": request.message}})

    # Appeler le LLM
    response_text = call_llm(messages)

    chat_history.append({{"role": "user", "content": request.message}})
    chat_history.append({{"role": "assistant", "content": response_text}})
    sessions[session_id] = chat_history[-20:]

    transfer_keywords = ["transférer", "humain", "parler à quelqu'un", "transfer", "human"]
    transferred = any(kw in response_text.lower() for kw in transfer_keywords)

    # Journaliser (non-bloquant)
    log_conversation(session_id, request.message, response_text, transferred)

    return ChatResponse(
        response=response_text,
        session_id=session_id,
        transferred=transferred,
    )


@app.get("/health")
async def health():
    return {{
        "status": "ok",
        "agent": "{company_name}",
        "timestamp": datetime.now().isoformat(),
        "docs": len(knowledge_docs),
    }}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
'''

    # Écrire le fichier
    agent_file = output_dir / "agent.py"
    with open(agent_file, "w", encoding="utf-8") as f:
        f.write(agent_code)

    logger.info(f"✅ Code agent généré : {agent_file}")
    return agent_file


# ─── ÉTAPE 6 — Génération des fichiers de configuration ──────────────────────

def generate_config_files(client_data: dict, output_dir: Path):
    """
    Génère les fichiers de configuration (.env, docker-compose.yml, requirements.txt).
    """
    company_slug = slugify(client_data["metadata"].get("company_name", "agent"))

    # .env.example
    env_content = f"""# Chatbot Factory — Configuration pour {client_data["metadata"].get("company_name", "Client")}
# Généré le {datetime.now().strftime("%Y-%m-%d %H:%M")}

# ─── LLM Backend ───────────────────────────────────────────────────────────
# Choisir: ollama | groq | openrouter
LLM_BACKEND=ollama
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b

# Alternative cloud (gratuit)
# LLM_BACKEND=groq
# GROQ_API_KEY=gsk_...
# GROQ_MODEL=llama-3.1-70b-versatile

# LLM_BACKEND=openrouter
# OPENROUTER_API_KEY=sk-or-...
# OPENROUTER_MODEL=meta-llama/llama-3.1-70b-instruct:free

# ─── Google Sheets ──────────────────────────────────────────────────────────
GOOGLE_CREDENTIALS=credentials.json
SPREADSHEET_ID=

# ─── Calendrier (optionnel) ─────────────────────────────────────────────────
CAL_COM_API_KEY=
CAL_COM_EVENT_TYPE_ID=

# ─── Courriels (optionnel) ──────────────────────────────────────────────────
RESEND_API_KEY=
EMAIL_FROM=@{company_slug}.com

# ─── CRM (optionnel) ────────────────────────────────────────────────────────
HUBSPOT_API_KEY=
"""

    # requirements.txt — version allégée pour Render
    requirements = """fastapi>=0.110
uvicorn>=0.29
pydantic>=2.0
python-dotenv>=1.0
gspread>=6.0
google-auth>=2.0
requests>=2.31
beautifulsoup4>=4.12
"""

    # docker-compose.yml
    docker_compose = f"""version: "3.9"

services:
  agent:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - ./knowledge_base:/app/knowledge_base
      - ./credentials.json:/app/credentials.json:ro
    restart: unless-stopped

  # Décommenter si tu utilises Ollama localement
  # ollama:
  #   image: ollama/ollama:latest
  #   ports:
  #     - "11434:11434"
  #   volumes:
  #     - ollama_data:/root/.ollama
  #   deploy:
  #     resources:
  #       reservations:
  #         devices:
  #           - driver: nvidia
  #             count: 1
  #             capabilities: [gpu]

# volumes:
#   ollama_data:
"""

    # Dockerfile
    dockerfile = """FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "agent.py"]
"""

    # build_knowledge_base.py — script d'indexation
    build_kb = '''#!/usr/bin/env python3
"""Construit la base vectorielle ChromaDB à partir des fichiers de connaissances."""

import json
from pathlib import Path
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

KB_DIR = Path("knowledge_base")
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

print("🔨 Construction de la base de connaissances...")

# Charger les documents
with open(KB_DIR / "knowledge.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)

# Découper en morceaux plus petits
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_size_overlap=200)
documents = []
for chunk in chunks:
    splits = splitter.create_documents(
        [chunk["content"]],
        metadatas=[{"source": chunk["source"], "title": chunk["title"]}] * len(splitter.split_text(chunk["content"]))
    )
    documents.extend(splits)

# Créer la base vectorielle
embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
vectorstore = Chroma.from_documents(
    documents=documents,
    embedding=embeddings,
    persist_directory=str(KB_DIR / "chroma"),
)

print(f"✅ Base construite : {vectorstore._collection.count()} chunks indexés")
'''

    # Écrire tous les fichiers
    files = {
        ".env.example": env_content,
        "requirements.txt": requirements,
        "docker-compose.yml": docker_compose,
        "Dockerfile": dockerfile,
        "build_knowledge_base.py": build_kb,
    }

    for filename, content in files.items():
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"  📄 {filename}")

    logger.info("✅ Fichiers de configuration générés")


# ─── ÉTAPE 7 — Tests automatiques ────────────────────────────────────────────

def run_automated_tests(output_dir: dict, client_data: dict) -> dict:
    """
    Pose 20 questions prédéfinies à l'agent et génère un rapport.
    """
    company = client_data["metadata"].get("company_name", "l'entreprise")
    industry = client_data["metadata"].get("industry", "")

    test_questions = [
        f"Quels sont les services offerts par {company}?",
        f"Quels sont vos horaires d'ouverture ?",
        f"Où êtes-vous situé ?",
        f"Comment puis-je prendre rendez-vous ?",
        f"Acceptez-vous les nouveaux clients ?",
        f"Quels sont vos tarifs ?",
        f"Offrez-vous une consultation gratuite ?",
        f"Combien de temps dure une séance ?",
        f"Acceptez-vous l'assurance ?",
        f"Que dois-je apporter lors de mon premier rendez-vous ?",
        f"Annuler ou reporter un rendez-vous",
        f"Parlez-moi de votre équipe",
        f"Avez-vous des promotions en ce moment ?",
        f"Je suis un nouveau client, que faire ?",
        f"Quelle est votre politique d'annulation ?",
        f"Offrez-vous des services en ligne / virtuels ?",
        f"Je veux parler à un humain",
        f"Quels modes de paiement acceptez-vous ?",
        f"Avez-vous un stationnement ?",
        f"Question complètement hors sujet : quelle est la capitale de la Mongolie ?",
    ]

    test_report = {
        "generated_at": datetime.now().isoformat(),
        "company": company,
        "total_questions": len(test_questions),
        "questions": test_questions,
        "status": "generated",
        "note": "Pour exécuter les tests, démarrez l'agent et utilisez le script test_agent.py",
    }

    # Sauvegarder le rapport
    report_file = output_dir / "test_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(test_report, f, ensure_ascii=False, indent=2)

    # Générer aussi un script de test
    test_script = f'''#!/usr/bin/env python3
"""Teste l'agent avec les questions prédéfinies."""

import requests
import json
from datetime import datetime

AGENT_URL = "http://localhost:8000"
REPORT_FILE = "test_results.json"

questions = {json.dumps(test_questions, ensure_ascii=False)}

results = []
print(f"🧪 Test de l'agent — {{len(questions)}} questions\\n")

for i, question in enumerate(questions, 1):
    try:
        resp = requests.post(
            f"{{AGENT_URL}}/json",
            json={{"message": question, "session_id": "test_suite"}},
            timeout=30,
        )
        data = resp.json()
        response = data.get("response", "ERREUR")
        transferred = data.get("transferred", False)
        
        # Évaluation basique
        is_relevant = len(response) > 20  # Au moins une phrase
        is_not_error = "erreur" not in response.lower() and "error" not in response.lower()
        passes = is_relevant and is_not_error
        
        status = "✅" if passes else "❌"
        print(f"{{status}} Q{{i}}: {{question[:60]}}...")
        print(f"   → {{response[:100]}}...\\n")
        
        results.append({{
            "question": question,
            "response": response,
            "transferred": transferred,
            "passes": passes,
        }})
    except Exception as e:
        print(f"❌ Q{{i}}: ERREUR — {{e}}\\n")
        results.append({{"question": question, "response": str(e), "passes": False}})

# Résumé
passed = sum(1 for r in results if r["passes"])
total = len(results)
print(f"\\n📊 Résultats : {{passed}}/{{total}} ({{passed/total*100:.0f}}%)")

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    json.dump({{"date": datetime.now().isoformat(), "results": results, "score": f"{{passed}}/{{total}}"}}, f, ensure_ascii=False, indent=2)

print(f"📄 Rapport sauvegardé : {{REPORT_FILE}}")
'''

    test_script_file = output_dir / "test_agent.py"
    with open(test_script_file, "w", encoding="utf-8") as f:
        f.write(test_script)

    logger.info("✅ Tests automatiques générés")
    return test_report


# ─── UTILITAIRES ──────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convertit un texte en slug (minuscules, tirets, sans accents)."""
    text = text.lower().strip()
    text = re.sub(r"[àáâãäå]", "a", text)
    text = re.sub(r"[èéêë]", "e", text)
    text = re.sub(r"[ìíîï]", "i", text)
    text = re.sub(r"[òóôõö]", "o", text)
    text = re.sub(r"[ùúûü]", "u", text)
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Chatbot Factory — Générateur d'agent")
    parser.add_argument("--sheet-id", required=True, help="ID du Google Sheet d'onboarding")
    parser.add_argument("--client-name", help="Nom du client (pour le dossier de sortie)")
    parser.add_argument("--skip-scrape", action="store_true", help="Sauter le scraping du site web")
    args = parser.parse_args()

    logger.info("🚀 Chatbot Factory — Génération d'agent")
    logger.info("=" * 50)

    # Étape 1 : Lire les données client
    logger.info("📋 Étape 1 — Lecture du Google Sheet...")
    client_data = read_client_sheet(args.sheet_id)

    company_name = client_data["metadata"].get("company_name", args.client_name or "client")
    company_slug = slugify(company_name)

    # Créer le dossier de sortie
    output_dir = OUTPUT_BASE / company_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 Dossier de sortie : {output_dir}")

    # Sauvegarder les données client
    with open(output_dir / "client_data.json", "w", encoding="utf-8") as f:
        json.dump(client_data, f, ensure_ascii=False, indent=2)

    # Étape 2 : Scraper le site web
    web_documents = []
    website = client_data["metadata"].get("website", "")
    if website and not args.skip_scrape:
        logger.info("🌐 Étape 2 — Scraping du site web...")
        web_documents = scrape_website(website)
    else:
        logger.info("⏭️ Étape 2 — Scraping ignoré")

    # Étape 3 : Créer la base de connaissances
    logger.info("📚 Étape 3 — Création de la base de connaissances...")
    create_knowledge_base(client_data, web_documents, output_dir)

    # Étape 4 : Générer le system prompt
    logger.info("🎭 Étape 4 — Génération du system prompt...")
    system_prompt = generate_system_prompt(client_data)
    with open(output_dir / "system_prompt.md", "w", encoding="utf-8") as f:
        f.write(system_prompt)

    # Étape 5 : Générer le code de l'agent
    logger.info("⚡ Étape 5 — Génération du code de l'agent...")
    generate_agent_code(client_data, system_prompt, output_dir)

    # Étape 6 : Générer les fichiers de configuration
    logger.info("🔧 Étape 6 — Génération des fichiers de configuration...")
    generate_config_files(client_data, output_dir)

    # Étape 7 : Tests automatiques
    logger.info("🧪 Étape 7 — Génération des tests...")
    run_automated_tests(output_dir, client_data)

    # Résumé
    logger.info("")
    logger.info("=" * 50)
    logger.info(f"✅ AGENT GÉNÉRÉ AVEC SUCCÈS pour {company_name}")
    logger.info(f"📁 Dossier : {output_dir}")
    logger.info("")
    logger.info("Prochaines étapes :")
    logger.info(f"  1. cd {output_dir}")
    logger.info("  2. Copier .env.example → .env et remplir les clés API")
    logger.info("  3. python agent.py")
    logger.info("  4. python test_agent.py")
    logger.info("  5. Déployer sur Render (push sur GitHub + webhook)")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
