#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════╗
║       🌟 Revival GDPS — Telegram Bot 🌟         ║
║       Request System & Server Management         ║
╚══════════════════════════════════════════════════╝

Требования:  pip install python-telegram-bot[all]
Запуск:      python bot.py
"""

import logging
import sqlite3
import json
import time
from datetime import datetime, timedelta
from contextlib import contextmanager

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from telegram.constants import ParseMode

# ──────────────────────── CONFIG ────────────────────────

BOT_TOKEN = "8374327193:AAGtfTBSeKt0TJl0-YEnFMN3fnjQAYyeM-Y"

OWNER_USERNAMES = ["antriphy", "spirated"]

CHANNEL_URL = "https://t.me/revival_gdps"
GROUP_URL = "https://t.me/revival_gdps_group"
SITE_URL = "https://www.glowhosting.ru/gd/awxptp/dashboard/"

DB_FILE = "revival_bot.db"

WARNING_LIMIT = 3
WARNING_RESET_DAYS = 7
BAN_DURATION_DAYS = 7

# ──────────────────── LOGGING ────────────────────────

logging.basicConfig(
    format="%(asctime)s │ %(name)-12s │ %(levelname)-7s │ %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("RevivalBot")

# ──────────────────── EMOJIS / DESIGN ────────────────────

E = {
    "star": "⭐",
    "fire": "🔥",
    "crown": "👑",
    "shield": "🛡",
    "hammer": "🔨",
    "check": "✅",
    "cross": "❌",
    "warn": "⚠️",
    "ban": "🚫",
    "back": "◀️",
    "home": "🏠",
    "gear": "⚙️",
    "link": "🔗",
    "channel": "📢",
    "group": "👥",
    "globe": "🌐",
    "pencil": "📝",
    "list": "📋",
    "id": "🆔",
    "trophy": "🏆",
    "diamond": "💎",
    "sparkle": "✨",
    "rocket": "🚀",
    "tools": "🛠",
    "user": "👤",
    "clock": "🕐",
    "inbox": "📥",
    "outbox": "📤",
    "flag": "🚩",
    "party": "🎉",
    "skull": "💀",
    "demon": "👿",
    "eye": "👁",
    "search": "🔍",
    "bolt": "⚡",
    "heart": "❤️",
    "info": "ℹ️",
    "num": "🔢",
    "level": "🎮",
    "arrow_r": "▸",
}

# ──────────────── DIFFICULTY → STARS MAP ─────────────────

DIFFICULTIES = {
    "Auto": {"stars": 1, "emoji": "🤖"},
    "Easy": {"stars": 2, "emoji": "😊"},
    "Normal": {"stars": 3, "emoji": "🙂"},
    "Hard": {"stars": [4, 5], "emoji": "😐"},
    "Harder": {"stars": [6, 7], "emoji": "😤"},
    "Insane": {"stars": [8, 9], "emoji": "🤯"},
    "Easy Demon": {"stars": 10, "emoji": "👿"},
    "Medium Demon": {"stars": 10, "emoji": "👿"},
    "Hard Demon": {"stars": 10, "emoji": "👿"},
    "Insane Demon": {"stars": 10, "emoji": "👿"},
    "Extreme Demon": {"stars": 10, "emoji": "👿"},
}

FEATURES = ["Star Rate", "Feature", "Epic", "Legendary", "Mythic"]
FEATURE_EMOJIS = {
    "Star Rate": "⭐",
    "Feature": "🌟",
    "Epic": "🔥",
    "Legendary": "💎",
    "Mythic": "✨",
}

# ──────────────── CONVERSATION STATES ──────────────────

(
    STATE_LEVEL_ID,
    STATE_DIFFICULTY,
    STATE_STARS_PICK,
    STATE_FEATURE,
    STATE_CONFIRM,
) = range(5)

# ──────────────────── DATABASE ──────────────────────────


def init_db():
    """Создаём таблицы при первом запуске."""
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       INTEGER PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                role          TEXT DEFAULT 'player',
                warnings      INTEGER DEFAULT 0,
                last_warning  TEXT,
                banned_until  TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                level_id      TEXT,
                difficulty    TEXT,
                stars         INTEGER,
                feature       TEXT,
                status        TEXT DEFAULT 'pending',
                reviewed_by   INTEGER,
                review_note   TEXT,
                created_at    TEXT DEFAULT (datetime('now')),
                reviewed_at   TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        db.commit()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ──────────────── USER HELPERS ──────────────────────

def ensure_user(user) -> dict:
    """Регистрирует / обновляет пользователя в БД."""
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE user_id=?", (user.id,)).fetchone()
        username = (user.username or "").lower()
        if row is None:
            role = "owner" if username in OWNER_USERNAMES else "player"
            db.execute(
                "INSERT INTO users (user_id, username, first_name, role) VALUES (?,?,?,?)",
                (user.id, username, user.first_name, role),
            )
            db.commit()
            return {
                "user_id": user.id, "username": username,
                "first_name": user.first_name, "role": role,
                "warnings": 0, "banned_until": None,
            }
        else:
            # Обновляем юзернейм если изменился
            if username != (row["username"] or ""):
                new_role = row["role"]
                if username in OWNER_USERNAMES and row["role"] != "owner":
                    new_role = "owner"
                db.execute(
                    "UPDATE users SET username=?, first_name=?, role=? WHERE user_id=?",
                    (username, user.first_name, new_role, user.id),
                )
                db.commit()
            # Если это владелец, но роль не owner — исправить
            if username in OWNER_USERNAMES and row["role"] != "owner":
                db.execute("UPDATE users SET role='owner' WHERE user_id=?", (user.id,))
                db.commit()
            return dict(row)


def is_owner(user) -> bool:
    u = ensure_user(user)
    return u["role"] == "owner"


def is_moderator(user) -> bool:
    u = ensure_user(user)
    return u["role"] in ("moderator", "senior_mod", "owner")


def is_senior_mod(user) -> bool:
    u = ensure_user(user)
    return u["role"] in ("senior_mod", "owner")


def is_banned(user) -> bool:
    u = ensure_user(user)
    if u["banned_until"]:
        ban_end = datetime.fromisoformat(u["banned_until"])
        if datetime.now() < ban_end:
            return True
        else:
            with get_db() as db:
                db.execute(
                    "UPDATE users SET banned_until=NULL, warnings=0 WHERE user_id=?",
                    (user.id,),
                )
                db.commit()
    return False


def get_role_badge(role: str) -> str:
    badges = {
        "owner": f"{E['crown']} Владелец",
        "senior_mod": f"{E['shield']} Ст. Модератор",
        "moderator": f"{E['hammer']} Модератор",
        "player": f"{E['user']} Игрок",
    }
    return badges.get(role, f"{E['user']} Игрок")


def get_stars_display(stars: int) -> str:
    return E["star"] * min(stars, 10)


# ──────────────── KEYBOARD BUILDERS ──────────────────

def main_menu_keyboard(user) -> InlineKeyboardMarkup:
    u = ensure_user(user)
    role = u["role"]

    buttons = [
        [InlineKeyboardButton(f"{E['pencil']} Реквест", callback_data="request_start")],
        [
            InlineKeyboardButton(f"{E['channel']} Канал", url=CHANNEL_URL),
            InlineKeyboardButton(f"{E['group']} Группа", url=GROUP_URL),
        ],
        [InlineKeyboardButton(f"{E['globe']} Сайт", url=SITE_URL)],
    ]

    if role in ("moderator", "senior_mod", "owner"):
        buttons.append([
            InlineKeyboardButton(f"{E['tools']} Утилиты", callback_data="utils_menu"),
        ])

    buttons.append([
        InlineKeyboardButton(f"{E['gear']} Настройки", callback_data="settings_menu"),
    ])

    return InlineKeyboardMarkup(buttons)


def back_button(callback_data="main_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{E['back']} Назад", callback_data=callback_data)]
    ])


# ══════════════════════════════════════════════════════
#                    HANDLERS
# ══════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — главное меню."""
    user = update.effective_user
    ensure_user(user)

    if is_banned(user):
        u = ensure_user(user)
        ban_end = datetime.fromisoformat(u["banned_until"])
        remaining = ban_end - datetime.now()
        days_left = remaining.days + 1
        text = (
            f"{E['ban']} <b>Вы заблокированы в боте</b>\n\n"
            f"Блокировка истекает через: <b>{days_left} дн.</b>\n"
            f"Дата разблокировки: <code>{ban_end.strftime('%d.%m.%Y %H:%M')}</code>\n\n"
            f"Причина: превышен лимит предупреждений."
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    u = ensure_user(user)
    role_badge = get_role_badge(u["role"])

    text = (
        f"{'━' * 30}\n"
        f"{E['rocket']}  <b>Revival GDPS</b>  {E['rocket']}\n"
        f"{'━' * 30}\n\n"
        f"{E['party']} Добро пожаловать, <b>{user.first_name}</b>!\n\n"
        f"{E['arrow_r']} Статус: {role_badge}\n"
        f"{E['arrow_r']} ID: <code>{user.id}</code>\n\n"
        f"{'─' * 30}\n"
        f"Выберите действие из меню ниже:\n"
        f"{'─' * 30}"
    )

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(user),
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(user),
        )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню по кнопке."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    if is_banned(user):
        u = ensure_user(user)
        ban_end = datetime.fromisoformat(u["banned_until"])
        remaining = ban_end - datetime.now()
        days_left = remaining.days + 1
        text = (
            f"{E['ban']} <b>Вы заблокированы в боте</b>\n\n"
            f"Блокировка истекает через: <b>{days_left} дн.</b>"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)
        return

    u = ensure_user(user)
    role_badge = get_role_badge(u["role"])

    text = (
        f"{'━' * 30}\n"
        f"{E['rocket']}  <b>Revival GDPS</b>  {E['rocket']}\n"
        f"{'━' * 30}\n\n"
        f"{E['party']} Добро пожаловать, <b>{user.first_name}</b>!\n\n"
        f"{E['arrow_r']} Статус: {role_badge}\n"
        f"{E['arrow_r']} ID: <code>{user.id}</code>\n\n"
        f"{'─' * 30}\n"
        f"Выберите действие из меню ниже:\n"
        f"{'─' * 30}"
    )
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user),
    )


