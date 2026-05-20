#!/usr/bin/env python3
"""
Chatbot Factory — Création du Google Sheet de test
====================================================
Crée un Google Sheet avec les données du client fictif
"Clinique Dentaire Sourire" et le partage avec ton email.

Usage:
    python create_test_sheet.py

Le script va :
    1. Ouvrir un navigateur pour l'authentification Google (une seule fois)
    2. Créer le Google Sheet
    3. Remplir avec les données du client fictif
    4. Afficher l'URL et l'ID du Sheet
"""

import os
import sys
import json
from pathlib import Path

# ─── Vérification des dépendances ─────────────────────────────────────────────

try:
    import gspread
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("📦 Installation des dépendances...")
    os.system("pip install gspread google-auth google-auth-oauthlib")
    import gspread
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

# ─── Configuration ────────────────────────────────────────────────────────────

# Utiliser le client_secret existant (OAuth)
CLIENT_SECRET_FILE = Path.home() / ".hermes" / "google_client_secret.json"
TOKEN_FILE = Path.home() / ".hermes" / "chatbot_factory_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Données du client fictif
CLIENT_DATA = [
    ["Question", "Réponse"],
    ["Quel est le nom de votre entreprise?", "Clinique Dentaire Sourire"],
    ["Dans quel secteur d'activité œuvrez-vous?", "Santé / Clinique médicale / Dentaire"],
    ["Quel est l'adresse de votre/vos succursale(s)?", "1234 Rue Saint-Jean, Montréal, QC H2X 1Y5"],
    ["Quel est votre numéro de téléphone principal?", "(514) 555-0123"],
    ["Quel est votre courriel de contact?", "info@cliniquesourire.ca"],
    ["Quel est l'URL de votre site web?", "https://cliniquesourire.ca"],
    ["Quel est votre principal point de friction?", "Trop d'appels répétitifs, Perte de clients hors heures"],
    ["Quel pourcentage de demandes récurrentes?", "50-75%"],
    ["Objectif principal de l'agent?", "Répondre aux FAQ, Prendre des rendez-vous, Qualifier des leads"],
    ["Pics saisonniers?", "Lundis matins et mercredis après-midis achalandés"],
    ["Services principaux", "Nettoyage dentaire, Blanchiment, Orthodontie, Implants, Urgences, Esthétique"],
    ["Prix standardisés", "Nettoyage: 150$-250$, Blanchiment: 400$-600$, Consultation: gratuite"],
    ["FAQ existante?", "Oui, sur le site web"],
    ["5 questions les plus fréquentes", "Horaires? Nouveaux patients? Assurance? Coût nettoyage? Urgences?"],
    ["Réponses FAQ", "Horaires: Lun-Ven 8h-18h, Sam 9h-14h. Nouveaux patients: oui. Assurance: oui. Nettoyage: 150-250$. Urgences: oui."],
    ["Canaux actuels", "Téléphone, Courriel, Site web, Facebook"],
    ["Canaux pour l'agent", "Site web (widget), Facebook Messenger"],
    ["CRM?", "Non"],
    ["Système de rendez-vous?", "Calendly"],
    ["Plateforme site web?", "WordPress"],
    ["Conformité?", "Loi 25 (Québec)"],
    ["Ton de l'entreprise?", "Chaleureux et accessible"],
    ["Bilingue?", "Oui, bilingue FR/EN"],
    ["Valeurs?", "Bienveillance, expertise, confort, confiance"],
    ["Sujets interdits?", "Pas de diagnostic médical, pas de recommandation de traitement"],
    ["Transfert humain?", "Diagnostic, plainte, urgence, prix complexe"],
    ["Horaires d'ouverture", "Lun-Ven 8h-18h, Sam 9h-14h, Dim Fermé"],
    ["Politiques?", "Annulation 24h avance, sinon 50$ frais"],
    ["Autre info?", "3 dentistes: Dr. Tremblay, Dr. Gagnon, Dr. Chen"],
    ["Responsable suivi?", "Marie Tremblay (propriétaire)"],
    ["Contact suivi?", "Courriel"],
    ["Budget?", "2500$ - 5000$"],
]


