#!/usr/bin/env python3
"""
Chatbot Factory — Google Form Generator
=========================================
Crée automatiquement le formulaire d'onboarding client
via l'API Google Forms.

Usage:
    python create_form.py --title "Chatbot Factory — Onboarding [Nom Client]"

Dépendances:
    pip install google-api-python-client google-auth google-auth-oauthlib

Setup:
    1. Activer l'API Google Forms dans Google Cloud Console
    2. Télécharger credentials.json (OAuth 2.0)
    3. Lancer le script — il ouvrira un navigateur pour l'authentification
"""

import os
import json
import argparse
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("create_form")


def get_google_creds():
    """Obtient les credentials Google via Service Account (pas de navigateur)."""
    from google.oauth2.service_account import Credentials

    SCOPES = [
        "https://www.googleapis.com/auth/forms.body",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

    creds_path = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    logger.info(f"✅ Credentials chargées : {creds.service_account_email}")
    return creds


def create_form(title: str, spreadsheet_id: str = None) -> dict:
    """
    Crée le formulaire d'onboarding complet.
    Crée automatiquement un Google Sheet pour stocker les réponses.
    Retourne l'ID du form, l'URL, et l'ID du Sheet.
    """
    from googleapiclient.discovery import build

    creds = get_google_creds()
    forms_service = build("forms", "v1", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # ─── Créer le Sheet d'abord ────────────────────────────────────────────
    if not spreadsheet_id:
        sheet_title = f"Réponses — {title}"
        spreadsheet = sheets_service.spreadsheets().create(body={
            "properties": {"title": sheet_title},
            "sheets": [{
                "properties": {
                    "title": "Réponses",
                    "gridProperties": {"frozenRowCount": 1}
                }
            }]
        }).execute()
        spreadsheet_id = spreadsheet["spreadsheetId"]
        sheet_url = spreadsheet["spreadsheetUrl"]
        logger.info(f"✅ Google Sheet créé : {sheet_url}")

        # Ajouter les en-têtes
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Réponses!A1:F1",
            valueInputOption="RAW",
            body={"values": [["Timestamp", "Session ID", "Message", "Réponse", "Transféré", "Lead Info"]]}
        ).execute()

        # Donner les droits au service account
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={"type": "user", "role": "writer", "emailAddress": creds.service_account_email},
        ).execute()
    else:
        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

    # Créer le form avec juste le titre (l'API n'accepte que ça à la création)
    import time
    form = {"info": {"title": title}}
    for attempt in range(3):
        try:
            result = forms_service.forms().create(body=form).execute()
            break
        except Exception as e:
            if attempt < 2:
                logger.warning(f"⚠️ Erreur création form (tentative {attempt+1}/3): {e}")
                time.sleep(2)
            else:
                raise
    form_id = result["formId"]
    form_url = result["responderUri"]
    logger.info(f"✅ Formulaire créé : {form_url}")

    # Ajouter la description via batchUpdate
    forms_service.forms().batchUpdate(formId=form_id, body={
        "requests": [{
            "updateFormInfo": {
                "info": {
                    "description": (
                        "Merci de remplir ce formulaire pour nous aider à créer votre agent conversationnel "
                        "sur mesure. Plus vos réponses sont détaillées, plus votre agent sera efficace!\n\n"
                        "⏱️ Temps estimé : 15-20 minutes\n"
                        "📧 Questions? Contactez-nous à info@chatbotfactory.xyz"
                    ),
                },
                "updateMask": "description",
            }
        }]
    }).execute()

    # ─── Ajouter les questions ──────────────────────────────────────────
    questions = build_questions()

    for i, question in enumerate(questions):
        batch = {
            "requests": [
                {
                    "createItem": {
                        "item": question,
                        "location": {"index": i},
                    }
                }
            ]
        }
        forms_service.forms().batchUpdate(formId=form_id, body=batch).execute()

    logger.info(f"✅ {len(questions)} questions ajoutées")

    # ─── Lier le form au Sheet ──────────────────────────────────────────
    # Note: L'API Forms ne permet pas de lier directement à un Sheet.
    # Il faut utiliser l'interface manuelle ou l'API Drive.
    # Alternative: on configure le form pour envoyer les réponses au Sheet via un trigger.
    logger.info(f"📊 Pour lier le form au Sheet :")
    logger.info(f"   1. Ouvrir le form : {form_url}")
    logger.info(f"   2. Aller dans 'Réponses' → 'Créer une feuille de calcul'")
    logger.info(f"   3. Sélectionner le Sheet existant : {sheet_url}")

    return {
        "form_id": form_id,
        "form_url": form_url,
        "spreadsheet_id": spreadsheet_id,
        "sheet_url": sheet_url,
        "title": title,
        "questions_count": len(questions),
    }


