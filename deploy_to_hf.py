#!/usr/bin/env python3
"""
Chatbot Factory — Déploiement automatique vers HuggingFace Spaces
=================================================================
Crée un HF Space dédié par client, pousse les fichiers de l'agent généré,
et configure les secrets (clés API, Google Sheet ID, etc.).

Usage:
    python deploy_to_hf.py --agent-dir generated_agents/<client_slug> \
                           --hf-token <HF_TOKEN> \
                           --openrouter-key <OPENROUTER_API_KEY> \
                           --openai-key <OPENAPI_API_KEY> \
                           [--google-credentials /path/to/credentials.json] \
                           [--dry-run]

Dépendances:
    pip install huggingface_hub requests
"""

import os
import sys
import json
import argparse
import logging
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deploy_to_hf")

# ─── Constants ────────────────────────────────────────────────────────────────

HF_API_BASE = "https://huggingface.co/api"
SPACE_SDK_DOCKERFILE = """# Chatbot Factory — Auto-generated Dockerfile for {company_name}
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Expose port
EXPOSE 7860

# Run the agent
CMD ["python", "agent.py"]
"""

README_TEMPLATE = """---
title: {company_name} Chatbot
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
app_file: agent.py
pinned: false
license: mit
---

# {company_name} Chatbot

Agent conversationnel généré automatiquement par Chatbot Factory.

## Endpoints

- `POST /chat` — Envoyer un message au chatbot
- `GET /health` — Health check
- `GET /` — Status

## Chatbot Factory

Projet : https://github.com/Cadderly85/Chatbot-Factory
"""


def slugify(text: str) -> str:
    """Convertit un texte en slug HF-compatible (minuscules, tirets)."""
    import re
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


def check_hf_token(hf_token: str) -> str:
    """Vérifie le token HF et retourne le username."""
    import requests
    resp = requests.get(
        f"{HF_API_BASE}/whoami-v2",
        headers={"Authorization": f"Bearer {hf_token}"},
    )
    if resp.status_code != 200:
        logger.error(f"Token HF invalide (HTTP {resp.status_code}): {resp.text[:200]}")
        raise ValueError("HF Token invalide")
    username = resp.json().get("name", "")
    logger.info(f"✅ Token HF validé — username: {username}")
    return username


def create_hf_space(
    hf_token: str,
    username: str,
    space_name: str,
    company_name: str,
    private: bool = False,
) -> str:
    """Crée un nouveau HF Space et retourne son URL."""
    import requests

    repo_id = f"{username}/{space_name}"
    url = f"{HF_API_BASE}/repos/create"

    payload = {
        "name": space_name,
        "private": private,
        "sdk": "docker",
        "license": "mit",
        "tags": ["chatbot-factory", "chatbot"],
    }

    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
    }

    logger.info(f"🏗️ Création du HF Space: {repo_id}...")
    resp = requests.post(url, json=payload, headers=headers)

    if resp.status_code == 409:
        logger.info(f"ℹ️ Le Space {repo_id} existe déjà — réutilisation.")
        return repo_id
    elif resp.status_code not in (200, 201):
        logger.error(f"Erreur création Space (HTTP {resp.status_code}): {resp.text[:200]}")
        raise RuntimeError(f"Impossible de créer le HF Space: {resp.text[:200]}")

    logger.info(f"✅ HF Space créé: https://huggingface.co/spaces/{repo_id}")
    return repo_id


def set_space_secrets(
    hf_token: str,
    repo_id: str,
    secrets: dict,
) -> None:
    """Configure les secrets du HF Space via l'API."""
    import requests

    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
    }

    for key, value in secrets.items():
        if not value:
            continue

        url = f"{HF_API_BASE}/spaces/{repo_id}/secrets"
        payload = {"key": key, "value": str(value)}

        resp = requests.post(url, json=payload, headers=headers)

        if resp.status_code in (200, 201):
            logger.info(f"  🔑 Secret '{key}' configuré")
        else:
            logger.warning(f"  ⚠️ Erreur secret '{key}' (HTTP {resp.status_code}): {resp.text[:100]}")


