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
    name TEXT UNIQUE
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
    cursor.execute("SELECT id, name FROM sections ORDER BY id")
    return cursor.fetchall()

def get_words(section_id):
    cursor.execute("SELECT word, translation FROM words WHERE section_id=?", (section_id,))
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
    waiting_bulk_words = State()
    waiting_broadcast_msg = State()
    waiting_broadcast_target = State()

# ====== KEYBOARDS ======
def build_sections_kb():
    sections = get_sections()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for s in sections:
        kb.add(types.KeyboardButton(f"{s[1]} ({len(get_words(s[0]))} ta so‘z)"))
    return kb

main_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Start Test")],
        [types.KeyboardButton(text="My Stats")],
        [types.KeyboardButton(text="Leaderboard")],
        [types.KeyboardButton(text="Weak Words")],
        [types.KeyboardButton(text="Admin Panel")]
    ],
    resize_keyboard=True
)

admin_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Add Section")],
        [types.KeyboardButton(text="Add Words Bulk")],
        [types.KeyboardButton(text="View All Users Stats")],
        [types.KeyboardButton(text="Broadcast Message")],
        [types.KeyboardButton(text="Back to Main")],
    ],
    resize_keyboard=True
)

# ====== START ======
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("🎉 WordEngine ga xush kelibsiz!\nHar kuni o‘rganing va streakni oshiring!", reply_markup=main_kb)

# ====== ADMIN PANEL ======
@dp.message(F.text == "Admin Panel")
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer("👨‍💻 Admin Panel", reply_markup=admin_kb)

@dp.message(F.text == "Add Section")
async def add_section(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer("Yangi section nomini yozing:")
    await state.set_state(AdminStates.waiting_new_section)

@dp.message(AdminStates.waiting_new_section)
async def save_section(msg: types.Message, state: FSMContext):
    name = msg.text.strip()
    try:
        cursor.execute("INSERT INTO sections (name) VALUES (?)", (name,))
        conn.commit()
        await msg.answer(f"✅ Section qo‘shildi: {name}")
    except sqlite3.IntegrityError:
        await msg.answer("❌ Bunday nomdagi section mavjud.")
    await state.clear()

@dp.message(F.text == "Add Words Bulk")
async def add_words_bulk_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    sections = get_sections()
    if not sections:
        await msg.answer("❌ Avval section qo‘shing!")
        return
    text = "Qaysi sectionga so‘zlar qo‘shilsin?\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\nSection ID raqamini yozing:")
    await state.set_state(AdminStates.waiting_section_for_word)

@dp.message(AdminStates.waiting_section_for_word)
async def process_section_for_bulk(msg: types.Message, state: FSMContext):
    try:
        sid = int(msg.text.strip())
        await state.update_data(section_id=sid)
        await msg.answer("So‘zlarni kiriting (har biri yangi qatorda, format: inglizcha-tarjimasi):")
        await state.set_state(AdminStates.waiting_bulk_words)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