def build_questions() -> list:
    """
    Construit la liste complète des questions du formulaire.
    Chaque question est un dict compatible avec l'API Google Forms.
    """

    questions = [
        # ═══════════════════════════════════════════════════════════════════
        # SECTION 1 : INFORMATIONS GÉNÉRALES
        # ═══════════════════════════════════════════════════════════════════
        {
            "title": "📋 Section 1 : Informations générales sur votre entreprise",
            "description": None,
            "pageBreakItem": {},
        },
        {
            "title": "Quel est le nom de votre entreprise?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Dans quel secteur d'activité œuvrez-vous?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Santé / Clinique médicale / Dentaire"},
                            {"value": "Restauration / Food service"},
                            {"value": "Assurance / Services financiers"},
                            {"value": "Technologies de l'information (TI)"},
                            {"value": "Commerce de détail"},
                            {"value": "Immobilier"},
                            {"value": "Services professionnels (comptable, avocat, consultant)"},
                            {"value": "Éducation / Formation"},
                            {"value": "Construction / Rénovation"},
                            {"value": "Transport / Logistique"},
                            {"value": "Beauté / Bien-être / Spa"},
                            {"value": "Autre"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Quel est l'adresse de votre/vos succursale(s)?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Quel est votre numéro de téléphone principal?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Quel est votre courriel de contact?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Quel est l'URL de votre site web?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },

        # ═══════════════════════════════════════════════════════════════════
        # SECTION 2 : OBJECTIFS COMMERCIAUX
        # ═══════════════════════════════════════════════════════════════════
        {
            "title": "🎯 Section 2 : Objectifs commerciaux et frictions",
            "description": None,
            "pageBreakItem": {},
        },
        {
            "title": "Quel est votre principal point de friction avec vos clients en ce moment?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "CHECKBOX",
                        "options": [
                            {"value": "Trop d'appels répétitifs (mêmes questions)"},
                            {"value": "Délais de réponse trop longs"},
                            {"value": "Perte de clients en dehors des heures d'ouverture"},
                            {"value": "Équipe submergée pendant les pics"},
                            {"value": "Difficulté à qualifier les leads"},
                            {"value": "Manque de personnel pour répondre au téléphone"},
                            {"value": "Clients qui ne trouvent pas l'info sur notre site"},
                            {"value": "Autre"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Si vous avez sélectionné 'Autre', précisez :",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Quel pourcentage de vos demandes sont des questions récurrentes? (horaires, prix, services, disponibilités)",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Moins de 25%"},
                            {"value": "25-50%"},
                            {"value": "50-75%"},
                            {"value": "Plus de 75%"},
                            {"value": "Je ne sais pas"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Quel est l'objectif PRINCIPAL de votre agent conversationnel?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "CHECKBOX",
                        "options": [
                            {"value": "Répondre aux FAQ (questions fréquentes)"},
                            {"value": "Prendre des rendez-vous"},
                            {"value": "Qualifier des leads (collecter nom, courriel, besoin)"},
                            {"value": "Réduire le volume d'appels"},
                            {"value": "Être disponible 24/7"},
                            {"value": "Orienter les clients vers le bon service"},
                            {"value": "Autre"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Avez-vous des pics saisonniers ou horaires où votre équipe est submergée?",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },

        # ═══════════════════════════════════════════════════════════════════
        # SECTION 3 : SERVICES ET CONNAISSANCES
        # ═══════════════════════════════════════════════════════════════════
        {
            "title": "📚 Section 3 : Services et connaissances",
            "description": None,
            "pageBreakItem": {},
        },
        {
            "title": "Listez vos services ou produits principaux (un par ligne)",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Avez-vous des prix ou forfaits standardisés? Si oui, listez-les ou indiquez où les trouver.",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Avez-vous une FAQ existante, un guide de services, ou des documents que le chatbot pourrait utiliser?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "CHECKBOX",
                        "options": [
                            {"value": "Oui, une FAQ sur notre site web"},
                            {"value": "Oui, des documents internes (PDF, Word)"},
                            {"value": "Oui, des scripts d'appel / réponses types"},
                            {"value": "Non, mais je peux les fournir"},
                            {"value": "Non, le chatbot se basera sur mon site web"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Si vous avez des documents à fournir, vous pouvez les téléverser ici ou nous les envoyer par courriel.",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Quelles sont les 5 questions les plus fréquentes que vous recevez de vos clients?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Pour chaque question ci-dessus, quelle est votre réponse idéale? (Question : Réponse, une par ligne)",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },

        # ═══════════════════════════════════════════════════════════════════
        # SECTION 4 : INTÉGRATIONS TECHNIQUES
        # ═══════════════════════════════════════════════════════════════════
        {
            "title": "🔌 Section 4 : Intégrations techniques et canaux",
            "description": None,
            "pageBreakItem": {},
        },
        {
            "title": "Sur quels canaux vos clients vous contactent-ils actuellement?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "CHECKBOX",
                        "options": [
                            {"value": "Téléphone"},
                            {"value": "Courriel"},
                            {"value": "Site web (formulaire de contact)"},
                            {"value": "Facebook / Messenger"},
                            {"value": "Instagram"},
                            {"value": "WhatsApp"},
                            {"value": "En personne"},
                            {"value": "Autre"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Sur quel(s) canal(s) souhaitez-vous déployer l'agent conversationnel?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "CHECKBOX",
                        "options": [
                            {"value": "Site web (widget de chat)"},
                            {"value": "Facebook Messenger"},
                            {"value": "WhatsApp"},
                            {"value": "Instagram DM"},
                            {"value": "Discord"},
                            {"value": "Slack (interne)"},
                            {"value": "Autre"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Utilisez-vous un CRM? Si oui, lequel?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "HubSpot"},
                            {"value": "Salesforce"},
                            {"value": "Zoho CRM"},
                            {"value": "Pipedrive"},
                            {"value": "Autre"},
                            {"value": "Non, je n'utilise pas de CRM"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Utilisez-vous un système de prise de rendez-vous en ligne? Si oui, lequel?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Cal.com"},
                            {"value": "Calendly"},
                            {"value": "Acuity Scheduling"},
                            {"value": "Jane App (cliniques)"},
                            {"value": "Square Appointments"},
                            {"value": "Autre"},
                            {"value": "Non"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Sur quelle plateforme est construit votre site web?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "WordPress"},
                            {"value": "Shopify"},
                            {"value": "Wix"},
                            {"value": "Squarespace"},
                            {"value": "Sur mesure (HTML/CSS/JS)"},
                            {"value": "Je ne sais pas"},
                            {"value": "Autre"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Avez-vous des exigences de conformité spécifiques? (Loi 25, RGPD, HIPAA, etc.)",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },

        # ═══════════════════════════════════════════════════════════════════
        # SECTION 5 : PERSONNALITÉ ET IMAGE DE MARQUE
        # ═══════════════════════════════════════════════════════════════════
        {
            "title": "🎭 Section 5 : Personnalité et image de marque",
            "description": None,
            "pageBreakItem": {},
        },
        {
            "title": "Comment décririez-vous le ton de votre entreprise?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Professionnel et formel"},
                            {"value": "Chaleureux et accessible"},
                            {"value": "Dynamique et moderne"},
                            {"value": "Rassurant et empathique"},
                            {"value": "Décontracté et amical"},
                            {"value": "Expert et technique"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Votre clientèle est-elle bilingue français/anglais?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Oui, bilingue FR/EN"},
                            {"value": "Principalement francophone"},
                            {"value": "Principalement anglophone"},
                            {"value": "Autre langue (précisez ci-dessous)"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Quels sont les valeurs ou mots-clés que l'agent doit refléter?",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Y a-t-il des sujets que l'agent ne doit JAMAIS aborder?",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Dans quelles situations l'agent devrait-il transférer à un humain?",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },

        # ═══════════════════════════════════════════════════════════════════
        # SECTION 6 : INFORMATIONS COMPLÉMENTAIRES
        # ═══════════════════════════════════════════════════════════════════
        {
            "title": "📝 Section 6 : Informations complémentaires",
            "description": None,
            "pageBreakItem": {},
        },
        {
            "title": "Quels sont vos horaires d'ouverture?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Avez-vous des politiques spécifiques que le chatbot devrait connaître? (annulation, retour, confidentialité, etc.)",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Y a-t-il autre chose que nous devrions savoir pour créer votre agent?",
            "questionItem": {
                "question": {
                    "required": False,
                    "textQuestion": {"paragraph": True},
                }
            },
        },
        {
            "title": "Qui sera la personne responsable du suivi avec Chatbot Factory?",
            "questionItem": {
                "question": {
                    "required": True,
                    "textQuestion": {"paragraph": False},
                }
            },
        },
        {
            "title": "Quel est le meilleur moyen de vous contacter pour le suivi?",
            "questionItem": {
                "question": {
                    "required": True,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Courriel"},
                            {"value": "Téléphone"},
                            {"value": "Visioconférence (Zoom, Google Meet)"},
                        ],
                    },
                }
            },
        },
        {
            "title": "Quel est votre budget approximatif pour ce projet?",
            "questionItem": {
                "question": {
                    "required": False,
                    "choiceQuestion": {
                        "type": "RADIO",
                        "options": [
                            {"value": "Moins de 1 000$"},
                            {"value": "1 000$ - 2 500$"},
                            {"value": "2 500$ - 5 000$"},
                            {"value": "5 000$ - 10 000$"},
                            {"value": "Plus de 10 000$"},
                            {"value": "Je préfère discuter"},
                        ],
                    },
                }
            },
        },
    ]

    return questions


def main():
    parser = argparse.ArgumentParser(description="Chatbot Factory — Créateur de Google Form")
    parser.add_argument("--title", default="Chatbot Factory — Onboarding Client", help="Titre du formulaire")
    parser.add_argument("--spreadsheet-id", help="ID du Google Sheet pour stocker les réponses")
    args = parser.parse_args()

    logger.info("📋 Chatbot Factory — Création du formulaire d'onboarding")
    logger.info("=" * 50)

    result = create_form(args.title, args.spreadsheet_id)

    logger.info("")
    logger.info("=" * 50)
    logger.info("✅ FORMULAIRE CRÉÉ AVEC SUCCÈS")
    logger.info(f"📋 Titre : {result['title']}")
    logger.info(f"🔗 URL : {result['form_url']}")
    logger.info(f"📊 Questions : {result['questions_count']}")
    logger.info("")
    logger.info("💡 Prochaines étapes :")
    logger.info("  1. Ouvrir le formulaire et vérifier les questions")
    logger.info("  2. Aller dans 'Réponses' → 'Créer une feuille de calcul' pour lier à Google Sheets")
    logger.info("  3. Partager le lien du formulaire avec le client")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
