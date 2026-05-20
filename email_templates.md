# ═══════════════════════════════════════════════════════════════════════════════
# Chatbot Factory — Templates de Courriel
# ═══════════════════════════════════════════════════════════════════════════════
# 4 templates pour couvrir le parcours client complet :
#
#   1. Premier contact / Proposition
#   2. Envoi du formulaire d'onboarding
#   3. Lien de démo (après génération de l'agent)
#   4. Suivi post-démo (relance)
#
# Variables à remplacer :
#   {prenom}          → Prénom du contact
#   {nom_client}      → Nom de l'entreprise du client
#   {nom_agent}       → Nom de l'agent (ex: "Clinique Santé Plus")
#   {form_url}        → Lien vers le Google Form
#   {demo_url}        → Lien vers la démo de l'agent
#   {agent_url}       → URL de l'agent en production
#   {widget_code}     → Code du widget à copier-coller
#   {votre_prenom}    → Ton prénom (le vendeur)
#   {votre_nom}       → Ton nom
#   {votre_tel}       → Ton numéro de téléphone
#   {votre_email}     → Ton courriel
#   {date}            → Date du jour
#   {rendez_vous}     → Lien Calendly/Cal.com pour prendre rendez-vous
#
# ═══════════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE 1 : Premier Contact / Proposition
# ─────────────────────────────────────────────────────────────────────────────
# Quand : Premier courriel froid ou après une recommandation
# Objectif : Accrocher, présenter la valeur, obtenir un rendez-vous

OBJET: {nom_client} — Un agent intelligent pour vos clients (24/7)

Bonjour {prenom},

Je me permets de vous écrire parce que je travaille avec des entreprises comme la vôtre pour résoudre un problème très concret :

**Vos clients ont des questions. Vous avez les réponses. Mais ils ne les trouvent pas au bon moment.**

Résultat ?
- Des appels répétitifs qui mobilisent votre équipe
- Des clients qui abandonnent en dehors des heures d'ouverture
- Des leads qui vont voir ailleurs parce qu'ils n'ont pas eu de réponse immédiate

Chez **Chatbot Factory**, on construit des **agents conversationnels intelligents** — pas des robots génériques, mais un assistant numérique **entraîné sur VOS connaissances**, qui :

✅ Répond aux questions de vos clients **24 heures sur 24, 7 jours sur 7**
✅ Prend des rendez-vous et qualifie les leads automatiquement
✅ S'intègre à votre site web, votre calendrier et votre CRM
✅ Parle le ton de votre entreprise (professionnel, chaleureux, bilingue…)

**Le tout en moins de 10 jours ouvrables.**

Je vous propose un appel de 15 minutes pour vous montrer ce que ça donnerait concrètement pour {nom_client}. Pas de pitch générique — une démo basée sur VOTRE site web.

📅 Quand vous conviendrait-il ? {rendez_vous}

Au plaisir d'échanger,

{votre_prenom} {votre_nom}
📧 {votre_email}
📱 {votre_tel}
🌐 chatbotfactory.xyz

---
*P.S. — Même si vous n'êtes pas prêt maintenant, je peux vous envoyer une analyse gratuite de votre site web pour identifier les questions les que vos clients se posent le plus. Aucune obligation.*

---

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE 2 : Envoi du Formulaire d'Onboarding
# ─────────────────────────────────────────────────────────────────────────────
# Quand : Après le premier appel, quand le client dit "go"
# Objectif : Lui envoyer le formulaire pour collecter ses informations

OBJET: Prochaine étape — Formulaire d'onboarding {nom_client}

Bonjour {prenom},

Merci pour notre conversation de tout à l'heure! C'était un plaisir d'en apprendre davantage sur {nom_client} et vos objectifs.

Comme discuté, la prochaine étape est de recueillir les informations qui nous permettront de construire votre agent conversationnel sur mesure.

📋 **Voici le formulaire à remplir :**
{form_url}

**Quelques détails :**
- ⏱️ Temps estimé : 15-20 minutes
- 📝 6 sections : infos générales, objectifs, services, intégrations, personnalité, budget
- 💡 Plus vos réponses sont détaillées, plus votre agent sera efficace
- 📎 Vous pouvez joindre des documents (FAQ, grille de prix, etc.)

**Ce qui se passe après :**
1. Vous remplissez le formulaire
2. On analyse vos réponses + on scrape votre site web
3. On génère votre agent personnalisé
4. On vous envoie un lien de démo pour tester

**Délai de livraison de la démo : 48-72 heures après réception du formulaire.**

N'hésitez pas à me contacter si vous avez des questions en remplissant le formulaire.

À bientôt!

{votre_prenom} {votre_nom}
📧 {votre_email}
📱 {votre_tel}