def get_credentials():
    """Obtient les credentials Google via OAuth2."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET_FILE.exists():
                print(f"❌ Fichier introuvable : {CLIENT_SECRET_FILE}")
                print("   Place ton google_client_secret.json dans ~/.hermes/")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Sauvegarder le token pour la prochaine fois
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"✅ Token sauvegardé : {TOKEN_FILE}")

    return creds


def create_sheet():
    """Crée et remplit le Google Sheet."""
    creds = get_credentials()
    gc = gspread.authorize(creds)

    # Créer le Spreadsheet
    print("📋 Création du Google Sheet...")
    sh = gc.create("Chatbot Factory — Test Client: Clinique Dentaire Sourire")

    # Partager avec le propriétaire du projet (lecture/écriture)
    # sh.share("", perm_type="anyone", role="writer")

    # Accéder à l'onglet par défaut
    worksheet = sh.sheet1
    worksheet.update_title("Réponses")

    # Remplir les données
    print("✏️ Remplissage des données...")
    worksheet.update(
        range_name=f"A1:B{len(CLIENT_DATA)}",
        values=CLIENT_DATA,
    )

    # Formater l'en-tête
    worksheet.format("A1:B1", {
        "backgroundColor": {"red": 0.39, "green": 0.45, "blue": 0.95},
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
        "horizontalAlignment": "CENTER",
    })

    # Ajuster la largeur des colonnes
    worksheet.columns_auto_resize(0, 2)

    # Créer un deuxième onglet pour les Conversations (vide, pour l'agent)
    conv_sheet = sh.add_worksheet(title="Conversations", rows=1000, cols=7)
    conv_sheet.update(
        range_name="A1:G1",
        values=[["Date", "Session ID", "Message utilisateur", "Réponse bot", "Lead info", "Transféré", "Client"]],
    )
    conv_sheet.format("A1:G1", {
        "backgroundColor": {"red": 0.13, "green": 0.77, "blue": 0.37},
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
    })

    # Créer un troisième onglet pour les Leads (vide, pour l'agent)
    leads_sheet = sh.add_worksheet(title="Leads", rows=1000, cols=7)
    leads_sheet.update(
        range_name="A1:G1",
        values=[["Date", "Nom", "Courriel", "Téléphone", "Intérêt", "Source", "Client"]],
    )
    leads_sheet.format("A1:G1", {
        "backgroundColor": {"red": 0.96, "green": 0.62, "blue": 0.04},
        "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
    })

    # Résultats
    sheet_id = sh.id
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

    print("")
    print("=" * 60)
    print("✅ GOOGLE SHEET CRÉÉ AVEC SUCCÈS!")
    print("=" * 60)
    print(f"📋 Titre : {sh.title}")
    print(f"🔗 URL : {sheet_url}")
    print(f"🆔 Sheet ID : {sheet_id}")
    print("")
    print("📂 Onglets créés :")
    print("   1. Réponses — Données du client fictif")
    print("   2. Conversations — Journal des conversations (pour l'agent)")
    print("   3. Leads — Leads captés (pour l'agent)")
    print("")
    print("💡 Prochaine étape :")
    print(f"   python generate_agent.py --sheet-id {sheet_id} --client-name 'Clinique Dentaire Sourire'")
    print("=" * 60)

    # Sauvegarder l'ID dans un fichier pour référence
    config_file = Path("test_sheet_config.json")
    with open(config_file, "w") as f:
        json.dump({
            "sheet_id": sheet_id,
            "sheet_url": sheet_url,
            "client_name": "Clinique Dentaire Sourire",
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }, f, indent=2)
    print(f"📄 Config sauvegardée : {config_file}")

    return sheet_id, sheet_url


if __name__ == "__main__":
    print("🤖 Chatbot Factory — Création du Google Sheet de test")
    print("=" * 60)
    print("")

    # Vérifier que le client_secret existe
    if not CLIENT_SECRET_FILE.exists():
        print(f"❌ Fichier introuvable : {CLIENT_SECRET_FILE}")
        print("")
        print("Pour obtenir ce fichier :")
        print("  1. Aller sur https://console.cloud.google.com/")
        print("  2. Créer un projet (ou utiliser 'web-factory-496023')")
        print("  3. Activer l'API Google Sheets + Google Drive")
        print("  4. Créer des credentials OAuth 2.0")
        print("  5. Télécharger le JSON et le placer dans ~/.hermes/google_client_secret.json")
        sys.exit(1)

    print("🔐 Authentification Google...")
    print("   Un navigateur va s'ouvrir. Connecte-toi avec ton compte Google.")
    print("")

    sheet_id, sheet_url = create_sheet()
