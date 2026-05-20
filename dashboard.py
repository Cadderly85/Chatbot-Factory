#!/usr/bin/env python3
"""
Chatbot Factory — Dashboard de Monitoring
==========================================
Streamlit dashboard pour surveiller tous les agents Chatbot Factory.

Lecture des données depuis Google Sheets :
  - Onglet "Conversations" : journal de toutes les conversations
  - Onglet "Leads" : leads captés par les agents

Usage:
    streamlit run dashboard.py

Dépendances:
    pip install streamlit gspread google-auth pandas plotly python-dotenv
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

# ─── Configuration Google Sheets ──────────────────────────────────────────────

GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")

# IDs des Google Sheets par client
# Format : {"client_name": "spreadsheet_id", ...}
# Peut aussi être chargé depuis un fichier JSON
CLIENTS_SHEETS_FILE = Path("clients_sheets.json")


def load_clients_config() -> dict:
    """Charge la configuration des clients (nom → spreadsheet_id)."""
    if CLIENTS_SHEETS_FILE.exists():
        with open(CLIENTS_SHEETS_FILE, "r") as f:
            return json.load(f)
    # Fallback : variable d'environnement
    sheets_json = os.getenv("CLIENTS_SHEETS", "{}")
    return json.loads(sheets_json)


def read_sheet(spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
    """Lit un onglet Google Sheet et retourne un DataFrame."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS, scopes=scopes)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        data = sheet.get_all_records()

        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        return df

    except Exception as e:
        logger.error(f"Erreur lecture Sheet {spreadsheet_id}/{worksheet_name}: {e}")
        return pd.DataFrame()


def load_all_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Charge les données de tous les clients.
    Retourne (conversations_df, leads_df) avec une colonne 'client'.
    """
    clients = load_clients_config()

    all_conversations = []
    all_leads = []

    for client_name, sheet_id in clients.items():
        # Conversations
        conv_df = read_sheet(sheet_id, "Conversations")
        if not conv_df.empty:
            conv_df["client"] = client_name
            all_conversations.append(conv_df)

        # Leads
        leads_df = read_sheet(sheet_id, "Leads")
        if not leads_df.empty:
            leads_df["client"] = client_name
            all_leads.append(leads_df)

    conversations = pd.concat(all_conversations, ignore_index=True) if all_conversations else pd.DataFrame()
    leads = pd.concat(all_leads, ignore_index=True) if all_leads else pd.DataFrame()

    return conversations, leads


# ─── Traitement des données ───────────────────────────────────────────────────

def process_conversations(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie et enrichit le DataFrame de conversations."""
    if df.empty:
        return df

    # Parser la date
    date_col = None
    for col in ["Date", "date", "Timestamp", "timestamp", "Horodatage"]:
        if col in df.columns:
            date_col = col
            break

    if date_col:
        df["datetime"] = pd.to_datetime(df[date_col], errors="coerce")
    else:
        df["datetime"] = pd.NaT

    df["date"] = df["datetime"].dt.date
    df["hour"] = df["datetime"].dt.hour
    df["day_of_week"] = df["datetime"].dt.day_name()

    # Détecter les transferts humains
    transfer_col = None
    for col in ["Transféré", "transferred", "Transfer", "transfer"]:
        if col in df.columns:
            transfer_col = col
            break

    if transfer_col:
        df["transferred"] = df[transfer_col].astype(str).str.lower().isin(["oui", "yes", "true", "1"])
    else:
        df["transferred"] = False

    return df


