/**
 * Chatbot Factory — Widget Vocal (Client-Side / No Whisper)
 * =========================================================
 * Widget de chat vocal qui utilise Web Speech API côté navigateur
 * pour la transcription. Aucun Whisper serveur requis.
 *
 * Flow:
 *   1. Client clique sur le bouton micro
 *   2. Web Speech API (webkitSpeechRecognition) transcrit la voix en texte
 *   3. Le texte est envoyé au serveur comme un message chat normal (POST /chat)
 *   4. La réponse texte s'affiche dans le widget
 *   5. Optionnel: SpeechSynthesis lit la réponse à voix haute
 *
 * Avantages:
 *   - Aucun serveur Whisper requis (fonctionne sur HF Spaces gratuit)
 *   - Transcription instantanée (pas d'upload audio)
 *   - Compatible Chrome, Edge, Safari (webkitSpeechRecognition)
 *
 * Inconvénients:
 *   - Firefox non supporté (pas de webkitSpeechRecognition)
 *   - Qualité de transcription dépendante du navigateur/OS
 *
 * Usage:
 *   <div id="chatbot-vocal"
 *        data-agent-url="https://cadderlyy-chatbot-factory-vocal.hf.space"
 *        data-language="fr"></div>
 *   <script src="vocal_widget_nowhisper.js"></script>
 *
 * Attributs data- optionnels:
 *   data-agent-url    — URL du serveur chat (requis)
 *   data-language     — "fr" ou "en" (défaut: "fr")
 *   data-tts-enabled  — "true" ou "false" pour lire la réponse (défaut: "true")
 */

