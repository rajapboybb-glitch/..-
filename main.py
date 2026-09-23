import asyncio
import logging
import sqlite3
import sys
import os
from os import getenv
from aiohttp import web

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- SOZLAMALAR ---
TOKEN = getenv("BOT_TOKEN", "8829743983:AAG4AjKrVc_xmeIvo7fHMARqNNCPdwBpthM")
ADMIN_ID = int(getenv("ADMIN_ID", "8923173548")) 

dp = Dispatcher()

# --- FSM HOLATLARI ---
class AddAnimeState(StatesGroup):
    waiting_for_code = State()
    waiting_for_title = State()
    waiting_for_photo = State()
    waiting_for_ep_count = State()
    waiting_for_genre = State()
    waiting_for_quality = State()
    waiting_for_dubbing = State()
    is_vip = State()

class DeleteAnimeState(StatesGroup):
    waiting_for_code = State()

class AddEpisodeVideoState(StatesGroup):
    waiting_for_code = State()
    waiting_for_ep_num = State()
    waiting_for_video = State()

class AddShortsState(StatesGroup):
    waiting_for_title = State()
    waiting_for_video = State()

class ChannelState(StatesGroup):
    waiting_for_channel = State()

class GiveVipState(StatesGroup):
    waiting_for_user_id = State()

class RemoveVipState(StatesGroup):
    waiting_for_user_id = State()

# --- MA'LUMOTLAR BAZASI ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    # Animelar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS animes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT,
            photo_id TEXT,
            episodes_count INTEGER DEFAULT 12,
            genre TEXT DEFAULT 'Sarguzasht',
            quality TEXT DEFAULT '720p - 1080p',
            dubbing TEXT DEFAULT 'Oʻzbekcha',
            is_vip INTEGER DEFAULT 0
        )
    """)
    
    # Qismlar (Videolar) jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_code TEXT,
            episode_num INTEGER,
            video_id TEXT,
            UNIQUE(anime_code, episode_num)
        )
    """)
    
    # Shorts jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            file_id TEXT
        )
    """)
    
    # Foydalanuvchilar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            is_vip INTEGER DEFAULT 0
        )
    """)

    # Sozlamalar jadvali
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def add_user(user_id: int, full_name: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name) VALUES (?, ?)", (user_id, full_name))
    conn.commit()
    conn.close()

def set_user_vip(user_id: int, status: int) -> bool:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        return False
    cursor.execute("UPDATE users SET is_vip = ? WHERE user_id = ?", (status, user_id))
    conn.commit()
    conn.close()
    return True

def is_user_vip(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT is_vip FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] == 1)

def add_anime(code: str, title: str, photo_id: str, ep_count: int, genre: str, quality: str, dubbing: str, is_vip: int = 0) -> bool:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO animes (code, title, photo_id, episodes_count, genre, quality, dubbing, is_vip) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (code, title, photo_id, ep_count, genre, quality, dubbing, is_vip))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    conn.close()
    return res

def add_or_update_episode(anime_code: str, ep_num: int, video_id: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO episodes (anime_code, episode_num, video_id)
        VALUES (?, ?, ?)
        ON CONFLICT(anime_code, episode_num) DO UPDATE SET video_id = excluded.video_id
    """, (anime_code, ep_num, video_id))
    conn.commit()
    conn.close()

def get_episode_video(anime_code: str, ep_num: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT video_id FROM episodes WHERE anime_code = ? AND episode_num = ?", (anime_code, ep_num))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def delete_anime_by_code(code: str) -> bool:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM animes WHERE code = ?", (code,))
    cursor.execute("DELETE FROM episodes WHERE anime_code = ?", (code,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def get_anime_by_code(code: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT title, photo_id, episodes_count, genre, quality, dubbing, is_vip 
        FROM animes WHERE code = ?
    """, (code,))
    result = cursor.fetchone()
    conn.close()
    return result

