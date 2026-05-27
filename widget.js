/**
 * Chatbot Factory — Widget Combiné Texte + Vocal
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Widget de chat premium avec :
 *   - Chat texte (envoi de messages)
 *   - Chat vocal (enregistrement micro → Whisper → LLM → TTS)
 *
 * Installation : Ajouter cette BALISE dans le <head> ou avant </body> :
 *
 *   <script src="https://cdn.jsdelivr.net/gh/Cadderly85/Chatbot-Factory@main/widget.js"
 *           data-agent-url="https://VOTRE-AGENT.hf.space"
 *           data-client-name="Nom du Client"
 *           data-primary-color="#6366f1"
 *           data-position="right"
 *           data-welcome-message="Bonjour ! Comment puis-je vous aider?"
 *           data-language="fr">
 *   </script>
 *
 * Chargement du vocal (optionnel, requiert Whisper + TTS sur le serveur) :
 *   Le vocal est automatiquement activé si le serveur expose /vocal/*
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
    console.error("[Chatbot Factory] data-agent-url est requis.");
    return;
  }

  const T = {
    fr: {
      placeholder: "Écrivez votre message...",
      send: "Envoyer",
      online: "En ligne",
      offline: "Hors ligne",
      typing: "Écrit...",
      errorMessage: "Désolé, une erreur s'est produite.",
      transferMessage: "Je vous transfère à un membre de notre équipe...",
      newConversation: "Nouvelle conversation",
      closeChat: "Fermer",
      minimizeChat: "Réduire",
      voiceStart: "Parler",
      voiceStop: "Arrêter",
      voiceRecording: "Enregistrement...",
      voiceError: "Micro non accessible. Vérifiez les permissions.",
      voiceProcessing: "Traitement...",
      poweredBy: "Propulsé par Chatbot Factory",
    },
    en: {
      placeholder: "Type your message...",
      send: "Send",
      online: "Online",
      offline: "Offline",
      typing: "Typing...",
      errorMessage: "Sorry, an error occurred.",
      transferMessage: "Transferring you to a team member...",
      newConversation: "New conversation",
      closeChat: "Close",
      minimizeChat: "Minimize",
      voiceStart: "Speak",
      voiceStop: "Stop",
      voiceRecording: "Recording...",
      voiceError: "Microphone not accessible. Check permissions.",
      voiceProcessing: "Processing...",
      poweredBy: "Powered by Chatbot Factory",
    },
  }[CONFIG.language] || {};

  // State
  let sessionId = "s_" + Math.random().toString(36).substring(2, 12);
  let isOpen = false;
  let isMinimized = false;
  let isTyping = false;
  let messageHistory = [];

  // ─── Helpers ────────────────────────────────────────────────────────────

  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function adjustColor(hex, amount) {
    const num = parseInt(hex.replace('#', ''), 16);
    const clamp = (v) => Math.min(255, Math.max(0, v));
    const r = clamp((num >> 16) + amount);
    const g = clamp(((num >> 8) & 0xFF) + amount);
    const b = clamp((num & 0xFF) + amount);
    return '#' + (0x1000000 + r * 0x10000 + g * 0x100 + b).toString(16).slice(1);
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ─── Styles ─────────────────────────────────────────────────────────────

  const S = CONFIG.primaryColor;

  const STYLES = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    .cf-widget-container {
      position: fixed;
      bottom: 24px;
      ${CONFIG.position}: 24px;
      z-index: 999999;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    /* ═══ FAB ═══ */
    .cf-fab {
      width: 64px; height: 64px;
      border-radius: 50%;
      background: linear-gradient(135deg, ${S}, ${adjustColor(S, -30)});
      border: none; cursor: pointer;
      box-shadow: 0 4px 24px rgba(0,0,0,0.18), 0 0 0 0 ${hexToRgba(S, 0.4)};
      display: flex; align-items: center; justify-content: center;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      animation: cf-pulse 2.5s ease-in-out infinite;
    }
    .cf-fab:hover {
      transform: scale(1.12) rotate(8deg);
      box-shadow: 0 8px 32px rgba(0,0,0,0.25), 0 0 0 8px ${hexToRgba(S, 0.15)};
      animation: none;
    }
    .cf-fab:active { transform: scale(0.95); }
    .cf-fab svg { width: 30px; height: 30px; fill: white; }
    .cf-fab .cf-close-icon { display: none; }
    .cf-fab.cf-open .cf-chat-icon { display: none; }
    .cf-fab.cf-open .cf-close-icon { display: block; }
    .cf-fab.cf-open { animation: none; transform: rotate(90deg); }
    @keyframes cf-pulse {
      0%, 100% { box-shadow: 0 4px 24px rgba(0,0,0,0.18), 0 0 0 0 ${hexToRgba(S, 0.4)}; }
      50% { box-shadow: 0 4px 24px rgba(0,0,0,0.18), 0 0 0 12px ${hexToRgba(S, 0)}; }
    }

    /* ═══ Chat Window ═══ */
    .cf-chat-window {
      display: none;
      width: 400px; height: 600px;
      max-height: calc(100vh - 120px);
      background: #fff;
      border-radius: 20px;
      box-shadow: 0 25px 60px rgba(0,0,0,0.12), 0 8px 24px rgba(0,0,0,0.08);
      flex-direction: column;
      overflow: hidden;
      margin-bottom: 16px;
      animation: cf-slide-up 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      border: 1px solid rgba(0,0,0,0.04);
    }
    .cf-chat-window.cf-visible { display: flex; }
    .cf-chat-window.cf-minimized { height: auto; }
    .cf-chat-window.cf-minimized .cf-messages,
    .cf-chat-window.cf-minimized .cf-input-area { display: none; }
    @keyframes cf-slide-up {
      from { opacity: 0; transform: translateY(30px) scale(0.92); }
      to { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* ═══ Header ═══ */
    .cf-header {
      background: linear-gradient(135deg, ${S}, ${adjustColor(S, -20)});
      color: white; padding: 18px 20px;
      display: flex; align-items: center; gap: 14px;
      cursor: pointer; user-select: none;
      position: relative; overflow: hidden;
    }
    .cf-header::before {
      content: ''; position: absolute;
      top: -50%; right: -30%;
      width: 120px; height: 120px;
      background: rgba(255,255,255,0.06);
      border-radius: 50%;
    }
    .cf-header::after {
      content: ''; position: absolute;
      bottom: -60%; left: -10%;
      width: 80px; height: 80px;
      background: rgba(255,255,255,0.04);
      border-radius: 50%;
    }
    .cf-header-avatar {
      width: 44px; height: 44px; border-radius: 50%;
      background: rgba(255,255,255,0.15);
      backdrop-filter: blur(10px);
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; overflow: hidden;
      border: 2px solid rgba(255,255,255,0.25);
      flex-shrink: 0; position: relative; z-index: 1;
    }
    .cf-header-avatar img { width: 100%; height: 100%; object-fit: cover; }
    .cf-header-info { flex: 1; position: relative; z-index: 1; }
    .cf-header-name { font-weight: 700; font-size: 16px; letter-spacing: -0.2px; }
    .cf-header-status {
      font-size: 12px; opacity: 0.9;
      display: flex; align-items: center; gap: 6px; margin-top: 2px;
    }
    .cf-status-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #4ade80; display: inline-block;
      box-shadow: 0 0 6px rgba(74,222,128,0.5);
    }
    .cf-status-dot.cf-offline { background: #f87171; box-shadow: 0 0 6px rgba(248,113,113,0.5); }
    .cf-header-actions { display: flex; gap: 2px; position: relative; z-index: 1; }
    .cf-header-btn {
      background: none; border: none; color: white;
      cursor: pointer; padding: 8px; border-radius: 10px;
      opacity: 0.75; transition: all 0.2s;
      display: flex; align-items: center; justify-content: center;
    }
    .cf-header-btn:hover { opacity: 1; background: rgba(255,255,255,0.15); transform: scale(1.1); }
    .cf-header-btn svg { width: 18px; height: 18px; fill: currentColor; }

    /* ═══ Messages ═══ */
    .cf-messages {
      flex: 1; overflow-y: auto; padding: 20px 16px;
      display: flex; flex-direction: column; gap: 14px;
      background: linear-gradient(180deg, #f8f9fc 0%, #f0f2f7 100%);
    }
    .cf-messages::-webkit-scrollbar { width: 6px; }
    .cf-messages::-webkit-scrollbar-track { background: transparent; }
    .cf-messages::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 10px; }
    .cf-messages::-webkit-scrollbar-thumb:hover { background: #9ca3af; }

    /* ═══ Bubbles ═══ */
    .cf-message {
      max-width: 82%; padding: 12px 16px;
      border-radius: 18px; font-size: 14px; line-height: 1.55;
      animation: cf-fade-in 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      word-wrap: break-word; position: relative;
    }
    @keyframes cf-fade-in {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .cf-message-bot {
      background: white; color: #1a1a2e;
      align-self: flex-start; border-bottom-left-radius: 6px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.06);
    }
    .cf-message-user {
      background: linear-gradient(135deg, ${S}, ${adjustColor(S, -15)});
      color: white; align-self: flex-end; border-bottom-right-radius: 6px;
      box-shadow: 0 2px 12px ${hexToRgba(S, 0.25)}, 0 1px 3px rgba(0,0,0,0.08);
    }
    .cf-message-time {
      font-size: 10px; opacity: 0.45; margin-top: 6px;
      text-align: right; font-weight: 500;
    }
    .cf-message-bot .cf-message-time { text-align: left; }

    /* Audio bubble */
    .cf-audio-bubble {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px;
    }
    .cf-audio-btn {
      width: 36px; height: 36px; border-radius: 50%;
      background: ${S}; border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; transition: transform 0.2s;
    }
    .cf-audio-btn:hover { transform: scale(1.1); }
    .cf-audio-btn svg { width: 16px; height: 16px; fill: white; }
    .cf-audio-wave {
      display: flex; align-items: center; gap: 2px; height: 20px;
    }
    .cf-audio-wave span {
      width: 3px; border-radius: 2px;
      background: ${S}; opacity: 0.5;
    }

    /* ═══ Typing ═══ */
    .cf-typing-indicator {
      display: none; align-self: flex-start;
      background: white; padding: 14px 18px;
      border-radius: 18px; border-bottom-left-radius: 6px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .cf-typing-indicator.cf-visible { display: flex; gap: 5px; animation: cf-fade-in 0.3s ease; }
    .cf-typing-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #c4c4c4; animation: cf-bounce 1.4s infinite ease-in-out;
    }
    .cf-typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .cf-typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes cf-bounce {
      0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
      30% { transform: translateY(-8px); opacity: 1; }
    }

    /* ═══ Input Area ═══ */
    .cf-input-area {
      padding: 12px 14px;
      border-top: 1px solid #eef0f3;
      background: white;
      display: flex; gap: 8px; align-items: center;
    }
    .cf-input-wrap {
      flex: 1; display: flex; align-items: center;
      background: #f8f9fb; border: 1.5px solid #e8eaed;
      border-radius: 24px; padding: 4px 4px 4px 16px;
      transition: all 0.25s;
    }
    .cf-input-wrap:focus-within {
      border-color: ${S}; background: white;
      box-shadow: 0 0 0 3px ${hexToRgba(S, 0.1)};
    }
    .cf-input {
      flex: 1; border: none; background: transparent;
      padding: 8px 0; font-size: 14px; font-family: inherit;
      resize: none; outline: none; max-height: 80px; line-height: 1.45;
    }
    .cf-input::placeholder { color: #a0a4ad; }

    /* ═══ Buttons ═══ */
    .cf-btn-circle {
      width: 40px; height: 40px; border-radius: 50%;
      border: none; cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0; transition: all 0.2s;
    }
    .cf-btn-circle svg { width: 20px; height: 20px; fill: white; }
    .cf-btn-circle:hover { transform: scale(1.08); }
    .cf-btn-circle:active { transform: scale(0.92); }
    .cf-btn-circle:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

    .cf-send-btn {
      background: linear-gradient(135deg, ${S}, ${adjustColor(S, -20)});
      box-shadow: 0 3px 12px ${hexToRgba(S, 0.3)};
    }
    .cf-send-btn:hover { box-shadow: 0 5px 20px ${hexToRgba(S, 0.4)}; }

    .cf-voice-btn {
      background: linear-gradient(135deg, #10b981, #059669);
      box-shadow: 0 3px 12px rgba(16,185,129,0.3);
    }
    .cf-voice-btn:hover { box-shadow: 0 5px 20px rgba(16,185,129,0.4); }
    .cf-voice-btn.cf-recording {
      background: linear-gradient(135deg, #ef4444, #dc2626);
      box-shadow: 0 3px 12px rgba(239,68,68,0.4);
      animation: cf-voice-pulse 1s ease-in-out infinite;
    }
    @keyframes cf-voice-pulse {
      0%, 100% { box-shadow: 0 3px 12px rgba(239,68,68,0.4), 0 0 0 0 rgba(239,68,68,0.3); }
      50% { box-shadow: 0 3px 12px rgba(239,68,68,0.4), 0 0 0 8px rgba(239,68,68,0); }
    }

    /* ═══ Voice Status Bar ═══ */
    .cf-voice-bar {
      display: none; align-items: center; gap: 10px;
      padding: 10px 16px; background: #fef3c7;
      border-top: 1px solid #fde68a;
      font-size: 13px; font-weight: 600; color: #92400e;
    }
    .cf-voice-bar.cf-visible { display: flex; }
    .cf-voice-bar-dot {
      width: 10px; height: 10px; border-radius: 50%;
      background: #ef4444; animation: cf-voice-pulse-dot 1s ease-in-out infinite;
    }
    @keyframes cf-voice-pulse-dot {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    /* ═══ Welcome ═══ */
    .cf-welcome {
      text-align: center; padding: 10px 20px;
      color: #9ca3af; font-size: 12px; font-weight: 500;
    }

    /* ═══ Responsive ═══ */
    @media (max-width: 480px) {
      .cf-chat-window {
        width: calc(100vw - 16px);
        height: calc(100vh - 90px);
        max-height: none;
        border-radius: 20px 20px 0 0;
        margin-bottom: 0;
      }
      .cf-widget-container { bottom: 8px; ${CONFIG.position}: 8px; }
      .cf-fab { width: 58px; height: 58px; }
      .cf-fab svg { width: 26px; height: 26px; }
    }
  `;

  // ─── Icons ──────────────────────────────────────────────────────────────

  const ICONS = {
    chat: `<svg class="cf-chat-icon" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/></svg>`,
    close: `<svg class="cf-close-icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>`,
    minimize: `<svg viewBox="0 0 24 24"><path d="M19 13H5v-2h14v2z"/></svg>`,
    send: `<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>`,
    mic: `<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1-9c0-.55.45-1 1-1s1 .45 1 1v6c0 .55-.45 1-1 1s-1-.45-1-1V5z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>`,
    micOff: `<svg viewBox="0 0 24 24"><path d="M19 11h-1.7c0 .74-.16 1.43-.43 2.05l1.23 1.23c.56-.98.9-2.09.9-3.28zm-4.02.17c0-.06.02-.11.02-.17V5c0-1.66-1.34-3-3-3S9 3.34 9 5v.18l5.98 5.99zM4.27 3L3 4.27l6.01 6.01V11c0 1.66 1.33 3 2.99 3 .22 0 .44-.03.65-.08l1.66 1.66c-.71.33-1.5.52-2.31.52-2.76 0-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c.91-.13 1.77-.45 2.54-.9l4.28 4.28 1.27-1.27L4.27 3z"/></svg>`,
    play: `<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>`,
    pause: `<svg viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>`,
  };

  // ─── Build DOM ──────────────────────────────────────────────────────────

  function buildWidget() {
    const c = document.createElement("div");
    c.className = "cf-widget-container";
    c.innerHTML = `
      <style>${STYLES}</style>

      <div class="cf-chat-window" id="cf-chat-window">
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

        <div class="cf-messages" id="cf-messages">
          <div class="cf-welcome">${T.poweredBy} 🚀</div>
        </div>

        <div class="cf-typing-indicator" id="cf-typing">
          <div class="cf-typing-dot"></div>
          <div class="cf-typing-dot"></div>
          <div class="cf-typing-dot"></div>
        </div>

        <div class="cf-voice-bar" id="cf-voice-bar">
          <span class="cf-voice-bar-dot"></span>
          <span id="cf-voice-bar-text">${T.voiceRecording}</span>
        </div>

        <div class="cf-input-area">
          <div class="cf-input-wrap">
            <textarea class="cf-input" id="cf-input" rows="1" placeholder="${T.placeholder}" aria-label="${T.placeholder}"></textarea>
          </div>
          <button class="cf-btn-circle cf-voice-btn" id="cf-voice" title="${T.voiceStart}">${ICONS.mic}</button>
          <button class="cf-btn-circle cf-send-btn" id="cf-send" title="${T.send}">${ICONS.send}</button>
        </div>
      </div>

      <button class="cf-fab" id="cf-fab" aria-label="Ouvrir le chat">
        ${ICONS.chat}
        ${ICONS.close}
      </button>
    `;
    document.body.appendChild(c);
    return c;
  }

  // ─── Init ────────────────────────────────────────────────────────────────

  const w = buildWidget();
  const fab = document.getElementById("cf-fab");
  const chatWindow = document.getElementById("cf-chat-window");
  const msgs = document.getElementById("cf-messages");
  const input = document.getElementById("cf-input");
  const sendBtn = document.getElementById("cf-send");
  const voiceBtn = document.getElementById("cf-voice");
  const typing = document.getElementById("cf-typing");
  const statusDot = document.getElementById("cf-status-dot");
  const statusText = document.getElementById("cf-status-text");
  const minBtn = document.getElementById("cf-minimize");
  const newBtn = document.getElementById("cf-new-chat");
  const header = document.getElementById("cf-header");
  const voiceBar = document.getElementById("cf-voice-bar");

  checkHealth();

  // ─── Events ─────────────────────────────────────────────────────────────

  fab.addEventListener("click", toggleChat);
  header.addEventListener("click", () => { if (isMinimized) toggleMinimize(); });
  minBtn.addEventListener("click", (e) => { e.stopPropagation(); toggleMinimize(); });
  newBtn.addEventListener("click", (e) => { e.stopPropagation(); startNewConversation(); });
  sendBtn.addEventListener("click", sendMessage);
  voiceBtn.addEventListener("click", toggleVoice);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 80) + "px"; });

  // ─── Voice Recording ────────────────────────────────────────────────────

  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  async function toggleVoice() {
    if (isRecording) {
      stopRecording();
    } else {
      await startRecording();
    }
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };

      mediaRecorder.onstop = async () => {
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        stream.getTracks().forEach(t => t.stop());
        await sendVoiceMessage(blob);
      };

      mediaRecorder.start();
      isRecording = true;
      voiceBtn.classList.add("cf-recording");
      voiceBtn.innerHTML = ICONS.micOff;
      voiceBar.classList.add("cf-visible");
      document.getElementById("cf-voice-bar-text").textContent = T.voiceRecording;
    } catch (err) {
      console.error("[Chatbot Factory] Micro error:", err);
      addMessage(T.voiceError, "bot");
    }
  }

  function stopRecording() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;
      voiceBtn.classList.remove("cf-recording");
      voiceBtn.innerHTML = ICONS.mic;
      document.getElementById("cf-voice-bar-text").textContent = T.voiceProcessing;
      isTyping = true;
      typing.classList.add("cf-visible");
      scrollToBottom();
    }
  }

  async function sendVoiceMessage(blob) {
    const formData = new FormData();
    formData.append("audio", blob, "recording.webm");
    formData.append("language", CONFIG.language);
    formData.append("session_id", sessionId);

    try {
      const resp = await fetch(`${CONFIG.agentUrl}/vocal/transcribe-and-respond`, {
        method: "POST",
        body: formData,
      });

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data = await resp.json();

      // Afficher la transcription
      if (data.transcription) {
        addMessage("🎤 " + data.transcription, "user");
      }

      // Afficher la réponse texte
      const botResponse = data.response || T.errorMessage;
      addMessage(botResponse, "bot");

      // Jouer l'audio TTS si disponible
      if (data.audio_base64) {
        const audio = new Audio("data:audio/mp3;base64," + data.audio_base64);
        audio.play().catch(() => {});
      }

    } catch (err) {
      console.error("[Chatbot Factory] Voice error:", err);
      addMessage(T.errorMessage, "bot");
      statusDot.classList.add("cf-offline");
      statusText.textContent = T.offline;
    } finally {
      isTyping = false;
      typing.classList.remove("cf-visible");
      voiceBar.classList.remove("cf-visible");
      scrollToBottom();
    }
  }

  // ─── Chat Functions ─────────────────────────────────────────────────────

  function toggleChat() {
    isOpen = !isOpen;
    fab.classList.toggle("cf-open", isOpen);
    chatWindow.classList.toggle("cf-visible", isOpen);
    if (isOpen && isMinimized) { isMinimized = false; chatWindow.classList.remove("cf-minimized"); }
    if (isOpen) {
      input.focus();
      if (messageHistory.length === 0 && CONFIG.welcomeMessage) addMessage(CONFIG.welcomeMessage, "bot");
    }
  }

  function toggleMinimize() {
    isMinimized = !isMinimized;
    chatWindow.classList.toggle("cf-minimized", isMinimized);
  }

  function startNewConversation() {
    sessionId = "s_" + Math.random().toString(36).substring(2, 12);
    messageHistory = [];
    msgs.innerHTML = '<div class="cf-welcome">' + T.poweredBy + ' 🚀</div>';
    if (CONFIG.welcomeMessage) addMessage(CONFIG.welcomeMessage, "bot");
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || isTyping) return;

    addMessage(text, "user");
    input.value = "";
    input.style.height = "auto";

    isTyping = true;
    typing.classList.add("cf-visible");
    sendBtn.disabled = true;
    scrollToBottom();

    try {
      const resp = await fetch(`${CONFIG.agentUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data = await resp.json();
      addMessage(data.response || T.errorMessage, "bot");
      if (data.transferred) addMessage(T.transferMessage, "bot");
    } catch (err) {
      addMessage(T.errorMessage, "bot");
      statusDot.classList.add("cf-offline");
      statusText.textContent = T.offline;
    } finally {
      isTyping = false;
      typing.classList.remove("cf-visible");
      sendBtn.disabled = false;
      scrollToBottom();
    }
  }

  function addMessage(text, sender) {
    const time = new Date().toLocaleTimeString(
      CONFIG.language === "fr" ? "fr-CA" : "en-US",
      { hour: "2-digit", minute: "2-digit" }
    );
    const d = document.createElement("div");
    d.className = `cf-message cf-message-${sender}`;
    d.innerHTML = `${escapeHtml(text).replace(/\n/g, "<br>")}<div class="cf-message-time">${time}</div>`;

    const welcome = msgs.querySelector(".cf-welcome");
    if (welcome) welcome.remove();

    msgs.appendChild(d);
    messageHistory.push({ sender, text, time });
    scrollToBottom();
  }

  function scrollToBottom() { msgs.scrollTop = msgs.scrollHeight; }

  async function checkHealth() {
    try {
      const r = await fetch(`${CONFIG.agentUrl}/health`, { signal: AbortSignal.timeout(5000) });
      if (r.ok) { statusDot.classList.remove("cf-offline"); statusText.textContent = T.online; }
      else throw new Error("not ok");
    } catch { statusDot.classList.add("cf-offline"); statusText.textContent = T.offline; }
  }

  // ─── Public API ─────────────────────────────────────────────────────────

  window.ChatbotFactory = {
    open: () => { if (!isOpen) toggleChat(); },
    close: () => { if (isOpen) toggleChat(); },
    toggle: toggleChat,
    newConversation: startNewConversation,
    checkHealth,
    getHistory: () => [...messageHistory],
  };

})();
