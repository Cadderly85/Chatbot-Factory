---
title: Chatbot Factory Vocal
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
---

# Chatbot Factory — Agent Texte + Vocal

Agent conversationnel pour entreprises avec :
- Chat texte via LLM (OpenRouter + fallback OpenAI)
- Reconnaissance vocale côté client (Web Speech API)
- Base de connaissances personnalisable

## Utilisation

```bash
curl -X POST https://cadderlyy-chatbot-factory-vocal.hf.space/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Bonjour", "session_id": "default"}'
```
