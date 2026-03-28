import sqlite3
import random
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import datetime
import matplotlib.pyplot as plt
import io

# ====== CONFIG ======
TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"  
ADMIN_IDS = [5932847351, 123456789]
COOLDOWN_HOURS = 1

# ====== BOT & FSM ======
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# ====== DATABASE ======
conn = sqlite3.connect("wordengine.db")
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY,
last_test TIMESTAMP
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS sections (
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
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

# ====== HELPERS ======
def get_sections():
    cursor.execute("SELECT id, name, quiz_type FROM sections")
    return cursor.fetchall()

def get_words(section_id):
    cursor.execute("SELECT word, translation FROM words WHERE section_id=?", (section_id,))
    return cursor.fetchall()

def can_take_test(user_id):
    cursor.execute("SELECT last_test FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if row is None:
        return True
    last_test = datetime.datetime.fromisoformat(row[0])
    return (datetime.datetime.now() - last_test).total_seconds() >= COOLDOWN_HOURS * 3600

def update_last_test(user_id):
    now = datetime.datetime.now().isoformat()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, last_test) VALUES (?,?)", (user_id, now))
    conn.commit()

# ====== FSM ======
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

class AdminStates(StatesGroup):
    waiting_new_section = State()
    waiting_section_choice = State()
    waiting_word_input = State()
    sending_broadcast = State()
    waiting_quiz_type = State()  # ✅ FIX

admin_section_choice = {}

# ====== START ======
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Start Test")],
            [types.KeyboardButton(text="My Stats")],
            [types.KeyboardButton(text="Leaderboard")]
        ],
        resize_keyboard=True
    )
    await msg.answer("WordEngine ga xush kelibsiz!", reply_markup=kb)

# ====== ADMIN ======
@dp.message(F.text == "/admin")
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Add Section")],
            [types.KeyboardButton(text="Add Word")],
            [types.KeyboardButton(text="Set Quiz Type")],
            [types.KeyboardButton(text="Send Broadcast")]
        ],
        resize_keyboard=True
    )
    await msg.answer("Admin panel", reply_markup=kb)

# ====== ADD SECTION ======
@dp.message(F.text == "Add Section")
async def add_section(msg: types.Message):
    await msg.answer("Section nomi:")
    await AdminStates.waiting_new_section.set()

@dp.message(AdminStates.waiting_new_section)
async def save_section(msg: types.Message):
    cursor.execute("INSERT INTO sections (name) VALUES (?)", (msg.text,))
    conn.commit()
    await msg.answer("✅ Qo‘shildi")
    await AdminStates.waiting_new_section.clear()

# ====== ADD WORD ======
@dp.message(F.text == "Add Word")
async def add_word(msg: types.Message):
    sections = get_sections()
    text = "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text)
    await AdminStates.waiting_section_choice.set()

@dp.message(AdminStates.waiting_section_choice)
async def choose_section(msg: types.Message):
    admin_section_choice[msg.from_user.id] = int(msg.text)
    await msg.answer("word - translation")
    await AdminStates.waiting_word_input.set()

@dp.message(AdminStates.waiting_word_input)
async def save_word(msg: types.Message):
    try:
        word, trans = msg.text.split(" - ")
        sec = admin_section_choice[msg.from_user.id]
        cursor.execute("INSERT INTO words VALUES (NULL,?,?,?)", (sec, word, trans))
        conn.commit()
        await msg.answer("✅ Qo‘shildi")
        await AdminStates.waiting_word_input.clear()
    except:
        await msg.answer("❌ Format: word - translation")

# ====== QUIZ TYPE ======
@dp.message(F.text == "Set Quiz Type")
async def set_quiz(msg: types.Message, state: FSMContext):
    sections = get_sections()
    text = "\n".join([f"{s[0]}: {s[1]} ({s[2]})" for s in sections])
    await msg.answer(text + "\nFormat: 1 MCQ")
    await state.set_state(AdminStates.waiting_quiz_type)

@dp.message(AdminStates.waiting_quiz_type)
async def save_quiz(msg: types.Message, state: FSMContext):
    try:
        sid, qt = msg.text.split()
        if qt not in ["MCQ", "translation"]:
            raise ValueError
        cursor.execute("UPDATE sections SET quiz_type=? WHERE id=?", (qt, int(sid)))
        conn.commit()
        await msg.answer("✅ Saqlandi")
        await state.clear()
    except:
        await msg.answer("❌ Format: 1 MCQ")

# ====== TEST ======
@dp.message(F.text == "Start Test")
async def start_test(msg: types.Message, state: FSMContext):
    sections = get_sections()
    text = "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text)
    await state.set_state(TestStates.waiting_section)

@dp.message(TestStates.waiting_section)
async def choose_test(msg: types.Message, state: FSMContext):
    sid = int(msg.text)
    words = get_words(sid)
    random.shuffle(words)
    cursor.execute("SELECT quiz_type FROM sections WHERE id=?", (sid,))
    qt = cursor.fetchone()[0]
    await state.update_data(words=words, i=0, score=0, qt=qt)
    await ask(msg, state)

async def ask(msg, state):
    d = await state.get_data()
    if d["i"] >= len(d["words"]):
        await msg.answer(f"Score: {d['score']}/{len(d['words'])}")
        await state.clear()
        return

    w, t = d["words"][d["i"]]
    if d["qt"] == "MCQ":
        opts = [x[1] for x in d["words"] if x[1] != t][:3] + [t]
        random.shuffle(opts)
        kb = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text=o)] for o in opts],
            resize_keyboard=True
        )
        await msg.answer(f"{w}", reply_markup=kb)
    else:
        await msg.answer(f"{w}")
    await state.update_data(correct=t)
    await state.set_state(TestStates.waiting_answer)

@dp.message(TestStates.waiting_answer)
async def check(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    if msg.text.strip() == d["correct"]:
        d["score"] += 1
    d["i"] += 1
    await state.update_data(score=d["score"], i=d["i"])
    await ask(msg, state)

# ====== RUN ======
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())