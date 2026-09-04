# Opengoon Telegram Bot

A feature-rich Telegram Bot built with `python-telegram-bot` for AI image generation, account & point management, user rewards, forced channel joining verification, and admin controls.

## 🚀 Features

- **AI Image Generation**: Supports multiple Opengoon modes (`transparent`, `xray`, `anime`, `real`, etc.).
- **Automatic Account Selection**: Automatically skips paused/inactive accounts and uses active accounts for background operations.
- **Log Channel & Auto-Deletion**: Sends generated images to log channel (`@absbabshsb`) first, then delivers to users with a 1-hour auto-delete timer.
- **Force Join Verification**: Ensures users subscribe to required channels before accessing bot features.
- **Points & Referral System**: Built-in points tracking, daily check-in rewards, and task completion bonuses.
- **Support Ticket System**: Direct communication system between users and bot admins.

---

## 🛠️ Railway Deployment Guide

### 1. Requirements
- Python 3.10+
- Dependencies listed in `requirements.txt`

### 2. Environment Variables
Set the following environment variables in your Railway Project Settings:

| Variable | Required | Description | Default Fallback |
| :--- | :---: | :--- | :--- |
| `BOT_TOKEN` | **Yes** | Your Telegram Bot Token from @BotFather | `7525682158:AAGv-M7A9zlpTuAcMvL-Qp8WJ5KuFemZgxk` |
| `ADMIN_PASSWORD` | No | Password for `/admin` authentication | `Shanucom101@` |
| `LOG_CHANNEL` | No | Channel username for image logging | `@absbabshsb` |

### 3. Deploying to Railway
1. Connect your GitHub repository (`Shancom900/bikni`) to Railway.
2. Select **Deploy from GitHub repo**.
3. Add the `BOT_TOKEN` environment variable under **Variables**.
4. Railway automatically detects `Procfile` (`worker: python bot.py`) and starts the bot!

---

## 📂 Project Structure

```text
├── bot.py              # Main Telegram bot handlers & business logic
├── db.py               # JSON Database operations & state management
├── account_creator.py  # Opengoon API auth & generation handlers
├── database.json       # Initial database file
├── requirements.txt    # Python dependencies
├── Procfile            # Deployment configuration for Railway / Heroku
└── README.md           # Project documentation
```

---

## 💻 Local Setup & Execution

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the bot**:
   ```bash
   python bot.py
   ```