def prepare_space_files(agent_dir: Path, company_name: str, company_slug: str) -> Path:
    """
    Prépare les fichiers à pousser vers le HF Space :
    - agent.py (le code de l'agent généré)
    - requirements.txt (deps HF Space)
    - knowledge_base/ (base de connaissances)
    - README.md (frontmatter HF)
    - Dockerfile
    - .gitattributes (pour LF line endings)

    Retourne le chemin du dossier temporaire préparé.
    """
    import tempfile

    # Créer un dossier temporaire propre
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"hf_deploy_{company_slug}_"))
    logger.info(f"📦 Préparation des fichiers dans {tmp_dir}")

    # 1. Copier l'agent.py
    agent_src = agent_dir / "agent.py"
    if agent_src.exists():
        shutil.copy2(agent_src, tmp_dir / "agent.py")
        logger.info("  📄 agent.py")
    else:
        logger.error(f"  ❌ agent.py non trouvé dans {agent_dir}")
        raise FileNotFoundError(f"agent.py manquant dans {agent_dir}")

    # 2. Copier la base de connaissances
    kb_src = agent_dir / "knowledge_base"
    if kb_src.exists():
        shutil.copytree(kb_src, tmp_dir / "knowledge_base")
        logger.info("  📄 knowledge_base/")
    else:
        logger.warning("  ⚠️ knowledge_base/ non trouvé — sera vide")

    # 3. requirements.txt adapté pour HF Space (pas besoin de gspread ici,
    #    l'agent tourne sur HF, les credentials Google sont via env)
    hf_requirements = """fastapi>=0.110
uvicorn>=0.29
pydantic>=2.0
python-dotenv>=1.0
gspread>=6.0
google-auth>=2.0
requests>=2.31
"""

    # Privilégier le requirements.txt du dossier agent s'il existe
    req_src = agent_dir / "requirements.txt"
    if req_src.exists():
        shutil.copy2(req_src, tmp_dir / "requirements.txt")
        logger.info("  📄 requirements.txt (depuis agent_dir)")
    else:
        (tmp_dir / "requirements.txt").write_text(hf_requirements, encoding="utf-8")
        logger.info("  📄 requirements.txt (HF par défaut)")

    # 4. README.md avec frontmatter HF
    readme_content = README_TEMPLATE.format(company_name=company_name)
    (tmp_dir / "README.md").write_text(readme_content, encoding="utf-8")
    logger.info("  📄 README.md")

    # 5. Dockerfile
    dockerfile_content = SPACE_SDK_DOCKERFILE.format(company_name=company_name)
    (tmp_dir / "Dockerfile").write_text(dockerfile_content, encoding="utf-8")
    logger.info("  📄 Dockerfile")

    # 6. .gitattributes (force LF)
    (tmp_dir / ".gitattributes").write_text("* text eol=lf\n", encoding="utf-8")

    return tmp_dir