def add_shorts(title: str, file_id: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO shorts (title, file_id) VALUES (?, ?)", (title, file_id))
    conn.commit()
    conn.close()

def get_random_shorts():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT title, file_id FROM shorts ORDER BY RANDOM() LIMIT 1")
    result = cursor.fetchone()
    conn.close()
    return result

def get_stats():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_vip = 1")
    vip_users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM animes WHERE is_vip = 0")
    anime_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM animes WHERE is_vip = 1")
    vip_anime_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM shorts")
    shorts_count = cursor.fetchone()[0]
    conn.close()
    return users_count, vip_users_count, anime_count, vip_anime_count, shorts_count

def set_setting(key: str, value: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# --- MAJBURIY OBUNANI TEKSHIRISH ---
async def check_subscription(bot: Bot, user_id: int) -> bool:
    channel = get_setting("required_channel")
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception as e:
        logging.error(f"Obuna tekshirishda xatolik: {e}")
        return True

def get_sub_keyboard(channel: str):
    channel_link = channel.replace("@", "https://t.me/") if channel.startswith("@") else channel
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=channel_link)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")]
        ]
    )

# --- QISMLARNI TUGMALARGA BO'LISH (PAGINATION: PAGE BO'YICHA 24 TA) ---
def get_anime_episodes_keyboard(code: str, total_episodes: int, page: int = 1):
    items_per_page = 24
    start_ep = (page - 1) * items_per_page + 1
    end_ep = min(page * items_per_page, total_episodes)
    
    buttons = []
    row = []
    
    # Qismlar tugmalari (6 tadan bir qatorda)
    for ep in range(start_ep, end_ep + 1):
        row.append(InlineKeyboardButton(text=f"{ep}", callback_data=f"ep_{code}_{ep}"))
        if len(row) == 6:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
        
    # Sahifalash tugmalari (Pagination)
    nav_buttons = []
    total_pages = (total_episodes + items_per_page - 1) // items_per_page
    
    if page > 1:
        prev_start = (page - 2) * items_per_page + 1
        prev_end = (page - 1) * items_per_page
        nav_buttons.append(InlineKeyboardButton(text=f"⏮ {prev_start}-{prev_end}", callback_data=f"page_{code}_{page - 1}"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"📑 {page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        next_start = page * items_per_page + 1
        next_end = min((page + 1) * items_per_page, total_episodes)
        nav_buttons.append(InlineKeyboardButton(text=f"{next_start}-{next_end} ⏭", callback_data=f"page_{code}_{page + 1}"))
        
    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="⭐ Baholash", callback_data=f"rate_{code}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- KEYBOARDS ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Anime Izlash")],
        [KeyboardButton(text="👑 VIP Animelar"), KeyboardButton(text="💎 VIP Obuna")],
        [KeyboardButton(text="⚙️ Kabinet"), KeyboardButton(text="▶️ Shorts")],
        [KeyboardButton(text="📑 Qo'llanma"), KeyboardButton(text="📢 Reklama")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Anime Qo'shish"), KeyboardButton(text="🎬 Qism Video Qo'shish")],
        [KeyboardButton(text="🗑 Animeni O'chirish"), KeyboardButton(text="🎬 Shorts Qo'shish")],
        [KeyboardButton(text="⚙️ Majburiy obuna sozlamalari")],
        [KeyboardButton(text="👑 VIP Berish (ID)"), KeyboardButton(text="❌ VIP Olib tashlash (ID)")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🔙 Asosiy Menyu")]
    ],
    resize_keyboard=True
)

channel_setting_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Kanal ulash / O'zgartirish")],
        [KeyboardButton(text="❌ Obunani o'chirish")],
        [KeyboardButton(text="⬅️ Admin Menyu")]
    ],
    resize_keyboard=True
)

# --- HANDLERS ---

@dp.message(CommandStart())
async def command_start_handler(message: Message, bot: Bot) -> None:
    add_user(message.from_user.id, message.from_user.full_name)
    if not await check_subscription(bot, message.from_user.id):
        channel = get_setting("required_channel")
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:", reply_markup=get_sub_keyboard(channel))
        return

    await message.answer(
        f"Assalomu alaykum, {html.bold(message.from_user.full_name)}!\n\n"
        f"AniOlam botiga xush kelibsiz! Anime kodini yuboring yoki menyudan foydalaning:",
        reply_markup=main_keyboard
    )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery, bot: Bot):
    if await check_subscription(bot, callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Obuna tasdiqlandi!", reply_markup=main_keyboard)
    else:
        await callback.answer("❌ Siz hali kanalga obuna bo'lmadingiz!", show_alert=True)

# --- ADMIN PANEL ---

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_keyboard)
    else:
        await message.answer("❌ Siz admin emassiz!")

