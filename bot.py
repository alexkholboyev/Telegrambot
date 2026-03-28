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
            pass  # bugun allaqachon yangilangan
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

# ====== FSM ======
class TestStates(StatesGroup):
    waiting_section = State()
    waiting_answer = State()

class AdminStates(StatesGroup):
    waiting_new_section = State()
    waiting_section_for_word = State()
    waiting_word = State()
    waiting_translation = State()
    waiting_example = State()
    waiting_quiz_type_section = State()
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

admin_kb = types.ReplyKeyboardMarkup(
    keyboard=[
        [types.KeyboardButton(text="Add Section")],
        [types.KeyboardButton(text="Add Word")],
        [types.KeyboardButton(text="Set Quiz Type")],
        [types.KeyboardButton(text="Back to Main")],
    ],
    resize_keyboard=True
)

# ====== START & HELP ======
@dp.message(F.text == "/start")
async def start(msg: types.Message):
    await msg.answer("🎉 <b>WordEngine</b> ga xush kelibsiz!\n\nHar kuni o‘rganing va streakni oshiring!", 
                     parse_mode="HTML", reply_markup=main_kb)

@dp.message(F.text == "/help")
async def help_cmd(msg: types.Message):
    await msg.answer("📋 Buyruqlar:\n/start - Boshlash\n/admin - Admin panel (faqat adminlar uchun)\n/help - Yordam")

# ====== ADMIN PANEL ======
@dp.message(F.text == "/admin")
async def admin_panel(msg: types.Message):
    if msg.from_user.id not in ADMIN_IDS:
        return
    await msg.answer("👨‍💻 <b>Admin panel</b>", parse_mode="HTML", reply_markup=admin_kb)

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

@dp.message(F.text == "Add Word")
async def add_word_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
    sections = get_sections()
    if not sections:
        await msg.answer("Avval section qo‘shing!")
        return
    text = "Qaysi sectionga so‘z qo‘shmoqchisiz?\n\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\n\nSection ID raqamini yozing:")
    await state.set_state(AdminStates.waiting_section_for_word)

@dp.message(AdminStates.waiting_section_for_word)
async def process_section_for_word(msg: types.Message, state: FSMContext):
    try:
        section_id = int(msg.text.strip())
        await state.update_data(section_id=section_id)
        await msg.answer("So‘zni kiriting (inglizcha yoki asl til):")
        await state.set_state(AdminStates.waiting_word)
    except:
        await msg.answer("❌ Noto‘g‘ri ID!")

@dp.message(AdminStates.waiting_word)
async def process_word(msg: types.Message, state: FSMContext):
    await state.update_data(word=msg.text.strip())
    await msg.answer("Tarjimasini kiriting:")
    await state.set_state(AdminStates.waiting_translation)

@dp.message(AdminStates.waiting_translation)
async def process_translation(msg: types.Message, state: FSMContext):
    await state.update_data(translation=msg.text.strip())
    await msg.answer("Misolni kiriting (ixtiyoriy, bo‘sh qoldirsa ham bo‘ladi):")
    await state.set_state(AdminStates.waiting_example)

