import os
import re
import io
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Set
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ChatMember,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from account_creator import (
    register_opengoon_account,
    login_opengoon_account,
    fetch_opengoon_balance,
    DEFAULT_PASSWORD,
)
from db import db

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram Bot Token & Admin Password
BOT_TOKEN = os.getenv("BOT_TOKEN", "7525682158:AAGv-M7A9zlpTuAcMvL-Qp8WJ5KuFemZgxk")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Shanucom101@")
LOG_CHANNEL = os.getenv("LOG_CHANNEL", "@absbabshsb")

# Authenticated Admin User IDs in session
AUTHENTICATED_ADMINS: Set[int] = set()

# User state storage: user_id -> state
USER_STATES: Dict[int, str] = {}
TEMP_ACCOUNT_DATA: Dict[int, Dict[str, str]] = {}
TEMP_TASK_DATA: Dict[int, Dict[str, Any]] = {}

# Available options mapped from opengoon.com features
OPENGOON_MODES = {
    "transparent": {"name": "🔍 Transparent (2 Points)", "endpoint": "/generations/xray", "page": "/xray", "style": "transparent", "cost": 2},
    "xray": {"name": "🩻 X-Ray (2 Points)", "endpoint": "/generations/xray", "page": "/xray", "style": "nude", "cost": 2},
    "nude": {"name": "🔞 Nude AI Generator (3 Points)", "endpoint": "/generations/xray", "page": "/xray", "style": "nude", "cost": 3},
    "bikini": {"name": "👙 Bikini (2 Points)", "endpoint": "/generations/xray", "page": "/xray", "style": "bikini", "cost": 2},
    "deepfake": {"name": "🎭 Deepfake Generator (2 Points)", "endpoint": "/generations/deepfake-ai", "page": "/deepfake-ai", "style": "nude", "cost": 2},
    "face_swap": {"name": "🔄 Face Swap (2 Points)", "endpoint": "/generations/face-swap", "page": "/face-swap", "style": "nude", "cost": 2},
    "bikini_remover": {"name": "🏖️ Bikini Remover (2 Points)", "endpoint": "/generations/bikini-remover", "page": "/bikini-remover", "style": "bikini", "cost": 2},
    "ai_girlfriend": {"name": "💋 AI Generator (2 Points)", "endpoint": "/generations/ai-generator", "page": "/ai-generator", "style": "nude", "cost": 2},
}

BASE_URL = "https://opengoon.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# Terms of Use Notice Text
TERMS_TEXT = (
    "⚠️ *TERMS OF USE & AGE VERIFICATION*\n\n"
    "• You must be 18 or the age of majority in your country.\n"
    "• You can't use other people's photos without their consent or if they are minors.\n"
    "• You are solely responsible for the content you generate.\n\n"
    "👉 By selecting *“Agree & Enter,”* you confirm the statements above and agree to our Terms of Use.\n"
    "📢 *Note:* You must join our official Telegram channel to access the bot!"
)

DEFAULT_IMAGE_URL = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80"


