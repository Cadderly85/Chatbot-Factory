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
    /* Container principal */
    .cf-widget-container {
      position: fixed;
      bottom: 20px;
      ${CONFIG.position}: 20px;
      z-index: 999999;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }

    /* Bouton d'ouverture */
    .cf-fab {
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: ${CONFIG.primaryColor};
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s, box-shadow 0.2s;
      position: relative;
    }
    .cf-fab:hover {
      transform: scale(1.08);
      box-shadow: 0 6px 25px rgba(0,0,0,0.2);
    }
    .cf-fab svg {
      width: 28px;
      height: 28px;
      fill: white;
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

    /* Badge notification */
    .cf-badge {
      position: absolute;
      top: -2px;
      right: -2px;
      width: 18px;
      height: 18px;
      background: #ef4444;
      border-radius: 50%;
      color: white;
      font-size: 11px;
      font-weight: bold;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid white;
    }

    /* Fenêtre de chat */
    .cf-chat-window {
      display: none;
      width: 380px;
      height: 560px;
      max-height: 70vh;
      background: white;
      border-radius: 16px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.15);
      flex-direction: column;
      overflow: hidden;
      margin-bottom: 12px;
      animation: cf-slide-up 0.3s ease;
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
      from { opacity: 0; transform: translateY(20px) scale(0.95); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* En-tête */
    .cf-header {
      background: ${CONFIG.primaryColor};
      color: white;
      padding: 16px 20px;
      display: flex;
      align-items: center;
      gap: 12px;
      cursor: pointer;
      user-select: none;
    }
    .cf-header-avatar {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: rgba(255,255,255,0.2);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      overflow: hidden;
    }
    .cf-header-avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .cf-header-info {
      flex: 1;
    }
    .cf-header-name {
      font-weight: 600;
      font-size: 15px;
    }
    .cf-header-status {
      font-size: 12px;
      opacity: 0.85;
      display: flex;
      align-items: center;
      gap: 5px;
    }
    .cf-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #4ade80;
      display: inline-block;
    }
    .cf-status-dot.cf-offline {
      background: #f87171;
    }
    .cf-header-actions {
      display: flex;
      gap: 4px;
    }
    .cf-header-btn {
      background: none;
      border: none;
      color: white;
      cursor: pointer;
      padding: 6px;
      border-radius: 6px;
      opacity: 0.8;
      transition: opacity 0.2s, background 0.2s;
    }
    .cf-header-btn:hover {
      opacity: 1;
      background: rgba(255,255,255,0.15);
    }
    .cf-header-btn svg {
      width: 18px;
      height: 18px;
      fill: currentColor;
    }

    /* Messages */
    .cf-messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #f8f9fb;
    }
    .cf-messages::-webkit-scrollbar {
      width: 5px;
    }
    .cf-messages::-webkit-scrollbar-thumb {
      background: #d1d5db;
      border-radius: 10px;
    }

    /* Bulles de message */
    .cf-message {
      max-width: 80%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 14px;
      line-height: 1.5;
      animation: cf-fade-in 0.2s ease;
      word-wrap: break-word;
    }
    @keyframes cf-fade-in {
      from { opacity: 0; transform: translateY(5px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .cf-message-bot {
      background: white;
      color: #1f2937;
      align-self: flex-start;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .cf-message-user {
      background: ${CONFIG.primaryColor};
      color: white;
      align-self: flex-end;
      border-bottom-right-radius: 4px;
    }
    .cf-message-time {
      font-size: 10px;
      opacity: 0.5;
      margin-top: 4px;
      text-align: right;
    }
    .cf-message-bot .cf-message-time {
      text-align: left;
    }

    /* Indicateur de frappe */
    .cf-typing-indicator {
      display: none;
      align-self: flex-start;
      background: white;
      padding: 12px 16px;
      border-radius: 14px;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .cf-typing-indicator.cf-visible {
      display: flex;
      gap: 4px;
    }
    .cf-typing-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #9ca3af;
      animation: cf-typing-bounce 1.4s infinite;
    }
    .cf-typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .cf-typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes cf-typing-bounce {
      0%, 60%, 100% { transform: translateY(0); }
      30% { transform: translateY(-6px); }
    }

    /* Zone de saisie */
    .cf-input-area {
      padding: 12px 16px;
      border-top: 1px solid #e5e7eb;
      background: white;
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }
    .cf-input {
      flex: 1;
      border: 1px solid #e5e7eb;
      border-radius: 20px;
      padding: 10px 16px;
      font-size: 14px;
      font-family: inherit;
      resize: none;
      outline: none;
      max-height: 100px;
      transition: border-color 0.2s;
      line-height: 1.4;
    }
    .cf-input:focus {
      border-color: ${CONFIG.primaryColor};
    }
    .cf-input::placeholder {
      color: #9ca3af;
    }
    .cf-send-btn {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: ${CONFIG.primaryColor};
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      transition: transform 0.15s, opacity 0.2s;
    }
    .cf-send-btn:hover {
      transform: scale(1.05);
    }
    .cf-send-btn:disabled {
      opacity: 0.4;
      cursor: not-allowed;
      transform: none;
    }
    .cf-send-btn svg {
      width: 18px;
      height: 18px;
      fill: white;
    }

    /* Message de bienvenue */
    .cf-welcome {
      text-align: center;
      padding: 8px 16px;
      color: #6b7280;
      font-size: 12px;
    }

    /* Responsive */
    @media (max-width: 480px) {
      .cf-chat-window {
        width: calc(100vw - 20px);
        height: calc(100vh - 100px);
        max-height: none;
        border-radius: 16px 16px 0 0;
        margin-bottom: 0;
      }
      .cf-widget-container {
        bottom: 10px;
        ${CONFIG.position}: 10px;
      }
    }
  `;

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
