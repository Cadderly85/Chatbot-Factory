/**
 * Chatbot Factory — Widget Vocal
 * ===============================
 * Widget de chat vocal à intégrer sur le site du client.
 * 
 * Flow:
 *   1. Client clique sur le bouton micro
 *   2. Le navigateur enregistre la voix (Web Audio API)
 *   3. L'audio est envoyé au serveur vocal
 *   4. Whisper transcrit → LLM répond → Edge TTS vocalise
 *   5. Le navigateur joue la réponse audio
 * 
 * Usage de test:
 *   <div id="chatbot-vocal"
 *        data-vocal-api-url="https://cadderlyy-chatbot-factory-vocal.hf.space"></div>
 *
 * La page de démo publique est hébergée sur GitHub Pages:
 *   https://cadderly85.github.io/Chatbot-Factory/
 */

(function() {
    'use strict';

    // ─── Configuration ─────────────────────────────────────────────────────────

    function getApiBaseUrl() {
        const container = document.getElementById('chatbot-vocal');
        const rawUrl =
            container?.dataset?.vocalApiUrl ||
            container?.dataset?.agentUrl ||
            "https://huggingface.co/spaces/Cadderlyy/chatbot-factory-vocal";

        return rawUrl.replace(/\/+$/, '');
    }

    const API_BASE_URL = getApiBaseUrl();

    const CONFIG = {
        serverUrl: `${API_BASE_URL}/vocal`,
        wsUrl: API_BASE_URL.replace(/^http(s?):/, 'ws$1:') + '/vocal/ws',
        language: 'fr-FR',
        maxRecordingSeconds: 60,
        silenceThreshold: 0.01,
        silenceTimeout: 2000,
    };

    // ─── État ──────────────────────────────────────────────────────────────────

    let isRecording = false;
    let isPlaying = false;
    let mediaRecorder = null;
    let audioChunks = [];
    let audioContext = null;
    let analyser = null;
    let silenceTimer = null;
    let stream = null;
    let pendingStopResolve = null;

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
                    <button class="cf-vocal-btn cf-vocal-record" id="cf-record-btn" title="Commencer l'enregistrement">
                        🎤
                    </button>
                    <button class="cf-vocal-btn cf-vocal-perms" id="cf-permissions-btn" title="Vérifier les permissions">
                        🔁
                    </button>
                    <button class="cf-vocal-btn cf-vocal-stop" id="cf-stop-btn" title="Arrêter l'enregistrement" style="display:none">
                        ⏹️
                    </button>
                </div>
                <div class="cf-vocal-visualizer" id="cf-visualizer"></div>
            </div>
        `;

        addStyles();
        attachEvents();
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
                color: #3a0f5a; /* deep purple text */
                margin-right: 20px;
                border-bottom-left-radius: 6px;
                font-weight: 600;
                box-shadow: 0 6px 18px rgba(0,0,0,0.08);
            }
            .cf-vocal-message.error {
                background: #ff4444;
                color: white;
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
            .cf-vocal-send {
                background: #00cc66;
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
            .cf-vocal-bar {
                width: 3px;
                background: rgba(255,255,255,0.6);
                border-radius: 2px;
                transition: height 0.1s;
            }
        `;
        document.head.appendChild(styles);
    }

    function attachEvents() {
        document.getElementById('cf-record-btn').addEventListener('click', startRecording);
        document.getElementById('cf-stop-btn').addEventListener('click', stopRecording);
        const permsBtn = document.getElementById('cf-permissions-btn');
        if (permsBtn) permsBtn.addEventListener('click', tryPermissions);
    }

    // ─── Enregistrement ────────────────────────────────────────────────────────

    async function startRecording() {
        if (isRecording) return;

        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                displayAudioPreview(audioBlob);

                // Envoi automatique après l'arrêt de l'enregistrement
                try {
                    await sendRecording();
                } catch (err) {
                    console.error('Erreur lors de l\'envoi automatique:', err);
                }

                if (pendingStopResolve) {
                    pendingStopResolve();
                    pendingStopResolve = null;
                }
            };

            mediaRecorder.start();
            isRecording = true;

            updateUI('recording');
            startVisualizer();
            addMessage('🎤 Enregistrement en cours... Parlez maintenant.', 'user');

        } catch (err) {
            console.error('Erreur microphone:', err);
            addMessage('❌ Impossible d\'accéder au microphone. Vérifiez les permissions.', 'error');
        }
    }

    async function stopRecording() {
        if (!isRecording) return;

        const stopPromise = new Promise((resolve) => {
            pendingStopResolve = resolve;
        });

        mediaRecorder.stop();
        stream.getTracks().forEach(track => track.stop());
        isRecording = false;

        stopVisualizer();
        // L'envoi se fait automatiquement dans mediaRecorder.onstop()
        updateUI('recorded');

        await stopPromise;
    }

    function displayAudioPreview(blob) {
        const url = URL.createObjectURL(blob);
        const messagesDiv = document.getElementById('cf-messages');
        const audioEl = document.createElement('audio');
        audioEl.controls = true;
        audioEl.src = url;
        audioEl.style.cssText = 'width:100%;margin-top:4px;height:32px;';
        messagesDiv.appendChild(audioEl);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    // ─── Envoi ─────────────────────────────────────────────────────────────────

    async function sendRecording() {
        if (audioChunks.length === 0) return;

        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        updateUI('processing');
        addMessage('⏳ Traitement en cours...', 'bot');

        try {
            // Envoyer l'audio au serveur
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');
            formData.append('language', CONFIG.language);

            const endpoint = `${CONFIG.serverUrl}/transcribe-and-respond`;
            console.info('[vocal-widget] POST', endpoint);

            const response = await fetch(endpoint, {
                method: 'POST',
                body: formData,
                mode: 'cors',
            });

            if (!response.ok) {
                const errorText = await response.text().catch(() => '');
                throw new Error(`Erreur serveur ${response.status}${errorText ? `: ${errorText}` : ''}`);
            }

            const data = await response.json();

            // Afficher la transcription
            if (data.transcription) {
                addMessage(data.transcription, 'user');
            }

            // Afficher et jouer la réponse
            if (data.response) {
                addMessage(data.response, 'bot');
            }

            if (data.audio_url) {
                playAudio(data.audio_url);
            } else if (data.audio_base64) {
                playAudioBase64(data.audio_base64);
            }

        } catch (err) {
            console.error('Erreur envoi:', err);
            addMessage(`❌ Erreur: ${err.message}`, 'error');
            addMessage(`ℹ️ Endpoint: ${CONFIG.serverUrl}/transcribe-and-respond`, 'error');
        } finally {
            // Toujours revenir à l'état ready et vider les chunks pour éviter ré-envoi
            audioChunks = [];
            updateUI('ready');
        }
    }

    // ─── Lecture audio ─────────────────────────────────────────────────────────

    function _showPlayingIndicator(on = true) {
        const el = document.getElementById('cf-playing-indicator');
        if (!el) return;
        if (on) el.classList.add('visible'); else el.classList.remove('visible');
    }

    function playAudio(url) {
        updateUI('playing');
        _showPlayingIndicator(true);
        const audio = new Audio(url);
        audio.onended = () => {
            _showPlayingIndicator(false);
            updateUI('ready');
        };
        audio.onerror = () => {
            _showPlayingIndicator(false);
            updateUI('ready');
        };
        audio.play();
    }

    function playAudioBase64(base64) {
        updateUI('playing');
        _showPlayingIndicator(true);
        const audio = new Audio(`data:audio/mpeg;base64,${base64}`);
        audio.onended = () => {
            _showPlayingIndicator(false);
            updateUI('ready');
        };
        audio.onerror = () => {
            _showPlayingIndicator(false);
            updateUI('ready');
        };
        audio.play();
    }

    // ─── UI ────────────────────────────────────────────────────────────────────

    function updateUI(state) {
        const status = document.getElementById('cf-status');
        const recordBtn = document.getElementById('cf-record-btn');
        const stopBtn = document.getElementById('cf-stop-btn');
        const sendBtn = document.getElementById('cf-send-btn'); // may be null

        const setDisplay = (el, val) => { if (el) el.style.display = val; };

        switch (state) {
            case 'recording':
                if (status) { status.textContent = '🔴 Enregistrement...'; status.className = 'cf-vocal-status recording'; }
                setDisplay(recordBtn, 'none');
                setDisplay(stopBtn, 'flex');
                setDisplay(sendBtn, 'none');
                break;
            case 'recorded':
                if (status) { status.textContent = '✅ Enregistré'; status.className = 'cf-vocal-status'; }
                setDisplay(recordBtn, 'flex');
                setDisplay(stopBtn, 'none');
                setDisplay(sendBtn, 'flex');
                break;
            case 'processing':
                if (status) { status.textContent = '⏳ Traitement...'; status.className = 'cf-vocal-status processing'; }
                setDisplay(recordBtn, 'none');
                setDisplay(stopBtn, 'none');
                setDisplay(sendBtn, 'none');
                break;
            case 'playing':
                if (status) { status.textContent = '🔊 Lecture...'; status.className = 'cf-vocal-status playing'; }
                setDisplay(recordBtn, 'flex');
                setDisplay(stopBtn, 'none');
                setDisplay(sendBtn, 'none');
                break;
            default: // ready
                if (status) { status.textContent = 'Prêt'; status.className = 'cf-vocal-status'; }
                setDisplay(recordBtn, 'flex');
                setDisplay(stopBtn, 'none');
                setDisplay(sendBtn, 'none');
        }
    }

    function addMessage(text, type) {
        const messagesDiv = document.getElementById('cf-messages');
        const msg = document.createElement('div');
        msg.className = `cf-vocal-message ${type}`;
        msg.textContent = text;
        messagesDiv.appendChild(msg);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    // ─── Visualiseur ───────────────────────────────────────────────────────────

    function startVisualizer() {
        const visualizer = document.getElementById('cf-visualizer');
        visualizer.innerHTML = '';

        for (let i = 0; i < 20; i++) {
            const bar = document.createElement('div');
            bar.className = 'cf-vocal-bar';
            bar.style.height = '4px';
            visualizer.appendChild(bar);
        }

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
            requestAnimationFrame(animate);
        }
        animate();
    }

    function stopVisualizer() {
        const visualizer = document.getElementById('cf-visualizer');
        if (visualizer) visualizer.innerHTML = '';
        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
    }

    async function tryPermissions() {
        try {
            const s = await navigator.mediaDevices.getUserMedia({ audio: true });
            s.getTracks().forEach(t => t.stop());
            addMessage('✅ Micro accessible — permissions OK.', 'bot');
            return true;
        } catch (err) {
            console.error('Permissions microphone failed:', err);
            addMessage('❌ Impossible d\'accéder au micro. Vérifiez les permissions du navigateur (icône cadenas).', 'error');
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