def get_main_keyboard():
    """Creates standard persistent reply keyboard for user navigation with Support, Tasks, and Giftcard buttons."""
    keyboard = [
        [
            KeyboardButton("🔍 Transparent"), 
            KeyboardButton("👙 Bikini")
        ],
        [
            KeyboardButton("🔞 Nude AI (3 Points)")
        ],
        [
            KeyboardButton("🎯 Tasks (+Points)"), 
            KeyboardButton("🎁 Refer & Earn (+1 Point)")
        ],
        [
            KeyboardButton("👤 My Balance"), 
            KeyboardButton("🎫 Redeem Giftcard")
        ],
        [
            KeyboardButton("💬 Support")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def check_channel_joined(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user has joined the mandatory channel."""
    settings = db.get_settings()
    channel = settings.get("channel_username", "@WorldLinkers")
    if not channel:
        return True
    
    channel_clean = channel.strip()
    if channel_clean.startswith("https://t.me/"):
        channel_clean = "@" + channel_clean.replace("https://t.me/", "").rstrip("/")
    elif channel_clean.startswith("t.me/"):
        channel_clean = "@" + channel_clean.replace("t.me/", "").rstrip("/")
    if not channel_clean.startswith("@") and not channel_clean.startswith("-100"):
        channel_clean = "@" + channel_clean

    try:
        member = await context.bot.get_chat_member(chat_id=channel_clean, user_id=user_id)
        status = getattr(member, "status", str(member)).lower()
        if status in ["member", "administrator", "creator", "owner"]:
            return True
        if status == "restricted":
            return getattr(member, "is_member", True)
        return False
    except Exception as e:
        logger.warning(f"Could not verify channel membership for {user_id} in {channel_clean}: {e}")
        return False


async def ensure_channel_joined(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Enforces mandatory channel join for non-admin users."""
    user = update.effective_user
    if not user:
        return True
    user_id = user.id
    if db.is_admin(user_id) or user_id in AUTHENTICATED_ADMINS:
        return True

    joined = await check_channel_joined(user_id, context)
    if joined:
        return True

    settings = db.get_settings()
    ch_username = settings.get("channel_username", "@WorldLinkers")
    ch_link = settings.get("channel_link", "https://t.me/WorldLinkers")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel First", url=ch_link)],
        [InlineKeyboardButton("✅ Check Membership / Joined", callback_data="check_force_join")]
    ])

    msg_text = (
        f"🚨 *MANDATORY CHANNEL JOIN REQUIRED*\n\n"
        f"To access Open Loom AI Bot, you MUST join our official Telegram channel first!\n\n"
        f"👉 Channel: *{ch_username}*\n"
        f"🔗 Link: [Click Here to Join]({ch_link})\n\n"
        f"After joining, tap the *'✅ Check Membership / Joined'* button below to proceed!"
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                msg_text, reply_markup=keyboard, parse_mode="Markdown"
            )
        except Exception:
            await update.callback_query.message.reply_text(
                msg_text, reply_markup=keyboard, parse_mode="Markdown"
            )
    elif update.message:
        await update.message.reply_text(
            msg_text, reply_markup=keyboard, parse_mode="Markdown"
        )
    return False


def get_session(cookie_str: str) -> requests.Session:
    """Creates a requests.Session pre-loaded with full cookie header."""
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Cookie"] = cookie_str
    for item in cookie_str.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            s.cookies.set(k, v, domain="opengoon.com")
    return s


def fetch_csrf_token(session: requests.Session, endpoint: str) -> str:
    """Fetches target page and extracts CSRF authenticity token."""
    url = f"{BASE_URL}{endpoint}"
    resp = session.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    meta = soup.find("meta", {"name": "csrf-token"})
    if meta and meta.get("content"):
        return meta["content"]
    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', resp.text)
    if match:
        return match.group(1)
    raise ValueError("CSRF Token could not be extracted from Opengoon.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command: Deep link Referral + Force Join + Terms UI."""
    user = update.effective_user
    user_id = user.id
    db.get_user(user_id)
    if user.username:
        db.update_username(user_id, user.username)

    if context.args:
        try:
            ref_id = int(context.args[0])
            if ref_id != user_id:
                db.set_referrer(user_id, ref_id)
        except ValueError:
            pass

    settings = db.get_settings()
    channel_link = settings.get("channel_link", "https://t.me/WorldLinkers")
    user_data = db.get_user(user_id)

    inline_keyboard = [
        [InlineKeyboardButton("📢 Join Channel First", url=channel_link)],
        [InlineKeyboardButton("✅ Agree & Enter", callback_data="agree_terms")]
    ]
    reply_markup_inline = InlineKeyboardMarkup(inline_keyboard)

    if user_data.get("agreed", False):
        if not await ensure_channel_joined(update, context):
            return
        await send_main_menu(update, context)
        return

    image_url = settings.get("terms_image_url", DEFAULT_IMAGE_URL)
    try:
        await update.message.reply_photo(
            photo=image_url,
            caption=TERMS_TEXT,
            reply_markup=reply_markup_inline,
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text(
            text=TERMS_TEXT,
            reply_markup=reply_markup_inline,
            parse_mode="Markdown"
        )


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the main interactive mode selector menu with Support & Tasks inline buttons."""
    user_id = update.effective_user.id
    points = db.get_points(user_id)

    keyboard = [
        [
            InlineKeyboardButton("🔍 Transparent (2 Points)", callback_data="mode_transparent"),
            InlineKeyboardButton("👙 Bikini (2 Points)", callback_data="mode_bikini")
        ],
        [
            InlineKeyboardButton("🔞 Nude AI (3 Points)", callback_data="mode_nude"),
        ],
        [
            InlineKeyboardButton("🎯 Tasks & Earn (+Pts)", callback_data="user_tasks_menu"),
            InlineKeyboardButton("🎁 Refer & Earn (+1 Ref)", callback_data="referral_info")
        ],
        [
            InlineKeyboardButton("🎫 Redeem Giftcard", callback_data="user_giftcard"),
            InlineKeyboardButton("💬 Customer Support", callback_data="user_support")
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    msg_text = (
        f"🔥 *Welcome to Open Loom AI Bot*\n\n"
        f"👤 *Your Account Points:* `{points} Points` ⚡\n"
        f"🎁 *Earn Free Points:* Complete 🎯 *Tasks*, Refer friends (+1 Pt), or Redeem a Giftcard!\n\n"
        f"Select a feature below to get started, then send a photo!"
    )

    if update.message:
        await update.message.reply_text(
            "👇 Choose a command below or select an inline feature:",
            reply_markup=get_main_keyboard()
        )
        await update.message.reply_text(
            msg_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                msg_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception:
            await update.callback_query.message.reply_text(
                msg_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )


async def send_user_tasks_menu(user_id: int, update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """Sends inline Tasks menu listing all available social tasks."""
    tasks = db.get_all_tasks()
    points = db.get_points(user_id)

    keyboard = []
    if not tasks:
        msg_text = "🎯 *TASKS & REWARDS*\n\nCurrently there are no active tasks available. Check back soon!"
    else:
        msg_text = (
            f"🎯 *OPEN LOOM TASKS & REWARDS* 🎁\n\n"
            f"Complete simple social tasks below to earn free Points!\n"
            f"Click any task button below to view instructions and claim reward.\n\n"
            f"👤 *Your Points Balance:* `{points} Points` ⚡"
        )
        for task in tasks:
            t_id = task.get("id")
            title = task.get("title", "Task")
            pts = task.get("points", 1)
            is_done = db.is_task_completed(user_id, t_id)
            if is_done:
                btn_text = f"✅ {title} (Claimed)"
            else:
                btn_text = f"🎯 {title} (+{pts} Pts)"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"task_view_{t_id}")])

    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if hasattr(update_or_query, "reply_text"):
        await update_or_query.reply_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        try:
            await update_or_query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            await update_or_query.message.reply_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")


async def send_task_detail(user_id: int, task_id: int, query):
    """Displays detailed instructions for a task with url link and claim button."""
    task = db.get_task(task_id)
    if not task:
        await query.answer("Task not found!", show_alert=True)
        return

    title = task.get("title", "Task")
    url = task.get("url", "#")
    pts = task.get("points", 1)
    is_done = db.is_task_completed(user_id, task_id)

    status_str = "✅ Claimed" if is_done else "⏳ Pending"

    msg_text = (
        f"🎯 *TASK DETAILS: {title}*\n\n"
        f"💎 *Reward:* `+{pts} Points`\n"
        f"📌 *Status:* {status_str}\n\n"
        f"👉 *Instructions:*\n"
        f"1. Click *'🔗 Open Task Link'* below to complete the action (e.g. follow, subscribe, join).\n"
        f"2. Return to this chat and tap *'✅ Check & Claim Reward'* to receive your `{pts} Points`!"
    )

    keyboard = [[InlineKeyboardButton("🔗 Open Task Link", url=url)]]
    if not is_done:
        keyboard.append([InlineKeyboardButton("✅ Check & Claim Reward", callback_data=f"task_claim_{task_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Tasks", callback_data="user_tasks_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")


def is_user_authenticated_admin(user_id: int) -> bool:
    """Returns True if user_id has unlocked Admin Panel via password."""
    return user_id in AUTHENTICATED_ADMINS or db.is_admin(user_id)


async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command handler (/admin) with Password Check."""
    user_id = update.effective_user.id
    if not is_user_authenticated_admin(user_id):
        USER_STATES[user_id] = "WAITING_FOR_ADMIN_PASSWORD"
        await update.message.reply_text(
            "🔒 *ADMIN PANEL LOCKED*\n\nPlease enter the Admin Password to unlock the control panel:",
            parse_mode="Markdown"
        )
        return

    await send_admin_panel(update.effective_chat.id, context)


async def send_admin_panel(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Sends the admin control panel with inline buttons including 💎 Points & 🎯 Tasks Sections."""
    keyboard = [
        [
            InlineKeyboardButton("💎 Points Section", callback_data="admin_points_menu"),
            InlineKeyboardButton("🎯 Manage Tasks", callback_data="admin_tasks_menu")
        ],
        [
            InlineKeyboardButton("🔑 Accounts List", callback_data="admin_accounts"),
            InlineKeyboardButton("➕ Add Account (Auto Login)", callback_data="admin_add_account_auto")
        ],
        [
            InlineKeyboardButton("🍪 Add Raw Cookie", callback_data="admin_add_cookie"),
            InlineKeyboardButton("📩 User Queries", callback_data="admin_queries")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"),
            InlineKeyboardButton("➕ Create Account", callback_data="admin_create_account")
        ],
        [
            InlineKeyboardButton("🔗 Set Invite Link", callback_data="admin_set_invite"),
            InlineKeyboardButton("📢 Set Channel", callback_data="admin_set_channel")
        ],
        [
            InlineKeyboardButton("📊 System Status", callback_data="admin_status")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=chat_id,
        text="⚙️ *Admin Control Panel*\n\n"
             "Select an option below to manage tasks, points, accounts, queries, auto-login, raw cookies, broadcast, or system settings:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def send_admin_tasks_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_target=None):
    """Sends the Admin Tasks control menu."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Add New Task", callback_data="admin_add_task_start"),
            InlineKeyboardButton("📋 View & Delete Tasks", callback_data="admin_view_tasks")
        ],
        [
            InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "🎯 *ADMIN TASK MANAGEMENT*\n\n"
        "Select an option below to create new user tasks (e.g. Instagram follow, YouTube subscribe, Telegram channel join) or delete existing ones:"
    )
    if reply_target and hasattr(reply_target, "edit_message_text"):
        await reply_target.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")


async def send_admin_tasks_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_target=None):
    """Lists all tasks with delete inline buttons."""
    tasks = db.get_all_tasks()
    if not tasks:
        msg_text = "⚠️ *No Tasks Found in Database!*\nClick '➕ Add New Task' to create one."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Tasks Menu", callback_data="admin_tasks_menu")]])
        if reply_target and hasattr(reply_target, "edit_message_text"):
            await reply_target.edit_message_text(msg_text, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=chat_id, text=msg_text, reply_markup=keyboard, parse_mode="Markdown")
        return

    msg_text = f"📋 *OPEN LOOM TASKS LIST ({len(tasks)} Total)*\n\n"
    keyboard = []
    for t in tasks:
        t_id = t.get("id")
        title = t.get("title", "Task")
        url = t.get("url", "")
        pts = t.get("points", 1)
        msg_text += f"• *#{t_id}* `{title}` | Link: `{url}` | Reward: `+{pts} Pts`\n"
        keyboard.append([InlineKeyboardButton(f"🗑️ Delete Task #{t_id} ({title})", callback_data=f"admin_delete_task_{t_id}")])

    keyboard.append([InlineKeyboardButton("🔙 Back to Tasks Menu", callback_data="admin_tasks_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if reply_target and hasattr(reply_target, "edit_message_text"):
        await reply_target.edit_message_text(msg_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=msg_text, reply_markup=reply_markup, parse_mode="Markdown")


async def send_points_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE, reply_target=None):
    """Sends the Points Management sub-menu."""
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Points to User", callback_data="admin_add_points_start"),
            InlineKeyboardButton("➖ Deduct Points", callback_data="admin_deduct_points_start")
        ],
        [
            InlineKeyboardButton("🎫 Create Giftcard Code", callback_data="admin_create_giftcard"),
            InlineKeyboardButton("📊 User Balances List", callback_data="admin_view_points_list")
        ],
        [
            InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin_panel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "💎 *POINTS MANAGEMENT SECTION*\n\n"
        "Select an action below to add/deduct points, create giftcard codes, or view user point balances:"
    )
    if reply_target and hasattr(reply_target, "edit_message_text"):
        await reply_target.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode="Markdown")


def format_account_card(acc: Dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """Formats single account details with toggle inline buttons."""
    acc_id = acc.get("id")
    email = acc.get("email", "Unknown Email")
    cookie = acc.get("cookie", "")
    cookie_snippet = cookie[:45] + "..." if len(cookie) > 45 else cookie
    credits = acc.get("credits", 5)
    status = acc.get("status", "active")

    status_str = "Active ✅" if status == "active" else "Paused ⏸️"

    text = (
        f"🆔 *Account ID:* `{acc_id}`\n"
        f"📧 *Email:* `{email}`\n"
        f"🔑 *Cookie:* `{cookie_snippet}`\n"
        f"💰 *OpenLoom Balance:* `{credits} Credits`\n"
        f"📌 *Status:* {status_str}"
    )

    if status == "active":
        action_btn = InlineKeyboardButton("⏸️ Pause", callback_data=f"acc_pause_{acc_id}")
    else:
        action_btn = InlineKeyboardButton("▶️ Enable", callback_data=f"acc_enable_{acc_id}")

    refresh_btn = InlineKeyboardButton("🔄 Refresh", callback_data=f"acc_refresh_{acc_id}")
    delete_btn = InlineKeyboardButton("🗑️ Delete", callback_data=f"acc_delete_{acc_id}")

    keyboard = InlineKeyboardMarkup([[action_btn, refresh_btn, delete_btn]])
    return text, keyboard


async def send_accounts_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Lists all accounts one by one with email, cookie, balance, status, and inline buttons."""
    accounts = db.get_all_accounts()

    if not accounts:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ *No Accounts Found!*\nClick '➕ Add Account (Auto Login)' to add one.",
            parse_mode="Markdown"
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📋 *OpenLoom Accounts List ({len(accounts)} Total)*\nListing accounts below:",
        parse_mode="Markdown"
    )

    for acc in accounts:
        card_text, keyboard = format_account_card(acc)
        await context.bot.send_message(
            chat_id=chat_id,
            text=card_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


async def send_queries_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Lists all user support queries with reply inline buttons."""
    queries = db.get_all_queries()

    if not queries:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ *No Support Queries Found!*",
            parse_mode="Markdown"
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📩 *User Support Queries ({len(queries)} Total)*\nListing queries below:",
        parse_mode="Markdown"
    )

    for q in queries:
        q_id = q.get("id")
        uid = q.get("user_id")
        uname = f"@{q.get('username')}" if q.get("username") else "No username"
        q_text = q.get("text", "")
        ts = q.get("timestamp", "")
        status = q.get("status", "pending")
        reply = q.get("reply")

        status_str = "Replied ✅" if status == "replied" else "Pending ⏳"

        msg = (
            f"📩 *Support Ticket #{q_id}*\n"
            f"👤 *User:* {uname} (`{uid}`)\n"
            f"📅 *Time:* `{ts}`\n"
            f"📌 *Status:* {status_str}\n"
            f"💬 *Query:* `{q_text}`\n"
        )
        if reply:
            msg += f"↩️ *Admin Reply:* `{reply}`\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 Reply to Ticket #{q_id}", callback_data=f"reply_query_{q_id}")]
        ])

        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )


