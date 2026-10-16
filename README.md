# 🤖 Bot Vinted / Shein Automation Multi-Navigateurs

Système d'automatisation e-commerce haute performance conçu pour scraper des fiches produits Shein, générer des photos flat-lay haute définition via **Google Gemini**, rédiger des annonces optimisées via **Meta AI**, synchroniser en temps réel sur **Google Sheets**, sauvegarder sur **Google Drive** et notifier sur **Telegram**.

---

## 🌟 Fonctionnalités Clés

1. **Architecture Multi-Navigateurs Isolée (AdsPower + Playwright)** :
   * Exécution simultanée sur 4 instances AdsPower dédiées (ports CDP isolés).
   * Zéro conflit d'onglets, zéro verrou bloquant inter-processus.
   * Orchestrateur de surveillance permanent avec watchdog et auto-reconnexion.

2. **Génération d'Images Flat-Lay HD (Google Gemini)** :
   * Envoi des 5 meilleures photos sources d'origine par injection `DataTransfer` (presse-papiers).
   * **Garde-fou strict** : vérification physique de la présence des vignettes attachées dans le DOM Gemini avant envoi du prompt.
   * Extraction directe du rendu HD via HTML5 Canvas (`naturalWidth` / `naturalHeight`).
   * Gestion intelligente des quotas avec mise en veille automatique et reprise autonome.

3. **Rédaction E-commerce Intelligente (Meta AI)** :
   * Génération de titres, descriptions attrayantes, matières et mots-clés selon l'identité spécifique de chaque compte Vinted.

4. **Synchronisation Google Sheets & Google Drive** :
   * Suivi d'état en direct dans les onglets vendeurs (`Fait scrap`, `Image générée`, `Rédaction fait`).
   * Téléversement automatisé des photos et prompts vers Google Drive via `rclone`.

5. **Validation et Notifications Telegram** :
   * Envoi de fiches de révision instantanées avec aperçu des flatlays et descriptions prêtes à publier.
   * Commandes interactives pour les opérateurs.

---

## 📁 Structure du Projet

```text
├── orchestrator_multi_ports.py  # Superviseur principal des 4 workers
├── runner_base.py               # Logique commune Playwright / Sheets / Gemini
├── runner_port_43983.py         # Worker dédié Navigateur 1
├── runner_port_34115.py         # Worker dédié Navigateur 2
├── runner_port_38049.py         # Worker dédié Navigateur 3
├── runner_port_42677.py         # Worker dédié Navigateur 4
├── cdp_gemini_flatlay.py        # Moteur de génération Gemini Flat-Lay
├── ai_redaction.py              # Moteur de rédaction Meta AI
├── scraper.py                   # Scraper Shein
├── account_library.py           # Bibliothèque des styles et prompts par compte
├── upload_to_gdrive.py          # Synchronisation Google Drive
├── telegram_bot.py              # Bot Telegram interactif
└── telegram_notifier.py         # Envoi des alertes et fiches de révision
```

---

## ⚙️ Prérequis & Installation

```bash
# Cloner le dépôt
git clone https://github.com/vanquydang905-boop/Bot-vinted.git
cd Bot-vinted

# Créer un environnement virtuel Python
python3 -m venv /root/venv
source /root/venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
playwright install chromium
```

---

## 🚀 Lancement

```bash
# Lancer l'orchestrateur multi-navigateurs
python orchestrator_multi_ports.py

# Lancer le bot Telegram en arrière-plan
python telegram_bot.py &
```
