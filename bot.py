import sqlite3
import random
import asyncio
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ===== CONFIG =====
TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"
ADMIN_IDS = [5932847351]
COOLDOWN_HOURS = 1

# ===== BOT & FSM =====
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)

# ===== DATABASE =====
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
    eng TEXT,
    uz TEXT,
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

# ===== HELPERS =====
def get_sections():
    cursor.execute("SELECT id, name, quiz_type FROM sections ORDER BY id")
    return cursor.fetchall()

def get_words(section_id):
    cursor.execute("SELECT eng, uz, example FROM words WHERE section_id=?", (section_id,))
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
        cursor.execute("UPDATE users SET streak=?, last_streak_date=? WHERE user_id=?", 
                      (streak, today, user_id))
    conn.commit()

def get_current_streak(user_id: int) -> int:
    cursor.execute("SELECT streak FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

# ===== FSM STATES =====
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

class AdminStates(StatesGroup):
    waiting_new_section = State()
    waiting_section_for_word = State()
    waiting_bulk_words = State()
    waiting_quiz_type_section = State()
    waiting_quiz_type = State()
    sending_broadcast = State()
    selecting_user = State()

# ===== KEYBOARDS =====
main_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("Start Test", "My Stats")
main_kb.add("Leaderboard", "Weak Words")

admin_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
admin_kb.add("Add Section", "Add Words Bulk")
admin_kb.add("Set Quiz Type", "Send Broadcast")
admin_kb.add("View All Stats", "Back to Main")

# ===== START & HELP =====
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("🎉 <b>WordEngine</b> ga xush kelibsiz!\nHar kuni o‘rganing va streakni oshiring!", 
                     parse_mode="HTML", reply_markup=main_kb)

@dp.message(F.text == "/help")
async def help_cmd(msg: types.Message):
    await msg.answer("/start - Boshlash\n/admin - Admin panel\n/help - Yordam")

# ===== ADMIN PANEL =====
@dp.message(F.text == "/admin")
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer("👨‍💻 <b>Admin panel</b>", parse_mode="HTML", reply_markup=admin_kb)

# --- Section Qo‘shish ---
@dp.message(F.text == "Add Section")
async def add_section(msg: types.Message, state: FSMContext):
    await msg.answer("Yangi section nomini yozing:")
    await state.set_state(AdminStates.waiting_new_section)

@dp.message(AdminStates.waiting_new_section)
async def save_section(msg: types.Message, state: FSMContext):
    name = msg.text.strip()
    try:
        cursor.execute("INSERT INTO sections (name) VALUES (?)", (name,))
        conn.commit()
        await msg.answer(f"✅ Section qo‘shildi: <b>{name}</b>", parse_mode="HTML")
    except sqlite3.IntegrityError:
        await msg.answer("❌ Bunday nomdagi section allaqachon mavjud.")
    await state.clear()

# --- So‘zlarni bulk qo‘shish ---
@dp.message(F.text == "Add Words Bulk")
async def add_words_bulk(msg: types.Message, state: FSMContext):
    sections = get_sections()
    if not sections:
        await msg.answer("Avval section qo‘shing!")
        return
    text = "Qaysi sectionga so‘z qo‘shmoqchisiz?\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\nSection ID raqamini yozing:")
    await state.set_state(AdminStates.waiting_section_for_word)

@dp.message(AdminStates.waiting_section_for_word)
async def process_section_bulk(msg: types.Message, state: FSMContext):
    try:
        sid = int(msg.text.strip())
        await state.update_data(section_id=sid)
        await msg.answer("So‘zlarni kiriting (har biri yangi qatorda) format: inglizcha-uzbekcha\nMasalan:\nApple-olma\nChair-stul")
        await state.set_state(AdminStates.waiting_bulk_words)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

@dp.message(AdminStates.waiting_bulk_words)
async def save_bulk_words(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    sid = data['section_id']
    lines = msg.text.strip().split("\n")
    added = 0
    for line in lines:
        if "-" not in line:
            continue
        eng, uz = line.split("-", 1)
        eng, uz = eng.strip(), uz.strip()
        if eng and uz:
            cursor.execute("INSERT INTO words (section_id, eng, uz) VALUES (?,?,?)", (sid, eng, uz))
            added += 1
    conn.commit()
    await msg.answer(f"✅ {added} ta so‘z qo‘shildi.")
    await state.clear()

# --- Quiz turi ---
@dp.message(F.text == "Set Quiz Type")
async def set_quiz_type_start(msg: types.Message, state: FSMContext):
    sections = get_sections()
    if not sections:
        await msg.answer("Sectionlar yo‘q.")
        return
    text = "Qaysi section uchun quiz turini o‘zgartirmoqchisiz?\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\nSection ID raqamini yozing:")
    await state.set_state(AdminStates.waiting_quiz_type_section)

@dp.message(AdminStates.waiting_quiz_type_section)
async def process_quiz_type_section(msg: types.Message, state: FSMContext):
    try:
        sid = int(msg.text.strip())
        await state.update_data(section_id=sid)
        await msg.answer("Quiz turini tanlang:\n1. translation\n2. MCQ\nRaqam yozing:")
        await state.set_state(AdminStates.waiting_quiz_type)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