async def send_referral_info(user_id: int, context: ContextTypes.DEFAULT_TYPE, reply_target):
    """Sends personal referral link with Share inline button and referral stats."""
    bot_username = context.bot.username or "OpenLoomBot"
    ref_link = f"https://t.me/{bot_username}?start={user_id}"

    share_text = quote_plus("🔥 Check out Open Loom AI Bot! Join now to generate images with free points!")
    share_url = f"https://t.me/share/url?url={quote_plus(ref_link)}&text={share_text}"

    user_data = db.get_user(user_id)
    ref_count = user_data.get("referrals_count", 0)
    points = db.get_points(user_id)

    msg_text = (
        f"✨ ═════════════════════ ✨\n"
        f"🎁  *REFER & EARN FREE POINTS*  🎁\n"
        f"✨ ═════════════════════ ✨\n\n"
        f"Share your personal referral link with your friends!\n"
        f"For every friend who joins using your link, you get *+1 Point*!\n\n"
        f"🔗 *Your Referral Link:*\n`{ref_link}`\n\n"
        f"📊 *Your Referral Stats:*\n"
        f"👥 Total Friends Joined: `{ref_count} Friends`\n"
        f"💎 Current Points Balance: `{points} Points`\n\n"
        f"👇 Click the button below to share directly with friends!"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Share Referral Link to Friends", url=share_url)]
    ])

    if hasattr(reply_target, "reply_text"):
        await reply_target.reply_text(msg_text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await reply_target.edit_message_text(msg_text, reply_markup=keyboard, parse_mode="Markdown")


async def send_cool_balance(user_id: int, context: ContextTypes.DEFAULT_TYPE, update: Update):
    """Sends a cool formatted Member Card / Balance screen."""
    points = db.get_points(user_id)
    user_data = db.get_user(user_id)
    ref_count = user_data.get("referrals_count", 0)

    if points >= 10 or ref_count >= 5:
        tier = "VIP Gold 👑"
    elif points >= 4 or ref_count >= 2:
        tier = "Pro Member 🌟"
    else:
        tier = "Standard Member ⚡"

    card_text = (
        f"✨ ════════════════════════ ✨\n"
        f"💳    *OPEN LOOM MEMBER CARD*    💳\n"
        f"✨ ════════════════════════ ✨\n\n"
        f"👤 *User ID:* `{user_id}`\n"
        f"💎 *Points Balance:* `{points} Points` ⚡\n"
        f"👥 *Total Referrals:* `{ref_count} Friends` 🎁\n"
        f"🔥 *Cost Per Image:* `2 Points`\n"
        f"🏆 *Account Status:* `{tier}`\n\n"
        f"✨ ════════════════════════ ✨"
    )

    bot_username = context.bot.username or "OpenLoomBot"
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    share_text = quote_plus("🔥 Join Open Loom AI Bot and get free generation points!")
    share_url = f"https://t.me/share/url?url={quote_plus(ref_link)}&text={share_text}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Earn More Points (+1 Ref)", callback_data="referral_info")],
        [InlineKeyboardButton("🚀 Share Link", url=share_url)]
    ])

    await update.message.reply_text(card_text, reply_markup=keyboard, parse_mode="Markdown")