(function() {
    'use strict';

    // ─── Configuration ─────────────────────────────────────────────────────────

    function getApiBaseUrl() {
        const container = document.getElementById('chatbot-vocal');
        const rawUrl =
            container?.dataset?.vocalApiUrl ||
            container?.dataset?.agentUrl ||
            "https://cadderlyy-chatbot-factory-vocal.hf.space";
        return rawUrl.replace(/\/+$/, '');
    }

    const API_BASE_URL = getApiBaseUrl();

    const CONFIG = {
        chatUrl: `${API_BASE_URL}/chat`,
        healthUrl: `${API_BASE_URL}/health`,
        language: (() => {
            const container = document.getElementById('chatbot-vocal');
            const lang = container?.dataset?.language || 'fr';
            return lang.startsWith('en') ? 'en-US' : 'fr-FR';
        })(),
        ttsEnabled: (() => {
            const container = document.getElementById('chatbot-vocal');
            const val = container?.dataset?.ttsEnabled;
            return val !== 'false'; // default true
        })(),
        maxRecordingSeconds: 60,
    };

    // ─── État ──────────────────────────────────────────────────────────────────

    let isRecording = false;
    let isPlaying = false;
    let recognition = null;
    let silenceTimer = null;
    let stream = null;

    // ─── Interface ─────────────────────────────────────────────────────────────

    function createWidget() {
        const container = document.getElementById('chatbot-vocal');
        if (!container) {
            console.error('Chatbot Factory: Element #chatbot-vocal non trouvé');
            return;
        }

        container.innerHTML = `
            <div class="cf-vocal-widget">
                <div class="cf-vocal-header">
                    <span class="cf-vocal-title">🎤 Assistant Vocal</span>
                    <span class="cf-vocal-status" id="cf-status">Prêt</span>
                    <span id="cf-playing-indicator" class="cf-playing-indicator" style="display:none" title="Lecture">🔊</span>
                </div>
                <div class="cf-vocal-messages" id="cf-messages"></div>
                <div class="cf-vocal-controls">
                    <button class="cf-vocal-btn cf-vocal-record" id="cf-record-btn" title="Parler">
                        🎤
                    </button>
                    <button class="cf-vocal-btn cf-vocal-stop" id="cf-stop-btn" title="Arrêter" style="display:none">
                        ⏹️
                    </button>
                    <button class="cf-vocal-btn cf-vocal-perms" id="cf-permissions-btn" title="Vérifier le micro">
                        🔁
                    </button>
                </div>
                <div class="cf-vocal-visualizer" id="cf-visualizer"></div>
                <div class="cf-vocal-browser-warning" id="cf-browser-warning" style="display:none">
                    ⚠️ Vocal non supporté sur ce navigateur. Utilisez Chrome ou Edge.
                </div>
            </div>
        `;

        addStyles();
        attachEvents();
        checkBrowserSupport();
    }

    function addStyles() {
        if (document.getElementById('cf-vocal-styles')) return;

        const styles = document.createElement('style');
        styles.id = 'cf-vocal-styles';
        styles.textContent = `
            .cf-vocal-widget {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 520px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 18px;
                padding: 20px;
                box-shadow: 0 12px 48px rgba(0,0,0,0.28);
                color: white;
                position: fixed;
                bottom: 24px;
                right: 24px;
                z-index: 10000;
            }
            .cf-vocal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
                padding-bottom: 8px;
                border-bottom: 1px solid rgba(255,255,255,0.2);
            }
            .cf-vocal-title {
                font-weight: 600;
                font-size: 14px;
            }
            .cf-vocal-status {
                font-size: 12px;
                opacity: 0.8;
                padding: 2px 8px;
                background: rgba(255,255,255,0.15);
                border-radius: 8px;
            }
            .cf-vocal-status.recording {
                background: #ff4444;
                animation: cf-pulse 1s infinite;
            }
            .cf-vocal-status.processing {
                background: #ffaa00;
            }
            .cf-vocal-status.playing {
                background: #00cc66;
            }
            @keyframes cf-pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            .cf-vocal-messages {
                max-height: 200px;
                overflow-y: auto;
                margin-bottom: 12px;
                padding: 8px;
                background: rgba(0,0,0,0.15);
                border-radius: 8px;
            }
            .cf-vocal-message {
                margin-bottom: 10px;
                padding: 10px 14px;
                border-radius: 14px;
                font-size: 15px;
                line-height: 1.45;
            }
            .cf-vocal-message.user {
                background: rgba(255,255,255,0.12);
                margin-left: 20px;
                border-bottom-right-radius: 6px;
                color: #fff;
            }
            .cf-vocal-message.bot {
                background: rgba(255,255,255,0.98);
                color: #3a0f5a;
                margin-right: 20px;
                border-bottom-left-radius: 6px;
                font-weight: 600;
                box-shadow: 0 6px 18px rgba(0,0,0,0.08);
            }
            .cf-vocal-message.error {
                background: #ff4444;
                color: white;
            }
            .cf-vocal-message.info {
                background: rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.7);
                font-size: 13px;
                text-align: center;
            }
            .cf-vocal-controls {
                display: flex;
                justify-content: center;
                gap: 12px;
                margin-bottom: 8px;
            }
            .cf-vocal-btn {
                width: 68px;
                height: 68px;
                border-radius: 50%;
                border: none;
                font-size: 28px;
                cursor: pointer;
                transition: transform 0.12s ease, box-shadow 0.12s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                user-select: none;
            }
            .cf-vocal-record {
                background: linear-gradient(180deg, #ff6b6b 0%, #ff3b5a 60%);
                color: white;
                box-shadow: 0 12px 30px rgba(255,59,90,0.28), inset 0 1px 0 rgba(255,255,255,0.18);
                border: 1px solid rgba(255,255,255,0.06);
            }
            .cf-vocal-record:hover {
                transform: translateY(-2px) scale(1.03);
                box-shadow: 0 16px 36px rgba(255,59,90,0.34), inset 0 1px 0 rgba(255,255,255,0.22);
            }
            .cf-vocal-record.recording {
                animation: cf-pulse-btn 1s infinite;
            }
            @keyframes cf-pulse-btn {
                0%, 100% { box-shadow: 0 4px 12px rgba(255,68,68,0.4); }
                50% { box-shadow: 0 4px 24px rgba(255,68,68,0.8); }
            }
            .cf-vocal-stop {
                background: #666;
                color: white;
            }
            .cf-vocal-perms {
                background: linear-gradient(180deg, #ffd166 0%, #ffb703 60%);
                color: #2b1b3a;
                box-shadow: 0 8px 20px rgba(255,183,3,0.18);
            }
            .cf-vocal-visualizer {
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 2px;
            }
            .cf-vocal-bar {
                width: 3px;
                background: rgba(255,255,255,0.6);
                border-radius: 2px;
                transition: height 0.1s;
            }
            .cf-playing-indicator {
                margin-left: 8px;
                font-size: 16px;
                opacity: 0.0;
                transform-origin: center;
                transition: opacity 0.18s ease, transform 0.18s ease;
            }
            .cf-playing-indicator.visible {
                opacity: 1.0;
                transform: scale(1.05);
                animation: cf-playing-pulse 1.2s infinite ease-in-out;
            }
            @keyframes cf-playing-pulse {
                0% { transform: scale(1); opacity: 0.9; }
                50% { transform: scale(1.15); opacity: 1; }
                100% { transform: scale(1); opacity: 0.9; }
            }
            .cf-vocal-browser-warning {
                margin-top: 8px;
                padding: 8px 12px;
                background: rgba(255,170,0,0.2);
                border-radius: 8px;
                font-size: 12px;
                text-align: center;
                color: #ffd166;
            }
        `;
        document.head.appendChild(styles);
    }

    function attachEvents() {
        document.getElementById('cf-record-btn').addEventListener('click', toggleRecording);
        document.getElementById('cf-stop-btn').addEventListener('click', stopRecording);
        const permsBtn = document.getElementById('cf-permissions-btn');
        if (permsBtn) permsBtn.addEventListener('click', tryPermissions);
    }

    // ─── Browser Support ───────────────────────────────────────────────────────

    function checkBrowserSupport() {
        const hasSpeechRecognition = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
        if (!hasSpeechRecognition) {
            const warning = document.getElementById('cf-browser-warning');
            if (warning) warning.style.display = 'block';
            const recordBtn = document.getElementById('cf-record-btn');
            if (recordBtn) {
                recordBtn.disabled = true;
                recordBtn.style.opacity = '0.4';
                recordBtn.style.cursor = 'not-allowed';
            }
            addMessage('⚠️ Web Speech API non supporté. Utilisez Chrome, Edge ou Safari.', 'info');
        }
    }

    function getSpeechRecognition() {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        return SR ? new SR() : null;
    }

    // ─── Enregistrement (Web Speech API) ───────────────────────────────────────

    function toggleRecording() {
        if (isRecording) {
            stopRecording();
        } else {
            startRecording();
        }
    }

    function startRecording() {
        if (isRecording) return;

        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) {
            addMessage('❌ Reconnaissance vocale non supportée sur ce navigateur.', 'error');
            return;
        }

        recognition = new SR();
        recognition.lang = CONFIG.language;
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        let finalTranscript = '';
        let interimTranscript = '';

        recognition.onstart = () => {
            isRecording = true;
            updateUI('recording');
            addMessage('🎤 Écoute en cours... Parlez maintenant.', 'info');
            startVisualizer();
        };

        recognition.onresult = (event) => {
            interimTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }

            // Afficher l'interim en temps réel
            if (interimTranscript) {
                updateLastMessage(interimTranscript, 'user');
            }
        };

        recognition.onerror = (event) => {
            console.error('SpeechRecognition error:', event.error);
            if (event.error === 'not-allowed') {
                addMessage('❌ Accès au microphone refusé. Vérifiez les permissions.', 'error');
            } else if (event.error === 'no-speech') {
                addMessage('⚠️ Aucun son détecté. Réessayez.', 'info');
            } else if (event.error === 'aborted') {
                // User stopped, ignore
            } else {
                addMessage(`❌ Erreur: ${event.error}`, 'error');
            }
            stopRecording();
        };

        recognition.onend = () => {
            // Si on a une transcription finale, l'envoyer
            if (finalTranscript.trim()) {
                sendTranscript(finalTranscript.trim());
            } else if (!isRecording) {
                // Arrêté manuellement sans transcription
                updateUI('ready');
            }
            // Reset
            finalTranscript = '';
            interimTranscript = '';
        };

        try {
            recognition.start();
        } catch (err) {
            console.error('Failed to start recognition:', err);
            addMessage('❌ Impossible de démarrer la reconnaissance vocale.', 'error');
        }

        // Timeout de sécurité
        silenceTimer = setTimeout(() => {
            if (isRecording) {
                stopRecording();
            }
        }, CONFIG.maxRecordingSeconds * 1000);
    }

    function stopRecording() {
        if (!isRecording) return;

        isRecording = false;
        clearTimeout(silenceTimer);
        stopVisualizer();

        if (recognition) {
            try {
                recognition.stop();
            } catch (e) {
                // Already stopped
            }
            recognition = null;
        }

        updateUI('ready');
    }

    // ─── Envoi au serveur ──────────────────────────────────────────────────────

    async function sendTranscript(text) {
        updateUI('processing');
        addMessage(text, 'user');
        addMessage('⏳ Traitement en cours...', 'info');

        try {
            const response = await fetch(CONFIG.chatUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    session_id: 'vocal_' + Date.now(),
                }),
                mode: 'cors',
            });

            if (!response.ok) {
                const errorText = await response.text().catch(() => '');
                throw new Error(`Erreur serveur ${response.status}${errorText ? ': ' + errorText : ''}`);
            }

            const data = await response.json();

            if (data.response) {
                addMessage(data.response, 'bot');

                // TTS: lire la réponse
                if (CONFIG.ttsEnabled) {
                    speakText(data.response);
                }
            } else {
                addMessage('⚠️ Pas de réponse du serveur.', 'error');
            }

        } catch (err) {
            console.error('Erreur envoi:', err);
            addMessage(`❌ Erreur: ${err.message}`, 'error');
            addMessage(`ℹ️ Endpoint: ${CONFIG.chatUrl}`, 'error');
        } finally {
            updateUI('ready');
        }
    }

    // ─── TTS (SpeechSynthesis) ─────────────────────────────────────────────────

    function speakText(text) {
        if (!('speechSynthesis' in window)) return;

        // Annuler toute lecture en cours
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = CONFIG.language;
        utterance.rate = 1.0;
        utterance.pitch = 1.0;

        // Essayer de trouver une voix appropriée
        const voices = window.speechSynthesis.getVoices();
        const langPrefix = CONFIG.language.substring(0, 2);
        const matchingVoice = voices.find(v => v.lang.startsWith(langPrefix));
        if (matchingVoice) {
            utterance.voice = matchingVoice;
        }

        utterance.onstart = () => {
            updateUI('playing');
            _showPlayingIndicator(true);
        };

        utterance.onend = () => {
            _showPlayingIndicator(false);
            updateUI('ready');
        };

        utterance.onerror = () => {
            _showPlayingIndicator(false);
            updateUI('ready');
        };

        window.speechSynthesis.speak(utterance);
    }

    // ─── Visualiseur ───────────────────────────────────────────────────────────

    let audioContext = null;
    let analyser = null;
    let visualizerAnimId = null;

    async function startVisualizer() {
        const visualizer = document.getElementById('cf-visualizer');
        if (!visualizer) return;

        visualizer.innerHTML = '';
        for (let i = 0; i < 20; i++) {
            const bar = document.createElement('div');
            bar.className = 'cf-vocal-bar';
            bar.style.height = '4px';
            visualizer.appendChild(bar);
        }

        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            audioContext = new AudioContext();
            analyser = audioContext.createAnalyser();
            const source = audioContext.createMediaStreamSource(stream);
            source.connect(analyser);
            analyser.fftSize = 64;

            const dataArray = new Uint8Array(analyser.frequencyBinCount);

            function animate() {
                if (!isRecording) return;
                analyser.getByteFrequencyData(dataArray);
                const bars = visualizer.querySelectorAll('.cf-vocal-bar');
                bars.forEach((bar, i) => {
                    const value = dataArray[i] || 0;
                    bar.style.height = Math.max(4, value / 4) + 'px';
                });
                visualizerAnimId = requestAnimationFrame(animate);
            }
            animate();
        } catch (err) {
            console.warn('Visualizer audio failed:', err);
        }
    }

    function stopVisualizer() {
        const visualizer = document.getElementById('cf-visualizer');
        if (visualizer) visualizer.innerHTML = '';

        if (visualizerAnimId) {
            cancelAnimationFrame(visualizerAnimId);
            visualizerAnimId = null;
        }

        if (stream) {
            stream.getTracks().forEach(t => t.stop());
            stream = null;
        }

        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
    }

    // ─── UI ────────────────────────────────────────────────────────────────────

    function updateUI(state) {
        const status = document.getElementById('cf-status');
        const recordBtn = document.getElementById('cf-record-btn');
        const stopBtn = document.getElementById('cf-stop-btn');

        const setDisplay = (el, val) => { if (el) el.style.display = val; };

        switch (state) {
            case 'recording':
                if (status) { status.textContent = '🔴 Écoute...'; status.className = 'cf-vocal-status recording'; }
                setDisplay(recordBtn, 'none');
                setDisplay(stopBtn, 'flex');
                break;
            case 'processing':
                if (status) { status.textContent = '⏳ Traitement...'; status.className = 'cf-vocal-status processing'; }
                setDisplay(recordBtn, 'none');
                setDisplay(stopBtn, 'none');
                break;
            case 'playing':
                if (status) { status.textContent = '🔊 Lecture...'; status.className = 'cf-vocal-status playing'; }
                setDisplay(recordBtn, 'flex');
                setDisplay(stopBtn, 'none');
                break;
            default: // ready
                if (status) { status.textContent = 'Prêt'; status.className = 'cf-vocal-status'; }
                setDisplay(recordBtn, 'flex');
                setDisplay(stopBtn, 'none');
        }
    }

    function addMessage(text, type) {
        const messagesDiv = document.getElementById('cf-messages');
        if (!messagesDiv) return;

        const msg = document.createElement('div');
        msg.className = `cf-vocal-message ${type}`;
        msg.textContent = text;
        messagesDiv.appendChild(msg);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function updateLastMessage(text, type) {
        const messagesDiv = document.getElementById('cf-messages');
        if (!messagesDiv) return;

        // Chercher le dernier message du même type et le mettre à jour
        const msgs = messagesDiv.querySelectorAll(`.cf-vocal-message.${type}`);
        if (msgs.length > 0) {
            const last = msgs[msgs.length - 1];
            // Ne mettre à jour que si c'est un message interim (pas déjà envoyé)
            if (!last.dataset.sent) {
                last.textContent = text;
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                return;
            }
        }

        // Sinon créer un nouveau message
        addMessage(text, type);
    }

    function _showPlayingIndicator(on) {
        const el = document.getElementById('cf-playing-indicator');
        if (!el) return;
        if (on) el.classList.add('visible'); else el.classList.remove('visible');
    }

    // ─── Permissions ───────────────────────────────────────────────────────────

    async function tryPermissions() {
        try {
            const s = await navigator.mediaDevices.getUserMedia({ audio: true });
            s.getTracks().forEach(t => t.stop());
            addMessage('✅ Micro accessible — permissions OK.', 'bot');
            return true;
        } catch (err) {
            console.error('Permissions microphone failed:', err);
            addMessage('❌ Impossible d\'accéder au micro. Vérifiez les permissions du navigateur.', 'error');
            return false;
        }
    }

    // ─── Initialisation ────────────────────────────────────────────────────────

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createWidget);
    } else {
        createWidget();
    }
})();