@dp.message(F.text == "🔙 Asosiy Menyu")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyuga qaytdingiz:", reply_markup=main_keyboard)

@dp.message(F.text == "⬅️ Admin Menyu")
async def back_to_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Admin menyuga qaytdingiz:", reply_markup=admin_keyboard)

@dp.message(F.text == "📊 Statistika")
async def stats_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        users, vip_users, animes, vips, shorts = get_stats()
        channel = get_setting("required_channel") or "Ulanmagan"
        await message.answer(
            f"📊 **Bot Statistikasi:**\n\n"
            f"👤 Foydalanuvchilar: {users} ta\n"
            f"👑 VIP Foydalanuvchilar: {vip_users} ta\n"
            f"🎬 Oddiy animelar: {animes} ta\n"
            f"👑 VIP animelar: {vips} ta\n"
            f"▶️ Shorts videolar: {shorts} ta\n"
            f"📢 Majburiy kanal: {channel}"
        )

# --- QISMGA VIDEO QO'SHISH (YANGI) ---
@dp.message(F.text == "🎬 Qism Video Qo'shish")
async def start_add_episode_video(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AddEpisodeVideoState.waiting_for_code)
        await message.answer("Video yuklamoqchi bo'lgan **ANIME KODI**ni kiriting (masalan: `101`):", reply_markup=ReplyKeyboardRemove())

@dp.message(AddEpisodeVideoState.waiting_for_code)
async def process_ep_code(message: Message, state: FSMContext):
    code = message.text.strip()
    anime = get_anime_by_code(code)
    if not anime:
        await message.answer("❌ Bunday kodli anime bazada topilmadi! Qaytadan kiriting yoki bekorni tanlang.")
        return
    await state.update_data(anime_code=code)
    await state.set_state(AddEpisodeVideoState.waiting_for_ep_num)
    await message.answer(f"Anime topildi: **{anime[0]}**\nNeshinchi qism videosini yuklamoqchisiz? (Raqam kiriting, masalan: `1`):")