# ══════════════════════════════════════════════════
#             REQUEST SYSTEM (ConversationHandler)
# ══════════════════════════════════════════════════

async def request_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало создания реквеста — ввод ID уровня."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if is_banned(user):
        await query.edit_message_text(f"{E['ban']} Вы заблокированы в боте.")
        return ConversationHandler.END

    # Проверка: есть ли уже pending реквест
    with get_db() as db:
        pending = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE user_id=? AND status='pending'",
            (user.id,),
        ).fetchone()
        if pending["cnt"] >= 3:
            await query.edit_message_text(
                f"{E['warn']} У вас уже <b>3 активных реквеста</b> на рассмотрении.\n"
                f"Дождитесь их обработки перед отправкой нового.",
                parse_mode=ParseMode.HTML,
                reply_markup=back_button("main_menu"),
            )
            return ConversationHandler.END

    text = (
        f"{'━' * 30}\n"
        f"{E['pencil']}  <b>Новый реквест</b>  {E['pencil']}\n"
        f"{'━' * 30}\n\n"
        f"{E['num']} <b>Шаг 1/4</b> — Введите <b>ID уровня</b>\n\n"
        f"{E['info']} ID должен содержать от 3 до 12 цифр.\n"
        f"Найти ID можно в описании уровня в игре.\n\n"
        f"{'─' * 30}\n"
        f"Отправьте ID сообщением ниже 👇\n"
        f"Или нажмите «Отмена» для выхода."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{E['cross']} Отмена", callback_data="request_cancel")]
    ])

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return STATE_LEVEL_ID


async def request_level_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получаем ID уровня."""
    text = update.message.text.strip()

    if not text.isdigit() or not (3 <= len(text) <= 12):
        await update.message.reply_text(
            f"{E['cross']} <b>Некорректный ID!</b>\n\n"
            f"ID должен содержать от 3 до 12 цифр.\n"
            f"Попробуйте ещё раз:",
            parse_mode=ParseMode.HTML,
        )
        return STATE_LEVEL_ID

    context.user_data["request_level_id"] = text

    # Показать клавиатуру сложности
    keyboard = []
    row = []
    for i, (diff, info) in enumerate(DIFFICULTIES.items()):
        row.append(
            InlineKeyboardButton(
                f"{info['emoji']} {diff}",
                callback_data=f"diff_{diff}",
            )
        )
        if len(row) == 2 or i == len(DIFFICULTIES) - 1:
            keyboard.append(row)
            row = []

    keyboard.append([
        InlineKeyboardButton(f"{E['cross']} Отмена", callback_data="request_cancel")
    ])

    msg_text = (
        f"{'━' * 30}\n"
        f"{E['pencil']}  <b>Новый реквест</b>  {E['pencil']}\n"
        f"{'━' * 30}\n\n"
        f"{E['check']} ID уровня: <code>{text}</code>\n\n"
        f"{E['star']} <b>Шаг 2/4</b> — Выберите <b>желаемую сложность</b>:\n"
        f"{'─' * 30}"
    )

    await update.message.reply_text(
        msg_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STATE_DIFFICULTY


async def request_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор сложности."""
    query = update.callback_query
    await query.answer()

    diff_name = query.data.replace("diff_", "")
    context.user_data["request_difficulty"] = diff_name
    diff_info = DIFFICULTIES[diff_name]
    stars = diff_info["stars"]

    if isinstance(stars, list):
        # Предложить выбрать звёзды
        keyboard = []
        row = []
        for s in stars:
            row.append(
                InlineKeyboardButton(
                    f"{E['star']} {s}",
                    callback_data=f"stars_{s}",
                )
            )
        keyboard.append(row)
        keyboard.append([
            InlineKeyboardButton(f"{E['back']} Назад", callback_data="request_start"),
            InlineKeyboardButton(f"{E['cross']} Отмена", callback_data="request_cancel"),
        ])

        text = (
            f"{'━' * 30}\n"
            f"{E['pencil']}  <b>Новый реквест</b>  {E['pencil']}\n"
            f"{'━' * 30}\n\n"
            f"{E['check']} ID: <code>{context.user_data['request_level_id']}</code>\n"
            f"{E['check']} Сложность: {diff_info['emoji']} {diff_name}\n\n"
            f"{E['star']} <b>Шаг 2.5/4</b> — Выберите количество <b>звёзд</b>:\n"
            f"{'─' * 30}"
        )

        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return STATE_STARS_PICK
    else:
        context.user_data["request_stars"] = stars
        return await show_feature_select(query, context)