@dp.message(AdminStates.waiting_quiz_type)
async def save_quiz_type(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    choice = int(msg.text.strip())
    qt = "translation" if choice == 1 else "MCQ"
    cursor.execute("UPDATE sections SET quiz_type=? WHERE id=?", (qt, data['section_id']))
    conn.commit()
    await msg.answer(f"✅ Quiz turi o‘zgartirildi: <b>{qt}</b>", parse_mode="HTML")
    await state.clear()

# --- Test boshlash ---
@dp.message(F.text == "Start Test")
async def start_test(msg: types.Message, state: FSMContext):
    if not can_take_test(msg.from_user.id):
        await msg.answer("⏳ 1 soat ichida yana test topshira olmaysiz.")
        return
    sections = get_sections()
    if not sections:
        await msg.answer("Hozircha section yo‘q.")
        return

    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for s in sections:
        cursor.execute("SELECT COUNT(*) FROM words WHERE section_id=?", (s[0],))
        count = cursor.fetchone()[0]
        kb.add(f"{s[1]} ({count} so‘z)")
    await msg.answer("Qaysi sectionni tanlaysiz?", reply_markup=kb)
    await state.set_state(TestStates.waiting_section)

# --- Test flow ---
@dp.message(TestStates.waiting_section)
async def choose_section(msg: types.Message, state: FSMContext):
    sections = get_sections()
    selected_name = msg.text.split("(")[0].strip()
    section = next((s for s in sections if s[1] == selected_name), None)
    if not section:
        await msg.answer("❌ Section topilmadi!")
        return
    sid = section[0]
    words = get_words(sid)
    if len(words) < 1:
        await msg.answer("❌ Bu sectionda so‘zlar yetarli emas!")
        return
    random.shuffle(words)
    await state.update_data(words=words, i=0, score=0, qt=section[2], section_id=sid, correct=None)
    update_last_test(msg.from_user.id)
    await ask_question(msg, state)

async def ask_question(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    if d["i"] >= len(d["words"]):
        score = d["score"]
        total = len(d["words"])
        update_streak(msg.from_user.id)
        cursor.execute("INSERT INTO attempts (user_id, section_id, score, total) VALUES (?,?,?,?)",
                       (msg.from_user.id, d["section_id"], score, total))
        conn.commit()
        streak = get_current_streak(msg.from_user.id)
        await msg.answer(f"🎉 Test tugadi!\nNatija: {score}/{total}\nStreak: 🔥 {streak} kun", reply_markup=main_kb)
        await state.clear()
        return

    eng, uz, example = d["words"][d["i"]]
    if d["qt"] == "MCQ":
        other_trans = [w[0] for w in d["words"] if w[0] != eng]
        opts = random.sample(other_trans, min(3, len(other_trans))) + [eng]
        random.shuffle(opts)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=o, callback_data=f"ans_{o}")] for o in opts])
        await msg.answer(f"<b>{uz}</b>", reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(f"<b>{uz}</b>\nMisol: {example or '—'}", parse_mode="HTML")

    await state.update_data(correct=eng)
    await state.set_state(TestStates.waiting_answer)

@dp.callback_query(F.data.startswith("ans_"))
async def handle_mcq(callback: types.CallbackQuery, state: FSMContext):
    d = await state.get_data()
    user_answer = callback.data[4:]
    is_correct = user_answer == d.get("correct")
    new_score = d["score"] + (1 if is_correct else 0)
    await state.update_data(score=new_score, i=d["i"] + 1)
    status = "✅" if is_correct else "❌"
    await callback.message.edit_text(f"{callback.message.text}\nSizning javobingiz: {user_answer} {status}", parse_mode="HTML")
    await ask_question(callback.message, state)

@dp.message(TestStates.waiting_answer)
async def check_translation(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    user_answer = msg.text.strip()
    correct = d.get("correct", "")
    new_score = d["score"] + (1 if user_answer.lower() == correct.lower() else 0)
    await state.update_data(score=new_score, i=d["i"] + 1)
    await ask_question(msg, state)

# ====== STATISTIKA =====
@dp.message(F.text == "My Stats")
async def my_stats(msg: types.Message):
    streak = get_current_streak(msg.from_user.id)
    cursor.execute("SELECT COUNT(*), ROUND(AVG(score * 100.0 / total),1) FROM attempts WHERE user_id=?", (msg.from_user.id,))
    row = cursor.fetchone()
    if not row or row[0]==0:
        await msg.answer("Siz hali test topshirmadingiz.")
    else:
        await msg.answer(f"📊 Sizning statistikangiz:\nStreak: 🔥 {streak} kun\nTestlar soni: {row[0]}\nO‘rtacha natija: {row[1]}%", parse_mode="HTML")

@dp.message(F.text == "Leaderboard")
async def leaderboard(msg: types.Message):
    cursor.execute("SELECT user_id, SUM(score) as total_score, COUNT(*) as tests FROM attempts GROUP BY user_id ORDER BY total_score DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        await msg.answer("Leaderboard bo‘sh.")
        return
    text = "🏆 Top 10 o‘yinchilar:\n"
    for i, r in enumerate(rows,1):
        text += f"{i}. User {r[0]} — {r[1]} ball ({r[2]} test)\n"
    await msg.answer(text)

@dp.message(F.text == "Weak Words")
async def weak_words(msg: types.Message):
    await msg.answer("🔧 Weak Words funksiyasi tez orada ishga tushadi.")

# ====== RUN =====
async def main():
    print("🤖 WordEngine boti ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())