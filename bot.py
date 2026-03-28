import sqlite3
import random
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import datetime

# ====== CONFIG ======
TOKEN = "8692757311:AAFFTPdtqd7NGn1w_QL1yZQbDN1lWvtCMxY"  
ADMIN_ID = 5932847351
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
    name TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER,
    word TEXT,
    translation TEXT,
    FOREIGN KEY(section_id) REFERENCES sections(id)
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
    cursor.execute("SELECT id, name FROM sections")
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
    now = datetime.datetime.now()
    diff = now - last_test
    return diff.total_seconds() >= COOLDOWN_HOURS * 3600

def update_last_test(user_id):
    now = datetime.datetime.now().isoformat()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, last_test) VALUES (?,?)", (user_id, now))
    conn.commit()

# ====== FSM ======
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

# ====== START ======
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Start Test")],
            [types.KeyboardButton(text="My Stats")]
        ],
        resize_keyboard=True
    )
    await msg.answer("WordEngine ga xush kelibsiz! Section tanlang. Bu XOS õquvchilari uchun mahsus bot :", reply_markup=kb)

# ====== ADMIN PANEL ======
@dp.message(F.text == "/admin")
async def admin_panel(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Add Section")],
            [types.KeyboardButton(text="Add Word")]
        ],
        resize_keyboard=True
    )
    await msg.answer("Admin panelga xush kelibsiz", reply_markup=kb)

# ====== ADD SECTION ======
@dp.message(F.text == "Add Section")
async def add_section(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer("Section nomini yozing:")

    @dp.message()
    async def save_section(m: types.Message):
        if m.from_user.id != ADMIN_ID:
            return
        cursor.execute("INSERT INTO sections (name) VALUES (?)", (m.text,))
        conn.commit()
        await m.answer(f"Section '{m.text}' qo'shildi!")

# ====== ADD WORD ======
@dp.message(F.text == "Add Word")
async def add_word(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    sections = get_sections()
    text = "Qaysi sectionga qo'shasiz?\n"
    for sec in sections:
        text += f"{sec[0]}: {sec[1]}\n"
    await msg.answer(text)

    @dp.message()
    async def choose_section(m: types.Message):
        if m.from_user.id != ADMIN_ID:
            return
        try:
            section_id = int(m.text)
        except:
            await m.answer("Faqat raqam kiriting!")
            return
        await m.answer("Word va translation formatida yozing: word - translation")

        @dp.message()
        async def save_word(mm: types.Message):
            if mm.from_user.id != ADMIN_ID:
                return
            try:
                word, trans = mm.text.split(" - ")
                cursor.execute("INSERT INTO words (section_id, word, translation) VALUES (?,?,?)",
                               (section_id, word.strip(), trans.strip()))
                conn.commit()
                await mm.answer(f"Word '{word}' qo'shildi!")
            except:
                await mm.answer("Format xato! word - translation shaklida yozing.")

# ====== START TEST ======
@dp.message(F.text == "Start Test")
async def start_test(msg: types.Message, state: FSMContext):
    sections = get_sections()
    if not sections:
        await msg.answer("Hech qanday section yo'q!")
        return
    text = "Qaysi section test qilamiz?\n"
    for sec in sections:
        text += f"{sec[0]}: {sec[1]}\n"
    await msg.answer(text)
    await state.set_state(TestStates.waiting_section)

@dp.message(TestStates.waiting_section)
async def choose_section(msg: types.Message, state: FSMContext):
    try:
        section_id = int(msg.text)
    except:
        await msg.answer("Faqat raqam kiriting!")
        return
    if not can_take_test(msg.from_user.id):
        await msg.answer("Keyingi testni 1 soatdan keyin qilishingiz mumkin!")
        await state.clear()
        return
    words = get_words(section_id)
    if not words:
        await msg.answer("Bu section bo'sh!")
        await state.clear()
        return

    random.shuffle(words)
    await state.update_data(section_id=section_id, words=words, score=0, index=0)
    await ask_question(msg, state)

async def ask_question(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    index = data['index']
    words = data['words']
    if index >= len(words):
        score = data['score']
        section_id = data['section_id']
        total = len(words)
        update_last_test(msg.from_user.id)
        cursor.execute("INSERT INTO attempts (user_id, section_id, score, total) VALUES (?,?,?,?)",
                       (msg.from_user.id, section_id, score, total))
        conn.commit()
        await msg.answer(f"Natija: {score}/{total} ({int(score/total*100)}%)")
        await state.clear()
        return

    word, correct = words[index]
    all_translations = [w[1] for w in words if w[1] != correct]
    wrongs = random.sample(all_translations, k=min(3, len(all_translations)))
    options = wrongs + [correct]
    random.shuffle(options)

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for opt in options:
        kb.add(types.KeyboardButton(opt))
    await msg.answer(f"Translate: {word}", reply_markup=kb)
    await state.update_data(correct=correct)
    await state.set_state(TestStates.waiting_answer)

@dp.message(TestStates.waiting_answer)
async def check_answer(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    correct = data['correct']
    words = data['words']
    index = data['index']
    score = data['score']
    if msg.text == correct:
        score += 1
    index += 1
    await state.update_data(score=score, index=index)
    await ask_question(msg, state)

# fallback handler
@dp.message()
async def answer_handler(msg: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == TestStates.waiting_section.state:
        await choose_section(msg, state)
    elif current_state == TestStates.waiting_answer.state:
        await check_answer(msg, state)

# ====== MY STATS ======
@dp.message(F.text == "My Stats")
async def my_stats(msg: types.Message):
    cursor.execute("SELECT COUNT(*), MAX(score) FROM attempts WHERE user_id=?", (msg.from_user.id,))
    row = cursor.fetchone()
    await msg.answer(f"Attempts: {row[0]}\nBest score: {row[1]}")

# ====== RUN ======
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