def git_push_to_space(
    tmp_dir: Path,
    repo_id: str,
    hf_token: str,
    dry_run: bool = False,
) -> str:
    """
    Initialise un repo git dans tmp_dir et pousse vers le HF Space via git.
    Retourne l'URL du Space.
    """
    hf_url = f"https://user:{hf_token}@huggingface.co/spaces/{repo_id}"

    commands = [
        ["git", "init"],
        ["git", "config", "user.name", "chatbot-factory[bot]"],
        ["git", "config", "user.email", "bot@chatbot-factory.local"],
        ["git", "add", "-A"],
        ["git", "commit", "-m", f"🚀 Deploy {repo_id} via Chatbot Factory — {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
        ["git", "remote", "add", "hf", hf_url],
        ["git", "push", "hf", "HEAD:main", "--force"],
    ]

    for cmd in commands:
        cmd_str = " ".join(cmd[:3]) + ("..." if len(cmd) > 3 else "")
        logger.info(f"  🔧 {cmd_str}")

        if dry_run:
            logger.info(f"     [DRY RUN] Commande ignorée")
            continue

        result = subprocess.run(
            cmd,
            cwd=str(tmp_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()[:300] if result.stderr else ""
            if "remote already exists" in stderr:
                logger.info("     Remote hf déjà configuré, on continue...")
                continue
            if "nothing to commit" in stderr or "nothing added" in stderr:
                logger.info("     Rien à commiter, on continue...")
                continue
            logger.error(f"     ❌ Erreur: {stderr}")
            raise RuntimeError(f"Échec git {' '.join(cmd[:2])}: {stderr}")

        if result.stdout.strip():
            logger.debug(f"     stdout: {result.stdout.strip()[:200]}")

    space_url = f"https://{repo_id.replace('/', '-')}.hf.space"
    logger.info(f"✅ Code poussé vers {space_url}")
    return space_url


def deploy_agent(
    agent_dir: Path,
    hf_token: str,
    openrouter_key: str = "",
    openai_key: str = "",
    google_credentials_path: str = "",
    dry_run: bool = False,
    space_name: str = None,
    private: bool = False,
) -> dict:
    """
    Pipeline complet de déploiement :
    1. Vérifie le token HF
    2. Crée le Space HF dédié
    3. Prépare les fichiers
    4. Configure les secrets
    5. Pousse le code via git

    Retourne un dict avec les infos du déploiement.
    """
    agent_dir = Path(agent_dir)
    if not agent_dir.exists():
        raise FileNotFoundError(f"Dossier agent non trouvé: {agent_dir}")

    # Lire les données client
    client_data_path = agent_dir / "client_data.json"
    if client_data_path.exists():
        with open(client_data_path, "r", encoding="utf-8") as f:
            client_data = json.load(f)
    else:
        client_data = {}

    company_name = client_data.get("metadata", {}).get("company_name", agent_dir.name)
    company_slug = slugify(company_name)
    space_name = space_name or f"chatbot-{company_slug}"

    logger.info("=" * 60)
    logger.info(f"🚀 Déploiement HF Space pour {company_name}")
    logger.info(f"   Space: {space_name}")
    logger.info(f"   Dossier agent: {agent_dir}")
    logger.info(f"   Dry run: {dry_run}")
    logger.info("=" * 60)

    # Étape 1 : Vérifier le token HF
    logger.info("🔑 Étape 1 — Vérification du token HF...")
    username = check_hf_token(hf_token)

    # Étape 2 : Créer le Space HF
    logger.info(f"🏗️ Étape 2 — Création du HF Space '{space_name}'...")
    if dry_run:
        repo_id = f"{username}/{space_name}"
        logger.info(f"   [DRY RUN] Space {repo_id}")
    else:
        repo_id = create_hf_space(hf_token, username, space_name, company_name, private)

    # Étape 3 : Préparer les fichiers
    logger.info("📦 Étape 3 — Préparation des fichiers...")
    if dry_run:
        logger.info("   [DRY RUN] Fichiers non préparés")
        tmp_dir = None
    else:
        tmp_dir = prepare_space_files(agent_dir, company_name, company_slug)

    # Étape 4 : Configure les secrets
    logger.info("🔐 Étape 4 — Configuration des secrets...")
    secrets = {
        "LLM_BACKEND": "auto",
        "OPENROUTER_API_KEY": openrouter_key or os.getenv("OPENROUTER_API_KEY", ""),
        "OPENROUTER_MODEL": os.getenv("OPENROUTER_MODEL", "openrouter/owl-alpha"),
        "OPENAI_API_KEY": openai_key or os.getenv("OPENAI_API_KEY", ""),
        "OPENAI_MODEL": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
    }

    # Ajouter le Google Sheet ID si disponible
    sheet_id = client_data.get("metadata", {}).get("spreadsheet_id", "")
    if sheet_id:
        secrets["SPREADSHEET_ID"] = sheet_id

    if dry_run:
        for k, v in secrets.items():
            masked = v[:8] + "..." if v and len(v) > 8 else "(vide)"
            logger.info(f"   [DRY RUN] {k} = {masked}")
    else:
        set_space_secrets(hf_token, repo_id, secrets)

    # Étape 5 : Pousser le code via git
    logger.info("📤 Étape 5 — Push vers HF Space...")
    if dry_run:
        logger.info("   [DRY RUN] Git push ignoré")
        space_url = f"https://huggingface.co/spaces/{repo_id}"
    else:
        # Note: google_credentials n'est PAS poussé (sécurité)
        # Le client doit l'ajouter manuellement comme secret file si besoin
        space_url = git_push_to_space(tmp_dir, repo_id, hf_token, dry_run)

    # Nettoyer le dossier temporaire
    if tmp_dir and tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("🧹 Dossier temporaire nettoyé")

    # Résultat
    app_url = f"https://{repo_id.replace('/', '-')}.hf.space"

    result = {
        "company_name": company_name,
        "company_slug": company_slug,
        "repo_id": repo_id,
        "space_url": f"https://huggingface.co/spaces/{repo_id}",
        "app_url": app_url,
        "deployed_at": datetime.now().isoformat(),
    }

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"✅ DÉPLOIEMENT TERMINÉ pour {company_name}")
    logger.info(f"   🌐 Space: {result['space_url']}")
    logger.info(f"   🤖 App:   {result['app_url']}")
    logger.info(f"   💬 Chat:  {result['app_url']}/chat")
    logger.info("=" * 60)

    return result


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Chatbot Factory — Déploiement automatique vers HF Space"
    )
    parser.add_argument(
        "--agent-dir",
        required=True,
        help="Chemin vers le dossier de l'agent généré (ex: generated_agents/mon-client)",
    )
    parser.add_argument(
        "--hf-token",
        default=os.getenv("HF_TOKEN", ""),
        help="Token HuggingFace (ou variable d'env HF_TOKEN)",
    )
    parser.add_argument(
        "--openrouter-key",
        default=os.getenv("OPENROUTER_API_KEY", ""),
        help="Clé API OpenRouter (ou variable d'env OPENROUTER_API_KEY)",
    )
    parser.add_argument(
        "--openai-key",
        default=os.getenv("OPENAI_API_KEY", ""),
        help="Clé API OpenAI (ou variable d'env OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--google-credentials",
        default="",
        help="Chemin vers le fichier credentials.json Google (optionnel, non poussé comme secret)",
    )
    parser.add_argument(
        "--space-name",
        default=None,
        help="Nom du HF Space (par défaut: chatbot-<slug>)",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="Créer le Space en privé",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simule sans rien créer/modifier côté HF",
    )
    args = parser.parse_args()

    if not args.hf_token:
        logger.error("❌ HF Token requis (--hf-token ou variable HF_TOKEN)")
        sys.exit(1)

    try:
        result = deploy_agent(
            agent_dir=args.agent_dir,
            hf_token=args.hf_token,
            openrouter_key=args.openrouter_key,
            openai_key=args.openai_key,
            google_credentials_path=args.google_credentials,
            dry_run=args.dry_run,
            space_name=args.space_name,
            private=args.private,
        )

        # Sauvegarder le résultat
        result_path = Path(args.agent_dir) / "deploy_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"📄 Résultat sauvegardé: {result_path}")

    except Exception as e:
        logger.error(f"❌ Erreur de déploiement: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
