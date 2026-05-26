#!/usr/bin/env python3
"""
Chatbot Factory — Monitor Google Sheet
=======================================
Poll le Google Sheet d'onboarding pour détecter les nouvelles soumissions
de formulaire et lancer automatiquement generate_agent.py pour chaque
nouveau client.

Fréquence : 4 fois par jour (configurable)
  - 08:00, 12:00, 16:00, 20:00 par défaut

Usage:
    python monitor_chatbot.py --sheet-id <GOOGLE_SHEET_ID>

Dépendances:
    pip install gspread google-auth schedule
"""

import os
import sys
import json
import argparse
import logging
import subprocess
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("monitor_chatbot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("monitor_chatbot")

# ─── Configuration ────────────────────────────────────────────────────────────

POLL_TIMES = ["08:00", "12:00", "16:00", "20:00"]  # 4 fois par jour
PROCESSED_FILE = Path(".processed_agents")
GENERATE_SCRIPT = Path(__file__).parent / "generate_agent.py"


def load_processed() -> dict:
    """Charge la liste des clients déjà traités."""
    if PROCESSED_FILE.exists():
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_processed(processed: dict):
    """Sauvegarde la liste des clients traités."""
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)


def get_sheet_rows(sheet_id: str) -> list[dict]:
    """Lit toutes les lignes du Google Sheet."""
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
    rows = worksheet.get_all_records()

    logger.info(f"📊 {len(rows)} lignes lues dans le Sheet")
    return rows


def find_new_submissions(rows: list[dict], processed: dict) -> list[dict]:
    """
    Trouve les nouvelles soumissions non traitées.
    Identifie chaque soumission par son timestamp (colonne 'Timestamp').
    """
    new_submissions = []

    for i, row in enumerate(rows):
        timestamp = str(row.get("Timestamp", "")).strip()
        email = str(row.get("Best email address to contact you", "")).strip()
        company = str(row.get("Business name", "")).strip()

        # Clé unique : timestamp + email
        key = f"{timestamp}_{email}"

        if not timestamp or not email:
            continue

        if key not in processed:
            new_submissions.append({
                "key": key,
                "row_index": i,
                "timestamp": timestamp,
                "email": email,
                "company": company,
                "row_data": row,
            })

    return new_submissions


def run_generate_agent(sheet_id: str, client_name: str, row_index: int):
    """Lance generate_agent.py pour un nouveau client."""
    logger.info(f"🚀 Lancement generate_agent.py pour {client_name} (ligne {row_index + 1})...")

    cmd = [
        sys.executable,
        str(GENERATE_SCRIPT),
        "--sheet-id", sheet_id,
        "--client-name", client_name,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max
        )

        if result.returncode == 0:
            logger.info(f"✅ Agent généré avec succès pour {client_name}")
            return True
        else:
            logger.error(f"❌ Erreur génération pour {client_name}: {result.stderr[:300]}")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"⏰ Timeout pour {client_name} (>10 min)")
        return False
    except Exception as e:
        logger.error(f"❌ Exception pour {client_name}: {e}")
        return False


def poll_once(sheet_id: str):
    """Un seul cycle de polling."""
    logger.info("=" * 60)
    logger.info(f"🔍 Poll du Google Sheet — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    processed = load_processed()
    rows = get_sheet_rows(sheet_id)
    new_submissions = find_new_submissions(rows, processed)

    if not new_submissions:
        logger.info("ℹ️ Aucune nouvelle soumission détectée")
        return

    logger.info(f"🆕 {len(new_submissions)} nouvelle(s) soumission(s) détectée(s)!")

    for sub in new_submissions:
        logger.info(f"  📋 {sub['company']} ({sub['email']}) — {sub['timestamp']}")

        success = run_generate_agent(
            sheet_id=sheet_id,
            client_name=sub["company"],
            row_index=sub["row_index"],
        )

        if success:
            processed[sub["key"]] = {
                "company": sub["company"],
                "email": sub["email"],
                "timestamp": sub["timestamp"],
                "processed_at": datetime.now().isoformat(),
            }
            save_processed(processed)
            logger.info(f"  ✅ {sub['company']} marqué comme traité")
        else:
            logger.warning(f"  ⚠️ {sub['company']} non traité — sera réessayé au prochain poll")

        # Pause entre chaque client pour ne pas surcharger
        time.sleep(5)


def run_scheduled(sheet_id: str):
    """Lance le polling planifié (4 fois par jour)."""
    import schedule

    logger.info("📅 Monitor Chatbot Factory démarré")
    logger.info(f"   Heures de poll: {', '.join(POLL_TIMES)}")
    logger.info(f"   Sheet ID: {sheet_id}")
    logger.info(f"   Script: {GENERATE_SCRIPT}")
    logger.info("")

    # Planifier les 4 polls quotidiens
    for t in POLL_TIMES:
        schedule.every().day.at(t).do(poll_once, sheet_id=sheet_id)
        logger.info(f"   ⏰ Poll planifié à {t}")

    # Lancer un premier poll immédiatement
    logger.info("")
    logger.info("🚀 Premier poll immédiat...")
    poll_once(sheet_id)

    # Boucle infinie
    logger.info("")
    logger.info("🔄 En attente des prochains polls...")
    while True:
        schedule.run_pending()
        time.sleep(60)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Chatbot Factory — Monitor Google Sheet (4x/jour)"
    )
    parser.add_argument(
        "--sheet-id",
        required=True,
        help="ID du Google Sheet d'onboarding",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Lancer un seul poll et quitter (pas de planification)",
    )
    parser.add_argument(
        "--poll-times",
        nargs="+",
        default=POLL_TIMES,
        help=f"Heures de poll (défaut: {' '.join(POLL_TIMES)})",
    )
    args = parser.parse_args()

    if args.poll_times != POLL_TIMES:
        POLL_TIMES = args.poll_times

    if args.once:
        logger.info("🔍 Mode single poll")
        poll_once(args.sheet_id)
    else:
        run_scheduled(args.sheet_id)


if __name__ == "__main__":
    main()
