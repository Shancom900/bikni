# Opengoon Telegram Bot

A feature-rich Telegram Bot built with `python-telegram-bot` for AI image generation, account & point management, user rewards, forced channel joining verification, and admin controls.

---

## ⚙️ Railway Environment Variables Example

Copy and paste these variable Key/Value pairs into your **Railway Project Settings -> Variables**:

### 1. `BOT_TOKEN` (Required)
```env
BOT_TOKEN=7525682158:AAGv-M7A9zlpTuAcMvL-Qp8WJ5KuFemZgxk
```

### 2. `ADMIN_PASSWORD` (Optional)
```env
ADMIN_PASSWORD=Shanucom101@
```

### 3. `LOG_CHANNEL` (Optional)
```env
LOG_CHANNEL=@absbabshsb
```

---

## 🛠️ Quick Variable Summary Table

| Key | Example Value | Description |
| :--- | :--- | :--- |
| `BOT_TOKEN` | `7525682158:AAGv-M7A9zlpTuAcMvL-Qp8WJ5KuFemZgxk` | Telegram bot token from @BotFather |
| `ADMIN_PASSWORD` | `Shanucom101@` | Admin access password for `/admin` command |
| `LOG_CHANNEL` | `@absbabshsb` | Telegram channel for logging generated images |

---

## 🚀 Features

- **AI Image Generation**: Supports multiple Opengoon modes (`transparent`, `xray`, `anime`, `real`, etc.).
- **Automatic Account Selection**: Automatically skips paused/inactive accounts and uses active accounts for background operations.
- **Log Channel & Auto-Deletion**: Sends generated images to log channel (`@absbabshsb`) first, then delivers to users with a 1-hour auto-delete timer.
- **Force Join Verification**: Ensures users subscribe to required channels before accessing bot features.
- **Points & Referral System**: Built-in points tracking, daily check-in rewards, and task completion bonuses.
- **Support Ticket System**: Direct communication system between users and bot admins.

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
