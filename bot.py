import sqlite3
import random
import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8762403455:AAHHDxlkFYY-2A473djM7YuP-HzdF7wfPMc"
ADMIN_IDS = [5932847351]
COOLDOWN_HOURS = 1

storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

conn = sqlite3.connect("wordengine.db", check_same_thread=False)
cursor = conn.cursor()

# ===== DB =====
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    last_test TIMESTAMP,
    streak INTEGER DEFAULT 0,
    last_streak_date DATE
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
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
    total INTEGER
)""")

conn.commit()

# ===== STATES =====
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

class AdminStates(StatesGroup):
    add_words = State()
    broadcast = State()
    select_user = State()

# ===== HELPERS =====
def get_sections():
    cursor.execute("SELECT id, name FROM sections")
    return cursor.fetchall()

def get_words(section_id):
    cursor.execute("SELECT word, translation FROM words WHERE section_id=?", (section_id,))
    return cursor.fetchall()

def save_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

# ===== KEYBOARDS =====
def main_kb():
    kb = [
        [types.KeyboardButton(text="Start Test")],
        [types.KeyboardButton(text="My Stats")],
        [types.KeyboardButton(text="Leaderboard")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def section_kb():
    sections = get_sections()
    kb = [[types.KeyboardButton(text=f"{s[0]}:{s[1]}")] for s in sections]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ===== START =====
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    save_user(msg.from_user.id)
    await msg.answer("🚀 WordEngine", reply_markup=main_kb())

# ===== ADMIN =====
@dp.message(F.text == "/admin")
async def admin(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Add Words")],
            [types.KeyboardButton(text="All Stats")],
            [types.KeyboardButton(text="Broadcast All")],
            [types.KeyboardButton(text="Broadcast One")]
        ],
        resize_keyboard=True
    )
    await msg.answer("Admin panel", reply_markup=kb)

# ===== ADD WORDS BULK =====
@dp.message(F.text == "Add Words")
async def add_words(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("Format:\nApple - olma\nInterested - qiziqarli")
    await state.set_state(AdminStates.add_words)

@dp.message(AdminStates.add_words)
async def save_words(msg: types.Message, state: FSMContext):
    lines = msg.text.split("\n")
    section_id = 1  # default (xohlasang keyin tanlash qo‘shamiz)

    count = 0
    for l in lines:
        if "-" in l:
            word, trans = l.split("-", 1)
            cursor.execute("INSERT INTO words (section_id, word, translation) VALUES (?,?,?)",
                           (section_id, word.strip(), trans.strip()))
            count += 1

    conn.commit()
    await msg.answer(f"✅ {count} ta so‘z qo‘shildi")
    await state.clear()

# ===== TEST =====
@dp.message(F.text == "Start Test")
async def start_test(msg: types.Message, state: FSMContext):
    await msg.answer("Section tanlang:", reply_markup=section_kb())
    await state.set_state(TestStates.waiting_section)

@dp.message(TestStates.waiting_section)
async def choose_section(msg: types.Message, state: FSMContext):
    sid = int(msg.text.split(":")[0])
    words = get_words(sid)
    random.shuffle(words)

    await state.update_data(words=words, i=0, score=0, sid=sid)
    await ask(msg, state)

async def ask(msg, state):
    d = await state.get_data()

    if d["i"] >= len(d["words"]):
        await msg.answer(f"Natija: {d['score']}/{len(d['words'])}")
        await state.clear()
        return

    word, trans = d["words"][d["i"]]

    # 🔥 Uzbekni chiqaramiz
    await msg.answer(f"Tarjima qiling: <b>{trans}</b>", parse_mode="HTML")

    await state.update_data(correct=word)
    await state.set_state(TestStates.waiting_answer)

@dp.message(TestStates.waiting_answer)
async def answer(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    correct = d["correct"].lower()

    score = d["score"]
    if msg.text.lower() == correct:
        score += 1

    await state.update_data(score=score, i=d["i"]+1)
    await ask(msg, state)

# ===== STATS =====
@dp.message(F.text == "My Stats")
async def stats(msg: types.Message):
    cursor.execute("SELECT COUNT(*) FROM attempts WHERE user_id=?", (msg.from_user.id,))
    c = cursor.fetchone()[0]
    await msg.answer(f"Siz {c} ta test ishlagansiz")

@dp.message(F.text == "Leaderboard")
async def lb(msg: types.Message):
    cursor.execute("SELECT user_id, SUM(score) FROM attempts GROUP BY user_id ORDER BY SUM(score) DESC LIMIT 5")
    rows = cursor.fetchall()

    text = "Top:\n"
    for r in rows:
        text += f"{r[0]} - {r[1]}\n"

    await msg.answer(text)

# ===== ALL STATS =====
@dp.message(F.text == "All Stats")
async def all_stats(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT user_id, COUNT(*) FROM attempts GROUP BY user_id")
    rows = cursor.fetchall()

    text = ""
    for r in rows:
        text += f"{r[0]} - {r[1]} test\n"

    await msg.answer(text or "Bo‘sh")

# ===== BROADCAST ALL =====
@dp.message(F.text == "Broadcast All")
async def bc_all(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("Xabar yozing:")
    await state.set_state(AdminStates.broadcast)

@dp.message(AdminStates.broadcast)
async def send_all(msg: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()

    for u in users:
        try:
            await bot.send_message(u[0], msg.text)
            await asyncio.sleep(0.05)
        except:
            pass

    await msg.answer("Yuborildi")
    await state.clear()

# ===== BROADCAST ONE =====
@dp.message(F.text == "Broadcast One")
async def bc_one(msg: types.Message, state: FSMContext):
    await msg.answer("User ID yoz:")
    await state.set_state(AdminStates.select_user)

@dp.message(AdminStates.select_user)
async def send_one(msg: types.Message, state: FSMContext):
    uid = int(msg.text)
    await state.update_data(uid=uid)
    await msg.answer("Xabar yozing:")
    await state.set_state(AdminStates.broadcast)

@dp.message(AdminStates.broadcast)
async def send_one_final(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    await bot.send_message(d["uid"], msg.text)
    await msg.answer("Yuborildi")
    await state.clear()

# ===== RUN =====
async def main():
    print("Bot ishga tushdi")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())