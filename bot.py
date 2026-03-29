import sqlite3
import random
import asyncio
import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ====== CONFIG ======
TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"
ADMIN_IDS = [5932847351]
COOLDOWN_HOURS = 1

# ====== BOT ======
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ====== DATABASE ======
conn = sqlite3.connect("wordengine.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_test TIMESTAMP,
    streak INTEGER DEFAULT 0,
    last_streak_date DATE
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE,
    quiz_type TEXT DEFAULT 'translation'
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER,
    word TEXT,
    translation TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    section_id INTEGER,
    score INTEGER,
    total INTEGER,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()

# ====== KEYBOARDS (FIXED) ======
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Start Test"), KeyboardButton(text="My Stats")],
        [KeyboardButton(text="Leaderboard"), KeyboardButton(text="Weak Words")]
    ],
    resize_keyboard=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Add Section"), KeyboardButton(text="Add Words Bulk")],
        [KeyboardButton(text="Set Quiz Type"), KeyboardButton(text="Send Broadcast")],
        [KeyboardButton(text="View All Stats"), KeyboardButton(text="Back to Main")]
    ],
    resize_keyboard=True
)

# ====== HELPERS ======
def get_sections():
    cursor.execute("SELECT id, name FROM sections")
    return cursor.fetchall()

# ====== FSM ======
class AdminStates(StatesGroup):
    waiting_new_section = State()
    waiting_section_for_word = State()
    waiting_word_bulk = State()
    waiting_broadcast = State()

# ====== START ======
@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer("🎉 WordEngine botiga xush kelibsiz!", reply_markup=main_kb)

# ====== ADMIN ======
@dp.message(F.text == "/admin")
async def admin_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("👨‍💻 Admin panel", reply_markup=admin_kb)

# ====== ADD SECTION ======
@dp.message(F.text == "Add Section")
async def add_section(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("Section nomini yoz:")
    await state.set_state(AdminStates.waiting_new_section)

@dp.message(AdminStates.waiting_new_section)
async def save_section(msg: Message, state: FSMContext):
    try:
        cursor.execute("INSERT INTO sections (name) VALUES (?)", (msg.text,))
        conn.commit()
        await msg.answer("✅ Qo‘shildi")
    except:
        await msg.answer("❌ Mavjud!")
    await state.clear()

# ====== BULK WORDS ======
@dp.message(F.text == "Add Words Bulk")
async def bulk_start(msg: Message, state: FSMContext):
    sections = get_sections()
    if not sections:
        await msg.answer("Section yo‘q!")
        return

    text = "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(f"Section tanla:\n{text}")
    await state.set_state(AdminStates.waiting_section_for_word)

@dp.message(AdminStates.waiting_section_for_word)
async def bulk_section(msg: Message, state: FSMContext):
    await state.update_data(section_id=int(msg.text))
    await msg.answer("Format:\nword-translation")
    await state.set_state(AdminStates.waiting_word_bulk)

@dp.message(AdminStates.waiting_word_bulk)
async def bulk_save(msg: Message, state: FSMContext):
    data = await state.get_data()
    sid = data['section_id']

    lines = msg.text.split("\n")
    count = 0

    for l in lines:
        if "-" in l:
            w, t = l.split("-", 1)
            cursor.execute("INSERT INTO words (section_id, word, translation) VALUES (?, ?, ?)", (sid, w.strip(), t.strip()))
            count += 1

    conn.commit()
    await msg.answer(f"✅ {count} ta qo‘shildi")
    await state.clear()

# ====== BROADCAST ======
@dp.message(F.text == "Send Broadcast")
async def broadcast_start(msg: Message, state: FSMContext):
    await msg.answer("Xabar yoz:")
    await state.set_state(AdminStates.waiting_broadcast)

@dp.message(AdminStates.waiting_broadcast)
async def broadcast_send(msg: Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    sent = 0
    for u in users:
        try:
            await bot.send_message(u[0], msg.text)
            sent += 1
        except:
            pass

    await msg.answer(f"✅ {sent} ta userga yuborildi")
    await state.clear()

# ====== RUN ======
async def main():
    print("Bot ishladi 🚀")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())