@dp.message(AdminStates.waiting_example)
async def save_word(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    example = msg.text.strip() if msg.text.strip() else None
    
    cursor.execute("""INSERT INTO words (section_id, word, translation, example) 
                      VALUES (?, ?, ?, ?)""", 
                   (data['section_id'], data['word'], data['translation'], example))
    conn.commit()
    
    await msg.answer(f"✅ So‘z qo‘shildi:\n<b>{data['word']}</b> — {data['translation']}", parse_mode="HTML")
    await state.clear()

@dp.message(F.text == "Set Quiz Type")
async def set_quiz_type_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: return
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
        await msg.answer("Hozircha hech qanday section yo‘q.")
        return

    text = "Mavjud sectionlar:\n" + "\n".join([f"{s[0]}: {s[1]}" for s in sections])
    await msg.answer(text + "\n\nTest boshlash uchun **Section ID** raqamini yozing:", parse_mode="Markdown")
    await state.set_state(TestStates.waiting_section)

@dp.message(TestStates.waiting_section)
async def choose_section(msg: types.Message, state: FSMContext):
    try:
        sid = int(msg.text.strip())
        words = get_words(sid)
        if len(words) < 4:
            await msg.answer("❌ Test uchun kamida 4 ta so‘z bo‘lishi kerak.")
            await state.clear()
            return

        random.shuffle(words)
        cursor.execute("SELECT quiz_type FROM sections WHERE id=?", (sid,))
        qt = cursor.fetchone()[0] or "translation"

        await state.update_data(words=words, i=0, score=0, qt=qt, section_id=sid, correct=None)
        update_last_test(msg.from_user.id)
        await ask_question(msg, state)
    except ValueError:
        await msg.answer("❌ Iltimos, faqat raqam kiriting!")
    except Exception as e:
        await msg.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko‘ring.")
        await state.clear()

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
        await msg.answer(f"🎉 <b>Test tugadi!</b>\n\nNatija: <b>{score}/{total}</b>\nStreak: 🔥 <b>{streak}</b> kun", 
                         parse_mode="HTML")
        await state.clear()
        return

    word, trans, example = d["words"][d["i"]]

    if d["qt"] == "MCQ":
        # 3 ta noto‘g‘ri + 1 to‘g‘ri variant
        other_trans = [w[1] for w in d["words"] if w[1] != trans]
        opts = random.sample(other_trans, min(3, len(other_trans))) + [trans]
        random.shuffle(opts)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=o, callback_data=f"ans_{o}")] for o in opts
        ])
        await msg.answer(f"<b>{word}</b>", reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(f"<b>{word}</b>\n\nMisol: {example or '—'}", parse_mode="HTML")

    await state.update_data(correct=trans)
    await state.set_state(TestStates.waiting_answer)

@dp.callback_query(F.data.startswith("ans_"))
async def handle_mcq(callback: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    user_answer = callback.data[4:]
    is_correct = user_answer == d.get("correct")
    new_score = d["score"] + (1 if is_correct else 0)

    await state.update_data(score=new_score, i=d["i"] + 1)

    status = "✅" if is_correct else "❌"
    await callback.message.edit_text(
        f"{callback.message.text}\n\nSizning javobingiz: <b>{user_answer}</b> {status}", 
        parse_mode="HTML"
    )

    # Keyingi savolni yuborish
    await ask_question(callback.message, state)

@dp.message(TestStates.waiting_answer)
async def check_translation(msg: types.Message, state: FSMContext):
    d = await state.get_data()
    user_answer = msg.text.strip().lower()
    correct = d.get("correct", "").lower()
    new_score = d["score"] + (1 if user_answer == correct else 0)

    await state.update_data(score=new_score, i=d["i"] + 1)
    await ask_question(msg, state)

# ====== STATISTIKA ======
@dp.message(F.text == "My Stats")
async def my_stats(msg: types.Message):
    streak = get_current_streak(msg.from_user.id)
    cursor.execute("""
        SELECT COUNT(*), ROUND(AVG(score * 100.0 / total), 1) 
        FROM attempts WHERE user_id=?
    """, (msg.from_user.id,))
    row = cursor.fetchone()

    if not row or row[0] == 0:
        await msg.answer("Siz hali hech qanday test topshirmadingiz.")
    else:
        await msg.answer(f"📊 <b>Sizning statistikangiz:</b>\n\n"
                         f"Streak: 🔥 <b>{streak}</b> kun\n"
                         f"Testlar soni: <b>{row[0]}</b>\n"
                         f"O‘rtacha natija: <b>{row[1]}%</b>", parse_mode="HTML")

@dp.message(F.text == "Leaderboard")
async def leaderboard(msg: types.Message):
    cursor.execute("""
        SELECT user_id, SUM(score) as total_score, COUNT(*) as tests 
        FROM attempts 
        GROUP BY user_id 
        ORDER BY total_score DESC LIMIT 10
    """)
    rows = cursor.fetchall()
    
    if not rows:
        await msg.answer("Leaderboard hozircha bo‘sh.")
        return

    text = "🏆 <b>Top 10 o‘yinchilar</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. User <b>{r[0]}</b> — {r[1]} ball ({r[2]} ta test)\n"
    await msg.answer(text, parse_mode="HTML")

@dp.message(F.text == "Weak Words")
async def weak_words(msg: types.Message):
    await msg.answer("🔧 <b>Weak Words</b> funksiyasi tez orada to‘liq ishga tushadi!\n\nHozircha tayyorlanmoqda...", parse_mode="HTML")

# ====== RUN ======
async def main():
    print("🤖 WordEngine boti ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())