async def prompt_support(user_id: int, update_or_query):
    """Prompts user to type support message."""
    USER_STATES[user_id] = "WAITING_FOR_SUPPORT_MSG"
    msg_text = (
        "💬 *OPEN LOOM CUSTOMER SUPPORT*\n\n"
        "Please type your question or support query in this chat below.\n"
        "Our admin team will receive your message and respond directly to you!"
    )
    if hasattr(update_or_query, "reply_text"):
        await update_or_query.reply_text(msg_text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(msg_text, parse_mode="Markdown")


async def prompt_giftcard(user_id: int, update_or_query):
    """Prompts user to type giftcard code."""
    USER_STATES[user_id] = "WAITING_FOR_GIFTCARD_CODE"
    msg_text = (
        "🎫 *REDEEM GIFTCARD CODE*\n\n"
        "Please type your Giftcard code in this chat (e.g. `LOOM-XXXXXXXX`):\n"
        "Points will be credited instantly to your account upon redemption!"
    )
    if hasattr(update_or_query, "reply_text"):
        await update_or_query.reply_text(msg_text, parse_mode="Markdown")
    else:
        await update_or_query.edit_message_text(msg_text, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all inline button callbacks."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # Check force join button verification
    if data == "check_force_join":
        joined = await check_channel_joined(user_id, context)
        if joined:
            db.set_user_agreed(user_id, True)
            await query.answer("✅ Channel membership verified! Welcome to Open Loom.", show_alert=True)
            await send_main_menu(update, context)
        else:
            settings = db.get_settings()
            ch_username = settings.get("channel_username", "@WorldLinkers")
            await query.answer(f"⚠️ You have not joined {ch_username} yet! Please join first.", show_alert=True)
        return

    # Terms Agreement & Force Join
    if data == "agree_terms":
        joined = await check_channel_joined(user_id, context)
        if not joined:
            settings = db.get_settings()
            ch_username = settings.get("channel_username", "@WorldLinkers")
            await query.answer(f"⚠️ Please join {ch_username} first to proceed!", show_alert=True)
            return

        db.set_user_agreed(user_id, True)

        referrer_id = db.reward_referrer(user_id)
        if referrer_id:
            try:
                ref_new_points = db.get_points(referrer_id)
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 *New Referral Milestone!*\n\nSomeone joined using your referral link!\n➕ You earned *+1 Point*!\n👤 Your New Balance: `{ref_new_points} Points`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.warning(f"Could not notify referrer {referrer_id}: {e}")

        try:
            await query.edit_message_caption(
                caption="✅ *Terms Accepted & Channel Verified!*\n\nWelcome! You have been granted *2 free points* to generate.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        await send_main_menu(update, context)
        return

    if data == "main_menu":
        if not await ensure_channel_joined(update, context):
            return
        await send_main_menu(update, context)
        return

    # User Tasks Callbacks
    if data == "user_tasks_menu":
        if not await ensure_channel_joined(update, context):
            return
        await send_user_tasks_menu(user_id, query, context)
        return

    if data.startswith("task_view_"):
        if not await ensure_channel_joined(update, context):
            return
        t_id = int(data.replace("task_view_", ""))
        await send_task_detail(user_id, t_id, query)
        return

    if data.startswith("task_claim_"):
        if not await ensure_channel_joined(update, context):
            return
        t_id = int(data.replace("task_claim_", ""))
        success, msg, pts = db.complete_task(user_id, t_id)
        if success:
            new_pts = db.get_points(user_id)
            await query.answer(f"🎉 Task Completed! +{pts} Points added! Balance: {new_pts} Pts", show_alert=True)
            await send_task_detail(user_id, t_id, query)
        else:
            await query.answer(f"⚠️ {msg}", show_alert=True)
        return

    if data == "referral_info":
        if not await ensure_channel_joined(update, context):
            return
        await send_referral_info(user_id, context, query)
        return

    if data == "user_support":
        if not await ensure_channel_joined(update, context):
            return
        await prompt_support(user_id, query)
        return

    if data == "user_giftcard":
        if not await ensure_channel_joined(update, context):
            return
        await prompt_giftcard(user_id, query)
        return

    # Admin Tasks Section Callbacks
    if data == "admin_tasks_menu":
        if not is_user_authenticated_admin(user_id):
            return
        await send_admin_tasks_menu(query.message.chat_id, context, query)
        return

    if data == "admin_view_tasks":
        if not is_user_authenticated_admin(user_id):
            return
        await send_admin_tasks_list(query.message.chat_id, context, query)
        return

    if data == "admin_add_task_start":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_TASK_TITLE"
        TEMP_TASK_DATA[user_id] = {}
        await query.edit_message_text(
            "➕ *Add New Task (Step 1/3)*\n\n"
            "Please send the Title for this task:\n"
            "Examples: `📸 Follow on Instagram`, `▶️ Subscribe YouTube`, `📢 Join Telegram Channel`",
            parse_mode="Markdown"
        )
        return

    if data.startswith("admin_delete_task_"):
        if not is_user_authenticated_admin(user_id):
            return
        t_id = int(data.replace("admin_delete_task_", ""))
        db.delete_task(t_id)
        await query.answer("🗑️ Task Deleted!", show_alert=True)
        await send_admin_tasks_list(query.message.chat_id, context, query)
        return

    # Admin Panel callbacks
    if data == "admin_panel":
        if not is_user_authenticated_admin(user_id):
            USER_STATES[user_id] = "WAITING_FOR_ADMIN_PASSWORD"
            await query.edit_message_text(
                "🔒 *ADMIN PANEL LOCKED*\n\nPlease type the Admin Password to unlock:",
                parse_mode="Markdown"
            )
            return
        await send_admin_panel(query.message.chat_id, context)
        return

    # Admin Points Section Callbacks
    if data == "admin_points_menu":
        if not is_user_authenticated_admin(user_id):
            return
        await send_points_menu(query.message.chat_id, context, query)
        return

    if data == "admin_create_giftcard":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_GC_POINTS_AMOUNT"
        await query.edit_message_text(
            "🎫 *Create Giftcard Code*\n\n"
            "Please send the Points amount for this Giftcard (e.g. `5` or `10`):",
            parse_mode="Markdown"
        )
        return

    if data == "admin_add_points_start":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_ADD_POINTS_INPUT"
        await query.edit_message_text(
            "➕ *Add Points to User*\n\n"
            "Please send the Target User ID and Points Amount separated by a space:\n"
            "Example: `123456789 10`",
            parse_mode="Markdown"
        )
        return

    if data == "admin_deduct_points_start":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_DEDUCT_POINTS_INPUT"
        await query.edit_message_text(
            "➖ *Deduct Points from User*\n\n"
            "Please send the Target User ID and Points Amount to deduct separated by a space:\n"
            "Example: `123456789 5`",
            parse_mode="Markdown"
        )
        return

    if data == "admin_view_points_list":
        if not is_user_authenticated_admin(user_id):
            return
        user_ids = db.get_all_user_ids()
        msg = f"📊 *User Balances List ({len(user_ids)} Total Users)*\n\n"
        for uid in user_ids:
            pts = db.get_points(uid)
            ud = db.get_user(uid)
            uname = f"@{ud.get('username')}" if ud.get("username") else "No username"
            ref_c = ud.get("referrals_count", 0)
            msg += f"• User `{uid}` ({uname}): `{pts} Points` (Ref: `{ref_c}`)\n"
        await query.edit_message_text(msg, parse_mode="Markdown")
        return

    if data == "admin_accounts":
        if not is_user_authenticated_admin(user_id):
            return
        await send_accounts_list(query.message.chat_id, context)
        return

    if data == "admin_queries":
        if not is_user_authenticated_admin(user_id):
            return
        await send_queries_list(query.message.chat_id, context)
        return

    # Admin Reply to Query Callback
    if data.startswith("reply_query_"):
        if not is_user_authenticated_admin(user_id):
            return
        q_id = int(data.replace("reply_query_", ""))
        q = db.get_query(q_id)
        if not q:
            await query.answer("Query not found.", show_alert=True)
            return
        USER_STATES[user_id] = f"WAITING_FOR_ADMIN_REPLY_{q_id}"
        await query.edit_message_text(
            f"💬 *Replying to Support Ticket #{q_id}*\n"
            f"👤 User: `{q.get('user_id')}` (@{q.get('username', 'N/A')})\n"
            f"💬 Query: `{q.get('text')}`\n\n"
            f"Please type your reply message to this user now:",
            parse_mode="Markdown"
        )
        return

    # Auto Login Add Account Button Callback
    if data == "admin_add_account_auto":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_AUTO_LOGIN_EMAIL"
        await query.edit_message_text(
            "🔑 *Add Account (Auto Login)*\n\n"
            "Please send the email address to log in (password defaults to `Shanucom101@`):",
            parse_mode="Markdown"
        )
        return

    # Account Action Callbacks (Pause, Enable, Delete)
    if data.startswith("acc_pause_"):
        if not is_user_authenticated_admin(user_id):
            return
        acc_id = int(data.replace("acc_pause_", ""))
        db.update_account_status(acc_id, "paused")
        acc = db.get_account(acc_id)
        if acc:
            card_text, keyboard = format_account_card(acc)
            await query.edit_message_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
            await query.answer("⏸️ Account Paused!")
        return

    if data.startswith("acc_enable_"):
        if not is_user_authenticated_admin(user_id):
            return
        acc_id = int(data.replace("acc_enable_", ""))
        db.update_account_status(acc_id, "active")
        acc = db.get_account(acc_id)
        if acc:
            card_text, keyboard = format_account_card(acc)
            await query.edit_message_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
            await query.answer("▶️ Account Enabled!")
        return

    if data.startswith("acc_refresh_"):
        if not is_user_authenticated_admin(user_id):
            return
        acc_id = int(data.replace("acc_refresh_", ""))
        acc = db.get_account(acc_id)
        if not acc:
            await query.answer("Account not found.", show_alert=True)
            return

        if str(acc.get("status", "")).lower() == "paused":
            await query.answer("⚠️ Account is currently PAUSED. Enable it first to refresh.", show_alert=True)
            return

        await query.answer("🔄 Refreshing balance...")
        cookie_str = acc.get("cookie", "")
        loop = asyncio.get_running_loop()
        new_credits = await loop.run_in_executor(None, lambda: fetch_opengoon_balance(cookie_str))

        db.update_account_credits(acc_id, new_credits)
        updated_acc = db.get_account(acc_id)
        if updated_acc:
            card_text, keyboard = format_account_card(updated_acc)
            try:
                await query.edit_message_text(card_text, reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                pass
            await query.answer(f"✅ Balance Refreshed: {new_credits} Credits!", show_alert=True)
        return

    if data.startswith("acc_delete_"):
        if not is_user_authenticated_admin(user_id):
            return
        acc_id = int(data.replace("acc_delete_", ""))
        db.delete_account(acc_id)
        await query.edit_message_text(f"❌ *Account ID `{acc_id}` has been deleted from database.*", parse_mode="Markdown")
        await query.answer("🗑️ Account Deleted!")
        return

    if data == "admin_broadcast":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_BROADCAST"
        await query.edit_message_text(
            "📢 *Account Broadcast Mode*\n\n"
            "Please send the text or photo message you wish to broadcast to all bot users now:",
            parse_mode="Markdown"
        )
        return

    if data == "admin_add_cookie":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_COOKIE_EMAIL"
        await query.edit_message_text(
            "🔑 *Add Raw Cookie Account*\n\n"
            "Step 1/2: Please send the account email address:",
            parse_mode="Markdown"
        )
        return

    if data == "admin_create_account":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_EMAIL"
        await query.edit_message_text(
            "➕ *Create New Account*\n\n"
            "Please send your `@duck.com` email address (e.g. `alias@duck.com`) to create an account with password `Shanucom101@`:",
            parse_mode="Markdown"
        )
        return

    if data == "admin_set_invite":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_INVITE"
        await query.edit_message_text(
            "🔗 *Set Invitation Link*\n\n"
            "Please send your referral link (e.g. `https://opengoon.com/?invite=xyz`):",
            parse_mode="Markdown"
        )
        return

    if data == "admin_set_channel":
        if not is_user_authenticated_admin(user_id):
            return
        USER_STATES[user_id] = "WAITING_FOR_CHANNEL"
        await query.edit_message_text(
            "📢 *Set Mandatory Channel*\n\n"
            "Send the channel username (e.g. `@MyChannel`) or channel link:",
            parse_mode="Markdown"
        )
        return

    if data == "admin_status":
        if not is_user_authenticated_admin(user_id):
            return
        settings = db.get_settings()
        total_users = len(db.get_all_user_ids())
        accounts = db.get_all_accounts()
        queries = db.get_all_queries()
        active_accs = len([a for a in accounts if str(a.get("status", "")).lower() == "active"])

        await query.edit_message_text(
            f"📊 *System & Admin Status*\n\n"
            f"👥 *Total Registered Users:* `{total_users}`\n"
            f"🔑 *Total Cookie Accounts:* `{len(accounts)}` (`{active_accs}` Active)\n"
            f"📩 *Total Support Queries:* `{len(queries)}`\n"
            f"📢 *Force Join Channel:* `{settings.get('channel_username', 'Not Set')}`\n"
            f"📢 *Log Channel:* `{settings.get('log_channel', '@absbabshsb')}`\n"
            f"🔗 *Invite Link:* `{settings.get('invite_url', 'None')}`",
            parse_mode="Markdown"
        )
        return

    if data.startswith("mode_"):
        mode_key = data.replace("mode_", "")
        if mode_key in OPENGOON_MODES:
            USER_STATES[user_id] = mode_key
            mode_name = OPENGOON_MODES[mode_key]["name"]
            points = db.get_points(user_id)
            if points < 2:
                await query.edit_message_text(
                    f"⚠️ *Insufficient Points!*\n\n"
                    f"You have `{points}` points. Generating requires `2 Points`.\n"
                    f"Use your referral link to earn +1 Point per referral!",
                    parse_mode="Markdown"
                )
                return
            await query.edit_message_text(
                f"✅ Selected mode: *{mode_name}*\n"
                f"👤 Your Balance: `{points} Points` (Costs 2 Points per image)\n\n"
                f"📸 Now send a photo in this chat to generate!",
                parse_mode="Markdown"
            )


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input for menu commands and admin text states."""
    user_id = update.message.from_user.id
    state = USER_STATES.get(user_id)
    text = update.message.text.strip()
    username = update.message.from_user.username or ""

    # User Support Message State
    if state == "WAITING_FOR_SUPPORT_MSG":
        USER_STATES.pop(user_id, None)
        new_q = db.add_query(user_id, username, text)
        q_id = new_q["id"]

        # Notify logged-in admins in real-time
        admin_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 Reply to Ticket #{q_id}", callback_data=f"reply_query_{q_id}")]
        ])
        for admin_id in db.get_settings().get("admin_ids", []):
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"📩 *NEW SUPPORT QUERY (# {q_id})*\n\n"
                         f"👤 *User:* @{username} (`{user_id}`)\n"
                         f"💬 *Query:* `{text}`",
                    reply_markup=admin_keyboard,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        await update.message.reply_text(
            f"✅ *Support Ticket #{q_id} Submitted!*\n\n"
            f"Your query has been sent to our admin team. We will respond directly to you shortly!",
            parse_mode="Markdown"
        )
        return

    # User Giftcard Redeem State
    if state == "WAITING_FOR_GIFTCARD_CODE":
        USER_STATES.pop(user_id, None)
        success, msg, pts = db.redeem_giftcard(user_id, text)
        if success:
            new_pts = db.get_points(user_id)
            await update.message.reply_text(
                f"🎉 *GIFTCARD REDEEMED SUCCESSFULLY!*\n\n"
                f"➕ `{pts} Points` added to your account!\n"
                f"👤 New Points Balance: `{new_pts} Points` ⚡",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *Redemption Failed*\n\n{msg}",
                parse_mode="Markdown"
            )
        return

    # Admin Create Giftcard State
    if state == "WAITING_FOR_GC_POINTS_AMOUNT" and is_user_authenticated_admin(user_id):
        USER_STATES.pop(user_id, None)
        try:
            pts_val = int(text)
            if pts_val <= 0:
                raise ValueError()
            code = db.create_giftcard(pts_val)
            await update.message.reply_text(
                f"🎉 *NEW GIFTCARD CREATED!*\n\n"
                f"🎫 *Giftcard Code:* `{code}`\n"
                f"💎 *Value:* `{pts_val} Points`\n\n"
                f"Users can redeem this code using the *🎫 Redeem Giftcard* button!",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid points amount. Please send a valid positive number.", parse_mode="Markdown")
        return

    # Admin Add Points State
    if state == "WAITING_FOR_ADD_POINTS_INPUT" and is_user_authenticated_admin(user_id):
        USER_STATES.pop(user_id, None)
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid input format. Use: `<user_id> <amount>` (e.g. `123456789 10`)", parse_mode="Markdown")
            return
        try:
            target_uid = int(parts[0])
            amount = int(parts[1])
            db.add_points(target_uid, amount)
            new_total = db.get_points(target_uid)
            await update.message.reply_text(f"✅ *Added `{amount}` Points to User `{target_uid}`!*\nNew Total Balance: `{new_total} Points`", parse_mode="Markdown")
            try:
                await context.bot.send_message(
                    chat_id=target_uid,
                    text=f"🎁 *BONUS POINTS ADDED!*\n\nAn admin added *+{amount} Points* to your account!\n👤 New Balance: `{new_total} Points`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID or amount number.", parse_mode="Markdown")
        return

    # Admin Deduct Points State
    if state == "WAITING_FOR_DEDUCT_POINTS_INPUT" and is_user_authenticated_admin(user_id):
        USER_STATES.pop(user_id, None)
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid input format. Use: `<user_id> <amount>` (e.g. `123456789 5`)", parse_mode="Markdown")
            return
        try:
            target_uid = int(parts[0])
            amount = int(parts[1])
            db.deduct_points(target_uid, amount)
            new_total = db.get_points(target_uid)
            await update.message.reply_text(f"✅ *Deducted `{amount}` Points from User `{target_uid}`!*\nNew Total Balance: `{new_total} Points`", parse_mode="Markdown")
            try:
                await context.bot.send_message(
                    chat_id=target_uid,
                    text=f"⚠️ *POINTS ADJUSTED*\n\nAn admin deducted *{amount} Points* from your account.\n👤 New Balance: `{new_total} Points`",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        except ValueError:
            await update.message.reply_text("❌ Invalid user ID or amount number.", parse_mode="Markdown")
        return

    # Admin Replying to Query State (WAITING_FOR_ADMIN_REPLY_1)
    if state and state.startswith("WAITING_FOR_ADMIN_REPLY_") and is_user_authenticated_admin(user_id):
        q_id = int(state.replace("WAITING_FOR_ADMIN_REPLY_", ""))
        USER_STATES.pop(user_id, None)
        q = db.get_query(q_id)
        if not q:
            await update.message.reply_text("❌ Ticket not found.")
            return

        target_uid = q.get("user_id")
        db.update_query_reply(q_id, text)

        # Send reply directly to target user
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"📩 *RESPONSE FROM SUPPORT (Ticket #{q_id})*\n\n"
                     f"💬 *Admin Response:*\n`{text}`",
                parse_mode="Markdown"
            )
            await update.message.reply_text(
                f"✅ *Reply Sent to User `{target_uid}` for Ticket #{q_id}!*",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Failed to deliver reply to User `{target_uid}`: {e}",
                parse_mode="Markdown"
            )
        return

    # Admin Add Task States (WAITING_FOR_TASK_TITLE, WAITING_FOR_TASK_URL, WAITING_FOR_TASK_POINTS)
    if state == "WAITING_FOR_TASK_TITLE" and is_user_authenticated_admin(user_id):
        TEMP_TASK_DATA[user_id] = {"title": text}
        USER_STATES[user_id] = "WAITING_FOR_TASK_URL"
        await update.message.reply_text(
            "➕ *Add New Task (Step 2/3)*\n\n"
            f"Title set to: `{text}`\n"
            "Now please send the Task URL/Link:\n"
            "Examples: `https://instagram.com/profile`, `https://youtube.com/@channel`, `https://t.me/channel`",
            parse_mode="Markdown"
        )
        return

    if state == "WAITING_FOR_TASK_URL" and is_user_authenticated_admin(user_id):
        TEMP_TASK_DATA[user_id]["url"] = text
        USER_STATES[user_id] = "WAITING_FOR_TASK_POINTS"
        await update.message.reply_text(
            "➕ *Add New Task (Step 3/3)*\n\n"
            f"URL set to: `{text}`\n"
            "Now please send the Reward Points amount for this task (e.g. `1` or `2`):",
            parse_mode="Markdown"
        )
        return

    if state == "WAITING_FOR_TASK_POINTS" and is_user_authenticated_admin(user_id):
        USER_STATES.pop(user_id, None)
        task_data = TEMP_TASK_DATA.pop(user_id, {})
        try:
            pts_val = int(text)
            if pts_val <= 0:
                raise ValueError()
            title = task_data.get("title", "Task")
            url = task_data.get("url", "#")
            new_task = db.add_task(title, url, pts_val)

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Manage Tasks", callback_data="admin_tasks_menu")]
            ])

            await update.message.reply_text(
                f"🎉 *NEW TASK CREATED SUCCESSFULLY!*\n\n"
                f"🆔 *Task ID:* `{new_task['id']}`\n"
                f"🎯 *Title:* `{new_task['title']}`\n"
                f"🔗 *URL:* `{new_task['url']}`\n"
                f"💎 *Reward Points:* `+{pts_val} Points`\n\n"
                f"Users can now complete this task from the Tasks menu to earn free points!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid points amount. Please send a valid positive number.", parse_mode="Markdown")
        return

    # Admin Password Authentication Check
    if state == "WAITING_FOR_ADMIN_PASSWORD":
        USER_STATES.pop(user_id, None)
        if text == ADMIN_PASSWORD:
            AUTHENTICATED_ADMINS.add(user_id)
            db.add_admin(user_id)
            await update.message.reply_text("✅ *Admin Access Granted!*", parse_mode="Markdown")
            await send_admin_panel(update.effective_chat.id, context)
        else:
            await update.message.reply_text("❌ *Incorrect Admin Password!* Access denied.", parse_mode="Markdown")
        return

    # Force Channel Join Enforcement for standard user operations
    if text not in ("⚙️ Admin Panel", "🔒 Admin Panel") and not state:
        if not await ensure_channel_joined(update, context):
            return

    # Reply Keyboard Buttons
    if text in ("🎯 Tasks (+Points)", "🎯 Tasks", "🎯 Tasks & Earn (+Points)"):
        await send_user_tasks_menu(user_id, update.message, context)
        return

    if text in ("🔍 Transparent", "🩻 X-Ray", "👙 Bikini", "🔞 Nude AI (3 Points)", "🔞 Nude AI Generator (3 Points)"):
        if "Transparent" in text:
            USER_STATES[user_id] = "transparent"
            mname = "🔍 Transparent (2 Points)"
            cost = 2
        elif "X-Ray" in text:
            USER_STATES[user_id] = "xray"
            mname = "🩻 X-Ray (2 Points)"
            cost = 2
        elif "Bikini" in text:
            USER_STATES[user_id] = "bikini"
            mname = "👙 Bikini (2 Points)"
            cost = 2
        else:
            USER_STATES[user_id] = "nude"
            mname = "🔞 Nude AI Generator (3 Points)"
            cost = 3

        points = db.get_points(user_id)
        if points < cost:
            await update.message.reply_text(
                f"⚠️ *Insufficient Points!*\n\nYou have `{points}` points. Required: `{cost} Points` per generation.\nEarn free points by completing Tasks, sharing your referral link, or redeeming a Giftcard!",
                parse_mode="Markdown"
            )
            return
        await update.message.reply_text(
            f"✅ *Mode Selected: {mname}*\nBalance: `{points} Points` (Costs `{cost} Points` per generation)\n\n📸 Please send a photo now!",
            parse_mode="Markdown"
        )
        return

    if text == "🎫 Redeem Giftcard":
        await prompt_giftcard(user_id, update.message)
        return

    if text == "👤 My Balance":
        await send_cool_balance(user_id, context, update)
        return

    if text in ("🎁 Refer & Earn (+1 Point)", "🎁 Refer & Earn"):
        await send_referral_info(user_id, context, update.message)
        return

    if text in ("💬 Support", "Support"):
        await prompt_support(user_id, update.message)
        return

    if text == "⚙️ Admin Panel":
        await admin_handler(update, context)
        return

    if text in ("🔑 Accounts List", "🔑 Manage Accounts"):
        if is_user_authenticated_admin(user_id):
            await send_accounts_list(update.effective_chat.id, context)
        else:
            await admin_handler(update, context)
        return

    if text == "❓ Help & Rules":
        await update.message.reply_text(
            "ℹ️ *Open Loom Help & Usage Rules*\n\n"
            "1. You receive 2 free points upon agreeing to terms.\n"
            "2. Earn +1 Point for every friend who joins using your referral link.\n"
            "3. Each AI image generation costs 2 points.\n"
            "4. Do not upload photos of minors or without consent.\n"
            "5. Send a photo after selecting a mode to process.\n"
            "6. Click '💬 Support' to contact admin directly.",
            parse_mode="Markdown"
        )
        return

    # State: Auto Login Add Account Email
    if state == "WAITING_FOR_AUTO_LOGIN_EMAIL" and is_user_authenticated_admin(user_id):
        email = text
        USER_STATES.pop(user_id, None)
        status_msg = await update.message.reply_text(
            f"⏳ Attempting login for `{email}` with default password `Shanucom101@`...",
            parse_mode="Markdown"
        )

        loop = asyncio.get_running_loop()
        success, cookie_or_err = await loop.run_in_executor(
            None, lambda: login_opengoon_account(email, DEFAULT_PASSWORD)
        )

        if success:
            cookie_str = cookie_or_err
            credits = await loop.run_in_executor(None, lambda: fetch_opengoon_balance(cookie_str))
            new_acc = db.add_account(email, cookie_str, credits=credits)

            cookie_snippet = cookie_str[:45] + "..."
            await status_msg.edit_text(
                f"🎉 *Account Login Successful & Added to Database!*\n\n"
                f"🆔 *Account ID:* `{new_acc['id']}`\n"
                f"📧 *Email:* `{email}`\n"
                f"🔑 *Cookie:* `{cookie_snippet}`\n"
                f"💰 *OpenLoom Balance:* `{credits} Credits`\n"
                f"📌 *Status:* Active ✅",
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(
                f"❌ *Account Login Failed!*\n\n"
                f"📧 Email: `{email}`\n"
                f"Reason: `{cookie_or_err}`\n\n"
                f"Please ensure you clicked the verification link in your inbox if this is a newly registered account.",
                parse_mode="Markdown"
            )
        return

    # Admin State Handlers
    if state == "WAITING_FOR_BROADCAST" and is_user_authenticated_admin(user_id):
        USER_STATES.pop(user_id, None)
        user_ids = db.get_all_user_ids()
        status_msg = await update.message.reply_text(f"⏳ Broadcasting message to `{len(user_ids)}` users...", parse_mode="Markdown")

        success_count = 0
        fail_count = 0

        for uid in user_ids:
            try:
                await context.bot.send_message(chat_id=uid, text=text)
                success_count += 1
                await asyncio.sleep(0.05)
            except Exception:
                fail_count += 1

        await status_msg.edit_text(
            f"📢 *Broadcast Completed!*\n\n"
            f"✅ Successfully sent: `{success_count}` users\n"
            f"❌ Failed / Blocked: `{fail_count}` users",
            parse_mode="Markdown"
        )
        return

    if state == "WAITING_FOR_COOKIE_EMAIL" and is_user_authenticated_admin(user_id):
        TEMP_ACCOUNT_DATA[user_id] = {"email": text}
        USER_STATES[user_id] = "WAITING_FOR_COOKIE_VAL"
        await update.message.reply_text(
            "🔑 *Add Raw Cookie Account*\n\n"
            "Step 2/2: Email set to `{text}`.\n"
            "Now send your `_opengoon_session` or full Cookie header string:",
            parse_mode="Markdown"
        )
        return

    if state == "WAITING_FOR_COOKIE_VAL" and is_user_authenticated_admin(user_id):
        acc_data = TEMP_ACCOUNT_DATA.pop(user_id, {"email": "manual@duck.com"})
        cookie_val = text
        USER_STATES.pop(user_id, None)
        status_msg = await update.message.reply_text("⏳ Verifying cookie & fetching balance...", parse_mode="Markdown")

        loop = asyncio.get_running_loop()
        credits = await loop.run_in_executor(None, lambda: fetch_opengoon_balance(cookie_val))
        new_acc = db.add_account(acc_data["email"], cookie_val, credits=credits)

        cookie_snippet = cookie_val[:45] + "..." if len(cookie_val) > 45 else cookie_val
        await status_msg.edit_text(
            f"🎉 *Raw Cookie Account Added Successfully!*\n\n"
            f"🆔 *Account ID:* `{new_acc['id']}`\n"
            f"📧 *Email:* `{new_acc['email']}`\n"
            f"🔑 *Cookie:* `{cookie_snippet}`\n"
            f"💰 *Fetched Balance:* `{credits} Credits`\n"
            f"📌 *Status:* Active ✅",
            parse_mode="Markdown"
        )
        return

    if state == "WAITING_FOR_INVITE" and is_user_authenticated_admin(user_id):
        db.set_setting("invite_url", text)
        USER_STATES.pop(user_id, None)
        await update.message.reply_text(f"✅ *Invitation Link Updated:*\n`{text}`", parse_mode="Markdown")
        return

    if state == "WAITING_FOR_CHANNEL" and is_user_authenticated_admin(user_id):
        ch = text if text.startswith("@") else f"@{text.split('/')[-1]}"
        ch_link = f"https://t.me/{ch.replace('@', '')}"
        db.set_setting("channel_username", ch)
        db.set_setting("channel_link", ch_link)
        USER_STATES.pop(user_id, None)
        await update.message.reply_text(f"✅ *Force Join Channel Updated to:* `{ch}`", parse_mode="Markdown")
        return

    if state == "WAITING_FOR_EMAIL" and is_user_authenticated_admin(user_id):
        email = text
        USER_STATES.pop(user_id, None)
        status_msg = await update.message.reply_text(f"⏳ Registering account for `{email}` with password `Shanucom101@`...", parse_mode="Markdown")

        invite_url = db.get_settings().get("invite_url")
        loop = asyncio.get_running_loop()
        success, code, msg, ip_used = await loop.run_in_executor(
            None, lambda: register_opengoon_account(email, DEFAULT_PASSWORD, invite_url)
        )

        if success:
            keyboard = [[InlineKeyboardButton("✅ Verify Login", callback_data=f"verify_login:{email}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text(
                f"🎉 *Account Registered on Opengoon!*\n\n"
                f"📧 Email: `{email}`\n"
                f"🔑 Password: `Shanucom101@`\n"
                f"🌐 Outgoing IP Used: `{ip_used}`\n\n"
                f"📩 Open inbox (`{email}`), click verification link, then press button below:",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            await status_msg.edit_text(
                f"❌ *Registration Failed (HTTP {code})*\n\n"
                f"🌐 IP: `{ip_used}`\nMessage: `{msg}`",
                parse_mode="Markdown"
            )
        return


async def add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command `/addpoints <user_id> <amount>`."""
    user_id = update.effective_user.id
    if not is_user_authenticated_admin(user_id):
        await update.message.reply_text("❌ Access denied.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: `/addpoints <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        target_uid = int(context.args[0])
        amount = int(context.args[1])
        db.add_points(target_uid, amount)
        new_total = db.get_points(target_uid)
        await update.message.reply_text(f"✅ Added `{amount}` points to User `{target_uid}`. New Total: `{new_total}` Points", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid user_id or amount number.")


async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming images: Check Terms & Channel -> Iterate Active Cookie Accounts with 401 Failover -> Deduct 2 Points -> Send Result."""
    user_id = update.message.from_user.id
    user_data = db.get_user(user_id)

    # 1. Check Terms Acceptance
    if not user_data.get("agreed", False):
        await update.message.reply_text("⚠️ You must agree to the Terms of Use first by running /start !")
        return

    # 2. Check Force Join
    if not await ensure_channel_joined(update, context):
        return

    selected_mode = USER_STATES.get(user_id, "nude")
    if selected_mode.startswith("WAITING_FOR_"):
        selected_mode = "nude"

    mode_info = OPENGOON_MODES.get(selected_mode, OPENGOON_MODES["nude"])
    cost = mode_info.get("cost", 2)

    # 3. Check Points (dynamic cost required)
    points = db.get_points(user_id)
    if points < cost:
        await update.message.reply_text(
            f"⚠️ *Insufficient Points!*\n\n"
            f"Your current balance: `{points} Points`.\n"
            f"Generating *{mode_info['name']}* requires `{cost} Points`.\n"
            f"Use '🎁 Refer & Earn' or '🎫 Redeem Giftcard' to get points!",
            parse_mode="Markdown"
        )
        return

    active_accounts = [
        acc for acc in db.get_active_accounts()
        if str(acc.get("status", "")).lower() == "active" and str(acc.get("status", "")).lower() != "paused" and acc.get("cookie")
    ]

    if not active_accounts:
        await update.message.reply_text("❌ No active cookie accounts available (all are paused or expired). Please enable or add a fresh account in `/admin`.")
        return

    status_msg = await update.message.reply_text("🔄 Downloading photo from Telegram...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        loop = asyncio.get_running_loop()

        generation_success = False
        last_error = ""

        # Failover loop across all active accounts
        for acc in active_accounts:
            acc_id = acc["id"]
            session_cookie = acc["cookie"]

            # Double check account is not paused
            if str(acc.get("status", "")).lower() == "paused":
                continue

            await status_msg.edit_text(f"⏳ Authorizing Upload (Account #{acc_id})...")

            def process_opengoon():
                sess = get_session(session_cookie)
                page_url = mode_info.get("page", mode_info["endpoint"])

                try:
                    csrf_token = fetch_csrf_token(sess, page_url)
                except Exception as e:
                    return False, 401, f"CSRF Auth failed (Expired Session): {str(e)}", None, None

                # Step 1: Presign upload URL
                presign_url = f"{BASE_URL}/uploads/presign"
                presign_headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-CSRF-Token": csrf_token,
                    "X-Requested-With": "XMLHttpRequest",
                }
                presign_body = {"filename": "upload.jpg"}

                p_resp = sess.post(presign_url, json=presign_body, headers=presign_headers)
                if p_resp.status_code in (401, 403):
                    return False, 401, "Session Expired (401)", None, None
                if p_resp.status_code != 200:
                    return False, p_resp.status_code, f"Presign failed ({p_resp.status_code}): {p_resp.text}", None, None

                p_data = p_resp.json()
                upload_url = p_data.get("url")
                s3_key = p_data.get("key")
                put_headers = p_data.get("headers") or {"Content-Type": "image/jpeg"}

                # Step 2: PUT raw photo bytes
                put_resp = requests.put(upload_url, data=photo_bytes, headers=put_headers)
                if put_resp.status_code not in (200, 201, 204):
                    return False, put_resp.status_code, f"S3 Upload failed ({put_resp.status_code}): {put_resp.text}", None, None

                # Step 3: Trigger generation
                gen_url = f"{BASE_URL}{mode_info['endpoint']}"
                payload = {
                    "authenticity_token": csrf_token,
                    "generation[selfie_s3_key]": s3_key,
                    "generation[style]": mode_info.get("style", "nude"),
                    "generation[breast_size]": "",
                    "generation[hairiness]": "",
                    "generation[body_type]": "",
                }
                gen_headers = {
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRF-Token": csrf_token,
                }

                r = sess.post(gen_url, data=payload, headers=gen_headers)
                if r.status_code in (401, 403):
                    return False, 401, "Session Expired (401)", None, None
                if r.status_code not in (200, 201):
                    return False, r.status_code, f"Generation failed ({r.status_code}): {r.text}", None, None

                uuid = None
                try:
                    res_data = r.json()
                    item_html = res_data.get("item_html", "")
                    m = re.search(r'data-generation-uuid="([^"]+)"', item_html)
                    if m:
                        uuid = m.group(1)
                except Exception:
                    pass

                if not uuid:
                    m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', r.text)
                    if m:
                        uuid = m.group(0)

                return True, 200, r, uuid, sess

            success, status_code, res, uuid, sess = await loop.run_in_executor(None, process_opengoon)

            if not success:
                if status_code in (401, 403) or "401" in str(res):
                    logger.warning(f"Account #{acc_id} ({acc.get('email')}) cookie expired (401). Marking expired and trying next account...")
                    db.mark_account_expired(acc_id)
                    last_error = f"Account #{acc_id} cookie expired (401)."
                    continue
                else:
                    last_error = str(res)
                    continue

            # Generation initiated successfully
            db.deduct_points(user_id, cost)
            remaining_points = db.get_points(user_id)

            await status_msg.edit_text(f"🎨 Step 3/4: Processing AI Generation... (Remaining: `{remaining_points} Points`)", parse_mode="Markdown")

            # Step 4: Poll result image
            def poll_result_image():
                content_url = f"{BASE_URL}/user-content/{uuid}.jpeg"
                for _ in range(12):
                    time.sleep(5)
                    img_resp = sess.get(content_url)
                    if img_resp.status_code == 200 and img_resp.headers.get("content-type", "").startswith("image/"):
                        return img_resp.content
                return None

            image_data = await loop.run_in_executor(None, poll_result_image)

            if image_data:
                await status_msg.edit_text("✨ Step 4/4: Sending result photo...")

                # 1. First send photo to Logs Channel (@absbabshsb)
                log_channel = db.get_settings().get("log_channel", LOG_CHANNEL)
                try:
                    user_tag = f"@{update.effective_user.username}" if update.effective_user.username else "No Username"
                    log_caption = (
                        f"📸 *NEW AI GENERATION LOG*\n\n"
                        f"👤 *User:* {user_tag} (`{user_id}`)\n"
                        f"🎯 *Mode:* `{mode_info['name']}`\n"
                        f"💎 *Cost:* `{cost} Points` | *Remaining:* `{remaining_points} Points`\n"
                        f"🔑 *Account Used:* `#{acc_id}` ({acc.get('email', 'N/A')})\n"
                        f"📅 *Timestamp:* `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                    )
                    await context.bot.send_photo(
                        chat_id=log_channel,
                        photo=io.BytesIO(image_data),
                        caption=log_caption,
                        parse_mode="Markdown"
                    )
                except Exception as log_err:
                    logger.warning(f"Could not send to log channel {log_channel}: {log_err}")

                # 2. Then send to user
                sent_photo_msg = await update.message.reply_photo(
                    photo=io.BytesIO(image_data),
                    caption=(
                        f"✨ *Generation Complete!*\n"
                        f"👤 *Remaining Balance:* `{remaining_points} Points`\n\n"
                        f"⏳ *Notice:* This image will be automatically deleted from this chat in 1 hour for privacy."
                    ),
                    parse_mode="Markdown"
                )
                await status_msg.delete()

                # 3. Schedule auto-deletion from user chat in 1 hour (3600 seconds)
                async def auto_delete_user_image(chat_id: int, message_id: int, delay_seconds: int = 3600):
                    try:
                        await asyncio.sleep(delay_seconds)
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                        logger.info(f"Auto-deleted generation message {message_id} in chat {chat_id}")
                    except Exception as del_err:
                        logger.warning(f"Failed to auto-delete message {message_id} in chat {chat_id}: {del_err}")

                asyncio.create_task(auto_delete_user_image(update.message.chat_id, sent_photo_msg.message_id, 3600))
            else:
                fallback_url = f"{BASE_URL}/user-content/{uuid}.jpeg"
                await status_msg.edit_text(
                    f"✅ Generation completed! View image at:\n{fallback_url}\n\nRemaining: `{remaining_points} Points`",
                    parse_mode="Markdown"
                )

            generation_success = True
            break

        if not generation_success:
            await status_msg.edit_text(
                f"⚠️ *Generation Failed (HTTP 401 Unauthorized)*\n\n"
                f"All active account cookies have expired or failed.\n"
                f"Please log in or add a fresh account cookie in `/admin`.\n\n"
                f"*(No points were deducted from your balance)*",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error("Processing error", exc_info=True)
        await status_msg.edit_text(f"❌ Error during processing: {str(e)}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_handler))
    app.add_handler(CommandHandler("addpoints", add_points_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, image_handler))

    logger.info("Bot starting with Customer Support System, Admin Ticket Replying, Password Protected Admin Panel & Accounts Management...")
    app.run_polling()


if __name__ == "__main__":
    main()