async def request_stars_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор звёзд (для Hard/Harder/Insane)."""
    query = update.callback_query
    await query.answer()

    stars = int(query.data.replace("stars_", ""))
    context.user_data["request_stars"] = stars
    return await show_feature_select(query, context)


async def show_feature_select(query, context) -> int:
    """Показать выбор Feature."""
    keyboard = []
    for feat in FEATURES:
        emoji = FEATURE_EMOJIS.get(feat, "")
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {feat}",
                callback_data=f"feat_{feat}",
            )
        ])
    keyboard.append([
        InlineKeyboardButton(f"{E['cross']} Отмена", callback_data="request_cancel")
    ])

    diff = context.user_data["request_difficulty"]
    diff_info = DIFFICULTIES[diff]
    stars = context.user_data["request_stars"]

    text = (
        f"{'━' * 30}\n"
        f"{E['pencil']}  <b>Новый реквест</b>  {E['pencil']}\n"
        f"{'━' * 30}\n\n"
        f"{E['check']} ID: <code>{context.user_data['request_level_id']}</code>\n"
        f"{E['check']} Сложность: {diff_info['emoji']} {diff}\n"
        f"{E['check']} Звёзды: {get_stars_display(stars)} ({stars})\n\n"
        f"{E['diamond']} <b>Шаг 3/4</b> — Выберите <b>фичер</b>:\n"
        f"{'─' * 30}"
    )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return STATE_FEATURE


async def request_feature(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор Feature."""
    query = update.callback_query
    await query.answer()

    feat = query.data.replace("feat_", "")
    context.user_data["request_feature"] = feat

    diff = context.user_data["request_difficulty"]
    diff_info = DIFFICULTIES[diff]
    stars = context.user_data["request_stars"]
    feat_emoji = FEATURE_EMOJIS.get(feat, "")

    text = (
        f"{'━' * 30}\n"
        f"{E['pencil']}  <b>Подтверждение реквеста</b>  {E['pencil']}\n"
        f"{'━' * 30}\n\n"
        f"{E['level']} <b>Шаг 4/4</b> — Проверьте данные:\n\n"
        f"  {E['id']} ID уровня: <code>{context.user_data['request_level_id']}</code>\n"
        f"  {diff_info['emoji']} Сложность: <b>{diff}</b>\n"
        f"  {E['star']} Звёзды: {get_stars_display(stars)} ({stars})\n"
        f"  {feat_emoji} Фичер: <b>{feat}</b>\n\n"
        f"{'─' * 30}\n"
        f"Всё верно? Отправьте реквест!"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"{E['check']} Отправить", callback_data="request_submit"),
            InlineKeyboardButton(f"{E['cross']} Отмена", callback_data="request_cancel"),
        ]
    ])

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
    )
    return STATE_CONFIRM


async def request_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение реквеста в БД."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    level_id = context.user_data.get("request_level_id")
    difficulty = context.user_data.get("request_difficulty")
    stars = context.user_data.get("request_stars")
    feature = context.user_data.get("request_feature")

    with get_db() as db:
        db.execute(
            "INSERT INTO requests (user_id, level_id, difficulty, stars, feature) VALUES (?,?,?,?,?)",
            (user.id, level_id, difficulty, stars, feature),
        )
        db.commit()
        req_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    diff_info = DIFFICULTIES.get(difficulty, {})
    feat_emoji = FEATURE_EMOJIS.get(feature, "")

    text = (
        f"{'━' * 30}\n"
        f"{E['party']}  <b>Реквест отправлен!</b>  {E['party']}\n"
        f"{'━' * 30}\n\n"
        f"{E['check']} Ваш реквест <b>#{req_id}</b> успешно отправлен\n"
        f"на рассмотрение модерации!\n\n"
        f"  {E['id']} ID уровня: <code>{level_id}</code>\n"
        f"  {diff_info.get('emoji', '')} Сложность: <b>{difficulty}</b>\n"
        f"  {E['star']} Звёзды: {get_stars_display(stars)} ({stars})\n"
        f"  {feat_emoji} Фичер: <b>{feature}</b>\n\n"
        f"{E['clock']} Ожидайте ответа от модерации.\n"
        f"{'─' * 30}"
    )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("main_menu"),
    )
    context.user_data.clear()
    return ConversationHandler.END