@dp.message(AddEpisodeVideoState.waiting_for_ep_num)
async def process_ep_num(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Iltimos, faqat raqam kiriting!")
        return
    await state.update_data(ep_num=int(message.text))
    await state.set_state(AddEpisodeVideoState.waiting_for_video)
    await message.answer("Endi ushbu qism uchun **VIDEO FAYL**ni yuboring:")

@dp.message(AddEpisodeVideoState.waiting_for_video, F.video)
async def process_ep_video(message: Message, state: FSMContext):
    data = await state.get_data()
    add_or_update_episode(data['anime_code'], data['ep_num'], message.video.file_id)
    await message.answer(f"✅ **{data['anime_code']}** kodli animening **{data['ep_num']}-qismi** videosi muvaffaqiyatli saqlandi!", reply_markup=admin_keyboard)
    await state.clear()

# --- ANIME O'CHIRISH ---
@dp.message(F.text == "🗑 Animeni O'chirish")
async def start_delete_anime(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(DeleteAnimeState.waiting_for_code)
        await message.answer("🗑 O'chirmoqchi bo'lgan animenangiz **KOD**ini kiriting:", reply_markup=ReplyKeyboardRemove())

@dp.message(DeleteAnimeState.waiting_for_code)
async def process_delete_anime(message: Message, state: FSMContext):
    code = message.text.strip()
    if delete_anime_by_code(code):
        await message.answer(f"✅ Kod `{code}` bo'lgan anime va uning barcha qismlari bazadan o'chirildi!", reply_markup=admin_keyboard)
    else:
        await message.answer(f"❌ Kod `{code}` bo'lgan anime bazadan topilmadi!", reply_markup=admin_keyboard)
    await state.clear()

# --- YANGI ANIME QO'SHISH ---
@dp.message(F.text == "➕ Anime Qo'shish")
async def start_add_anime(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AddAnimeState.waiting_for_code)
        await message.answer("Yangi anime uchun **KOD** kiriting (masalan: `101`):", reply_markup=ReplyKeyboardRemove())

@dp.message(AddAnimeState.waiting_for_code)
async def process_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await state.set_state(AddAnimeState.waiting_for_title)
    await message.answer("Anime **NOMINI** kiriting (Masalan: `Naruto`):")

@dp.message(AddAnimeState.waiting_for_title)
async def process_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddAnimeState.waiting_for_photo)
    await message.answer("Anime uchun **POSTER (RASM)** yuboring:")

@dp.message(AddAnimeState.waiting_for_photo, F.photo)
async def process_photo(message: Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(AddAnimeState.waiting_for_ep_count)
    await message.answer("Anime umumiy nechta **QISM**dan iborat? (Raqam kiriting, masalan: `500`):")

@dp.message(AddAnimeState.waiting_for_ep_count)
async def process_ep_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Raqam kiriting!")
        return
    await state.update_data(ep_count=int(message.text))
    await state.set_state(AddAnimeState.waiting_for_genre)
    await message.answer("Anime **JANRI**ni kiriting (Masalan: `Sarguzasht, Jangari`):")

@dp.message(AddAnimeState.waiting_for_genre)
async def process_genre(message: Message, state: FSMContext):
    await state.update_data(genre=message.text.strip())
    await state.set_state(AddAnimeState.waiting_for_quality)
    await message.answer("Anime **SIFATINI** kiriting (Masalan: `720p - 1080p`):")

@dp.message(AddAnimeState.waiting_for_quality)
async def process_quality(message: Message, state: FSMContext):
    await state.update_data(quality=message.text.strip())
    await state.set_state(AddAnimeState.waiting_for_dubbing)
    await message.answer("Ovoz bergan studio/shaxs (Masalan: `AniMedia`):")

@dp.message(AddAnimeState.waiting_for_dubbing)
async def process_dubbing(message: Message, state: FSMContext):
    await state.update_data(dubbing=message.text.strip())
    await state.set_state(AddAnimeState.is_vip)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Oddiy Anime"), KeyboardButton(text="👑 VIP Anime")]],
        resize_keyboard=True
    )
    await message.answer("Ushbu anime turi qanday?", reply_markup=keyboard)

@dp.message(AddAnimeState.is_vip)
async def process_is_vip(message: Message, state: FSMContext):
    is_vip = 1 if "VIP" in message.text else 0
    data = await state.get_data()
    
    res = add_anime(
        code=data['code'],
        title=data['title'],
        photo_id=data['photo_id'],
        ep_count=data['ep_count'],
        genre=data['genre'],
        quality=data['quality'],
        dubbing=data['dubbing'],
        is_vip=is_vip
    )
    
    if res:
        await message.answer("✅ Anime muvaffaqiyatli saqlandi!\n\nEndi '🎬 Qism Video Qo'shish' tugmasi orqali qismlariga video yuklashingiz mumkin.", reply_markup=admin_keyboard)
    else:
        await message.answer("❌ Xatolik: Bu kod bazada mavjud!", reply_markup=admin_keyboard)
    await state.clear()

# --- VIP BERISH / OLIB TASHALASH ---
@dp.message(F.text == "👑 VIP Berish (ID)")
async def start_give_vip(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(GiveVipState.waiting_for_user_id)
        await message.answer("👑 VIP beriladigan foydalanuvchining **Telegram ID** sini kiriting:", reply_markup=ReplyKeyboardRemove())

@dp.message(GiveVipState.waiting_for_user_id)
async def process_give_vip(message: Message, state: FSMContext):
    user_id_text = message.text.strip()
    if not user_id_text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak:")
        return

    user_id = int(user_id_text)
    if set_user_vip(user_id, status=1):
        await message.answer(f"✅ Foydalanuvchi `{user_id}` ga VIP statusi berildi!", reply_markup=admin_keyboard)
    else:
        await message.answer("❌ Foydalanuvchi bazadan topilmadi!", reply_markup=admin_keyboard)
    await state.clear()

@dp.message(F.text == "❌ VIP Olib tashlash (ID)")
async def start_remove_vip(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(RemoveVipState.waiting_for_user_id)
        await message.answer("❌ VIP olib tashlanadigan **Telegram ID** ni kiriting:", reply_markup=ReplyKeyboardRemove())

@dp.message(RemoveVipState.waiting_for_user_id)
async def process_remove_vip(message: Message, state: FSMContext):
    user_id_text = message.text.strip()
    if not user_id_text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak:")
        return

    user_id = int(user_id_text)
    if set_user_vip(user_id, status=0):
        await message.answer(f"✅ Foydalanuvchi `{user_id}` dan VIP olib tashlandi!", reply_markup=admin_keyboard)
    else:
        await message.answer("❌ Foydalanuvchi bazadan topilmadi!", reply_markup=admin_keyboard)
    await state.clear()

# --- SHORTS QO'SHISH ---
@dp.message(F.text == "🎬 Shorts Qo'shish")
async def start_add_shorts(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(AddShortsState.waiting_for_title)
        await message.answer("Shorts uchun sarlavha kiriting:", reply_markup=ReplyKeyboardRemove())

@dp.message(AddShortsState.waiting_for_title)
async def process_shorts_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddShortsState.waiting_for_video)
    await message.answer("Shorts **VIDEO FAYLINI** yuboring:")

@dp.message(AddShortsState.waiting_for_video, F.video)
async def process_shorts_video(message: Message, state: FSMContext):
    data = await state.get_data()
    add_shorts(data['title'], message.video.file_id)
    await message.answer("✅ Shorts muvaffaqiyatli saqlandi!", reply_markup=admin_keyboard)
    await state.clear()

# --- MAJBURIY OBUNA ---
@dp.message(F.text == "⚙️ Majburiy obuna sozlamalari")
async def sub_settings_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        channel = get_setting("required_channel")
        status = f"Hozirgi kanal: {channel}" if channel else "Hozircha kanal o'rnatilmagan."
        await message.answer(f"⚙️ **Majburiy obuna sozlamalari**\n\n{status}", reply_markup=channel_setting_keyboard)

@dp.message(F.text == "➕ Kanal ulash / O'zgartirish")
async def add_channel_start(message: Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.set_state(ChannelState.waiting_for_channel)
        await message.answer("📢 Kanal username-ini kiriting (`@kanalim_uz`):", reply_markup=ReplyKeyboardRemove())

@dp.message(ChannelState.waiting_for_channel)
async def process_channel_input(message: Message, state: FSMContext):
    channel = message.text.strip()
    if not channel.startswith("@"):
        await message.answer("❌ Kanal username-i `@` bilan boshlanishi kerak!")
        return
    set_setting("required_channel", channel)
    await state.clear()
    await message.answer(f"✅ Kanal `{channel}` ga o'zgartirildi!", reply_markup=channel_setting_keyboard)

@dp.message(F.text == "❌ Obunani o'chirish")
async def remove_channel_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        set_setting("required_channel", "")
        await message.answer("✅ Majburiy obuna o'chirildi!", reply_markup=channel_setting_keyboard)

# --- FOYDALANUVCHI TUGMALARI ---
@dp.message(F.text == "▶️ Shorts")
async def user_shorts_handler(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        channel = get_setting("required_channel")
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:", reply_markup=get_sub_keyboard(channel))
        return
    
    shorts = get_random_shorts()
    if shorts:
        title, file_id = shorts
        await message.answer_video(video=file_id, caption=f"🎬 <b>{title}</b>\n\nYana ko'rish uchun ▶️ Shorts tugmasini bosing!")
    else:
        await message.answer("🎬 Hozircha Shorts qo'shilmagan.")

@dp.message(F.text == "🔍 Anime Izlash")
async def anime_search_handler(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        channel = get_setting("required_channel")
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:", reply_markup=get_sub_keyboard(channel))
        return
    await message.answer("🔎 Anime kodini kiriting (Masalan: `101`):")

@dp.message(F.text == "👑 VIP Animelar")
async def vip_anime_info(message: Message):
    await message.answer("👑 VIP Animelarni tomosha qilish uchun sizda VIP maqom bo'lishi kerak. Obuna olish uchun '💎 VIP Obuna' bo'limiga o'ting.")

@dp.message(F.text == "💎 VIP Obuna")
async def vip_sub_handler(message: Message):
    await message.answer("💳 VIP obuna xarid qilish uchun adminga murojaat qiling:\n\n🆔 ID: `" + str(message.from_user.id) + "`")

@dp.message(F.text == "⚙️ Kabinet")
async def cabinet_handler(message: Message):
    vip_status = "👑 VIP A'zo" if is_user_vip(message.from_user.id) else "👤 Oddiy a'zo"
    await message.answer(f"👤 **Kabinet:**\n\n🆔 ID: `{message.from_user.id}`\n👤 Ism: {message.from_user.full_name}\n💎 Maqom: {vip_status}")

@dp.message(F.text == "📑 Qo'llanma")
async def guide_handler(message: Message):
    await message.answer("📖 Botdan foydalanish:\n1. Anime kodini yuboring.\n2. Qism raqamini tanlang va tomosha qiling!")

@dp.message(F.text == "📢 Reklama")
async def ad_handler(message: Message):
    await message.answer("📢 Reklama bo'yicha adminga murojaat qiling.")

# --- INLINE TUGMALAR HANDLERS (SAHIFALASH VA QISM YUBORISH) ---
@dp.callback_query(F.data.startswith("page_"))
async def page_callback_handler(callback: CallbackQuery):
    _, code, page = callback.data.split("_")
    page = int(page)
    
    anime = get_anime_by_code(code)
    if anime:
        total_episodes = anime[2]
        keyboard = get_anime_episodes_keyboard(code, total_episodes, page)
        await callback.message.edit_reply_markup(reply_markup=keyboard)
        await callback.answer(f"{page}-bo'lim")
    else:
        await callback.answer("Anime topilmadi!", show_alert=True)

@dp.callback_query(F.data == "noop")
async def noop_callback_handler(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data.startswith("ep_"))
async def episode_callback_handler(callback: CallbackQuery, bot: Bot):
    _, code, ep = callback.data.split("_")
    ep_num = int(ep)
    
    anime = get_anime_by_code(code)
    if not anime:
        await callback.answer("Anime topilmadi!", show_alert=True)
        return

    title = anime[0]
    video_id = get_episode_video(code, ep_num)
    
    if video_id:
        channel = get_setting("required_channel") or "@AniOlam"
        caption = f"🎬 <b>{title}</b>\n▶️ <b>{ep_num}-qism</b>\n\n⚙️ @{(await bot.get_me()).username}"
        await callback.message.answer_video(video=video_id, caption=caption)
        await callback.answer()
    else:
        await callback.answer(f"⚠️ {ep_num}-qism videosi hali yuklanmagan!", show_alert=True)

@dp.callback_query(F.data.startswith("rate_"))
async def rate_callback_handler(callback: CallbackQuery):
    await callback.answer("Bahoingiz qabul qilindi! ⭐ 5/5", show_alert=True)

# --- KOD BO'YICHA ANIME QIDIRUV ---
@dp.message()
async def search_anime_handler(message: Message, bot: Bot):
    if not await check_subscription(bot, message.from_user.id):
        channel = get_setting("required_channel")
        await message.answer("⚠️ Botdan foydalanish uchun kanalga obuna bo'ling:", reply_markup=get_sub_keyboard(channel))
        return

    code = message.text.strip()
    anime = get_anime_by_code(code)
    
    if anime:
        title, photo_id, ep_count, genre, quality, dubbing, is_vip = anime
        
        if is_vip and not is_user_vip(message.from_user.id):
            await message.answer("👑 Ushbu anime **VIP** hisoblanadi! VIP Obuna xarid qiling.")
            return

        channel = get_setting("required_channel") or "@AniOlam"
        
        caption = (
            f"💻 <b>Anime nomi: {title}</b>\n\n"
            f"╭─────────────────────\n"
            f"├▶ <b>Holati:</b> {ep_count} qism\n"
            f"├▶ <b>Sifat:</b> {quality}\n"
            f"├▶ <b>Janrlari:</b> {genre}\n"
            f"├▶ <b>Kanal:</b> {channel}\n"
            f"├▶ <b>Ovoz:</b> {dubbing}\n"
            f"╰─────────────────────\n\n"
            f"⚙️ <b>Botimiz:</b> @{(await bot.get_me()).username}\n"
            f"🆔 <b>Anime KODI:</b> {code}\n"
            f"⭐ <b>Reyting:</b> 4.8 / 5"
        )
        
        # Birinchi sahifa (1-24 qismlar)
        keyboard = get_anime_episodes_keyboard(code, ep_count, page=1)
        
        if photo_id:
            await message.answer_photo(
                photo=photo_id, 
                caption=caption, 
                reply_markup=keyboard
            )
        else:
            await message.answer(
                text=caption, 
                reply_markup=keyboard
            )
    else:
        await message.answer("❌ Afsuski, bu kod bo'yicha anime topilmadi.")

# --- RENDER VEB-SERVER ---
async def handle(request):
    return web.Response(text="Bot ishlayapti!")

async def main() -> None:
    init_db()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())