---

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE 3 : Lien de Démo (après génération de l'agent)
# ─────────────────────────────────────────────────────────────────────────────
# Quand : L'agent est prêt et déployé sur Render
# Objectif : Inviter le client à tester et donner du feedback

OBJET: 🎉 Votre agent est prêt! — Démo {nom_client}

Bonjour {prenom},

Bonne nouvelle : **votre agent conversationnel est en ligne!** 🚀

🤖 **Accédez à votre démo ici :**
{demo_url}

**Comment tester :**
1. Cliquez sur le lien ci-dessus
2. Cliquez sur l'icône de chat en bas à droite
3. Posez des questions comme le ferait un vrai client de {nom_client}
4. Testez différents scénarios : prise de rendez-vous, questions sur les services, demande de prix, etc.

**Ce qui fonctionne :**
✅ Réponses basées sur le contenu de votre site web
✅ Base de connaissances entraînée sur vos services
✅ Ton et personnalité alignés avec votre image de marque
✅ Transfert vers un humain quand nécessaire

**Ce qu'on aimerait que vous testiez :**
- Les réponses sont-elles exactes?
- Le ton vous semble-t-il approprié?
- Y a-t-il des questions auxquelles l'agent ne répond pas bien?
- Des ajustements à faire?

📝 **Donnez-nous votre feedback ici :**
[LIEN GOOGLE FORM FEEDBACK — à créer]

**Prochaines étapes après validation :**
1. On ajuste selon vos commentaires
2. On configure les intégrations (calendrier, CRM, courriel)
3. On vous fournit le code du widget à intégrer sur votre site web
4. Go-live! 🎯

Je vous propose un appel de suivi dans 3-4 jours pour discuter de vos impressions. Ça vous va?

📅 {rendez_vous}

Hâte de savoir ce que vous en pensez!

{votre_prenom} {votre_nom}
📧 {votre_email}
📱 {votre_tel}

---

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE 4 : Suivi Post-Démo (Relance)
# ─────────────────────────────────────────────────────────────────────────────
# Quand : 3-4 jours après l'envoi de la démo, pas de réponse
# Objectif : Relancer doucement, lever les objections

OBJET: Suivi — Votre démo {nom_client}

Bonjour {prenom},

Je voulais faire un petit suivi concernant la démo de votre agent conversationnel que je vous ai envoyée il y a quelques jours.

Avez-vous eu l'occasion de la tester? J'aimerais beaucoup avoir vos impressions — même si c'est juste 2-3 minutes de feedback, ça nous aide énormément à ajuster.

**Rappel du lien :** {demo_url}

**Quelques questions pour guider votre test :**
- L'agent répond-il correctement aux questions sur vos services?
- Le ton vous semble-t-il approprié pour {nom_client}?
- Y a-t-il des informations manquantes ou inexactes?

Si vous avez des questions ou des hésitations, c'est tout à fait normal — c'est exactement à ça que sert la phase de démo. On ajuste jusqu'à ce que ce soit parfait.

📅 **On planifie un appel de 15 minutes pour en discuter?**
{rendez_vous}

Pas de pression — je suis là quand vous êtes prêt.

Bonne journée!

{votre_prenom} {votre_nom}
📧 {votre_email}
📱 {votre_tel}

---
*P.S. — Si le timing n'est pas idéal en ce moment, aucun souci. Dites-moi quand vous préférez qu'on reprenne contact.*

---

# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE 5 : Go-Live (Mise en production)
# ─────────────────────────────────────────────────────────────────────────────
# Quand : Le client a validé la démo, on passe en production
# Objectif : Lui remettre le widget et les instructions finales

OBJET: 🎯 Go-Live! — Votre agent {nom_client} est en production

Bonjour {prenom},

Félicitations! Votre agent conversationnel est officiellement **en production**. 🎉

**Voici les informations pour l'intégrer à votre site web :**

---

**📋 Code du widget à ajouter à votre site :**

Copiez ce code et collez-le juste avant la balise `</body>` de votre site web (ou dans le `<head>`) :

```html
<script src="{widget_url}"
        data-agent-url="{agent_url}"
        data-client-name="{nom_agent}"
        data-primary-color="#6366f1"
        data-language="fr">
</script>
```

**Où le coller selon votre plateforme :**

| Plateforme | Où coller le code |
|---|---|
| **WordPress** | Apparence → Éditeur de thème → footer.php OU utiliser le plugin "Insert Headers and Footers" |
| **Wix** | Paramètres → Avancé → Suivi et analytics → Nouveau outil → Custom |
| **Shopify** | Boutique en ligne → Thèmes → Personnaliser → Paramètres du thème → Scripts supplémentaires |
| **Squarespace** | Paramètres → Avancé → Injection de code → Footer |
| **Site sur mesure** | Coller avant `</body>` dans le fichier HTML principal |

---

**🔗 URL de votre agent :** {agent_url}

**📊 Tableau de bord :** Vous recevrez un rapport hebdomadaire automatique avec :
- Nombre de conversations
- Taux de résolution
- Leads captés
- Questions les plus fréquentes

---

**✅ Checklist de validation :**
- [ ] Le widget apparaît sur votre site web
- [ ] L'agent répond correctement aux questions
- [ ] Le bouton de transfert humain fonctionne
- [ ] Les rendez-vous sont créés dans votre calendrier (si applicable)
- [ ] Les confirmations courriel sont envoyées (si applicable)

---

**🔧 Support :**
Si vous avez un problème ou une question, répondez simplement à ce courriel ou contactez-moi directement.

**Prochain rendez-vous :** On planifie un suivi dans 2 semaines pour analyser les premières métriques et optimiser.

📅 {rendez_vous}

Encore félicitations pour cette étape! {nom_client} fait maintenant partie des entreprises innovantes qui offrent une expérience client 24/7.

Au plaisir!

{votre_prenom} {votre_nom}
📧 {votre_email}
📱 {votre_tel}
🌐 chatbotfactory.xyz

---

# ═══════════════════════════════════════════════════════════════════════════════
# NOTES D'UTILISATION
# ═══════════════════════════════════════════════════════════════════════════════
#
# 1. Personnalisez CHAQUE courriel avec les vraies informations du client
# 2. Ne jamais envoyer un courriel "template" sans personnalisation
# 3. Le ton est professionnel mais accessible — pas corporate rigide
# 4. Toujours inclure un CTA clair (call-to-action) : rendez-vous, feedback, etc.
# 5. Les P.S. sont lus — utilisez-les pour ajouter de la valeur ou lever une objection
# 6. Gardez les courts : si ça tient sur un écran de téléphone, c'est parfait
#
# ═══════════════════════════════════════════════════════════════════════════════