def process_leads(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie et enrichit le DataFrame de leads."""
    if df.empty:
        return df

    date_col = None
    for col in ["Date", "date", "Timestamp", "timestamp"]:
        if col in df.columns:
            date_col = col
            break

    if date_col:
        df["datetime"] = pd.to_datetime(df[date_col], errors="coerce")
        df["date"] = df["datetime"].dt.date
    else:
        df["datetime"] = pd.NaT
        df["date"] = None

    return df


# ─── Métriques ────────────────────────────────────────────────────────────────

def compute_metrics(conversations: pd.DataFrame, leads: pd.DataFrame) -> dict:
    """Calcule les métriques clés."""
    metrics = {}

    if not conversations.empty:
        metrics["total_conversations"] = len(conversations)
        metrics["unique_sessions"] = conversations["session_id"].nunique() if "session_id" in conversations.columns else "N/A"
        metrics["transfer_rate"] = conversations["transferred"].mean() * 100 if "transferred" in conversations.columns else 0
        metrics["resolution_rate"] = 100 - metrics["transfer_rate"]
        metrics["avg_per_day"] = conversations.groupby("date").size().mean() if "date" in conversations.columns else 0
    else:
        metrics["total_conversations"] = 0
        metrics["unique_sessions"] = 0
        metrics["transfer_rate"] = 0
        metrics["resolution_rate"] = 0
        metrics["avg_per_day"] = 0

    if not leads.empty:
        metrics["total_leads"] = len(leads)
        metrics["leads_per_day"] = leads.groupby("date").size().mean() if "date" in leads.columns else 0
    else:
        metrics["total_leads"] = 0
        metrics["leads_per_day"] = 0

    return metrics


# ─── Dashboard Streamlit ──────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="Chatbot Factory — Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # ─── Titre ─────────────────────────────────────────────────────────────

    st.title("🤖 Chatbot Factory — Dashboard de Monitoring")
    st.markdown("Vue d'ensemble de tous vos agents conversationnels")

    # ─── Sidebar ───────────────────────────────────────────────────────────

    st.sidebar.title("⚙️ Configuration")

    # Filtre client
    clients = load_clients_config()
    client_names = ["Tous les clients"] + list(clients.keys())
    selected_client = st.sidebar.selectbox("Client", client_names)

    # Filtre date
    date_range = st.sidebar.selectbox(
        "Période",
        ["7 derniers jours", "30 derniers jours", "90 derniers jours", "Tout"],
        index=1,
    )

    if date_range == "7 derniers jours":
        days_filter = 7
    elif date_range == "30 derniers jours":
        days_filter = 30
    elif date_range == "90 derniers jours":
        days_filter = 90
    else:
        days_filter = None

    # Bouton refresh
    if st.sidebar.button("🔄 Rafraîchir les données"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Légende")
    st.sidebar.markdown("- **Taux de résolution** = % de conversations sans transfert humain")
    st.sidebar.markdown("- **Leads** = contacts qualifiés captés par l'agent")

    # ─── Chargement des données ────────────────────────────────────────────

    with st.spinner("Chargement des données..."):
        conversations, leads = load_all_data()

    if conversations.empty and leads.empty:
        st.warning("⚠️ Aucune donnée trouvée. Vérifiez la configuration des clients dans `clients_sheets.json`.")
        st.info("""
        **Pour commencer :**
        1. Créez un fichier `clients_sheets.json` à côté du dashboard :
        ```json
        {
          "Clinique Santé Plus": "1A2B3C4D5E6F...",
          "Restaurant Le Gourmet": "7G8H9I0J1K2L..."
        }
        ```
        2. Rafraîchissez la page
        """)
        return

    # Traitement
    conversations = process_conversations(conversations)
    leads = process_leads(leads)

    # Filtres
    if selected_client != "Tous les clients":
        conversations = conversations[conversations["client"] == selected_client] if not conversations.empty else conversations
        leads = leads[leads["client"] == selected_client] if not leads.empty else leads

    if days_filter and not conversations.empty and "datetime" in conversations.columns:
        cutoff = datetime.now() - timedelta(days=days_filter)
        conversations = conversations[conversations["datetime"] >= cutoff]

    if days_filter and not leads.empty and "datetime" in leads.columns:
        cutoff = datetime.now() - timedelta(days=days_filter)
        leads = leads[leads["datetime"] >= cutoff]

    # Métriques
    metrics = compute_metrics(conversations, leads)

    # ─── Métriques principales ─────────────────────────────────────────────

    st.markdown("### 📊 Métriques clés")

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("💬 Conversations", f"{metrics['total_conversations']:,}")
    col2.metric("👤 Sessions uniques", f"{metrics['unique_sessions']:,}")
    col3.metric("✅ Taux de résolution", f"{metrics['resolution_rate']:.1f}%")
    col4.metric("🔄 Transferts humains", f"{metrics['transfer_rate']:.1f}%")
    col5.metric("🎯 Leads captés", f"{metrics['total_leads']:,}")

    st.markdown("---")

    # ─── Graphiques ────────────────────────────────────────────────────────

    if not conversations.empty:
        col_left, col_right = st.columns(2)

        # Graphique 1 : Conversations par jour
        with col_left:
            st.markdown("#### 📈 Conversations par jour")
            daily = conversations.groupby("date").size().reset_index(name="count")
            daily["date"] = pd.to_datetime(daily["date"])

            fig = px.bar(
                daily,
                x="date",
                y="count",
                labels={"date": "Date", "count": "Conversations"},
                color_discrete_sequence=["#6366f1"],
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                height=300,
                xaxis_title="",
                yaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Graphique 2 : Taux de résolution par jour
        with col_right:
            st.markdown("#### ✅ Taux de résolution par jour")
            if "transferred" in conversations.columns:
                daily_res = conversations.groupby("date").agg(
                    total=("transferred", "count"),
                    transferred=("transferred", "sum"),
                ).reset_index()
                daily_res["resolution_rate"] = (1 - daily_res["transferred"] / daily_res["total"]) * 100
                daily_res["date"] = pd.to_datetime(daily_res["date"])

                fig = px.line(
                    daily_res,
                    x="date",
                    y="resolution_rate",
                    labels={"date": "Date", "resolution_rate": "Taux de résolution (%)"},
                    color_discrete_sequence=["#22c55e"],
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=300,
                    xaxis_title="",
                    yaxis_title="",
                    yaxis_range=[0, 100],
                )
                st.plotly_chart(fig, use_container_width=True)

        # Graphique 3 : Distribution horaire
        col_left2, col_right2 = st.columns(2)

        with col_left2:
            st.markdown("#### 🕐 Distribution horaire")
            hourly = conversations.groupby("hour").size().reset_index(name="count")

            fig = px.bar(
                hourly,
                x="hour",
                y="count",
                labels={"hour": "Heure", "count": "Conversations"},
                color_discrete_sequence=["#8b5cf6"],
            )
            fig.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                height=300,
                xaxis_title="Heure de la journée",
                yaxis_title="",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Graphique 4 : Par client (si plusieurs)
        with col_right2:
            st.markdown("#### 🏢 Par client")
            if "client" in conversations.columns and conversations["client"].nunique() > 1:
                by_client = conversations.groupby("client").size().reset_index(name="count")
                by_client = by_client.sort_values("count", ascending=True)

                fig = px.bar(
                    by_client,
                    x="count",
                    y="client",
                    orientation="h",
                    labels={"client": "", "count": "Conversations"},
                    color_discrete_sequence=["#f59e0b"],
                )
                fig.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=300,
                    xaxis_title="",
                    yaxis_title="",
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Ajoutez plus de clients pour voir la comparaison.")

    # ─── Section Leads ─────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("### 🎯 Leads captés")

    if not leads.empty:
        col_l1, col_l2 = st.columns(2)

        with col_l1:
            # Leads par jour
            st.markdown("#### Leads par jour")
            daily_leads = leads.groupby("date").size().reset_index(name="count")
            daily_leads["date"] = pd.to_datetime(daily_leads["date"])

            fig = px.bar(
                daily_leads,
                x="date",
                y="count",
                labels={"date": "Date", "count": "Leads"},
                color_discrete_sequence=["#10b981"],
            )
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=250)
            st.plotly_chart(fig, use_container_width=True)

        with col_l2:
            # Leads par client
            if "client" in leads.columns and leads["client"].nunique() > 1:
                st.markdown("#### Leads par client")
                by_client_leads = leads.groupby("client").size().reset_index(name="count")

                fig = px.pie(
                    by_client_leads,
                    values="count",
                    names="client",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                )
                fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=250)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Ajoutez plus de clients pour voir la répartition.")

        # Tableau des derniers leads
        st.markdown("#### Derniers leads")
        display_cols = [c for c in ["date", "client", "Nom", "Name", "nom", "name", "Courriel", "Email", "email", "Intérêt", "Interest", "intérêt", "Source", "source"] if c in leads.columns]
        if display_cols:
            st.dataframe(
                leads[display_cols].sort_values("datetime", ascending=False).head(20) if "datetime" in leads.columns else leads[display_cols].head(20),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.dataframe(leaders.head(20), use_container_width=True, hide_index=True)
    else:
        st.info("Aucun lead capté pour le moment.")

    # ─── Section Conversations récentes ─────────────────────────────────────

    st.markdown("---")
    st.markdown("### 💬 Conversations récentes")

    if not conversations.empty:
        display_cols = [c for c in ["datetime", "client", "session_id", "Message", "message", "User", "user", "Réponse", "Response", "response", "transferred"] if c in conversations.columns]

        if display_cols:
            recent = conversations.sort_values("datetime", ascending=False).head(30) if "datetime" in conversations.columns else conversations.head(30)
            st.dataframe(
                recent[display_cols],
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("Aucune conversation enregistrée pour le moment.")

    # ─── Footer ────────────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown(
        f"<p style='text-align: center; color: #9ca3af; font-size: 12px;'>"
        f"Chatbot Factory Dashboard — Dernière mise à jour : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        f"</p>",
        unsafe_allow_html=True,
    )


# ─── Point d'entrée ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
