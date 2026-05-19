"""
╔══════════════════════════════════════════════════════╗
║           🎬 KINO BOT v4.2 — WORKING               ║
║     Start ishlaydi | User saqlanadi                ║
╚══════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime
from functools import wraps
from typing import List, Tuple, Optional

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter
)
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import (
    InlineKeyboardBuilder,
    ReplyKeyboardBuilder
)

# ============================================================
# ⚙️ CONFIG
# ============================================================

TOKEN = "8442828078:AAEhrUziWIXgjrBmoDAic1nHUXyOYC4umsQ"
SUPER_ADMINS = [5996676608]
DB_NAME = "kino_bot.db"
BROADCAST_DELAY = 0.05
BROADCAST_CHUNK = 25

# ============================================================
# 📋 LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("KinoBot")

# ============================================================
# 🤖 BOT INITIALIZATION
# ============================================================

bot = Bot(
    token=TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# ============================================================
# 🔄 STATES
# ============================================================

class AdminStates(StatesGroup):
    movie_name = State()
    movie_code = State()
    movie_video = State()
    movie_desc = State()
    movie_genre = State()
    movie_year = State()
    movie_quality = State()
    movie_language = State()
    edit_code = State()
    edit_field = State()
    edit_value = State()
    delete_code = State()
    add_channel = State()
    add_private_channel = State()
    del_channel = State()
    broadcast = State()
    reply_feedback = State()
    dm_user_id = State()
    dm_message = State()
    ban_input = State()
    set_welcome = State()

class UserStates(StatesGroup):
    feedback = State()

# ============================================================
# 🚦 RATE LIMITER
# ============================================================

_rate_store: dict = defaultdict(list)

def rate_limit(max_per_sec: int = 3, window: int = 5):
    def decorator(func):
        @wraps(func)
        async def wrapper(event, *args, **kwargs):
            uid = event.from_user.id if hasattr(event, 'from_user') else 0
            now = time.time()
            _rate_store[uid] = [t for t in _rate_store[uid] if now - t < window]
            if len(_rate_store[uid]) >= max_per_sec:
                if isinstance(event, Message):
                    await event.answer("⏳ Iltimos, biroz kuting...")
                return
            _rate_store[uid].append(now)
            return await func(event, *args, **kwargs)
        return wrapper
    return decorator

# ============================================================
# 🗄️ DATABASE
# ============================================================

class Database:

    @staticmethod
    async def init():
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")

            await db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned INTEGER DEFAULT 0,
                    ban_reason TEXT,
                    total_searches INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL COLLATE NOCASE,
                    name TEXT NOT NULL,
                    description TEXT,
                    genre TEXT,
                    year INTEGER,
                    quality TEXT DEFAULT 'HD',
                    language TEXT DEFAULT 'Uzbek',
                    file_id TEXT NOT NULL,
                    thumbnail_id TEXT,
                    views INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0.0,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    title TEXT,
                    chat_id INTEGER,
                    invite_link TEXT,
                    is_private INTEGER DEFAULT 0,
                    is_required INTEGER DEFAULT 1,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS feedbacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    message TEXT NOT NULL,
                    reply TEXT,
                    is_read INTEGER DEFAULT 0,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    new_users INTEGER DEFAULT 0,
                    searches INTEGER DEFAULT 0,
                    found INTEGER DEFAULT 0,
                    not_found INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS broadcast_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    sent INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                INSERT OR IGNORE INTO settings(key,value) VALUES
                    ('maintenance','0'),
                    ('welcome_text','🎬 <b>KinoBot</b>ga xush kelibsiz!\n\nKino kodini yuboring yoki menyudan foydalaning.');
            """)
            await db.commit()
        logger.info("✅ Database initialized successfully")

    # ── USERS ────────────────────────────────────────────

    @staticmethod
    async def add_user(user_id: int, username: str = None, full_name: str = None) -> bool:
        """Returns True if new user, False if existing"""
        async with aiosqlite.connect(DB_NAME) as db:
            existing = await (await db.execute(
                "SELECT id FROM users WHERE id=?", (user_id,)
            )).fetchone()

            if existing:
                await db.execute(
                    "UPDATE users SET username=?, full_name=?, last_active=CURRENT_TIMESTAMP WHERE id=?",
                    (username, full_name, user_id)
                )
                await db.commit()
                return False
            else:
                await db.execute(
                    "INSERT INTO users(id, username, full_name) VALUES(?,?,?)",
                    (user_id, username, full_name)
                )
                await db.commit()
                await Database.stat_increment("new_users")
                return True

    @staticmethod
    async def get_user(user_id: int) -> Optional[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            row = await (await db.execute(
                "SELECT id, username, full_name, joined, is_banned, ban_reason, total_searches FROM users WHERE id=?",
                (user_id,)
            )).fetchone()
        if row:
            return {
                "id": row[0], "username": row[1], "full_name": row[2],
                "joined": row[3], "is_banned": row[4],
                "ban_reason": row[5], "total_searches": row[6]
            }
        return None

    @staticmethod
    async def get_all_users() -> List[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                "SELECT id, username, full_name, joined, is_banned, total_searches FROM users ORDER BY joined DESC"
            )).fetchall()
        return [
            {"id": r[0], "username": r[1], "full_name": r[2],
             "joined": r[3], "is_banned": r[4], "total_searches": r[5]}
            for r in rows
        ]

    @staticmethod
    async def ban_user(user_id: int, reason: str = None, ban: bool = True):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE users SET is_banned=?, ban_reason=? WHERE id=?",
                (1 if ban else 0, reason, user_id)
            )
            await db.commit()

    @staticmethod
    async def all_user_ids() -> List[int]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                "SELECT id FROM users WHERE is_banned=0"
            )).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    async def user_count() -> int:
        async with aiosqlite.connect(DB_NAME) as db:
            row = await (await db.execute("SELECT COUNT(*) FROM users")).fetchone()
        return row[0] if row else 0

    # ── MOVIES ───────────────────────────────────────────

    @staticmethod
    async def add_movie(code: str, name: str, file_id: str, **kwargs):
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute(
                    """INSERT INTO movies(code, name, description, genre, year, quality, language, file_id, thumbnail_id)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        code.upper(), name,
                        kwargs.get("description"),
                        kwargs.get("genre"),
                        kwargs.get("year"),
                        kwargs.get("quality", "HD"),
                        kwargs.get("language", "Uzbek"),
                        file_id,
                        kwargs.get("thumbnail_id")
                    )
                )
                await db.commit()
            return True, "ok"
        except aiosqlite.IntegrityError:
            return False, "Bu kod allaqachon mavjud!"
        except Exception as e:
            return False, str(e)

    @staticmethod
    async def get_movie(code: str) -> Optional[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            row = await (await db.execute(
                """SELECT code, name, description, genre, year, quality, language,
                   file_id, thumbnail_id, views, rating
                FROM movies WHERE code=? AND is_active=1""",
                (code.upper(),)
            )).fetchone()

            if row:
                await db.execute(
                    "UPDATE movies SET views=views+1 WHERE code=?",
                    (code.upper(),)
                )
                await db.commit()
                return {
                    "code": row[0], "name": row[1], "description": row[2],
                    "genre": row[3], "year": row[4], "quality": row[5],
                    "language": row[6], "file_id": row[7], "thumbnail_id": row[8],
                    "views": row[9] + 1, "rating": row[10]
                }
        return None

    @staticmethod
    async def search_movies(query: str, limit: int = 10) -> List[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                """SELECT code, name, genre, year, quality, views, rating
                FROM movies WHERE is_active=1 AND (LOWER(name) LIKE ? OR code LIKE ?)
                ORDER BY views DESC LIMIT ?""",
                (f"%{query.lower()}%", f"%{query.upper()}%", limit)
            )).fetchall()
        return [
            {"code": r[0], "name": r[1], "genre": r[2], "year": r[3],
             "quality": r[4], "views": r[5], "rating": r[6]} for r in rows
        ]

    @staticmethod
    async def all_movies() -> List[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                "SELECT code, name, genre, year, quality, views, rating FROM movies WHERE is_active=1 ORDER BY id DESC"
            )).fetchall()
        return [
            {"code": r[0], "name": r[1], "genre": r[2], "year": r[3],
             "quality": r[4], "views": r[5], "rating": r[6]} for r in rows
        ]

    @staticmethod
    async def top_movies(limit: int = 10) -> List[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                "SELECT code, name, genre, year, quality, views, rating FROM movies WHERE is_active=1 ORDER BY views DESC LIMIT ?",
                (limit,)
            )).fetchall()
        return [
            {"code": r[0], "name": r[1], "genre": r[2], "year": r[3],
             "quality": r[4], "views": r[5], "rating": r[6]} for r in rows
        ]

    @staticmethod
    async def update_movie(code: str, field: str, value) -> bool:
        allowed = {"name", "description", "genre", "year", "quality", "language"}
        if field not in allowed:
            return False
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                f"UPDATE movies SET {field}=?, updated=CURRENT_TIMESTAMP WHERE code=?",
                (value, code.upper())
            )
            await db.commit()
        return True

    @staticmethod
    async def delete_movie(code: str) -> bool:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE movies SET is_active=0 WHERE code=?",
                (code.upper(),)
            )
            await db.commit()
        return True

    @staticmethod
    async def movie_count() -> int:
        async with aiosqlite.connect(DB_NAME) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM movies WHERE is_active=1"
            )).fetchone()
        return row[0] if row else 0

    # ── CHANNELS ─────────────────────────────────────────

    @staticmethod
    async def add_channel(username: str, title: str = None,
                          chat_id: int = None, invite_link: str = None,
                          is_private: bool = False):
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute(
                    "INSERT INTO channels(username, title, chat_id, invite_link, is_private) VALUES(?,?,?,?,?)",
                    (username, title, chat_id, invite_link, 1 if is_private else 0)
                )
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    @staticmethod
    async def delete_channel(username: str) -> bool:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("DELETE FROM channels WHERE username=?", (username,))
            await db.commit()
        return True

    @staticmethod
    async def get_channels() -> List[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                "SELECT username, title, chat_id, invite_link, is_private, is_required FROM channels"
            )).fetchall()
        return [
            {"username": r[0], "title": r[1], "chat_id": r[2],
             "invite_link": r[3], "is_private": r[4], "is_required": r[5]}
            for r in rows
        ]

    @staticmethod
    async def get_required_channels() -> List[dict]:
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(
                "SELECT username, title, chat_id, invite_link, is_private FROM channels WHERE is_required=1"
            )).fetchall()
        return [
            {"username": r[0], "title": r[1], "chat_id": r[2],
             "invite_link": r[3], "is_private": r[4]}
            for r in rows
        ]

    # ── FEEDBACKS ────────────────────────────────────────

    @staticmethod
    async def add_feedback(user_id: int, username: str, full_name: str, message: str):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO feedbacks(user_id, username, full_name, message) VALUES(?,?,?,?)",
                (user_id, username, full_name, message)
            )
            await db.commit()

    @staticmethod
    async def get_feedbacks(limit: int = 10, unread_only: bool = True) -> List[dict]:
        query = "SELECT id, user_id, username, full_name, message, reply, created FROM feedbacks"
        if unread_only:
            query += " WHERE is_read=0"
        query += " ORDER BY created DESC LIMIT ?"
        async with aiosqlite.connect(DB_NAME) as db:
            rows = await (await db.execute(query, (limit,))).fetchall()
        return [
            {"id": r[0], "user_id": r[1], "username": r[2], "full_name": r[3],
             "message": r[4], "reply": r[5], "created": r[6]} for r in rows
        ]

    @staticmethod
    async def reply_to_feedback(feedback_id: int, reply_text: str):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE feedbacks SET reply=?, is_read=1 WHERE id=?",
                (reply_text, feedback_id)
            )
            await db.commit()

    # ── STATISTICS ───────────────────────────────────────

    @staticmethod
    async def stat_increment(column: str):
        today = datetime.now().strftime("%Y-%m-%d")
        columns = ["new_users", "searches", "found", "not_found"]
        if column not in columns:
            return
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                f"INSERT INTO daily_stats(date, {column}) VALUES(?,1) "
                f"ON CONFLICT(date) DO UPDATE SET {column}={column}+1",
                (today,)
            )
            await db.commit()

    @staticmethod
    async def get_stats() -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_NAME) as db:
            td = await (await db.execute(
                "SELECT new_users, searches, found, not_found FROM daily_stats WHERE date=?",
                (today,)
            )).fetchone()

            total_users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
            total_movies = (await (await db.execute("SELECT COUNT(*) FROM movies WHERE is_active=1")).fetchone())[0]
            total_views = (await (await db.execute("SELECT COALESCE(SUM(views),0) FROM movies")).fetchone())[0]
            total_channels = (await (await db.execute("SELECT COUNT(*) FROM channels")).fetchone())[0]
            banned = (await (await db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")).fetchone())[0]
            unread_fb = (await (await db.execute("SELECT COUNT(*) FROM feedbacks WHERE is_read=0")).fetchone())[0]

        return {
            "td_new": td[0] if td else 0, "td_search": td[1] if td else 0,
            "td_found": td[2] if td else 0, "td_nf": td[3] if td else 0,
            "total_users": total_users, "total_movies": total_movies,
            "total_views": total_views, "total_channels": total_channels,
            "banned": banned, "unread_fb": unread_fb
        }

    # ── SETTINGS ─────────────────────────────────────────

    @staticmethod
    async def get_setting(key: str, default: str = "") -> str:
        async with aiosqlite.connect(DB_NAME) as db:
            row = await (await db.execute(
                "SELECT value FROM settings WHERE key=?", (key,)
            )).fetchone()
        return row[0] if row else default

    @staticmethod
    async def set_setting(key: str, value: str):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)",
                (key, value)
            )
            await db.commit()

    @staticmethod
    async def log_broadcast(admin_id: int, sent: int, failed: int, total: int):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO broadcast_log(admin_id, sent, failed, total) VALUES(?,?,?,?)",
                (admin_id, sent, failed, total)
            )
            await db.commit()

# ============================================================
# 🔐 HELPERS
# ============================================================

def is_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMINS

async def check_subscription(user_id: int) -> Tuple[bool, List[dict]]:
    channels = await Database.get_required_channels()
    if not channels:
        return True, []

    not_subscribed = []
    for ch in channels:
        try:
            if ch["is_private"]:
                if ch["chat_id"]:
                    try:
                        member = await bot.get_chat_member(ch["chat_id"], user_id)
                        if member.status not in ["member", "administrator", "creator"]:
                            not_subscribed.append(ch)
                    except:
                        not_subscribed.append(ch)
                else:
                    not_subscribed.append(ch)
            else:
                member = await bot.get_chat_member(ch["username"], user_id)
                if member.status not in ["member", "administrator", "creator"]:
                    not_subscribed.append(ch)
        except TelegramAPIError:
            not_subscribed.append(ch)

    return len(not_subscribed) == 0, not_subscribed

# ============================================================
# 🎨 KEYBOARDS
# ============================================================

def admin_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(
        KeyboardButton(text="🎬 Kino qo'shish"),
        KeyboardButton(text="📋 Kinolar ro'yxati"),
        KeyboardButton(text="✏️ Kino tahrirlash"),
        KeyboardButton(text="❌ Kino o'chirish")
    )
    kb.add(
        KeyboardButton(text="📢 Kanal qo'shish"),
        KeyboardButton(text="🔒 Private kanal"),
        KeyboardButton(text="📋 Kanallar ro'yxati"),
        KeyboardButton(text="❌ Kanal o'chirish")
    )
    kb.add(
        KeyboardButton(text="📊 Statistika"),
        KeyboardButton(text="📨 Broadcast"),
        KeyboardButton(text="✉️ Foydalanuvchiga xabar"),
        KeyboardButton(text="🚫 Ban / Unban")
    )
    kb.add(
        KeyboardButton(text="📝 Fikrlar"),
        KeyboardButton(text="🔥 Top 10"),
        KeyboardButton(text="👥 Foydalanuvchilar"),
        KeyboardButton(text="⚙️ Sozlamalar")
    )
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def user_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(
        KeyboardButton(text="🔥 Top kinolar"),
        KeyboardButton(text="🔍 Kinolar katalogi")
    )
    kb.add(
        KeyboardButton(text="📝 Fikr bildirish"),
        KeyboardButton(text="ℹ️ Yordam")
    )
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def subscription_kb(channels: List[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in channels:
        if ch["is_private"] and ch["invite_link"]:
            link = ch["invite_link"]
        elif ch["is_private"]:
            continue
        else:
            link = f"https://t.me/{ch['username'].lstrip('@')}"
        kb.button(
            text=f"📢 {ch['title'] or ch['username']}",
            url=link
        )
    kb.button(text="✅ Tekshirish", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()

def movie_action_kb(code: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Do'stlarga ulashish", switch_inline_query=code)
    kb.button(text="⭐ Baholash", callback_data=f"rate:{code}")
    kb.adjust(1)
    return kb.as_markup()

def movie_list_kb(movies: List[dict], page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    for m in movies[start:end]:
        kb.button(
            text=f"🎬 {m['name'][:30]} [{m['code']}]",
            callback_data=f"movie_info:{m['code']}"
        )
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"movie_page:{page-1}"))
    if end < len(movies):
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"movie_page:{page+1}"))
    if nav_buttons:
        kb.row(*nav_buttons)
    
    kb.button(text="◀️ Yopish", callback_data="close_msg")
    kb.adjust(1)
    return kb.as_markup()

def genre_kb() -> InlineKeyboardMarkup:
    genres = [
        "Action", "Drama", "Comedy", "Thriller", "Horror",
        "Sci-Fi", "Romance", "Animation", "Documentary", "Fantasy",
        "Mystery", "Adventure", "Crime", "Biography", "Musical"
    ]
    kb = InlineKeyboardBuilder()
    for g in genres:
        kb.button(text=g, callback_data=f"pick_genre:{g}")
    kb.button(text="⏭ O'tkazib yuborish", callback_data="skip_genre")
    kb.adjust(3)
    return kb.as_markup()

def quality_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for q in ["4K UHD", "1080p Full HD", "720p HD", "480p", "360p"]:
        kb.button(text=q, callback_data=f"pick_quality:{q}")
    kb.adjust(2)
    return kb.as_markup()

def language_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lang in ["Uzbek", "Russian", "English", "Turkish", "Dublyaj"]:
        kb.button(text=lang, callback_data=f"pick_language:{lang}")
    kb.adjust(2)
    return kb.as_markup()

def rate_keyboard(code: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text="⭐" * i, callback_data=f"do_rate:{code}:{i}")
    kb.adjust(5)
    return kb.as_markup()

def confirm_delete_kb(code: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Ha, o'chirilsin", callback_data=f"confirm_del:{code}")
    kb.button(text="❌ Bekor qilish", callback_data="close_msg")
    kb.adjust(2)
    return kb.as_markup()

# ============================================================
# 📩 START COMMAND
# ============================================================

@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    """Handle /start command"""
    await state.clear()
    user = msg.from_user
    
    # Save user to database
    is_new = await Database.add_user(user.id, user.username, user.full_name)
    
    # Check maintenance mode
    maint = await Database.get_setting("maintenance", "0")
    if maint == "1" and not is_admin(user.id):
        return await msg.answer("🔧 Botda texnik ishlar olib borilmoqda. Tez orada qaytamiz!")
    
    # ADMIN START
    if is_admin(user.id):
        welcome_text = "🎉 Yangi admin qo'shildi!" if is_new else "👋 Qaytib keldingiz!"
        return await msg.answer(
            f"{welcome_text}\n\n👑 <b>Admin panel</b>\n\nBarcha boshqaruv tugmalari klaviaturada:",
            reply_markup=admin_menu_kb()
        )
    
    # USER START - check subscription
    ok, not_sub = await check_subscription(user.id)
    if not ok:
        return await msg.answer(
            f"👋 Salom, <b>{user.full_name}</b>!\n\n"
            "Botdan foydalanish uchun quyidagi kanallarga <b>obuna bo'ling</b>:",
            reply_markup=subscription_kb(not_sub)
        )
    
    welcome = await Database.get_setting("welcome_text",
        "🎬 <b>KinoBot</b>ga xush kelibsiz!\n\nKino kodini yuboring yoki menyudan foydalaning.")
    
    greeting = "🎉 Xush kelibsiz!" if is_new else "👋 Qaytib keldingiz!"
    
    await msg.answer(
        f"{greeting} <b>{user.full_name}</b>!\n\n{welcome}",
        reply_markup=user_menu_kb()
    )

# ============================================================
# 🔔 SUBSCRIPTION CHECK
# ============================================================

@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    ok, not_sub = await check_subscription(call.from_user.id)
    if ok:
        await call.message.delete()
        await call.message.answer(
            "✅ <b>Tabriklaymiz!</b> Barcha kanallarga obuna bo'ldingiz!\n\n"
            "Kino kodini yuboring yoki menyudan foydalaning:",
            reply_markup=user_menu_kb()
        )
    else:
        await call.answer("❌ Hali ham barcha kanallarga obuna bo'lmadingiz!", show_alert=True)

@dp.callback_query(F.data == "close_msg")
async def cb_close(call: CallbackQuery):
    try:
        await call.message.delete()
    except:
        pass

# ============================================================
# 🎬 ADMIN: KINO QO'SHISH
# ============================================================

@dp.message(F.text == "🎬 Kino qo'shish")
async def admin_add_movie_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.movie_name)
    await msg.answer("🎬 <b>Kino qo'shish</b>\n\n1️⃣ Kino <b>nomini</b> yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(AdminStates.movie_name))
async def admin_movie_name(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.update_data(name=msg.text.strip())
    await state.set_state(AdminStates.movie_code)
    await msg.answer("2️⃣ Kino <b>kodini</b> yuboring (masalan: 1001):")

@dp.message(StateFilter(AdminStates.movie_code))
async def admin_movie_code(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    code = msg.text.strip().upper()
    existing = await Database.get_movie(code)
    if existing:
        return await msg.answer("❌ Bu kod allaqachon band! Boshqa kod yuboring:")
    await state.update_data(code=code)
    await state.set_state(AdminStates.movie_video)
    await msg.answer("3️⃣ Kino <b>videosini</b> yuboring:")

@dp.message(StateFilter(AdminStates.movie_video))
async def admin_movie_video(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    if msg.video:
        file_id = msg.video.file_id
        thumb_id = msg.video.thumbnail.file_id if msg.video.thumbnail else None
    elif msg.document:
        file_id = msg.document.file_id
        thumb_id = msg.document.thumbnail.file_id if msg.document.thumbnail else None
    else:
        return await msg.answer("❌ Video yoki fayl yuboring!")
    
    await state.update_data(file_id=file_id, thumbnail_id=thumb_id)
    await state.set_state(AdminStates.movie_desc)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭ O'tkazib yuborish", callback_data="skip_desc")
    await msg.answer("4️⃣ Kino <b>tavsifini</b> yuboring (ixtiyoriy):", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "skip_desc", StateFilter(AdminStates.movie_desc))
async def admin_skip_desc(call: CallbackQuery, state: FSMContext):
    await state.update_data(description=None)
    await state.set_state(AdminStates.movie_genre)
    await call.message.edit_text("5️⃣ <b>Janrni</b> tanlang:", reply_markup=genre_kb())

@dp.message(StateFilter(AdminStates.movie_desc))
async def admin_movie_desc(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.update_data(description=msg.text.strip())
    await state.set_state(AdminStates.movie_genre)
    await msg.answer("5️⃣ <b>Janrni</b> tanlang:", reply_markup=genre_kb())

@dp.callback_query(F.data.startswith("pick_genre:"), StateFilter(AdminStates.movie_genre))
async def admin_pick_genre(call: CallbackQuery, state: FSMContext):
    await state.update_data(genre=call.data.split(":")[1])
    await state.set_state(AdminStates.movie_year)
    await call.message.edit_text("6️⃣ Kino <b>yilini</b> yuboring (masalan: 2024):")

@dp.callback_query(F.data == "skip_genre", StateFilter(AdminStates.movie_genre))
async def admin_skip_genre(call: CallbackQuery, state: FSMContext):
    await state.update_data(genre=None)
    await state.set_state(AdminStates.movie_year)
    await call.message.edit_text("6️⃣ Kino <b>yilini</b> yuboring:")

@dp.message(StateFilter(AdminStates.movie_year))
async def admin_movie_year(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    year = int(msg.text) if msg.text.strip().isdigit() else None
    await state.update_data(year=year)
    await state.set_state(AdminStates.movie_quality)
    await msg.answer("7️⃣ <b>Sifatni</b> tanlang:", reply_markup=quality_kb())

@dp.callback_query(F.data.startswith("pick_quality:"), StateFilter(AdminStates.movie_quality))
async def admin_pick_quality(call: CallbackQuery, state: FSMContext):
    await state.update_data(quality=call.data.split(":")[1])
    await state.set_state(AdminStates.movie_language)
    await call.message.edit_text("8️⃣ <b>Tilni</b> tanlang:", reply_markup=language_kb())

@dp.callback_query(F.data.startswith("pick_language:"), StateFilter(AdminStates.movie_language))
async def admin_pick_language(call: CallbackQuery, state: FSMContext):
    lang = call.data.split(":")[1]
    data = await state.get_data()
    
    ok, msg_text = await Database.add_movie(
        code=data["code"],
        name=data["name"],
        file_id=data["file_id"],
        description=data.get("description"),
        genre=data.get("genre"),
        year=data.get("year"),
        quality=data.get("quality", "HD"),
        language=lang,
        thumbnail_id=data.get("thumbnail_id")
    )
    
    await state.clear()
    
    if ok:
        await call.message.edit_text(
            f"✅ <b>Kino qo'shildi!</b>\n\n🎬 {data['name']}\n🔑 Kod: <code>{data['code']}</code>"
        )
        await call.message.answer("👑 Admin panel", reply_markup=admin_menu_kb())
    else:
        await call.message.edit_text(f"❌ Xatolik: {msg_text}")
        await call.message.answer("👑 Admin panel", reply_markup=admin_menu_kb())

# ============================================================
# 📋 ADMIN: KINOLAR RO'YXATI
# ============================================================

@dp.message(F.text == "📋 Kinolar ro'yxati")
async def admin_movies_list(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    movies = await Database.all_movies()
    if not movies:
        return await msg.answer("📋 Hozircha kinolar yo'q!")
    
    await msg.answer(
        f"📋 <b>Barcha kinolar</b> ({len(movies)} ta):",
        reply_markup=movie_list_kb(movies)
    )

@dp.callback_query(F.data.startswith("movie_page:"))
async def cb_movie_page(call: CallbackQuery):
    page = int(call.data.split(":")[1])
    movies = await Database.all_movies()
    try:
        await call.message.edit_reply_markup(reply_markup=movie_list_kb(movies, page))
    except:
        pass

@dp.callback_query(F.data.startswith("movie_info:"))
async def cb_movie_info(call: CallbackQuery):
    code = call.data.split(":")[1]
    movie = await Database.get_movie(code)
    if not movie:
        return await call.answer("Kino topilmadi!", show_alert=True)
    
    text = (
        f"🎬 <b>{movie['name']}</b>\n\n"
        f"🔑 Kod: <code>{movie['code']}</code>\n"
        f"📝 Tavsif: {movie.get('description') or '—'}\n"
        f"🎭 Janr: {movie.get('genre') or '—'}\n"
        f"📅 Yil: {movie.get('year') or '—'}\n"
        f"📺 Sifat: {movie.get('quality', 'HD')}\n"
        f"🗣 Til: {movie.get('language', 'Uzbek')}\n"
        f"👁 Ko'rishlar: {movie.get('views', 0)}\n"
        f"⭐ Reyting: {movie.get('rating', 0)}/5"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Tahrirlash", callback_data=f"edit_movie:{code}")
    kb.button(text="❌ O'chirish", callback_data=f"delete_movie:{code}")
    kb.button(text="◀️ Orqaga", callback_data="close_msg")
    kb.adjust(2, 1)
    
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup())
    except:
        await call.message.answer(text, reply_markup=kb.as_markup())

# ============================================================
# ✏️ ADMIN: KINO TAHRIRLASH
# ============================================================

@dp.message(F.text == "✏️ Kino tahrirlash")
async def admin_edit_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.edit_code)
    await msg.answer("✏️ Tahrirlanadigan kino <b>kodini</b> yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(AdminStates.edit_code))
async def admin_edit_code(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    code = msg.text.strip().upper()
    movie = await Database.get_movie(code)
    if not movie:
        await state.clear()
        return await msg.answer("❌ Kino topilmadi!", reply_markup=admin_menu_kb())
    
    await state.update_data(edit_code=code)
    
    fields = ["name", "description", "genre", "year", "quality", "language"]
    labels = {
        "name": "📝 Nomi", "description": "📄 Tavsifi",
        "genre": "🎭 Janri", "year": "📅 Yili",
        "quality": "📺 Sifati", "language": "🗣 Tili"
    }
    
    kb = InlineKeyboardBuilder()
    for f in fields:
        kb.button(text=labels[f], callback_data=f"edit_field:{f}")
    kb.button(text="◀️ Bekor", callback_data="close_msg")
    kb.adjust(2)
    
    await msg.answer(
        f"✏️ <b>{movie['name']}</b>\n\nQaysi maydonni tahrirlamoqchisiz?",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.startswith("edit_field:"))
async def cb_edit_field(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    field = call.data.split(":")[1]
    await state.update_data(edit_field=field)
    await state.set_state(AdminStates.edit_value)
    await call.message.edit_text(f"✏️ Yangi <b>{field}</b> qiymatini yuboring:")

@dp.message(StateFilter(AdminStates.edit_value))
async def admin_edit_value(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    data = await state.get_data()
    code = data["edit_code"]
    field = data["edit_field"]
    value = msg.text.strip()
    
    if field == "year":
        value = int(value) if value.isdigit() else None
    
    ok = await Database.update_movie(code, field, value)
    await state.clear()
    
    if ok:
        await msg.answer("✅ Yangilandi!", reply_markup=admin_menu_kb())
    else:
        await msg.answer("❌ Xatolik!", reply_markup=admin_menu_kb())

@dp.callback_query(F.data.startswith("edit_movie:"))
async def cb_edit_movie(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await state.update_data(edit_code=code)
    
    fields = ["name", "description", "genre", "year", "quality", "language"]
    labels = {
        "name": "📝 Nomi", "description": "📄 Tavsifi",
        "genre": "🎭 Janri", "year": "📅 Yili",
        "quality": "📺 Sifati", "language": "🗣 Tili"
    }
    
    kb = InlineKeyboardBuilder()
    for f in fields:
        kb.button(text=labels[f], callback_data=f"edit_field:{f}")
    kb.button(text="◀️ Bekor", callback_data=f"movie_info:{code}")
    kb.adjust(2)
    
    await call.message.edit_text("Qaysi maydonni tahrirlash kerak?", reply_markup=kb.as_markup())

# ============================================================
# ❌ ADMIN: KINO O'CHIRISH
# ============================================================

@dp.message(F.text == "❌ Kino o'chirish")
async def admin_delete_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.delete_code)
    await msg.answer("❌ O'chiriladigan kino <b>kodini</b> yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(AdminStates.delete_code))
async def admin_delete_code(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    code = msg.text.strip().upper()
    movie = await Database.get_movie(code)
    if not movie:
        await state.clear()
        return await msg.answer("❌ Kino topilmadi!", reply_markup=admin_menu_kb())
    
    await state.update_data(delete_code=code)
    await msg.answer(
        f"⚠️ <b>{movie['name']}</b> ({code}) kinosini o'chirishni tasdiqlaysizmi?",
        reply_markup=confirm_delete_kb(code)
    )

@dp.callback_query(F.data.startswith("confirm_del:"))
async def cb_confirm_delete(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await Database.delete_movie(code)
    await state.clear()
    await call.message.edit_text(f"✅ <code>{code}</code> kodli kino o'chirildi!")
    await call.message.answer("👑 Admin panel", reply_markup=admin_menu_kb())

@dp.callback_query(F.data.startswith("delete_movie:"))
async def cb_delete_movie(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    code = call.data.split(":")[1]
    await state.update_data(delete_code=code)
    await call.message.edit_text(
        f"⚠️ <code>{code}</code> kodli kinoni o'chirishni tasdiqlaysizmi?",
        reply_markup=confirm_delete_kb(code)
    )

# ============================================================
# 📢 ADMIN: KANALLAR
# ============================================================

@dp.message(F.text == "📢 Kanal qo'shish")
async def admin_add_channel_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.add_channel)
    await msg.answer("📢 Ochiq kanal <b>username</b>ini yuboring (@username):", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(AdminStates.add_channel))
async def admin_add_channel(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    username = msg.text.strip()
    if not username.startswith("@"):
        username = "@" + username
    
    try:
        chat = await bot.get_chat(username)
        ok = await Database.add_channel(
            username=username, title=chat.title, chat_id=chat.id, is_private=False
        )
        await state.clear()
        if ok:
            await msg.answer(f"✅ Kanal qo'shildi: <b>{chat.title}</b>", reply_markup=admin_menu_kb())
        else:
            await msg.answer("❌ Bu kanal allaqachon qo'shilgan!", reply_markup=admin_menu_kb())
    except Exception:
        await msg.answer("❌ Xatolik! Bot kanalda admin bo'lishi kerak!", reply_markup=admin_menu_kb())
        await state.clear()

@dp.message(F.text == "🔒 Private kanal")
async def admin_add_private_channel(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.add_private_channel)
    await msg.answer(
        "🔒 Private kanal ma'lumotlarini yuboring:\n\n"
        "<b>Format:</b>\n<code>@username | chat_id | havola</code>\n\n"
        "<i>Masalan:</i>\n<code>@private_ch | -100123456 | https://t.me/+abc</code>",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(StateFilter(AdminStates.add_private_channel))
async def admin_add_private_channel_process(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    try:
        parts = msg.text.strip().split("|")
        if len(parts) < 2:
            return await msg.answer("❌ Noto'g'ri format!")
        
        username = parts[0].strip()
        if not username.startswith("@"):
            username = "@" + username
        
        chat_id = int(parts[1].strip()) if parts[1].strip().lstrip("-").isdigit() else None
        invite_link = parts[2].strip() if len(parts) > 2 else None
        
        ok = await Database.add_channel(
            username=username, title=username, chat_id=chat_id,
            invite_link=invite_link, is_private=True
        )
        await state.clear()
        
        if ok:
            await msg.answer(f"✅ Private kanal qo'shildi!\n\n🔒 {username}", reply_markup=admin_menu_kb())
        else:
            await msg.answer("❌ Bu kanal allaqachon qo'shilgan!", reply_markup=admin_menu_kb())
    except:
        await msg.answer("❌ Xatolik!", reply_markup=admin_menu_kb())
        await state.clear()

@dp.message(F.text == "📋 Kanallar ro'yxati")
async def admin_channels_list(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    channels = await Database.get_channels()
    if not channels:
        return await msg.answer("📋 Kanallar yo'q!")
    
    text = "📢 <b>Kanallar ro'yxati:</b>\n\n"
    for i, ch in enumerate(channels, 1):
        lock = "🔒" if ch["is_private"] else "🌐"
        text += f"{i}. {lock} {ch['title'] or ch['username']}\n   {ch['username']}\n\n"
    
    await msg.answer(text)

@dp.message(F.text == "❌ Kanal o'chirish")
async def admin_delete_channel_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.del_channel)
    await msg.answer("❌ O'chiriladigan kanal <b>username</b>ini yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(AdminStates.del_channel))
async def admin_delete_channel(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    username = msg.text.strip()
    if not username.startswith("@"):
        username = "@" + username
    
    await Database.delete_channel(username)
    await state.clear()
    await msg.answer(f"✅ {username} kanali o'chirildi!", reply_markup=admin_menu_kb())

# ============================================================
# 📊 STATISTIKA
# ============================================================

@dp.message(F.text == "📊 Statistika")
async def admin_stats(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    stats = await Database.get_stats()
    
    text = (
        "📊 <b>STATISTIKA</b>\n\n"
        "━━━ <b>Bugun</b> ━━━\n"
        f"👥 Yangi: <b>{stats['td_new']}</b>\n"
        f"🔍 Qidiruv: <b>{stats['td_search']}</b>\n"
        f"✅ Topildi: <b>{stats['td_found']}</b>\n"
        f"❌ Topilmadi: <b>{stats['td_nf']}</b>\n\n"
        "━━━ <b>Umumiy</b> ━━━\n"
        f"👥 Foydalanuvchilar: <b>{stats['total_users']:,}</b>\n"
        f"🎬 Kinolar: <b>{stats['total_movies']:,}</b>\n"
        f"👁 Ko'rishlar: <b>{stats['total_views']:,}</b>\n"
        f"📢 Kanallar: <b>{stats['total_channels']}</b>\n"
        f"🚫 Ban: <b>{stats['banned']}</b>\n"
        f"📝 O'qilmagan fikrlar: <b>{stats['unread_fb']}</b>"
    )
    await msg.answer(text)

# ============================================================
# 👥 ADMIN: FOYDALANUVCHILAR RO'YXATI
# ============================================================

@dp.message(F.text == "👥 Foydalanuvchilar")
async def admin_users_list(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    users = await Database.get_all_users()
    if not users:
        return await msg.answer("👥 Hozircha foydalanuvchilar yo'q!")
    
    text = f"👥 <b>FOYDALANUVCHILAR</b> ({len(users)} ta):\n\n"
    for i, u in enumerate(users[:20], 1):
        ban = "🚫" if u["is_banned"] else "✅"
        text += (
            f"{i}. {ban} {u['full_name'] or 'Nomalum'}\n"
            f"   🆔 <code>{u['id']}</code> | @{u['username'] or '—'}\n"
            f"   🔍 {u['total_searches']} qidiruv\n\n"
        )
    
    if len(users) > 20:
        text += f"... va yana {len(users) - 20} ta"
    
    await msg.answer(text)

# ============================================================
# 📨 BROADCAST
# ============================================================

@dp.message(F.text == "📨 Broadcast")
async def admin_broadcast_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    users = await Database.all_user_ids()
    await state.set_state(AdminStates.broadcast)
    await msg.answer(
        f"📨 <b>Broadcast</b>\n\n👥 {len(users):,} ta foydalanuvchiga yuboriladi.\n\nXabar yuboring:",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(StateFilter(AdminStates.broadcast))
async def admin_broadcast_send(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    users = await Database.all_user_ids()
    progress_msg = await msg.answer(f"⏳ Yuborilmoqda... 0/{len(users):,}")
    
    sent = 0
    failed = 0
    
    for i, user_id in enumerate(users):
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=msg.chat.id, message_id=msg.message_id)
            sent += 1
        except:
            failed += 1
        
        if (i + 1) % BROADCAST_CHUNK == 0:
            try:
                await progress_msg.edit_text(f"⏳ {i+1}/{len(users):,}\n✅ {sent:,} | ❌ {failed:,}")
            except:
                pass
        await asyncio.sleep(BROADCAST_DELAY)
    
    await Database.log_broadcast(msg.from_user.id, sent, failed, len(users))
    await state.clear()
    
    await progress_msg.edit_text(f"✅ <b>Yakunlandi!</b>\n\n✅ {sent:,} | ❌ {failed:,}")
    await msg.answer("👑 Admin panel", reply_markup=admin_menu_kb())

# ============================================================
# ✉️ FOYDALANUVCHIGA XABAR
# ============================================================

@dp.message(F.text == "✉️ Foydalanuvchiga xabar")
async def admin_dm_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.dm_user_id)
    await msg.answer("✉️ Foydalanuvchi <b>ID</b> sini yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(AdminStates.dm_user_id))
async def admin_dm_user_id(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    if not msg.text.strip().isdigit():
        return await msg.answer("❌ Faqat raqam yuboring!")
    
    await state.update_data(dm_uid=int(msg.text.strip()))
    await state.set_state(AdminStates.dm_message)
    await msg.answer("✉️ Yuboriladigan xabarni yozing:")

@dp.message(StateFilter(AdminStates.dm_message))
async def admin_dm_send(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    data = await state.get_data()
    
    try:
        await bot.copy_message(chat_id=data["dm_uid"], from_chat_id=msg.chat.id, message_id=msg.message_id)
        await msg.answer("✅ Xabar yuborildi!", reply_markup=admin_menu_kb())
    except:
        await msg.answer("❌ Yuborib bo'lmadi!", reply_markup=admin_menu_kb())
    
    await state.clear()

# ============================================================
# 🚫 BAN / UNBAN
# ============================================================

@dp.message(F.text == "🚫 Ban / Unban")
async def admin_ban_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(AdminStates.ban_input)
    await msg.answer(
        "🚫 <b>Ban / Unban</b>\n\n"
        "<code>ban ID sabab</code>\n<code>unban ID</code>\n<code>info ID</code>",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(StateFilter(AdminStates.ban_input))
async def admin_ban_process(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    
    parts = msg.text.strip().split(maxsplit=2)
    if len(parts) < 2:
        return await msg.answer("❌ Format: ban ID sabab", reply_markup=admin_menu_kb())
    
    cmd = parts[0].lower()
    uid_str = parts[1]
    
    if not uid_str.lstrip("-").isdigit():
        return await msg.answer("❌ Noto'g'ri ID!", reply_markup=admin_menu_kb())
    
    uid = int(uid_str)
    
    if cmd == "info":
        user = await Database.get_user(uid)
        if not user:
            return await msg.answer("❌ Topilmadi!")
        text = (
            f"👤 ID: <code>{user['id']}</code>\n"
            f"Ism: {user['full_name'] or '—'}\n"
            f"Username: @{user['username'] or '—'}\n"
            f"Ban: {'🚫 Ha' if user['is_banned'] else '✅ Yoq'}"
        )
        if user['is_banned']:
            text += f"\nSabab: {user['ban_reason'] or '—'}"
        await msg.answer(text, reply_markup=admin_menu_kb())
    
    elif cmd == "ban":
        reason = parts[2] if len(parts) > 2 else "Sababsiz"
        await Database.ban_user(uid, reason, True)
        await msg.answer(f"✅ Ban qilindi!", reply_markup=admin_menu_kb())
        try:
            await bot.send_message(uid, f"🚫 Siz ban qilindingiz.\nSabab: {reason}")
        except:
            pass
    
    elif cmd == "unban":
        await Database.ban_user(uid, None, False)
        await msg.answer(f"✅ Ban olindi!", reply_markup=admin_menu_kb())
        try:
            await bot.send_message(uid, "✅ Baningiz olib tashlandi!")
        except:
            pass
    
    else:
        await msg.answer("❌ Noto'g'ri buyruq!", reply_markup=admin_menu_kb())
    
    await state.clear()

# ============================================================
# 📝 FIKRLAR
# ============================================================

@dp.message(F.text == "📝 Fikrlar")
async def admin_feedbacks(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    fbs = await Database.get_feedbacks(limit=10, unread_only=True)
    if not fbs:
        return await msg.answer("📝 O'qilmagan fikrlar yo'q!")
    
    text = "📝 <b>O'QILMAGAN FIKRLAR</b>\n\n"
    kb = InlineKeyboardBuilder()
    
    for fb in fbs:
        text += (
            f"👤 <b>{fb['full_name'] or 'Nomalum'}</b>\n"
            f"🆔 <code>{fb['user_id']}</code>\n"
            f"💬 {fb['message'][:200]}\n\n"
        )
        kb.button(text=f"↩️ Javob", callback_data=f"reply_fb:{fb['id']}:{fb['user_id']}")
    
    kb.button(text="◀️ Yopish", callback_data="close_msg")
    kb.adjust(1)
    
    await msg.answer(text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("reply_fb:"))
async def cb_reply_feedback(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    _, fb_id, user_id = call.data.split(":")
    await state.update_data(reply_fb_id=int(fb_id), reply_uid=int(user_id))
    await state.set_state(AdminStates.reply_feedback)
    await call.message.edit_text("↩️ Javob yuboring:")

@dp.message(StateFilter(AdminStates.reply_feedback))
async def admin_send_reply(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    data = await state.get_data()
    
    await Database.reply_to_feedback(data["reply_fb_id"], msg.text)
    
    try:
        await bot.send_message(data["reply_uid"], f"📬 <b>Admindan javob:</b>\n\n{msg.text}")
    except:
        pass
    
    await state.clear()
    await msg.answer("✅ Javob yuborildi!", reply_markup=admin_menu_kb())

# ============================================================
# 🔥 TOP 10
# ============================================================

@dp.message(F.text == "🔥 Top 10")
async def admin_top(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    movies = await Database.top_movies(10)
    if not movies:
        return await msg.answer("Hozircha kinolar yo'q!")
    
    medals = ["🥇", "🥈", "🥉"]
    text = "🔥 <b>TOP 10 KINOLAR</b>\n\n"
    
    for i, m in enumerate(movies):
        icon = medals[i] if i < 3 else f"{i+1}."
        text += f"{icon} <b>{m['name']}</b>\n   🔑 <code>{m['code']}</code> | 👁 {m['views']:,}\n\n"
    
    await msg.answer(text)

# ============================================================
# ⚙️ SOZLAMALAR
# ============================================================

@dp.message(F.text == "⚙️ Sozlamalar")
async def admin_settings(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    
    maint = await Database.get_setting("maintenance", "0")
    status = "🔴 Yoqilgan" if maint == "1" else "🟢 O'chirilgan"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔧 O'zgartirish", callback_data="toggle_maint")
    kb.button(text="📝 Welcome xabar", callback_data="change_welcome")
    kb.button(text="◀️ Yopish", callback_data="close_msg")
    kb.adjust(1)
    
    await msg.answer(f"⚙️ <b>SOZLAMALAR</b>\n\n🔧 Maintenance: {status}", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "toggle_maint")
async def cb_toggle_maint(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    current = await Database.get_setting("maintenance", "0")
    new_value = "0" if current == "1" else "1"
    await Database.set_setting("maintenance", new_value)
    await call.answer("✅ O'zgartirildi!", show_alert=True)
    await admin_settings(call.message)

@dp.callback_query(F.data == "change_welcome")
async def cb_change_welcome(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminStates.set_welcome)
    await call.message.edit_text("📝 Yangi welcome xabarni yuboring:")

@dp.message(StateFilter(AdminStates.set_welcome))
async def admin_set_welcome(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await Database.set_setting("welcome_text", msg.text)
    await state.clear()
    await msg.answer("✅ Saqlandi!", reply_markup=admin_menu_kb())

# ============================================================
# 👤 USER: TOP KINOLAR
# ============================================================

@dp.message(F.text == "🔥 Top kinolar")
async def user_top_movies(msg: Message):
    if is_admin(msg.from_user.id):
        return
    
    ok, not_sub = await check_subscription(msg.from_user.id)
    if not ok:
        return await msg.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=subscription_kb(not_sub))
    
    movies = await Database.top_movies(10)
    if not movies:
        return await msg.answer("Hozircha kinolar yo'q!")
    
    medals = ["🥇", "🥈", "🥉"]
    text = "🔥 <b>TOP 10 KINOLAR</b>\n\n"
    
    for i, m in enumerate(movies):
        icon = medals[i] if i < 3 else f"{i+1}."
        text += f"{icon} <b>{m['name']}</b>\n   🔑 Kod: <code>{m['code']}</code>\n   👁 {m['views']:,}\n\n"
    
    await msg.answer(text)

@dp.message(F.text == "🔍 Kinolar katalogi")
async def user_catalog(msg: Message):
    if is_admin(msg.from_user.id):
        return
    
    ok, not_sub = await check_subscription(msg.from_user.id)
    if not ok:
        return await msg.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=subscription_kb(not_sub))
    
    movies = await Database.all_movies()
    if not movies:
        return await msg.answer("Hozircha kinolar yo'q!")
    
    await msg.answer(f"📋 <b>Kinolar katalogi</b> ({len(movies)} ta):", reply_markup=movie_list_kb(movies))

@dp.message(F.text == "📝 Fikr bildirish")
async def user_feedback_start(msg: Message, state: FSMContext):
    if is_admin(msg.from_user.id):
        return
    
    ok, not_sub = await check_subscription(msg.from_user.id)
    if not ok:
        return await msg.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=subscription_kb(not_sub))
    
    await state.set_state(UserStates.feedback)
    await msg.answer("📝 Fikringizni yuboring:", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(UserStates.feedback))
async def user_feedback_send(msg: Message, state: FSMContext):
    user = msg.from_user
    await Database.add_feedback(user.id, user.username or "", user.full_name or "", msg.text)
    
    for admin_id in SUPER_ADMINS:
        try:
            await bot.send_message(admin_id, f"📝 <b>Yangi fikr</b>\n\n👤 {user.full_name} (@{user.username or '—'})\n💬 {msg.text[:500]}")
        except:
            pass
    
    await state.clear()
    await msg.answer("✅ Fikringiz qabul qilindi!", reply_markup=user_menu_kb())

@dp.message(F.text == "ℹ️ Yordam")
async def user_help(msg: Message):
    if is_admin(msg.from_user.id):
        return
    
    await msg.answer(
        "ℹ️ <b>YORDAM</b>\n\n"
        "🎬 Kino kodini yuboring (masalan: <code>1001</code>)\n"
        "🔍 Kino nomini yozing - qidiruv ishlaydi\n\n"
        "🔥 Top kinolar - menyudan tanlang\n"
        "📝 Fikr bildirish - menyudan tanlang"
    )

# ============================================================
# 🔍 MOVIE SEARCH (USER) - ENG PASTDA BO'LISHI KERAK
# ============================================================

@dp.message(F.text)
@rate_limit(max_per_sec=3)
async def search_movie(msg: Message):
    """Handle movie search for users - must be last handler"""
    user_id = msg.from_user.id
    
    # Admin xabarlari bu yerga tushmasligi kerak
    if is_admin(user_id):
        return
    
    ok, not_sub = await check_subscription(user_id)
    if not ok:
        return await msg.answer("⚠️ Avval kanallarga obuna bo'ling:", reply_markup=subscription_kb(not_sub))
    
    query = msg.text.strip()
    await Database.stat_increment("searches")
    
    # Exact code match
    movie = await Database.get_movie(query)
    if movie:
        await Database.stat_increment("found")
        try:
            await msg.answer_video(
                video=movie["file_id"],
                caption=(
                    f"🎬 <b>{movie['name']}</b>\n\n"
                    f"🔑 Kod: <code>{movie['code']}</code>\n"
                    f"📅 Yil: {movie.get('year') or '—'}\n"
                    f"🎭 Janr: {movie.get('genre') or '—'}\n"
                    f"📺 Sifat: {movie.get('quality', 'HD')}\n"
                    f"🗣 Til: {movie.get('language', 'Uzbek')}\n"
                    f"👁 Ko'rishlar: {movie.get('views', 0):,}"
                ),
                reply_markup=movie_action_kb(movie["code"])
            )
        except:
            await msg.answer_document(
                document=movie["file_id"],
                caption=f"🎬 <b>{movie['name']}</b>\n🔑 Kod: <code>{movie['code']}</code>",
                reply_markup=movie_action_kb(movie["code"])
            )
        return
    
    # Name search
    if len(query) >= 2:
        results = await Database.search_movies(query)
        if results:
            await Database.stat_increment("found")
            text = f"🔍 <b>«{query}» bo'yicha natijalar:</b>\n\n"
            
            kb = InlineKeyboardBuilder()
            for r in results[:10]:
                text += f"🎬 <b>{r['name']}</b>\n   🔑 Kod: <code>{r['code']}</code>\n   👁 {r['views']:,}\n\n"
                kb.button(text=f"▶️ {r['name'][:25]}", callback_data=f"watch:{r['code']}")
            kb.adjust(1)
            
            return await msg.answer(text, reply_markup=kb.as_markup())
    
    await Database.stat_increment("not_found")
    await msg.answer(f"❌ <b>«{query}»</b> topilmadi!", reply_markup=user_menu_kb())

@dp.callback_query(F.data.startswith("watch:"))
async def cb_watch_movie(call: CallbackQuery):
    code = call.data.split(":")[1]
    movie = await Database.get_movie(code)
    if not movie:
        return await call.answer("Kino topilmadi!", show_alert=True)
    
    try:
        await call.message.answer_video(
            video=movie["file_id"],
            caption=f"🎬 <b>{movie['name']}</b>\n🔑 Kod: <code>{movie['code']}</code>",
            reply_markup=movie_action_kb(movie["code"])
        )
    except:
        await call.message.answer_document(
            document=movie["file_id"],
            caption=f"🎬 <b>{movie['name']}</b>",
            reply_markup=movie_action_kb(movie["code"])
        )

# ============================================================
# ⭐ RATING
# ============================================================

@dp.callback_query(F.data.startswith("rate:"))
async def cb_rate_prompt(call: CallbackQuery):
    code = call.data.split(":")[1]
    await call.message.edit_text("⭐ Baholang:", reply_markup=rate_keyboard(code))

@dp.callback_query(F.data.startswith("do_rate:"))
async def cb_do_rate(call: CallbackQuery):
    _, code, score = call.data.split(":")
    await call.answer(f"✅ Baholadingiz: {'⭐'*int(score)}", show_alert=True)
    try:
        await call.message.delete()
    except:
        pass

# ============================================================
# 🛑 ERROR HANDLER
# ============================================================

@dp.errors()
async def error_handler(event):
    exc = event.exception
    if isinstance(exc, asyncio.CancelledError):
        return False
    logger.error(f"Xatolik: {exc}")
    return True

# ============================================================
# 🚀 MAIN
# ============================================================

async def main():
    logger.info("🚀 KinoBot v4.2 ishga tushmoqda...")
    
    await Database.init()
    await bot.delete_webhook(drop_pending_updates=True)
    
    bot_info = await bot.get_me()
    logger.info(f"✅ Bot: @{bot_info.username}")
    logger.info("✅ Barcha tizimlar tayyor!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot to'xtatildi")
    except Exception as e:
        logger.critical(f"💥 Kritik xatolik: {e}", exc_info=True)
        sys.exit(1)