/**
 * Chatbot Factory — Widget de Chat
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Installation : Ajouter cette BALISE dans le <head> ou avant </body> du site client :
 *
 *   <script src="https://cdn.chatbotfactory.xyz/widget.js"
 *           data-agent-url="https://mon-agent.up.railway.app"
 *           data-client-name="Nom du Client"
 *           data-primary-color="#6366f1"
 *           data-position="right">
 *   </script>
 *
 * Personnalisation :
 *   data-agent-url       URL de l'agent déployé (Render, Railway, etc.) — OBLIGATOIRE
 *   data-client-name     Nom affiché dans l'en-tête du chat
 *   data-primary-color   Couleur principale (boutons, en-tête, bulles bot)
 *   data-position        Position du bouton : "right" (défaut) ou "left"
 *   data-welcome-message Message d'accueil personnalisé
 *   data-language        "fr" (défaut) ou "en"
 *   data-avatar-url      URL d'un avatar personnalisé (optionnel)
 *
 * ═══════════════════════════════════════════════════════════════════════════
 */

(function () {
  "use strict";

  // ─── Configuration ──────────────────────────────────────────────────────

  const scriptTag = document.currentScript;
  const CONFIG = {
    agentUrl: scriptTag?.dataset?.agentUrl || "",
    clientName: scriptTag?.dataset?.clientName || "Assistant",
    primaryColor: scriptTag?.dataset?.primaryColor || "#6366f1",
    position: scriptTag?.dataset?.position || "right",
    welcomeMessage: scriptTag?.dataset?.welcomeMessage || "",
    language: scriptTag?.dataset?.language || "fr",
    avatarUrl: scriptTag?.dataset?.avatarUrl || "",
  };

  if (!CONFIG.agentUrl) {
    console.error("[Chatbot Factory] data-agent-url est requis. Voir documentation.");
    return;
  }

  // Textes selon la langue
  const TEXTS = {
    fr: {
      placeholder: "Écrivez votre message...",
      send: "Envoyer",
      online: "En ligne",
      offline: "Hors ligne",
      typing: "Écrit...",
      errorMessage: "Désolé, une erreur s'est produite. Veuillez réessayer.",
      transferMessage: "Je vous transfère à un membre de notre équipe. Un instant...",
      newConversation: "Nouvelle conversation",
      closeChat: "Fermer le chat",
      minimizeChat: "Réduire",
    },
    en: {
      placeholder: "Type your message...",
      send: "Send",
      online: "Online",
      offline: "Offline",
      typing: "Typing...",
      errorMessage: "Sorry, an error occurred. Please try again.",
      transferMessage: "Transferring you to a team member. One moment...",
      newConversation: "New conversation",
      closeChat: "Close chat",
      minimizeChat: "Minimize",
    },
  };
  const T = TEXTS[CONFIG.language] || TEXTS.fr;

  // State
  let sessionId = "session_" + Math.random().toString(36).substring(2, 15);
  let isOpen = false;
  let isMinimized = false;
  let isTyping = false;
  let messageHistory = [];

  // ─── Styles ─────────────────────────────────────────────────────────────

  const STYLES = `
    /* ═══════════════════════════════════════════════════════════════════════
       Chatbot Factory — Premium Widget Styles
       ═══════════════════════════════════════════════════════════════════════ */

    .cf-widget-container {
      position: fixed;
      bottom: 24px;
      ${CONFIG.position}: 24px;
      z-index: 999999;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    /* ─── Floating Action Button ─────────────────────────────────────────── */

    .cf-fab {
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: linear-gradient(135deg, ${CONFIG.primaryColor}, ${adjustColor(CONFIG.primaryColor, -30)});
      border: none;
      cursor: pointer;
      box-shadow:
        0 4px 24px rgba(0,0,0,0.18),
        0 0 0 0 ${hexToRgba(CONFIG.primaryColor, 0.4)};
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      animation: cf-pulse 2.5s ease-in-out infinite;
    }
    .cf-fab:hover {
      transform: scale(1.12) rotate(8deg);
      box-shadow:
        0 8px 32px rgba(0,0,0,0.25),
        0 0 0 8px ${hexToRgba(CONFIG.primaryColor, 0.15)};
      animation: none;
    }
    .cf-fab:active {
      transform: scale(0.95);
    }
    .cf-fab svg {
      width: 30px;
      height: 30px;
      fill: white;
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .cf-fab .cf-close-icon {
      display: none;
    }
    .cf-fab.cf-open .cf-chat-icon {
      display: none;
    }
    .cf-fab.cf-open .cf-close-icon {
      display: block;
    }
    .cf-fab.cf-open {
      animation: none;
      transform: rotate(90deg);
    }

    @keyframes cf-pulse {
      0%, 100% { box-shadow: 0 4px 24px rgba(0,0,0,0.18), 0 0 0 0 ${hexToRgba(CONFIG.primaryColor, 0.4)}; }
      50% { box-shadow: 0 4px 24px rgba(0,0,0,0.18), 0 0 0 12px ${hexToRgba(CONFIG.primaryColor, 0)}; }
    }

    /* ─── Notification badge ─────────────────────────────────────────────── */

    .cf-badge {
      position: absolute;
      top: -2px;
      right: -2px;
      width: 20px;
      height: 20px;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      border-radius: 50%;
      color: white;
      font-size: 11px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2.5px solid white;
      box-shadow: 0 2px 8px rgba(239,68,68,0.4);
      animation: cf-badge-pop 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    @keyframes cf-badge-pop {
      0% { transform: scale(0); }
      80% { transform: scale(1.2); }
      100% { transform: scale(1); }
    }

    /* ─── Chat window ────────────────────────────────────────────────────── */

    .cf-chat-window {
      display: none;
      width: 400px;
      height: 600px;
      max-height: calc(100vh - 120px);
      background: #ffffff;
      border-radius: 20px;
      box-shadow:
        0 25px 60px rgba(0,0,0,0.12),
        0 8px 24px rgba(0,0,0,0.08);
      flex-direction: column;
      overflow: hidden;
      margin-bottom: 16px;
      animation: cf-slide-up 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      border: 1px solid rgba(0,0,0,0.04);
    }
    .cf-chat-window.cf-visible {
      display: flex;
    }
    .cf-chat-window.cf-minimized {
      height: auto;
    }
    .cf-chat-window.cf-minimized .cf-messages,
    .cf-chat-window.cf-minimized .cf-input-area {
      display: none;
    }

    @keyframes cf-slide-up {
      from { opacity: 0; transform: translateY(30px) scale(0.92); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* ─── Header ─────────────────────────────────────────────────────────── */

    .cf-header {
      background: linear-gradient(135deg, ${CONFIG.primaryColor}, ${adjustColor(CONFIG.primaryColor, -20)});
      color: white;
      padding: 18px 20px;
      display: flex;
      align-items: center;
      gap: 14px;
      cursor: pointer;
      user-select: none;
      position: relative;
      overflow: hidden;
    }
    .cf-header::before {
      content: '';
      position: absolute;
      top: -50%;
      right: -30%;
      width: 120px;
      height: 120px;
      background: rgba(255,255,255,0.06);
      border-radius: 50%;
    }
    .cf-header::after {
      content: '';
      position: absolute;
      bottom: -60%;
      left: -10%;
      width: 80px;
      height: 80px;
      background: rgba(255,255,255,0.04);
      border-radius: 50%;
    }

    .cf-header-avatar {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: rgba(255,255,255,0.15);
      backdrop-filter: blur(10px);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      overflow: hidden;
      border: 2px solid rgba(255,255,255,0.25);
      flex-shrink: 0;
      position: relative;
      z-index: 1;
    }
    .cf-header-avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }

    .cf-header-info {
      flex: 1;
      position: relative;
      z-index: 1;
    }
    .cf-header-name {
      font-weight: 700;
      font-size: 16px;
      letter-spacing: -0.2px;
    }
    .cf-header-status {
      font-size: 12px;
      opacity: 0.9;
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 2px;
    }
    .cf-status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #4ade80;
      display: inline-block;
      box-shadow: 0 0 6px rgba(74,222,128,0.5);
    }
    .cf-status-dot.cf-offline {
      background: #f87171;
      box-shadow: 0 0 6px rgba(248,113,113,0.5);
    }

    .cf-header-actions {
      display: flex;
      gap: 2px;
      position: relative;
      z-index: 1;
    }
    .cf-header-btn {
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      padding: 8px;
      border-radius: 10px;
      opacity: 0.75;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .cf-header-btn:hover {
      opacity: 1;
      background: rgba(255,255,255,0.15);
      transform: scale(1.1);
    }
    .cf-header-btn svg {
      width: 18px;
      height: 18px;
      fill: currentColor;
    }

    /* ─── Messages area ──────────────────────────────────────────────────── */

    .cf-messages {
      flex: 1;
      overflow-y: auto;
      padding: 20px 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      background: linear-gradient(180deg, #f8f9fc 0%, #f0f2f7 100%);
    }
    .cf-messages::-webkit-scrollbar {
      width: 6px;
    }
    .cf-messages::-webkit-scrollbar-track {
      background: transparent;
    }
    .cf-messages::-webkit-scrollbar-thumb {
      background: #d1d5db;
      border-radius: 10px;
    }
    .cf-messages::-webkit-scrollbar-thumb:hover {
      background: #9ca3af;
    }

    /* ─── Message bubbles ────────────────────────────────────────────────── */

    .cf-message {
      max-width: 82%;
      padding: 12px 16px;
      border-radius: 18px;
      font-size: 14px;
      line-height: 1.55;
      animation: cf-fade-in 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      word-wrap: break-word;
      position: relative;
    }
    @keyframes cf-fade-in {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .cf-message-bot {
      background: white;
      color: #1a1a2e;
      align-self: flex-start;
      border-bottom-left-radius: 6px;
      box-shadow:
        0 2px 8px rgba(0,0,0,0.04),
        0 1px 3px rgba(0,0,0,0.06);
    }
    .cf-message-bot::before {
      content: '';
      position: absolute;
      left: -6px;
      bottom: 12px;
      width: 12px;
      height: 12px;
      background: white;
      border-radius: 0 0 0 4px;
      transform: rotate(45deg);
    }

    .cf-message-user {
      background: linear-gradient(135deg, ${CONFIG.primaryColor}, ${adjustColor(CONFIG.primaryColor, -15)});
      color: white;
      align-self: flex-end;
      border-bottom-right-radius: 6px;
      box-shadow:
        0 2px 12px ${hexToRgba(CONFIG.primaryColor, 0.25)},
        0 1px 3px rgba(0,0,0,0.08);
    }

    .cf-message-time {
      font-size: 10px;
      opacity: 0.45;
      margin-top: 6px;
      text-align: right;
      font-weight: 500;
    }
    .cf-message-bot .cf-message-time {
      text-align: left;
    }

    /* ─── Typing indicator ───────────────────────────────────────────────── */

    .cf-typing-indicator {
      display: none;
      align-self: flex-start;
      background: white;
      padding: 14px 18px;
      border-radius: 18px;
      border-bottom-left-radius: 6px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
      margin-left: 0;
    }
    .cf-typing-indicator.cf-visible {
      display: flex;
      gap: 5px;
      animation: cf-fade-in 0.3s ease;
    }
    .cf-typing-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #c4c4c4;
      animation: cf-typing-bounce 1.4s infinite ease-in-out;
    }
    .cf-typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .cf-typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes cf-typing-bounce {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
      30% { transform: translateY(-8px); opacity: 1; }
    }

    /* ─── Input area ─────────────────────────────────────────────────────── */

    .cf-input-area {
      padding: 14px 16px;
      border-top: 1px solid #eef0f3;
      background: white;
      display: flex;
      gap: 10px;
      align-items: flex-end;
    }
    .cf-input {
      flex: 1;
      border: 1.5px solid #e8eaed;
      border-radius: 24px;
      padding: 11px 18px;
      font-size: 14px;
      font-family: inherit;
      resize: none;
      outline: none;
      max-height: 100px;
      transition: all 0.25s;
      line-height: 1.45;
      background: #f8f9fb;
    }
    .cf-input:focus {
      border-color: ${CONFIG.primaryColor};
      background: white;
      box-shadow: 0 0 0 3px ${hexToRgba(CONFIG.primaryColor, 0.1)};
    }
    .cf-input::placeholder {
      color: #a0a4ad;
    }

    .cf-send-btn {
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: linear-gradient(135deg, ${CONFIG.primaryColor}, ${adjustColor(CONFIG.primaryColor, -20)});
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 3px 12px ${hexToRgba(CONFIG.primaryColor, 0.3)};
    }
    .cf-send-btn:hover {
      transform: scale(1.1);
      box-shadow: 0 5px 20px ${hexToRgba(CONFIG.primaryColor, 0.4)};
    }
    .cf-send-btn:active {
      transform: scale(0.92);
    }
    .cf-send-btn:disabled {
      opacity: 0.35;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    .cf-send-btn svg {
      width: 20px;
      height: 20px;
      fill: white;
    }

    /* ─── Welcome text ───────────────────────────────────────────────────── */

    .cf-welcome {
      text-align: center;
      padding: 10px 20px;
      color: #9ca3af;
      font-size: 12px;
      font-weight: 500;
    }

    /* ─── Responsive ─────────────────────────────────────────────────────── */

    @media (max-width: 480px) {
      .cf-chat-window {
        width: calc(100vw - 16px);
        height: calc(100vh - 90px);
        max-height: none;
        border-radius: 20px 20px 0 0;
        margin-bottom: 0;
      }
      .cf-widget-container {
        bottom: 8px;
        ${CONFIG.position}: 8px;
      }
      .cf-fab {
        width: 58px;
        height: 58px;
      }
      .cf-fab svg {
        width: 26px;
        height: 26px;
      }
    }
  `;

  // ─── Helpers couleurs ────────────────────────────────────────────────────

  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function adjustColor(hex, amount) {
    const num = parseInt(hex.replace('#', ''), 16);
    const r = Math.min(255, Math.max(0, (num >> 16) + amount));
    const g = Math.min(255, Math.max(0, ((num >> 8) & 0x00FF) + amount));
    const b = Math.min(255, Math.max(0, (num & 0x0000FF) + amount));
    return '#' + (0x1000000 + r * 0x10000 + g * 0x100 + b).toString(16).slice(1);
  }

  // ─── SVG Icons ──────────────────────────────────────────────────────────

  const ICONS = {
    chat: `<svg class="cf-chat-icon" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/></svg>`,
    close: `<svg class="cf-close-icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`,
    minimize: `<svg viewBox="0 0 24 24"><path d="M19 13H5v-2h14v2z"/></svg>`,
    send: `<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>`,
  };

  // ─── Construction du DOM ─────────────────────────────────────────────────

  function buildWidget() {
    const container = document.createElement("div");
    container.className = "cf-widget-container";
    container.innerHTML = `
      <style>${STYLES}</style>

      <!-- Fenêtre de chat -->
      <div class="cf-chat-window" id="cf-chat-window">
        <!-- En-tête -->
        <div class="cf-header" id="cf-header">
          <div class="cf-header-avatar">
            ${CONFIG.avatarUrl ? `<img src="${CONFIG.avatarUrl}" alt="${CONFIG.clientName}">` : "🤖"}
          </div>
          <div class="cf-header-info">
            <div class="cf-header-name">${escapeHtml(CONFIG.clientName)}</div>
            <div class="cf-header-status">
              <span class="cf-status-dot" id="cf-status-dot"></span>
              <span id="cf-status-text">${T.online}</span>
            </div>
          </div>
          <div class="cf-header-actions">
            <button class="cf-header-btn" id="cf-new-chat" title="${T.newConversation}">${ICONS.refresh}</button>
            <button class="cf-header-btn" id="cf-minimize" title="${T.minimizeChat}">${ICONS.minimize}</button>
          </div>
        </div>

        <!-- Messages -->
        <div class="cf-messages" id="cf-messages">
          <div class="cf-welcome">Propulsé par Chatbot Factory 🚀</div>
        </div>

        <!-- Indicateur de frappe -->
        <div class="cf-typing-indicator" id="cf-typing">
          <div class="cf-typing-dot"></div>
          <div class="cf-typing-dot"></div>
          <div class="cf-typing-dot"></div>
        </div>

        <!-- Zone de saisie -->
        <div class="cf-input-area">
          <textarea class="cf-input" id="cf-input" rows="1" placeholder="${T.placeholder}" aria-label="${T.placeholder}"></textarea>
          <button class="cf-send-btn" id="cf-send" aria-label="${T.send}">${ICONS.send}</button>
        </div>
      </div>

      <!-- Bouton flottant -->
      <button class="cf-fab" id="cf-fab" aria-label="Ouvrir le chat">
        ${ICONS.chat}
        ${ICONS.close}
      </button>
    `;

    document.body.appendChild(container);
    return container;
  }

  // ─── Initialisation ─────────────────────────────────────────────────────

  const widget = buildWidget();
  const fab = document.getElementById("cf-fab");
  const chatWindow = document.getElementById("cf-chat-window");
  const messagesContainer = document.getElementById("cf-messages");
  const input = document.getElementById("cf-input");
  const sendBtn = document.getElementById("cf-send");
  const typingIndicator = document.getElementById("cf-typing");
  const statusDot = document.getElementById("cf-status-dot");
  const statusText = document.getElementById("cf-status-text");
  const minimizeBtn = document.getElementById("cf-minimize");
  const newChatBtn = document.getElementById("cf-new-chat");
  const header = document.getElementById("cf-header");

  // Vérifier la santé de l'agent au chargement
  checkHealth();

  // ─── Événements ─────────────────────────────────────────────────────────

  fab.addEventListener("click", toggleChat);
  header.addEventListener("click", () => {
    if (isMinimized) toggleMinimize();
  });
  minimizeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMinimize();
  });
  newChatBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    startNewConversation();
  });
  sendBtn.addEventListener("click", sendMessage);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Auto-resize du textarea
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 100) + "px";
  });

  // ─── Fonctions ──────────────────────────────────────────────────────────

  function toggleChat() {
    isOpen = !isOpen;
    fab.classList.toggle("cf-open", isOpen);
    chatWindow.classList.toggle("cf-visible", isOpen);

    if (isOpen && isMinimized) {
      isMinimized = false;
      chatWindow.classList.remove("cf-minimized");
    }

    if (isOpen) {
      input.focus();
      // Message de bienvenue si c'est la première ouverture
      if (messageHistory.length === 0 && CONFIG.welcomeMessage) {
        addMessage(CONFIG.welcomeMessage, "bot");
      }
    }
  }

  function toggleMinimize() {
    isMinimized = !isMinimized;
    chatWindow.classList.toggle("cf-minimized", isMinimized);
  }

  function startNewConversation() {
    sessionId = "session_" + Math.random().toString(36).substring(2, 15);
    messageHistory = [];
    messagesContainer.innerHTML = '<div class="cf-welcome">Propulsé par Chatbot Factory 🚀</div>';
    if (CONFIG.welcomeMessage) {
      addMessage(CONFIG.welcomeMessage, "bot");
    }
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || isTyping) return;

    // Afficher le message utilisateur
    addMessage(text, "user");
    input.value = "";
    input.style.height = "auto";

    // Afficher l'indicateur de frappe
    isTyping = true;
    typingIndicator.classList.add("cf-visible");
    sendBtn.disabled = true;
    scrollToBottom();

    try {
      const response = await fetch(`${CONFIG.agentUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      const botResponse = data.response || T.errorMessage;
      const transferred = data.transferred || false;

      addMessage(botResponse, "bot");

      if (transferred) {
        addMessage(T.transferMessage, "bot");
      }

    } catch (error) {
      console.error("[Chatbot Factory] Erreur:", error);
      addMessage(T.errorMessage, "bot");
      statusDot.classList.add("cf-offline");
      statusText.textContent = T.offline;
    } finally {
      isTyping = false;
      typingIndicator.classList.remove("cf-visible");
      sendBtn.disabled = false;
      scrollToBottom();
    }
  }

  function addMessage(text, sender) {
    const time = new Date().toLocaleTimeString(CONFIG.language === "fr" ? "fr-CA" : "en-US", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const msgDiv = document.createElement("div");
    msgDiv.className = `cf-message cf-message-${sender}`;
    msgDiv.innerHTML = `
      ${escapeHtml(text).replace(/\n/g, "<br>")}
      <div class="cf-message-time">${time}</div>
    `;

    // Retirer le message de bienvenue si présent
    const welcome = messagesContainer.querySelector(".cf-welcome");
    if (welcome) welcome.remove();

    messagesContainer.appendChild(msgDiv);
    messageHistory.push({ sender, text, time });
    scrollToBottom();
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  async function checkHealth() {
    try {
      const resp = await fetch(`${CONFIG.agentUrl}/health`, { method: "GET", signal: AbortSignal.timeout(5000) });
      if (resp.ok) {
        statusDot.classList.remove("cf-offline");
        statusText.textContent = T.online;
      } else {
        throw new Error("not ok");
      }
    } catch {
      statusDot.classList.add("cf-offline");
      statusText.textContent = T.offline;
    }
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ─── API publique (optionnel — pour contrôle externe) ────────────────────

  window.ChatbotFactory = {
    open: () => { if (!isOpen) toggleChat(); },
    close: () => { if (isOpen) toggleChat(); },
    toggle: toggleChat,
    newConversation: startNewConversation,
    checkHealth,
    getHistory: () => [...messageHistory],
    setSessionId: (id) => { sessionId = id; },
  };

})();
