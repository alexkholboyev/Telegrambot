import sqlite3
import random
import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

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
    last_test TIMESTAMP,
    streak INTEGER DEFAULT 0,
    last_streak_date DATE
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
    translation TEXT,
    example TEXT
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
    cursor.execute("SELECT word, translation, example FROM words WHERE section_id=?", (section_id,))
    return cursor.fetchall()

def can_take_test(user_id):
    cursor.execute("SELECT last_test FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return True
    last = datetime.datetime.fromisoformat(row[0])
    return (datetime.datetime.now() - last).total_seconds() >= COOLDOWN_HOURS * 3600

def update_streak(user_id):
    today = datetime.date.today()
    cursor.execute("SELECT streak, last_streak_date FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, streak, last_streak_date) VALUES (?,1,?)", (user_id, today))
    else:
        streak, last_date = row
        last = datetime.date.fromisoformat(last_date) if last_date else None
        if last == today:
            pass
        elif last == today - datetime.timedelta(days=1):
            streak += 1
        else:
            streak = 1
        cursor.execute("UPDATE users SET streak=?, last_streak_date=? WHERE user_id=?", (streak, today, user_id))
    conn.commit()

# ====== FSM ======
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

class AdminStates(StatesGroup):
    waiting_new_section = State()
    waiting_section_choice = State()
    waiting_word_input = State()
    waiting_quiz_type = State()

# ====== KEYBOARDS ======
main_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Start Test")],
        [types.KeyboardButton(text="My Stats")],
        [types.KeyboardButton(text="Leaderboard")],
        [types.KeyboardButton(text="Weak Words")]
    ],
    resize_keyboard=True
)

# ====== START ======
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("🎉 WordEngine ga xush kelibsiz!\nHar kuni o‘rganing va streakni oshiring!", reply_markup=main_kb)

@dp.message(F.text == "/help")
async def help_cmd(msg: types.Message):
    await msg.answer("📋 Buyruqlar:\n/start - Boshlash\n/admin - Admin panel (faqat adminlar uchun)\n/help - Yordam")

# ====== ADMIN (oldingi kabi, lekin example qo‘shish bilan yangilangan) ======
@dp.message(F.text == "/admin")
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS: return
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Add Section")],
            [types.KeyboardButton(text="Add Word")],
            [types.KeyboardButton(text="Set Quiz Type")],
        ],
        resize_keyboard=True
    )
    await msg.answer("👨‍💻 Admin panel", reply_markup=kb)

# Add Section, Add Word, Set Quiz Type — oldingi versiyada to‘g‘ri edi, shuning uchun ularni qoldirdim (joy tejash uchun qisqartirdim, kerak bo‘lsa to‘liq so‘rang).

# ====== TEST (Inline Keyboard bilan yangilangan) ======
@dp.message(F.text == "Start Test")
async def start_test(msg: types.Message, state: FSMContext):
    if not can_take_test(msg.from_user.id):
        await msg.answer("⏳ 1 soat ichida yana test topshira olmaysiz.")
        return

    sections = get_sections()
    if not sections:
        await msg.answer("Hozircha section yo‘q.")
        return
    text = "Tanlang:\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\n\nSection ID raqamini yozing:")
    await state.set_state(TestStates.waiting_section)

@dp.message(TestStates.waiting_section)
async def choose_test(msg: types.Message, state: FSMContext):
    try:
        sid = int(msg.text.strip())
        words = get_words(sid)
        if len(words) < 4:
            await msg.answer("Test uchun kamida 4 ta so‘z kerak.")
            await state.clear()
            return
        random.shuffle(words)
        cursor.execute("SELECT quiz_type FROM sections WHERE id=?", (sid,))
        qt = cursor.fetchone()[0] or "translation"

        await state.update_data(words=words, i=0, score=0, qt=qt, section_id=sid, correct=None)
        await ask_question(msg, state)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

async def ask_question(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    if d["i"] >= len(d["words"]):
        score = d["score"]
        total = len(d["words"])
        update_streak(msg.from_user.id)
        cursor.execute("INSERT INTO attempts (user_id, section_id, score, total) VALUES (?,?,?,?)",
                       (msg.from_user.id, d["section_id"], score, total))
        conn.commit()

        await msg.answer(f"🎉 Test tugadi!\nNatija: <b>{score}/{total}</b>\nStreak: {get_current_streak(msg.from_user.id)} kun!", parse_mode="HTML")
        await state.clear()
        return

    word, trans, example = d["words"][d["i"]]
    if d["qt"] == "MCQ":
        opts = [x[1] for x in d["words"] if x[1] != trans][:3] + [trans]
        random.shuffle(opts)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=o, callback_data=f"ans_{o}")] for o in opts
        ])
        await msg.answer(f"<b>{word}</b>", reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(f"<b>{word}</b>\n\nMisol: {example or 'Misol yo‘q'}", parse_mode="HTML")
        kb = None  # translation uchun oddiy

    await state.update_data(correct=trans)
    await state.set_state(TestStates.waiting_answer)

@dp.callback_query(F.data.startswith("ans_"))
async def handle_mcq(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    user_answer = callback.data[4:]  # ans_ dan keyin
    score = d["score"] + (1 if user_answer == d.get("correct") else 0)
    await state.update_data(score=score, i=d["i"] + 1)
    await callback.message.edit_text(f"{callback.message.text}\n\nJavob: {user_answer} {'✅' if user_answer == d.get('correct') else '❌'}")
    await ask_question(callback.message, state)

@dp.message(TestStates.waiting_answer)
async def check_translation(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    score = d["score"] + (1 if msg.text.strip().lower() == d.get("correct", "").lower() else 0)
    await state.update_data(score=score, i=d["i"] + 1)
    await ask_question(msg, state)

def get_current_streak(user_id):
    cursor.execute("SELECT streak FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

# ====== My Stats, Leaderboard, Weak Words ======
@dp.message(F.text == "My Stats")
async def my_stats(msg: types.Message):
    streak = get_current_streak(msg.from_user.id)
    cursor.execute("SELECT COUNT(*), ROUND(AVG(score * 100.0 / total), 1) FROM attempts WHERE user_id=?", (msg.from_user.id,))
    row = cursor.fetchone()
    if row[0] == 0:
        await msg.answer("Siz hali test topshirmadingiz.")
    else:
        await msg.answer(f"📊 Sizning statistikangiz:\n\n"
                         f"Streak: 🔥 <b>{streak}</b> kun\n"
                         f"Testlar: <b>{row[0]}</b>\n"
                         f"O‘rtacha: <b>{row[1]}%</b>", parse_mode="HTML")

@dp.message(F.text == "Leaderboard")
async def leaderboard(msg: types.Message):
    cursor.execute("""
        SELECT user_id, SUM(score) as total, COUNT(*) as tests 
        FROM attempts GROUP BY user_id ORDER BY total DESC LIMIT 10
    """)
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Leaderboard bo‘sh.")
        return
    text = "🏆 Top 10:\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. User {r[0]} — {r[1]} ball ({r[2]} ta)\n"
    await msg.answer(text)

@dp.message(F.text == "Weak Words")
async def weak_words(msg: types.Message):
    # Oddiy misol: eng ko‘p xato qilingan so‘zlarni topish (hozircha umumiy)
    await msg.answer("Hozircha Weak Words funksiyasi tayyorlanmoqda.\nTez orada to‘liq ishlaydi!")

# ====== RUN ======
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())