@dp.message(AdminStates.waiting_bulk_words)
async def save_bulk_words(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    sid = data['section_id']
    lines = msg.text.strip().split("\n")
    count = 0
    for line in lines:
        if "-" in line:
            eng, uzb = line.split("-", 1)
            cursor.execute("INSERT INTO words (section_id, word, translation) VALUES (?, ?, ?)",
                           (sid, eng.strip(), uzb.strip()))
            count += 1
    conn.commit()
    await msg.answer(f"✅ {count} ta so‘z qo‘shildi!")
    await state.clear()

# ====== VIEW USERS STATS ======
@dp.message(F.text == "View All Users Stats")
async def view_all_users(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS: return
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    text = ""
    for u in users:
        uid = u[0]
        streak = get_current_streak(uid)
        cursor.execute("SELECT COUNT(*), ROUND(AVG(score*100.0/total),1) FROM attempts WHERE user_id=?", (uid,))
        row = cursor.fetchone()
        tests = row[0] if row else 0
        avg = row[1] if row else 0
        text += f"User {uid}: {tests} test, avg {avg}%, streak {streak}\n"
    await msg.answer(text or "Hozircha foydalanuvchilar yo‘q.")

# ====== BROADCAST ======
@dp.message(F.text == "Broadcast Message")
async def broadcast_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer("📢 Yuboriladigan xabarni yozing:")
    await state.set_state(AdminStates.waiting_broadcast_msg)

@dp.message(AdminStates.waiting_broadcast_msg)
async def broadcast_target(msg: types.Message, state: FSMContext):
    await state.update_data(message_text=msg.text.strip())
    await msg.answer("Barchaga yuborilsinmi? Ha/Yo‘q")
    await state.set_state(AdminStates.waiting_broadcast_target)

@dp.message(AdminStates.waiting_broadcast_target)
async def send_broadcast(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    text = data['message_text']
    target_all = msg.text.strip().lower() in ["ha", "yes"]
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        uid = u[0]
        if target_all or uid in ADMIN_IDS:  # agar faqat tanlangan bo‘lsa admin
            try:
                await bot.send_message(uid, text)
                count += 1
            except:
                pass
    await msg.answer(f"📢 Xabar {count} foydalanuvchiga yuborildi!")
    await state.clear()

# ====== BACK TO MAIN ======
@dp.message(F.text == "Back to Main")
async def back_to_main(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer("Asosiy menyuga qaytdingiz.", reply_markup=main_kb)

# ====== TEST ======
@dp.message(F.text == "Start Test")
async def start_test(msg: types.Message, state: FSMContext):
    if not can_take_test(msg.from_user.id):
        await msg.answer("⏳ 1 soat ichida yana test topshira olmaysiz.")
        return

    sections = get_sections()
    if not sections:
        await msg.answer("Hozircha section yo‘q.")
        return

    kb = build_sections_kb()
    await msg.answer("Test boshlash uchun section tanlang:", reply_markup=kb)
    await state.set_state(TestStates.waiting_section)

@dp.message(TestStates.waiting_section)
async def choose_section(msg: types.Message, state: FSMContext):
    text = msg.text.split("(")[0].strip()  # section nomi
    cursor.execute("SELECT id FROM sections WHERE name=?", (text,))
    row = cursor.fetchone()
    if not row:
        await msg.answer("❌ Noto‘g‘ri section!")
        return
    sid = row[0]
    words = get_words(sid)
    if len(words) < 1:
        await msg.answer("❌ Bu sectionda so‘zlar yetarli emas.")
        return
    random.shuffle(words)
    await state.update_data(words=words, i=0, score=0, section_id=sid, correct=None)
    update_last_test(msg.from_user.id)
    await ask_question(msg, state)

async def ask_question(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    if d["i"] >= len(d["words"]):
        score = d["score"]
        total = len(d["words"])
        update_streak(msg.from_user.id)
        cursor.execute("INSERT INTO attempts (user_id, section_id, score, total) VALUES (?,?,?,?)",
                       (msg.from_user.id, d['section_id'], score, total))
        conn.commit()
        streak = get_current_streak(msg.from_user.id)
        await msg.answer(f"🎉 Test tugadi!\nNatija: {score}/{total}\nStreak: {streak} kun")
        await state.clear()
        return
    word, trans = d["words"][d["i"]]
    await msg.answer(f"Tarjima qiling: <b>{trans}</b>", parse_mode="HTML")
    await state.update_data(correct=word)
    await state.set_state(TestStates.waiting_answer)

@dp.message(TestStates.waiting_answer)
async def check_answer(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    user_ans = msg.text.strip().lower()
    correct = d.get("correct", "").lower()
    score = d["score"] + (1 if user_ans == correct else 0)
    await state.update_data(score=score, i=d["i"] + 1)
    await ask_question(msg, state)

# ====== RUN ======
async def main():
    print("🤖 WordEngine ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())