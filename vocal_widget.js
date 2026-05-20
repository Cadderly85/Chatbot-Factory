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
 * Usage:
 *   <script src="https://cdn.chatbotfactory.xyz/vocal-widget.js"></script>
 *   <div id="chatbot-vocal" data-agent-url="https://agent.onrender.com"></div>
 */

(function() {
    'use strict';

    // ─── Configuration ─────────────────────────────────────────────────────────

    const CONFIG = {
        serverUrl: (document.querySelector('#chatbot-vocal')?.dataset?.agentUrl || '') + '/vocal',
        wsUrl: (document.querySelector('#chatbot-vocal')?.dataset?.agentUrl || '') + '/vocal/ws',
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
                </div>
                <div class="cf-vocal-messages" id="cf-messages"></div>
                <div class="cf-vocal-controls">
                    <button class="cf-vocal-btn cf-vocal-record" id="cf-record-btn" title="Commencer l'enregistrement">
                        🎤
                    </button>
                    <button class="cf-vocal-btn cf-vocal-stop" id="cf-stop-btn" title="Arrêter l'enregistrement" style="display:none">
                        ⏹️
                    </button>
                    <button class="cf-vocal-btn cf-vocal-send" id="cf-send-btn" title="Envoyer" style="display:none">
                        📤
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
                max-width: 400px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 16px;
                padding: 16px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.2);
                color: white;
                position: fixed;
                bottom: 20px;
                right: 20px;
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
                margin-bottom: 8px;
                padding: 8px 12px;
                border-radius: 12px;
                font-size: 13px;
                line-height: 1.4;
            }
            .cf-vocal-message.user {
                background: rgba(255,255,255,0.2);
                margin-left: 20px;
                border-bottom-right-radius: 4px;
            }
            .cf-vocal-message.bot {
                background: rgba(255,255,255,0.9);
                color: #333;
                margin-right: 20px;
                border-bottom-left-radius: 4px;
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
                width: 56px;
                height: 56px;
                border-radius: 50%;
                border: none;
                font-size: 24px;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .cf-vocal-record {
                background: #ff4444;
                color: white;
                box-shadow: 0 4px 12px rgba(255,68,68,0.4);
            }
            .cf-vocal-record:hover {
                background: #ff6666;
                transform: scale(1.05);
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
        `;
        document.head.appendChild(styles);
    }

    function attachEvents() {
        document.getElementById('cf-record-btn').addEventListener('click', startRecording);
        document.getElementById('cf-stop-btn').addEventListener('click', stopRecording);
        document.getElementById('cf-send-btn').addEventListener('click', sendRecording);
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

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                displayAudioPreview(audioBlob);
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

    function stopRecording() {
        if (!isRecording) return;

        mediaRecorder.stop();
        stream.getTracks().forEach(track => track.stop());
        isRecording = false;

        updateUI('recorded');
        stopVisualizer();
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

            const response = await fetch(CONFIG.serverUrl + '/transcribe-and-respond', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Erreur serveur: ${response.status}`);
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

            updateUI('ready');

        } catch (err) {
            console.error('Erreur envoi:', err);
            addMessage(`❌ Erreur: ${err.message}`, 'error');
            updateUI('ready');
        }
    }

    // ─── Lecture audio ─────────────────────────────────────────────────────────

    function playAudio(url) {
        updateUI('playing');
        const audio = new Audio(url);
        audio.onended = () => updateUI('ready');
        audio.play();
    }

    function playAudioBase64(base64) {
        updateUI('playing');
        const audio = new Audio(`data:audio/mp3;base64,${base64}`);
        audio.onended = () => updateUI('ready');
        audio.play();
    }

    // ─── UI ────────────────────────────────────────────────────────────────────

    function updateUI(state) {
        const status = document.getElementById('cf-status');
        const recordBtn = document.getElementById('cf-record-btn');
        const stopBtn = document.getElementById('cf-stop-btn');
        const sendBtn = document.getElementById('cf-send-btn');

        switch (state) {
            case 'recording':
                status.textContent = '🔴 Enregistrement...';
                status.className = 'cf-vocal-status recording';
                recordBtn.style.display = 'none';
                stopBtn.style.display = 'flex';
                sendBtn.style.display = 'none';
                break;
            case 'recorded':
                status.textContent = '✅ Enregistré';
                status.className = 'cf-vocal-status';
                recordBtn.style.display = 'flex';
                stopBtn.style.display = 'none';
                sendBtn.style.display = 'flex';
                break;
            case 'processing':
                status.textContent = '⏳ Traitement...';
                status.className = 'cf-vocal-status processing';
                recordBtn.style.display = 'none';
                stopBtn.style.display = 'none';
                sendBtn.style.display = 'none';
                break;
            case 'playing':
                status.textContent = '🔊 Lecture...';
                status.className = 'cf-vocal-status playing';
                recordBtn.style.display = 'flex';
                stopBtn.style.display = 'none';
                sendBtn.style.display = 'none';
                break;
            default: // ready
                status.textContent = 'Prêt';
                status.className = 'cf-vocal-status';
                recordBtn.style.display = 'flex';
                stopBtn.style.display = 'none';
                sendBtn.style.display = 'none';
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
        visualizer.innerHTML = '';
        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
    }

    // ─── Initialisation ────────────────────────────────────────────────────────

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createWidget);
    } else {
        createWidget();
    }
})();