async def request_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена реквеста."""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    await query.edit_message_text(
        f"{E['cross']} <b>Реквест отменён.</b>\n\nВы можете начать заново из главного меню.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("main_menu"),
    )
    return ConversationHandler.END


# ══════════════════════════════════════════════════
#                SETTINGS MENU
# ══════════════════════════════════════════════════

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    u = ensure_user(user)

    with get_db() as db:
        req_count = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE user_id=?", (user.id,)
        ).fetchone()["cnt"]
        pending = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE user_id=? AND status='pending'",
            (user.id,),
        ).fetchone()["cnt"]
        approved = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE user_id=? AND status='approved'",
            (user.id,),
        ).fetchone()["cnt"]
        rejected = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE user_id=? AND status='rejected'",
            (user.id,),
        ).fetchone()["cnt"]

    text = (
        f"{'━' * 30}\n"
        f"{E['gear']}  <b>Настройки & Профиль</b>  {E['gear']}\n"
        f"{'━' * 30}\n\n"
        f"{E['user']} <b>{user.first_name}</b>"
        f"{' (@' + user.username + ')' if user.username else ''}\n"
        f"{E['id']} ID: <code>{user.id}</code>\n"
        f"{E['shield']} Роль: {get_role_badge(u['role'])}\n"
        f"{E['warn']} Предупреждений: <b>{u['warnings']}/{WARNING_LIMIT}</b>\n\n"
        f"{'─' * 30}\n"
        f"{E['list']} <b>Статистика реквестов:</b>\n\n"
        f"  {E['inbox']} Всего: <b>{req_count}</b>\n"
        f"  {E['clock']} На рассмотрении: <b>{pending}</b>\n"
        f"  {E['check']} Одобрено: <b>{approved}</b>\n"
        f"  {E['cross']} Отклонено: <b>{rejected}</b>\n"
        f"{'─' * 30}"
    )

    keyboard = [
        [InlineKeyboardButton(f"{E['list']} Мои реквесты", callback_data="my_requests")],
        [InlineKeyboardButton(f"{E['back']} Назад", callback_data="main_menu")],
    ]

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def my_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    with get_db() as db:
        requests = db.execute(
            "SELECT * FROM requests WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
            (user.id,),
        ).fetchall()

    if not requests:
        await query.edit_message_text(
            f"{E['inbox']} <b>У вас пока нет реквестов.</b>\n\nОтправьте свой первый уровень!",
            parse_mode=ParseMode.HTML,
            reply_markup=back_button("settings_menu"),
        )
        return

    status_emoji = {"pending": E["clock"], "approved": E["check"], "rejected": E["cross"]}
    status_text = {"pending": "На рассмотрении", "approved": "Одобрен", "rejected": "Отклонён"}

    text = (
        f"{'━' * 30}\n"
        f"{E['list']}  <b>Ваши реквесты</b>  {E['list']}\n"
        f"{'━' * 30}\n\n"
    )

    for req in requests:
        s_emoji = status_emoji.get(req["status"], "❓")
        s_text = status_text.get(req["status"], "Неизвестно")
        diff_info = DIFFICULTIES.get(req["difficulty"], {})
        feat_emoji = FEATURE_EMOJIS.get(req["feature"], "")
        created = datetime.fromisoformat(req["created_at"]).strftime("%d.%m.%Y %H:%M")

        text += (
            f"{s_emoji} <b>#{req['id']}</b> │ "
            f"ID: <code>{req['level_id']}</code> │ "
            f"{diff_info.get('emoji', '')} {req['difficulty']} │ "
            f"{feat_emoji} {req['feature']}\n"
            f"   {E['clock']} {created} │ {s_text}\n\n"
        )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("settings_menu"),
    )


# ══════════════════════════════════════════════════
#            UTILITIES (MODERATORS / OWNER)
# ══════════════════════════════════════════════════

async def utils_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_moderator(user):
        await query.edit_message_text(
            f"{E['ban']} У вас нет доступа к этому разделу.",
            reply_markup=back_button("main_menu"),
        )
        return

    u = ensure_user(user)
    role = u["role"]

    with get_db() as db:
        pending_cnt = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE status='pending'"
        ).fetchone()["cnt"]

    text = (
        f"{'━' * 30}\n"
        f"{E['tools']}  <b>Утилиты модерации</b>  {E['tools']}\n"
        f"{'━' * 30}\n\n"
        f"{E['inbox']} Реквестов на рассмотрении: <b>{pending_cnt}</b>\n"
        f"{'─' * 30}"
    )

    keyboard = [
        [InlineKeyboardButton(f"{E['inbox']} Список реквестов ({pending_cnt})", callback_data="mod_requests_list")],
        [InlineKeyboardButton(f"{E['search']} Поиск реквеста по ID", callback_data="mod_search_request")],
    ]

    if role in ("senior_mod", "owner"):
        keyboard.append([
            InlineKeyboardButton(f"{E['warn']} Выдать предупреждение", callback_data="mod_warn_user"),
        ])

    if role == "owner":
        keyboard.extend([
            [InlineKeyboardButton(f"{E['crown']} Управление ролями", callback_data="owner_roles")],
            [InlineKeyboardButton(f"{E['ban']} Забаненные", callback_data="owner_bans")],
            [InlineKeyboardButton(f"{E['list']} Все модераторы", callback_data="owner_mod_list")],
        ])

    keyboard.append([
        InlineKeyboardButton(f"{E['back']} Назад", callback_data="main_menu"),
    ])

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── Список реквестов (для модератора) ───

async def mod_requests_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_moderator(user):
        await query.edit_message_text(f"{E['ban']} Нет доступа.")
        return

    page = context.user_data.get("mod_req_page", 0)
    per_page = 5

    with get_db() as db:
        total = db.execute(
            "SELECT COUNT(*) as cnt FROM requests WHERE status='pending'"
        ).fetchone()["cnt"]
        requests = db.execute(
            "SELECT r.*, u.username, u.first_name FROM requests r "
            "JOIN users u ON r.user_id = u.user_id "
            "WHERE r.status='pending' ORDER BY r.created_at ASC LIMIT ? OFFSET ?",
            (per_page, page * per_page),
        ).fetchall()

    if not requests:
        await query.edit_message_text(
            f"{E['check']} <b>Нет реквестов на рассмотрении!</b>\n\nВсе реквесты обработаны.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_button("utils_menu"),
        )
        return

    text = (
        f"{'━' * 30}\n"
        f"{E['inbox']}  <b>Реквесты на рассмотрении</b>  {E['inbox']}\n"
        f"{'━' * 30}\n"
        f"Страница {page + 1}/{max(1, (total + per_page - 1) // per_page)} │ "
        f"Всего: {total}\n\n"
    )

    keyboard = []
    for req in requests:
        diff_info = DIFFICULTIES.get(req["difficulty"], {})
        feat_emoji = FEATURE_EMOJIS.get(req["feature"], "")
        user_display = req["first_name"] or req["username"] or "Unknown"

        text += (
            f"{E['arrow_r']} <b>#{req['id']}</b> │ "
            f"Уровень: <code>{req['level_id']}</code>\n"
            f"   {diff_info.get('emoji', '')} {req['difficulty']} │ "
            f"{E['star']}{req['stars']} │ "
            f"{feat_emoji} {req['feature']}\n"
            f"   {E['user']} {user_display}\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(
                f"📋 #{req['id']} — Просмотр",
                callback_data=f"mod_review_{req['id']}",
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Пред.", callback_data="mod_req_prev"))
    if (page + 1) * per_page < total:
        nav_row.append(InlineKeyboardButton("➡️ След.", callback_data="mod_req_next"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton(f"{E['back']} Назад", callback_data="utils_menu")
    ])

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mod_req_page_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    page = context.user_data.get("mod_req_page", 0)
    if query.data == "mod_req_next":
        context.user_data["mod_req_page"] = page + 1
    elif query.data == "mod_req_prev":
        context.user_data["mod_req_page"] = max(0, page - 1)

    await mod_requests_list(update, context)


# ─── Просмотр реквеста модератором ───

async def mod_review_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_moderator(user):
        await query.edit_message_text(f"{E['ban']} Нет доступа.")
        return

    req_id = int(query.data.replace("mod_review_", ""))

    with get_db() as db:
        req = db.execute(
            "SELECT r.*, u.username, u.first_name, u.user_id as sender_id, u.warnings "
            "FROM requests r JOIN users u ON r.user_id = u.user_id WHERE r.id=?",
            (req_id,),
        ).fetchone()

    if not req:
        await query.edit_message_text(
            f"{E['cross']} Реквест не найден.",
            reply_markup=back_button("mod_requests_list"),
        )
        return

    diff_info = DIFFICULTIES.get(req["difficulty"], {})
    feat_emoji = FEATURE_EMOJIS.get(req["feature"], "")
    user_display = req["first_name"] or req["username"] or "Unknown"
    username_str = f"@{req['username']}" if req["username"] else "нет"
    created = datetime.fromisoformat(req["created_at"]).strftime("%d.%m.%Y %H:%M")

    text = (
        f"{'━' * 30}\n"
        f"{E['search']}  <b>Реквест #{req_id}</b>  {E['search']}\n"
        f"{'━' * 30}\n\n"
        f"{E['level']} <b>Данные уровня:</b>\n"
        f"  {E['id']} ID: <code>{req['level_id']}</code>\n"
        f"  {diff_info.get('emoji', '')} Сложность: <b>{req['difficulty']}</b>\n"
        f"  {E['star']} Звёзды: {get_stars_display(req['stars'])} ({req['stars']})\n"
        f"  {feat_emoji} Фичер: <b>{req['feature']}</b>\n\n"
        f"{E['user']} <b>Отправитель:</b>\n"
        f"  Имя: {user_display}\n"
        f"  Username: {username_str}\n"
        f"  ID: <code>{req['sender_id']}</code>\n"
        f"  {E['warn']} Предупреждений: {req['warnings']}/{WARNING_LIMIT}\n\n"
        f"{E['clock']} Дата: {created}\n"
        f"{'─' * 30}"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"{E['check']} Одобрить", callback_data=f"mod_approve_{req_id}"),
            InlineKeyboardButton(f"{E['cross']} Отклонить", callback_data=f"mod_reject_{req_id}"),
        ],
        [
            InlineKeyboardButton(
                f"{E['warn']} Предупреждение",
                callback_data=f"mod_warn_req_{req_id}",
            ),
        ],
        [InlineKeyboardButton(f"{E['back']} К списку", callback_data="mod_requests_list")],
    ]

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def mod_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_moderator(user):
        return

    req_id = int(query.data.replace("mod_approve_", ""))

    with get_db() as db:
        req = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
        if not req or req["status"] != "pending":
            await query.edit_message_text(
                f"{E['cross']} Реквест уже обработан или не найден.",
                reply_markup=back_button("mod_requests_list"),
            )
            return

        db.execute(
            "UPDATE requests SET status='approved', reviewed_by=?, reviewed_at=datetime('now') WHERE id=?",
            (user.id, req_id),
        )
        db.commit()

    diff_info = DIFFICULTIES.get(req["difficulty"], {})
    feat_emoji = FEATURE_EMOJIS.get(req["feature"], "")

    text = (
        f"{'━' * 30}\n"
        f"{E['check']}  <b>Реквест #{req_id} ОДОБРЕН</b>  {E['check']}\n"
        f"{'━' * 30}\n\n"
        f"  {E['id']} ID уровня: <code>{req['level_id']}</code>\n"
        f"  {diff_info.get('emoji', '')} {req['difficulty']} │ "
        f"{E['star']}{req['stars']} │ {feat_emoji} {req['feature']}\n\n"
        f"  {E['hammer']} Одобрил: <b>{user.first_name}</b>\n"
        f"{'─' * 30}"
    )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("mod_requests_list"),
    )

    # Уведомить игрока
    try:
        notify_text = (
            f"{E['party']} <b>Ваш реквест #{req_id} одобрен!</b>\n\n"
            f"Уровень <code>{req['level_id']}</code> был принят модерацией.\n"
            f"Ожидайте рейта в игре! {E['star']}"
        )
        await context.bot.send_message(
            chat_id=req["user_id"], text=notify_text, parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def mod_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_moderator(user):
        return

    req_id = int(query.data.replace("mod_reject_", ""))

    with get_db() as db:
        req = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
        if not req or req["status"] != "pending":
            await query.edit_message_text(
                f"{E['cross']} Реквест уже обработан или не найден.",
                reply_markup=back_button("mod_requests_list"),
            )
            return

        db.execute(
            "UPDATE requests SET status='rejected', reviewed_by=?, reviewed_at=datetime('now') WHERE id=?",
            (user.id, req_id),
        )
        db.commit()

    text = (
        f"{'━' * 30}\n"
        f"{E['cross']}  <b>Реквест #{req_id} ОТКЛОНЁН</b>  {E['cross']}\n"
        f"{'━' * 30}\n\n"
        f"  {E['id']} ID уровня: <code>{req['level_id']}</code>\n"
        f"  {E['hammer']} Отклонил: <b>{user.first_name}</b>\n"
        f"{'─' * 30}"
    )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("mod_requests_list"),
    )

    # Уведомить игрока
    try:
        notify_text = (
            f"{E['cross']} <b>Ваш реквест #{req_id} отклонён.</b>\n\n"
            f"Уровень <code>{req['level_id']}</code> не был принят.\n"
            f"Вы можете отправить новый реквест."
        )
        await context.bot.send_message(
            chat_id=req["user_id"], text=notify_text, parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


# ─── Предупреждение из реквеста ───

async def mod_warn_from_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_moderator(user):
        return

    req_id = int(query.data.replace("mod_warn_req_", ""))

    with get_db() as db:
        req = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
        if not req:
            await query.edit_message_text(
                f"{E['cross']} Реквест не найден.",
                reply_markup=back_button("mod_requests_list"),
            )
            return

        target_id = req["user_id"]
        target_user = db.execute("SELECT * FROM users WHERE user_id=?", (target_id,)).fetchone()

        if not target_user:
            await query.edit_message_text(f"{E['cross']} Пользователь не найден.")
            return

        # Проверить сброс предупреждений (7 дней)
        warnings = target_user["warnings"]
        if target_user["last_warning"]:
            last_warn = datetime.fromisoformat(target_user["last_warning"])
            if datetime.now() - last_warn > timedelta(days=WARNING_RESET_DAYS):
                warnings = 0

        warnings += 1

        if warnings >= WARNING_LIMIT:
            ban_until = (datetime.now() + timedelta(days=BAN_DURATION_DAYS)).isoformat()
            db.execute(
                "UPDATE users SET warnings=?, last_warning=datetime('now'), banned_until=? WHERE user_id=?",
                (warnings, ban_until, target_id),
            )
            # Отклоняем реквест
            db.execute(
                "UPDATE requests SET status='rejected', reviewed_by=?, reviewed_at=datetime('now'), review_note='Спам-реквест' WHERE id=?",
                (user.id, req_id),
            )
            db.commit()

            result_text = (
                f"{E['ban']} <b>Пользователь забанен!</b>\n\n"
                f"Предупреждений: {warnings}/{WARNING_LIMIT}\n"
                f"Бан на {BAN_DURATION_DAYS} дней.\n"
                f"Реквест #{req_id} отклонён."
            )

            # Уведомить пользователя
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        f"{E['ban']} <b>Вы были заблокированы в боте!</b>\n\n"
                        f"Причина: спам-реквесты ({warnings} предупреждений).\n"
                        f"Срок: {BAN_DURATION_DAYS} дней."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
        else:
            db.execute(
                "UPDATE users SET warnings=?, last_warning=datetime('now') WHERE user_id=?",
                (warnings, target_id),
            )
            # Отклоняем реквест
            db.execute(
                "UPDATE requests SET status='rejected', reviewed_by=?, reviewed_at=datetime('now'), review_note='Спам-реквест' WHERE id=?",
                (user.id, req_id),
            )
            db.commit()

            result_text = (
                f"{E['warn']} <b>Предупреждение выдано!</b>\n\n"
                f"Предупреждений: {warnings}/{WARNING_LIMIT}\n"
                f"Реквест #{req_id} отклонён."
            )

            # Уведомить пользователя
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        f"{E['warn']} <b>Вы получили предупреждение!</b>\n\n"
                        f"Причина: спам-реквест.\n"
                        f"Предупреждений: {warnings}/{WARNING_LIMIT}\n"
                        f"При {WARNING_LIMIT} предупреждениях — бан на {BAN_DURATION_DAYS} дней.\n"
                        f"Сброс предупреждений через {WARNING_RESET_DAYS} дней."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass

    await query.edit_message_text(
        result_text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("mod_requests_list"),
    )


# ─── Поиск реквеста по ID ───

async def mod_search_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_moderator(update.effective_user):
        return

    context.user_data["awaiting_search"] = True
    await query.edit_message_text(
        f"{E['search']} <b>Поиск реквеста</b>\n\n"
        f"Введите номер реквеста (например: 1, 5, 42):",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("utils_menu"),
    )


# ─── Выдать предупреждение ───

async def mod_warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    if not is_senior_mod(user):
        await query.edit_message_text(
            f"{E['ban']} Недостаточно прав. Требуется: Ст. Модератор или Владелец.",
            reply_markup=back_button("utils_menu"),
        )
        return

    context.user_data["awaiting_warn_user_id"] = True
    await query.edit_message_text(
        f"{E['warn']} <b>Выдать предупреждение</b>\n\n"
        f"Введите Telegram ID пользователя:",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("utils_menu"),
    )


# ══════════════════════════════════════════════════
#              OWNER FUNCTIONS
# ══════════════════════════════════════════════════

async def owner_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_owner(update.effective_user):
        await query.edit_message_text(f"{E['ban']} Только для владельца.")
        return

    text = (
        f"{'━' * 30}\n"
        f"{E['crown']}  <b>Управление ролями</b>  {E['crown']}\n"
        f"{'━' * 30}\n\n"
        f"Для управления ролями используйте команды:\n\n"
        f"<code>/setrole [user_id] moderator</code>\n"
        f"  — Назначить модератором\n\n"
        f"<code>/setrole [user_id] senior_mod</code>\n"
        f"  — Назначить ст. модератором\n\n"
        f"<code>/setrole [user_id] player</code>\n"
        f"  — Снять роль (обычный игрок)\n\n"
        f"{'─' * 30}\n"
        f"<b>Иерархия ролей:</b>\n"
        f"  {E['crown']} Владелец — полный доступ\n"
        f"  {E['shield']} Ст. Модератор — реквесты + предупреждения\n"
        f"  {E['hammer']} Модератор — реквесты\n"
        f"  {E['user']} Игрок — отправка реквестов\n"
        f"{'─' * 30}"
    )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("utils_menu"),
    )


async def setrole_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /setrole [user_id] [role]"""
    user = update.effective_user
    if not is_owner(user):
        await update.message.reply_text(f"{E['ban']} Только для владельца.")
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            f"Использование: <code>/setrole [user_id] [role]</code>\n"
            f"Роли: moderator, senior_mod, player",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text(f"{E['cross']} Некорректный ID.")
        return

    role = args[1].lower()
    if role not in ("moderator", "senior_mod", "player"):
        await update.message.reply_text(
            f"{E['cross']} Некорректная роль. Допустимые: moderator, senior_mod, player"
        )
        return

    with get_db() as db:
        target = db.execute("SELECT * FROM users WHERE user_id=?", (target_id,)).fetchone()
        if not target:
            await update.message.reply_text(f"{E['cross']} Пользователь не найден в базе. Он должен сначала написать /start боту.")
            return
        if target["role"] == "owner":
            await update.message.reply_text(f"{E['cross']} Нельзя изменить роль владельца.")
            return
        db.execute("UPDATE users SET role=? WHERE user_id=?", (role, target_id))
        db.commit()

    await update.message.reply_text(
        f"{E['check']} Роль пользователя <code>{target_id}</code> "
        f"(<b>{target['first_name']}</b>) изменена на: {get_role_badge(role)}",
        parse_mode=ParseMode.HTML,
    )

    # Уведомить пользователя
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"{E['sparkle']} <b>Ваша роль изменена!</b>\n\n"
                f"Новая роль: {get_role_badge(role)}\n"
                f"Изменил: {E['crown']} {user.first_name}"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def owner_bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_owner(update.effective_user):
        await query.edit_message_text(f"{E['ban']} Только для владельца.")
        return

    with get_db() as db:
        banned = db.execute(
            "SELECT * FROM users WHERE banned_until IS NOT NULL AND banned_until > datetime('now')"
        ).fetchall()

    if not banned:
        text = (
            f"{'━' * 30}\n"
            f"{E['ban']}  <b>Забаненные пользователи</b>  {E['ban']}\n"
            f"{'━' * 30}\n\n"
            f"{E['check']} Нет забаненных пользователей.\n"
            f"{'─' * 30}"
        )
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=back_button("utils_menu"),
        )
        return

    text = (
        f"{'━' * 30}\n"
        f"{E['ban']}  <b>Забаненные пользователи</b>  {E['ban']}\n"
        f"{'━' * 30}\n\n"
    )

    keyboard = []
    for u in banned:
        ban_end = datetime.fromisoformat(u["banned_until"])
        remaining = ban_end - datetime.now()
        days_left = remaining.days + 1
        username_str = f"@{u['username']}" if u["username"] else "—"

        text += (
            f"{E['user']} <b>{u['first_name']}</b> ({username_str})\n"
            f"  ID: <code>{u['user_id']}</code>\n"
            f"  {E['warn']} Предупреждений: {u['warnings']}\n"
            f"  {E['clock']} Осталось: {days_left} дн.\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(
                f"🔓 Разбанить {u['first_name']}",
                callback_data=f"owner_unban_{u['user_id']}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(f"{E['back']} Назад", callback_data="utils_menu")
    ])

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def owner_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_owner(update.effective_user):
        return

    target_id = int(query.data.replace("owner_unban_", ""))

    with get_db() as db:
        db.execute(
            "UPDATE users SET banned_until=NULL, warnings=0 WHERE user_id=?",
            (target_id,),
        )
        db.commit()
        target = db.execute("SELECT * FROM users WHERE user_id=?", (target_id,)).fetchone()

    name = target["first_name"] if target else str(target_id)

    await query.edit_message_text(
        f"{E['check']} <b>Пользователь {name} разбанен!</b>\n"
        f"Предупреждения сброшены.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_button("owner_bans"),
    )

    # Уведомить
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"{E['party']} <b>Вы были разбанены!</b>\n\n"
                f"Теперь вы снова можете пользоваться ботом.\n"
                f"Пожалуйста, не нарушайте правила."
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass


async def owner_mod_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_owner(update.effective_user):
        return

    with get_db() as db:
        mods = db.execute(
            "SELECT * FROM users WHERE role IN ('moderator', 'senior_mod', 'owner') ORDER BY role DESC"
        ).fetchall()

    text = (
        f"{'━' * 30}\n"
        f"{E['shield']}  <b>Команда модерации</b>  {E['shield']}\n"
        f"{'━' * 30}\n\n"
    )

    for m in mods:
        username_str = f"@{m['username']}" if m["username"] else "—"
        text += (
            f"{get_role_badge(m['role'])}\n"
            f"  {E['user']} {m['first_name']} ({username_str})\n"
            f"  {E['id']} <code>{m['user_id']}</code>\n\n"
        )

    await query.edit_message_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=back_button("utils_menu"),
    )


# ══════════════════════════════════════════════════
#         MESSAGE HANDLER (для поиска / варнов)
# ══════════════════════════════════════════════════

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений (поиск, предупреждения)."""
    user = update.effective_user
    text = update.message.text.strip()

    # Поиск реквеста
    if context.user_data.get("awaiting_search"):
        context.user_data.pop("awaiting_search", None)
        if not text.isdigit():
            await update.message.reply_text(
                f"{E['cross']} Введите числовой ID реквеста.",
                reply_markup=back_button("utils_menu"),
            )
            return

        req_id = int(text)
        with get_db() as db:
            req = db.execute(
                "SELECT r.*, u.username, u.first_name FROM requests r "
                "JOIN users u ON r.user_id = u.user_id WHERE r.id=?",
                (req_id,),
            ).fetchone()

        if not req:
            await update.message.reply_text(
                f"{E['cross']} Реквест #{req_id} не найден.",
                reply_markup=back_button("utils_menu"),
            )
            return

        diff_info = DIFFICULTIES.get(req["difficulty"], {})
        feat_emoji = FEATURE_EMOJIS.get(req["feature"], "")
        status_map = {"pending": f"{E['clock']} На рассмотрении", "approved": f"{E['check']} Одобрен", "rejected": f"{E['cross']} Отклонён"}
        created = datetime.fromisoformat(req["created_at"]).strftime("%d.%m.%Y %H:%M")

        result = (
            f"{'━' * 30}\n"
            f"{E['search']}  <b>Реквест #{req_id}</b>  {E['search']}\n"
            f"{'━' * 30}\n\n"
            f"  {E['id']} ID уровня: <code>{req['level_id']}</code>\n"
            f"  {diff_info.get('emoji', '')} Сложность: <b>{req['difficulty']}</b>\n"
            f"  {E['star']} Звёзды: {get_stars_display(req['stars'])} ({req['stars']})\n"
            f"  {feat_emoji} Фичер: <b>{req['feature']}</b>\n\n"
            f"  {E['user']} Отправитель: {req['first_name']}\n"
            f"  {E['clock']} Дата: {created}\n"
            f"  Статус: {status_map.get(req['status'], 'Неизвестно')}\n"
            f"{'─' * 30}"
        )

        keyboard = []
        if req["status"] == "pending":
            keyboard.append([
                InlineKeyboardButton(f"{E['check']} Одобрить", callback_data=f"mod_approve_{req_id}"),
                InlineKeyboardButton(f"{E['cross']} Отклонить", callback_data=f"mod_reject_{req_id}"),
            ])
        keyboard.append([InlineKeyboardButton(f"{E['back']} Назад", callback_data="utils_menu")])

        await update.message.reply_text(
            result, parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # Выдача предупреждения по ID
    if context.user_data.get("awaiting_warn_user_id"):
        context.user_data.pop("awaiting_warn_user_id", None)
        if not text.isdigit():
            await update.message.reply_text(f"{E['cross']} Введите числовой ID пользователя.")
            return

        target_id = int(text)

        with get_db() as db:
            target = db.execute("SELECT * FROM users WHERE user_id=?", (target_id,)).fetchone()
            if not target:
                await update.message.reply_text(
                    f"{E['cross']} Пользователь не найден.",
                    reply_markup=back_button("utils_menu"),
                )
                return

            if target["role"] in ("owner", "senior_mod"):
                await update.message.reply_text(
                    f"{E['cross']} Нельзя выдать предупреждение этому пользователю.",
                    reply_markup=back_button("utils_menu"),
                )
                return

            warnings = target["warnings"]
            if target["last_warning"]:
                last_warn = datetime.fromisoformat(target["last_warning"])
                if datetime.now() - last_warn > timedelta(days=WARNING_RESET_DAYS):
                    warnings = 0

            warnings += 1

            if warnings >= WARNING_LIMIT:
                ban_until = (datetime.now() + timedelta(days=BAN_DURATION_DAYS)).isoformat()
                db.execute(
                    "UPDATE users SET warnings=?, last_warning=datetime('now'), banned_until=? WHERE user_id=?",
                    (warnings, ban_until, target_id),
                )
            else:
                db.execute(
                    "UPDATE users SET warnings=?, last_warning=datetime('now') WHERE user_id=?",
                    (warnings, target_id),
                )
            db.commit()

        result = (
            f"{E['warn']} <b>Предупреждение выдано!</b>\n\n"
            f"{E['user']} {target['first_name']} (ID: <code>{target_id}</code>)\n"
            f"Предупреждений: {warnings}/{WARNING_LIMIT}\n"
        )
        if warnings >= WARNING_LIMIT:
            result += f"\n{E['ban']} Пользователь забанен на {BAN_DURATION_DAYS} дней."

        await update.message.reply_text(
            result, parse_mode=ParseMode.HTML,
            reply_markup=back_button("utils_menu"),
        )

        # Уведомить
        try:
            if warnings >= WARNING_LIMIT:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        f"{E['ban']} <b>Вы были заблокированы!</b>\n"
                        f"Предупреждений: {warnings}/{WARNING_LIMIT}\n"
                        f"Бан на {BAN_DURATION_DAYS} дней."
                    ),
                    parse_mode=ParseMode.HTML,
                )
            else:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=(
                        f"{E['warn']} <b>Вы получили предупреждение!</b>\n"
                        f"Предупреждений: {warnings}/{WARNING_LIMIT}\n"
                        f"Сброс через {WARNING_RESET_DAYS} дней."
                    ),
                    parse_mode=ParseMode.HTML,
                )
        except Exception:
            pass
        return


# ══════════════════════════════════════════════════
#                 HELP COMMAND
# ══════════════════════════════════════════════════

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = ensure_user(user)

    text = (
        f"{'━' * 30}\n"
        f"{E['info']}  <b>Помощь — Revival GDPS Bot</b>  {E['info']}\n"
        f"{'━' * 30}\n\n"
        f"<b>Основные команды:</b>\n"
        f"  /start — Главное меню\n"
        f"  /help — Эта справка\n\n"
        f"<b>Как отправить реквест:</b>\n"
        f"  1. Нажмите «{E['pencil']} Реквест» в меню\n"
        f"  2. Введите ID уровня (3-12 цифр)\n"
        f"  3. Выберите сложность и звёзды\n"
        f"  4. Выберите фичер\n"
        f"  5. Подтвердите отправку\n\n"
        f"<b>Лимиты:</b>\n"
        f"  {E['inbox']} Макс. 3 реквеста на рассмотрении\n"
        f"  {E['warn']} {WARNING_LIMIT} предупреждения = бан на {BAN_DURATION_DAYS} дней\n"
        f"  {E['clock']} Сброс предупреждений: {WARNING_RESET_DAYS} дней\n"
        f"{'─' * 30}"
    )

    if u["role"] in ("moderator", "senior_mod", "owner"):
        text += (
            f"\n\n<b>Команды модерации:</b>\n"
            f"  Используйте кнопку «{E['tools']} Утилиты»\n"
        )
    if u["role"] == "owner":
        text += (
            f"\n<b>Команды владельца:</b>\n"
            f"  /setrole [user_id] [role]\n"
            f"  /stats — Статистика бота\n"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════
#                 STATS COMMAND (owner)
# ══════════════════════════════════════════════════

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user):
        await update.message.reply_text(f"{E['ban']} Только для владельца.")
        return

    with get_db() as db:
        total_users = db.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        total_requests = db.execute("SELECT COUNT(*) as cnt FROM requests").fetchone()["cnt"]
        pending = db.execute("SELECT COUNT(*) as cnt FROM requests WHERE status='pending'").fetchone()["cnt"]
        approved = db.execute("SELECT COUNT(*) as cnt FROM requests WHERE status='approved'").fetchone()["cnt"]
        rejected = db.execute("SELECT COUNT(*) as cnt FROM requests WHERE status='rejected'").fetchone()["cnt"]
        banned = db.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE banned_until IS NOT NULL AND banned_until > datetime('now')"
        ).fetchone()["cnt"]
        mods = db.execute("SELECT COUNT(*) as cnt FROM users WHERE role IN ('moderator', 'senior_mod')").fetchone()["cnt"]

    text = (
        f"{'━' * 30}\n"
        f"{E['trophy']}  <b>Статистика бота</b>  {E['trophy']}\n"
        f"{'━' * 30}\n\n"
        f"{E['user']} Пользователей: <b>{total_users}</b>\n"
        f"{E['shield']} Модераторов: <b>{mods}</b>\n"
        f"{E['ban']} Забанено: <b>{banned}</b>\n\n"
        f"{E['inbox']} Всего реквестов: <b>{total_requests}</b>\n"
        f"  {E['clock']} Ожидают: <b>{pending}</b>\n"
        f"  {E['check']} Одобрено: <b>{approved}</b>\n"
        f"  {E['cross']} Отклонено: <b>{rejected}</b>\n"
        f"{'─' * 30}"
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ══════════════════════════════════════════════════
#                   MAIN
# ══════════════════════════════════════════════════

def main():
    """Запуск бота."""
    init_db()
    logger.info("База данных инициализирована")

    app = Application.builder().token(BOT_TOKEN).build()

    # ─── Conversation Handler для реквестов ───
    request_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(request_start, pattern="^request_start$"),
        ],
        states={
            STATE_LEVEL_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, request_level_id),
                CallbackQueryHandler(request_cancel, pattern="^request_cancel$"),
            ],
            STATE_DIFFICULTY: [
                CallbackQueryHandler(request_difficulty, pattern="^diff_"),
                CallbackQueryHandler(request_cancel, pattern="^request_cancel$"),
            ],
            STATE_STARS_PICK: [
                CallbackQueryHandler(request_stars_pick, pattern="^stars_"),
                CallbackQueryHandler(request_start, pattern="^request_start$"),
                CallbackQueryHandler(request_cancel, pattern="^request_cancel$"),
            ],
            STATE_FEATURE: [
                CallbackQueryHandler(request_feature, pattern="^feat_"),
                CallbackQueryHandler(request_cancel, pattern="^request_cancel$"),
            ],
            STATE_CONFIRM: [
                CallbackQueryHandler(request_submit, pattern="^request_submit$"),
                CallbackQueryHandler(request_cancel, pattern="^request_cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(request_cancel, pattern="^request_cancel$"),
            CommandHandler("start", start_command),
        ],
        per_message=False,
    )

    # ─── Регистрация хендлеров ───
    app.add_handler(request_conv)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("setrole", setrole_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^settings_menu$"))
    app.add_handler(CallbackQueryHandler(my_requests, pattern="^my_requests$"))
    app.add_handler(CallbackQueryHandler(utils_menu, pattern="^utils_menu$"))
    app.add_handler(CallbackQueryHandler(mod_requests_list, pattern="^mod_requests_list$"))
    app.add_handler(CallbackQueryHandler(mod_req_page_change, pattern="^mod_req_(prev|next)$"))
    app.add_handler(CallbackQueryHandler(mod_review_request, pattern=r"^mod_review_\d+$"))
    app.add_handler(CallbackQueryHandler(mod_approve, pattern=r"^mod_approve_\d+$"))
    app.add_handler(CallbackQueryHandler(mod_reject, pattern=r"^mod_reject_\d+$"))
    app.add_handler(CallbackQueryHandler(mod_warn_from_request, pattern=r"^mod_warn_req_\d+$"))
    app.add_handler(CallbackQueryHandler(mod_search_request, pattern="^mod_search_request$"))
    app.add_handler(CallbackQueryHandler(mod_warn_user, pattern="^mod_warn_user$"))
    app.add_handler(CallbackQueryHandler(owner_roles, pattern="^owner_roles$"))
    app.add_handler(CallbackQueryHandler(owner_bans, pattern="^owner_bans$"))
    app.add_handler(CallbackQueryHandler(owner_unban, pattern=r"^owner_unban_\d+$"))
    app.add_handler(CallbackQueryHandler(owner_mod_list, pattern="^owner_mod_list$"))

    # Обработка текстовых сообщений (поиск, варны)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("🚀 Revival GDPS Bot запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
