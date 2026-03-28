import sqlite3
import random
import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ====== CONFIG ======
TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"
ADMIN_IDS = [5932847351]
COOLDOWN_HOURS = 1

# ====== BOT & FSM ======
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

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
    translation TEXT,
    example TEXT,
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
    cursor.execute("SELECT id, name, quiz_type FROM sections ORDER BY id")
    return cursor.fetchall()

def get_words(section_id):
    cursor.execute("SELECT word, translation, example FROM words WHERE section_id=?", (section_id,))
    return cursor.fetchall()

def can_take_test(user_id: int) -> bool:
    cursor.execute("SELECT last_test FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        return True
    try:
        last = datetime.datetime.fromisoformat(row[0])
        return (datetime.datetime.now() - last).total_seconds() >= COOLDOWN_HOURS * 3600
    except:
        return True

def update_last_test(user_id: int):
    now = datetime.datetime.now().isoformat()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, last_test) VALUES (?, ?)", (user_id, now))
    conn.commit()

def update_streak(user_id: int):
    today = datetime.date.today()
    cursor.execute("SELECT streak, last_streak_date FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, streak, last_streak_date) VALUES (?, 1, ?)", (user_id, today))
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

def get_current_streak(user_id: int) -> int:
    cursor.execute("SELECT streak FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

# ====== FSM ======
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

class AdminStates(StatesGroup):
    waiting_new_section = State()
    waiting_section_for_word = State()
    waiting_word_bulk = State()
    waiting_quiz_type_section = State()
    waiting_quiz_type = State()
    waiting_broadcast = State()

# ====== KEYBOARDS ======
main_kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
main_kb.add("Start Test", "My Stats")
main_kb.add("Leaderboard", "Weak Words")

admin_kb = types.ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
admin_kb.add("Add Section", "Add Words Bulk")
admin_kb.add("Set Quiz Type", "Send Broadcast")
admin_kb.add("View All Stats", "Back to Main")

# ====== START & HELP ======
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("🎉 <b>WordEngine</b> ga xush kelibsiz!\n\nHar kuni o‘rganing va streakni oshiring!", parse_mode="HTML", reply_markup=main_kb)

@dp.message(F.text == "/help")
async def help_cmd(msg: types.Message):
    await msg.answer("📋 Buyruqlar:\n/start - Boshlash\n/admin - Admin panel (faqat adminlar uchun)\n/help - Yordam")

# ====== ADMIN PANEL ======
@dp.message(F.text == "/admin")
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer("👨‍💻 <b>Admin panel</b>", parse_mode="HTML", reply_markup=admin_kb)

# Admin: Add Section
@dp.message(F.text == "Add Section")
async def add_section(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer("Yangi section nomini yozing:")
    await state.set_state(AdminStates.waiting_new_section)

@dp.message(AdminStates.waiting_new_section)
async def save_section(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: 
        await state.clear()
        return
    name = msg.text.strip()
    try:
        cursor.execute("INSERT INTO sections (name) VALUES (?)", (name,))
        conn.commit()
        await msg.answer(f"✅ Section qo‘shildi: <b>{name}</b>", parse_mode="HTML")
    except sqlite3.IntegrityError:
        await msg.answer("❌ Bunday nomdagi section allaqachon mavjud.")
    await state.clear()

# Admin: Bulk add words
@dp.message(F.text == "Add Words Bulk")
async def add_words_bulk(msg: types.Message, state: FSMContext):
    sections = get_sections()
    if not sections:
        await msg.answer("Avval section qo‘shing!")
        return
    text = "Qaysi sectionga so‘zlar qo‘shmoqchisiz?\n\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\n\nSection ID raqamini yozing:")
    await state.set_state(AdminStates.waiting_section_for_word)

@dp.message(AdminStates.waiting_section_for_word)
async def process_section_bulk(msg: types.Message, state: FSMContext):
    try:
        section_id = int(msg.text.strip())
        await state.update_data(section_id=section_id)
        await msg.answer("So‘z va tarjimalarni kiriting, har biri yangi qatorda:\nformat: inglizcha-tarjimasi")
        await state.set_state(AdminStates.waiting_word_bulk)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

@dp.message(AdminStates.waiting_word_bulk)
async def save_words_bulk(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    section_id = data['section_id']
    lines = msg.text.strip().split("\n")
    count = 0
    for line in lines:
        if "-" in line:
            word, trans = line.split("-", 1)
            word, trans = word.strip(), trans.strip()
            cursor.execute("INSERT INTO words (section_id, word, translation) VALUES (?, ?, ?)", (section_id, word, trans))
            count += 1
    conn.commit()
    await msg.answer(f"✅ {count} ta so‘z qo‘shildi!")
    await state.clear()

# Admin: Set Quiz Type
@dp.message(F.text == "Set Quiz Type")
async def set_quiz_type_start(msg: types.Message, state: FSMContext):
    sections = get_sections()
    if not sections:
        await msg.answer("Sectionlar yo‘q.")
        return
    text = "Qaysi section uchun quiz turini o‘zgartirmoqchisiz?\n\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\n\nSection ID raqamini yozing:")
    await state.set_state(AdminStates.waiting_quiz_type_section)

@dp.message(AdminStates.waiting_quiz_type_section)
async def process_quiz_type_section(msg: types.Message, state: FSMContext):
    try:
        sid = int(msg.text.strip())
        await state.update_data(section_id=sid)
        await msg.answer("Quiz turini tanlang:\n1. translation\n2. MCQ\n\nRaqam yozing (1 yoki 2):")
        await state.set_state(AdminStates.waiting_quiz_type)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

@dp.message(AdminStates.waiting_quiz_type)
async def save_quiz_type(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        choice = int(msg.text.strip())
        qt = "translation" if choice == 1 else "MCQ"
        cursor.execute("UPDATE sections SET quiz_type=? WHERE id=?", (qt, data['section_id']))
        conn.commit()
        await msg.answer(f"✅ Quiz turi o‘zgartirildi: <b>{qt}</b>", parse_mode="HTML")
    except:
        await msg.answer("❌ Noto‘g‘ri tanlov!")
    await state.clear()

# Admin: View all stats
@dp.message(F.text == "View All Stats")
async def view_all_stats(msg: types.Message):
    cursor.execute("SELECT user_id, COUNT(*), ROUND(AVG(score*100.0/total),1) FROM attempts GROUP BY user_id")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Hozircha hech qanday foydalanuvchi statistika yo‘q.")
        return
    text = "📊 <b>All Users Stats</b>\n\n"
    for r in rows:
        text += f"User {r[0]} - {r[1]} test ({r[2]}%)\n"
    await msg.answer(text, parse_mode="HTML")

# Admin: Send Broadcast
@dp.message(F.text == "Send Broadcast")
async def send_broadcast(msg: types.Message, state: FSMContext):
    await msg.answer("Xabar matnini kiriting:")
    await state.set_state(AdminStates.waiting_broadcast)

@dp.message(AdminStates.waiting_broadcast)
async def process_broadcast(msg: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], msg.text)
            count += 1
        except: pass
    await msg.answer(f"✅ Xabar {count} foydalanuvchiga yuborildi!")
    await state.clear()

# ====== TEST va STATS (translation / MCQ) ======
# Shunday qilib test funksiyasi oldingi kod bilan ishlaydi
# Lekin har doim inglizcha so‘z soraladi va tarjima javob bo‘ladi
# Multiple choice faqat admin tanlagan sectionlarda ishlaydi

# ====== RUN ======
async def main():
    print("🤖 WordEngine boti ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())