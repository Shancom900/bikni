import json
import os
import random
import string
from typing import Dict, Any, List, Optional
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(__file__), "database.json")

DEFAULT_DATA = {
    "users": {},
    "accounts": [],
    "queries": [],
    "giftcards": {},
    "tasks": [
        {
            "id": 1,
            "title": "📸 Follow on Instagram",
            "url": "https://instagram.com",
            "points": 1
        },
        {
            "id": 2,
            "title": "📢 Join Telegram Channel",
            "url": "https://t.me/WorldLinkers",
            "points": 1
        },
        {
            "id": 3,
            "title": "▶️ Subscribe YouTube Channel",
            "url": "https://youtube.com",
            "points": 1
        }
    ],
    "settings": {
        "admin_ids": [7525682158],
        "channel_username": "@WorldLinkers",
        "channel_link": "https://t.me/WorldLinkers",
        "log_channel": "@absbabshsb",
        "terms_image_url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80",
        "invite_url": "https://opengoon.com/?invite=ovbtvifn"
    }
}

class Database:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(DATA_FILE):
            self._save_raw(DEFAULT_DATA)
            return DEFAULT_DATA
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if "accounts" not in d:
                    d["accounts"] = DEFAULT_DATA["accounts"]
                if "queries" not in d:
                    d["queries"] = []
                if "giftcards" not in d:
                    d["giftcards"] = {}
                if "tasks" not in d:
                    d["tasks"] = DEFAULT_DATA["tasks"]
                return d
        except Exception:
            return DEFAULT_DATA

    def _save(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def _save_raw(self, data: Dict[str, Any]):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    # --- Gift Cards Management ---
    def create_giftcard(self, points: int) -> str:
        """Generates a unique giftcard code worth N points."""
        code = "LOOM-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        giftcards = self.data.get("giftcards", {})
        giftcards[code] = {
            "points": points,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "used": False,
            "used_by": None
        }
        self.data["giftcards"] = giftcards
        self._save()
        return code

    def redeem_giftcard(self, user_id: int, code: str) -> tuple[bool, str, int]:
        """Redeems a giftcard code for a user."""
        code = code.strip().upper()
        giftcards = self.data.get("giftcards", {})
        if code not in giftcards:
            return False, "Invalid Gift Card Code!", 0
        gc = giftcards[code]
        if gc.get("used"):
            return False, "This Gift Card has already been redeemed!", 0
        points = gc.get("points", 0)
        gc["used"] = True
        gc["used_by"] = user_id
        self.data["giftcards"] = giftcards
        self.add_points(user_id, points)
        self._save()
        return True, f"Successfully redeemed `{points} Points`!", points

    # --- Support Queries Management ---
    def add_query(self, user_id: int, username: str, text: str) -> Dict[str, Any]:
        queries = self.data.get("queries", [])
        next_id = max([q.get("id", 0) for q in queries], default=0) + 1
        new_q = {
            "id": next_id,
            "user_id": user_id,
            "username": username or "",
            "text": text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending",
            "reply": None
        }
        queries.append(new_q)
        self.data["queries"] = queries
        self._save()
        return new_q

    def get_all_queries(self) -> List[Dict[str, Any]]:
        return self.data.get("queries", [])

    def get_query(self, query_id: int) -> Optional[Dict[str, Any]]:
        for q in self.get_all_queries():
            if q.get("id") == query_id:
                return q
        return None

    def update_query_reply(self, query_id: int, reply_text: str) -> bool:
        queries = self.get_all_queries()
        for q in queries:
            if q.get("id") == query_id:
                q["status"] = "replied"
                q["reply"] = reply_text
                self.data["queries"] = queries
                self._save()
                return True
        return False

    # --- Account Cookie Management ---
    def get_all_accounts(self) -> List[Dict[str, Any]]:
        return self.data.get("accounts", [])

    def get_active_accounts(self) -> List[Dict[str, Any]]:
        return [
            acc for acc in self.get_all_accounts()
            if str(acc.get("status", "")).lower() == "active" and str(acc.get("status", "")).lower() != "paused" and acc.get("cookie")
        ]

    def mark_account_expired(self, acc_id: int):
        accounts = self.get_all_accounts()
        for acc in accounts:
            if acc.get("id") == acc_id:
                acc["status"] = "expired (401)"
                self.data["accounts"] = accounts
                self._save()
                break

    def add_account(self, email: str, cookie: str, credits: int = 5) -> Dict[str, Any]:
        accounts = self.get_all_accounts()
        next_id = max([a.get("id", 0) for a in accounts], default=0) + 1
        new_acc = {
            "id": next_id,
            "email": email,
            "cookie": cookie,
            "status": "active",
            "credits": credits
        }
        accounts.append(new_acc)
        self.data["accounts"] = accounts
        self._save()
        return new_acc

    def get_account(self, acc_id: int) -> Optional[Dict[str, Any]]:
        for acc in self.get_all_accounts():
            if acc.get("id") == acc_id:
                return acc
        return None

    def update_account_status(self, acc_id: int, status: str) -> bool:
        accounts = self.get_all_accounts()
        for acc in accounts:
            if acc.get("id") == acc_id:
                acc["status"] = status
                self.data["accounts"] = accounts
                self._save()
                return True
        return False

    def update_account_credits(self, acc_id: int, credits: int) -> bool:
        accounts = self.get_all_accounts()
        for acc in accounts:
            if acc.get("id") == acc_id:
                acc["credits"] = credits
                self.data["accounts"] = accounts
                self._save()
                return True
        return False

    def delete_account(self, acc_id: int) -> bool:
        accounts = self.get_all_accounts()
        new_accounts = [acc for acc in accounts if acc.get("id") != acc_id]
        if len(new_accounts) != len(accounts):
            self.data["accounts"] = new_accounts
            self._save()
            return True
        return False

    def get_active_cookie(self) -> Optional[str]:
        active_accs = self.get_active_accounts()
        if active_accs:
            return active_accs[0]["cookie"]
        return None

    # --- User Management ---
    def get_user(self, user_id: int) -> Dict[str, Any]:
        uid = str(user_id)
        if uid not in self.data["users"]:
            self.data["users"][uid] = {
                "agreed": False,
                "points": 2,
                "username": "",
                "referred_by": None,
                "referral_rewarded": False,
                "referrals_count": 0,
                "completed_tasks": []
            }
            self._save()
        else:
            user = self.data["users"][uid]
            if "completed_tasks" not in user:
                user["completed_tasks"] = []
                self._save()
        return self.data["users"][uid]

    def set_user_agreed(self, user_id: int, agreed: bool = True):
        uid = str(user_id)
        user = self.get_user(user_id)
        user["agreed"] = agreed
        self.data["users"][uid] = user
        self._save()

    def set_referrer(self, user_id: int, referrer_id: int):
        uid = str(user_id)
        ref_id = str(referrer_id)
        if uid == ref_id:
            return
        user = self.get_user(user_id)
        if not user.get("referred_by") and ref_id in self.data["users"]:
            user["referred_by"] = ref_id
            self.data["users"][uid] = user
            self._save()

    def reward_referrer(self, user_id: int) -> Optional[int]:
        uid = str(user_id)
        user = self.get_user(user_id)
        referrer_id_str = user.get("referred_by")
        if referrer_id_str and not user.get("referral_rewarded"):
            if referrer_id_str in self.data["users"]:
                referrer = self.data["users"][referrer_id_str]
                referrer["points"] = referrer.get("points", 0) + 1
                referrer["referrals_count"] = referrer.get("referrals_count", 0) + 1
                self.data["users"][referrer_id_str] = referrer

                user["referral_rewarded"] = True
                self.data["users"][uid] = user
                self._save()
                return int(referrer_id_str)
        return None

    def update_username(self, user_id: int, username: str):
        uid = str(user_id)
        user = self.get_user(user_id)
        user["username"] = username or ""
        self.data["users"][uid] = user
        self._save()

    def get_points(self, user_id: int) -> int:
        user = self.get_user(user_id)
        return user.get("points", 2)

    def deduct_points(self, user_id: int, amount: int = 2) -> bool:
        user = self.get_user(user_id)
        current = user.get("points", 0)
        if current >= amount:
            user["points"] = current - amount
            self.data["users"][str(user_id)] = user
            self._save()
            return True
        return False

    def add_points(self, user_id: int, amount: int):
        user = self.get_user(user_id)
        user["points"] = user.get("points", 0) + amount
        self.data["users"][str(user_id)] = user
        self._save()

    def get_all_user_ids(self):
        return [int(uid) for uid in self.data["users"].keys()]

    # --- Task Management ---
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        return self.data.get("tasks", [])

    def get_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        for task in self.get_all_tasks():
            if task.get("id") == task_id:
                return task
        return None

    def add_task(self, title: str, url: str, points: int) -> Dict[str, Any]:
        tasks = self.get_all_tasks()
        next_id = max([t.get("id", 0) for t in tasks], default=0) + 1
        new_task = {
            "id": next_id,
            "title": title,
            "url": url,
            "points": points
        }
        tasks.append(new_task)
        self.data["tasks"] = tasks
        self._save()
        return new_task

    def delete_task(self, task_id: int) -> bool:
        tasks = self.get_all_tasks()
        new_tasks = [t for t in tasks if t.get("id") != task_id]
        if len(new_tasks) != len(tasks):
            self.data["tasks"] = new_tasks
            self._save()
            return True
        return False

    def is_task_completed(self, user_id: int, task_id: int) -> bool:
        user = self.get_user(user_id)
        completed = user.get("completed_tasks", [])
        return task_id in completed

    def complete_task(self, user_id: int, task_id: int) -> tuple[bool, str, int]:
        task = self.get_task(task_id)
        if not task:
            return False, "Task not found!", 0
        user = self.get_user(user_id)
        completed = user.get("completed_tasks", [])
        if task_id in completed:
            return False, "You have already completed this task!", 0
        
        pts = task.get("points", 1)
        completed.append(task_id)
        user["completed_tasks"] = completed
        user["points"] = user.get("points", 0) + pts
        self.data["users"][str(user_id)] = user
        self._save()
        return True, f"Task completed successfully! +{pts} Points added.", pts

    def get_settings(self) -> Dict[str, Any]:
        return self.data.get("settings", DEFAULT_DATA["settings"])

    def set_setting(self, key: str, value: Any):
        if "settings" not in self.data:
            self.data["settings"] = DEFAULT_DATA["settings"]
        self.data["settings"][key] = value
        self._save()

    def is_admin(self, user_id: int) -> bool:
        admins = self.data.get("settings", {}).get("admin_ids", [])
        return user_id in admins or len(admins) == 0

    def add_admin(self, user_id: int):
        admins = self.data.get("settings", {}).get("admin_ids", [])
        if user_id not in admins:
            admins.append(user_id)
            self.set_setting("admin_ids", admins)

db = Database()
