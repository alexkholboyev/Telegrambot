import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import date, timedelta

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"          # ← O'zgartiring
ADMIN_ID = 5932847351                     # ← O'zingizning ID'ingizni qo'ying
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN)

# DB
conn = sqlite3.connect('word_test_bot.db', check_same_thread=False)
c = conn.cursor()

# Jadval yaratish
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    total_tests INTEGER DEFAULT 0,
    total_correct INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_test_date TEXT,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
)''')

c.execute('''CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY,
    level TEXT,
    section TEXT DEFAULT 'General',
    english TEXT,
    uz_meaning TEXT,
    UNIQUE(level, section, english)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_weak (
    user_id INTEGER,
    word_id INTEGER,
    error_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY,
    name TEXT,
    date TEXT,
    price INTEGER,
    prize INTEGER,
    participants TEXT DEFAULT '[]'
)''')

conn.commit()

# Namuna so'zlar (agar jadval bo'sh bo'lsa)
c.execute("SELECT COUNT(*) FROM words")
if c.fetchone()[0] == 0:
    samples = [
        ("A1", "Daily Life", "hello", "salom"), ("A1", "Daily Life", "apple", "olma"),
        ("A1", "Animals", "cat", "mushuk"), ("A1", "Animals", "dog", "it"),
        ("A2", "School", "school", "maktab"), ("A2", "Family", "family", "oilasi"),
        ("B1", "General", "important", "muhim"), ("B1", "Environment", "environment", "atrof-muhit"),
        ("IELTS", "Academic", "sustainable", "barqaror"), ("IELTS", "Academic", "innovation", "innovatsiya"),
    ]
    for lvl, sec, en, uz in samples:
        c.execute("INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)", 
                  (lvl, sec, en, uz))
    conn.commit()

# Holatlar
user_states = {}

# ==================== KEYBOARD ====================
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📘 Test", "📊 My Statistics")
    markup.add("❗ My Weak Words", "🏆 Leaders")
    markup.add("💰 Earn Challenge")
    return markup

# ==================== START ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    bot.send_message(message.chat.id, 
        "👋 Xush kelibsiz <b>WORD TEST BOT</b> ga!\n\n"
        "Level va Section tanlab test ishlang!", 
        parse_mode='HTML', reply_markup=main_keyboard())

# ==================== MENU ====================
@bot.message_handler(func=lambda m: m.text in ["📘 Test", "📊 My Statistics", "❗ My Weak Words", "🏆 Leaders", "💰 Earn Challenge"])
def menu_handler(message):
    if message.text == "📘 Test":
        show_levels(message)
    elif message.text == "📊 My Statistics":
        show_statistics(message)
    elif message.text == "❗ My Weak Words":
        show_weak_words(message)
    elif message.text == "🏆 Leaders":
        show_leaders(message)
    elif message.text == "💰 Earn Challenge":
        show_challenges(message)

# ==================== LEVEL → SECTION TANLASH ====================
def show_levels(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    levels = ["A1", "A2", "B1", "B2", "IELTS"]
    for lvl in levels:
        markup.add(types.InlineKeyboardButton(lvl, callback_data=f"level:{lvl}"))
    bot.send_message(message.chat.id, "📘 Qaysi **darajadan** boshlaymiz?", 
                     parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("level:"))
def choose_section(call):
    level = call.data.split(":")[1]
    c.execute("SELECT DISTINCT section FROM words WHERE level = ? ORDER BY section", (level,))
    sections = [row[0] for row in c.fetchall()]

    if not sections:
        bot.answer_callback_query(call.id, "Bu darajada so'z yo'q!")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    for sec in sections:
        markup.add(types.InlineKeyboardButton(sec, callback_data=f"start_test:{level}:{sec}"))

    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"📘 {level} darajasi\n\nQaysi **bo'limdan** test qilamiz?",
        parse_mode='HTML',
        reply_markup=markup
    )

# ==================== TEST BOSHLASH VA O'TKAZISH ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("start_test:"))
def start_test_callback(call):
    _, level, section = call.data.split(":")
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    c.execute("""SELECT id, english, uz_meaning 
                 FROM words 
                 WHERE level = ? AND section = ? 
                 ORDER BY RANDOM() LIMIT 10""", (level, section))
    questions_raw = c.fetchall()

    if len(questions_raw) < 5:
        bot.answer_callback_query(call.id, "❌ Bu bo'limda yetarli so'z yo'q!")
        return

    test_data = []
    for word_id, english, correct in questions_raw:
        c.execute("""SELECT uz_meaning FROM words 
                     WHERE level = ? AND section = ? AND id != ? 
                     ORDER BY RANDOM() LIMIT 3""", (level, section, word_id))
        others = [row[0] for row in c.fetchall()]
        options = [correct] + others[:3]
        random.shuffle(options)

        test_data.append({
            "word_id": word_id,
            "english": english,
            "correct": correct,
            "options": options
        })

    user_states[user_id] = {
        "state": "test",
        "level": level,
        "section": section,
        "questions": test_data,
        "current": 0,
        "score": 0,
        "wrong": []
    }

    bot.answer_callback_query(call.id)
    send_next_question(chat_id, user_id)

def send_next_question(chat_id, user_id):
    state = user_states.get(user_id)
    if not state or state["current"] >= len(state["questions"]):
        end_test(chat_id, user_id)
        return

    q = state["questions"][state["current"]]
    markup = types.InlineKeyboardMarkup(row_width=2)
    for i, opt in enumerate(q["options"]):
        markup.add(types.InlineKeyboardButton(opt, callback_data=f"answer:{state['current']}:{i}"))

    text = f"❓ Savol {state['current'] + 1}/10\n\n" \
           f"<b>{state['level']}</b> | <b>{state['section']}</b>\n\n" \
           f"So‘z: <b>{q['english']}</b>\nMa’nosini tanlang:"

    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

def end_test(chat_id, user_id):
    state = user_states.pop(user_id, None)
    if not state:
        return

    score = state["score"]
    total = len(state["questions"])
    percent = round(score / total * 100)

    # Statistikani yangilash
    c.execute("UPDATE users SET total_tests = total_tests + 1, total_correct = total_correct + ? WHERE user_id = ?", 
              (score, user_id))
    
    xp_gain = score * 10
    c.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (xp_gain, user_id))
    c.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    new_xp = c.fetchone()[0]
    new_level = (new_xp // 1000) + 1
    c.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))

    # Zaif so'zlar
    for w_id in state.get("wrong", []):
        c.execute("""INSERT INTO user_weak (user_id, word_id, error_count) 
                     VALUES (?, ?, 1) 
                     ON CONFLICT(user_id, word_id) DO UPDATE SET error_count = error_count + 1""",
                  (user_id, w_id))

    # Streak
    today = date.today().isoformat()
    c.execute("SELECT last_test_date, streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    last_date = row[0] if row else None
    streak = row[1] if row else 0

    if last_date != today:
        if last_date and date.fromisoformat(last_date) == date.today() - timedelta(days=1):
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak = ?, last_test_date = ? WHERE user_id = ?", 
                  (streak, today, user_id))

    conn.commit()

    bot.send_message(chat_id,
        f"🎉 <b>Test tugadi!</b>\n\n"
        f"Daraja: <b>{state['level']}</b> | Bo‘lim: <b>{state['section']}</b>\n"
        f"To‘g‘ri: <b>{score}/{total}</b> ({percent}%)\n"
        f"XP: +{xp_gain}\nStreak: 🔥 {streak} kun",
        parse_mode='HTML', reply_markup=main_keyboard())

# ==================== JAVOB CALLBACK ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("answer:"))
def handle_answer(call):
    user_id = call.from_user.id
    try:
        _, q_idx_str, opt_idx_str = call.data.split(":")
        q_idx = int(q_idx_str)
        opt_idx = int(opt_idx_str)
    except:
        return

    state = user_states.get(user_id)
    if not state:
        return

    q = state["questions"][q_idx]
    chosen = q["options"][opt_idx]

    if chosen == q["correct"]:
        state["score"] += 1
        bot.answer_callback_query(call.id, "✅ To‘g‘ri!")
    else:
        state["wrong"].append(q["word_id"])
        bot.answer_callback_query(call.id, f"❌ Xato! To‘g‘ri: {q['correct']}")

    state["current"] += 1
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    send_next_question(call.message.chat.id, user_id)

# ==================== ADMIN PANEL (To‘g‘rilangan) ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Siz admin emassiz!")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Add Words (Group)", "📋 View Users")
    markup.add("📢 Broadcast", "💰 Manage Challenges")
    bot.send_message(message.chat.id, "🛠 <b>ADMIN PANEL</b>", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Add Words (Group)")
def add_words_group(message):
    text = ("So‘zlarni quyidagi formatda yuboring:\n\n"
            "<b>Level | Section | English - Uzbek</b>\n\n"
            "Misol:\n"
            "A1 | Daily Life | hello - salom\n"
            "IELTS | Academic | sustainable - barqaror\n\n"
            "Bir nechta qator yozsa bo‘ladi.")

    bot.send_message(message.chat.id, text, parse_mode='HTML')
    user_states[ADMIN_ID] = {"state": "add_words_group"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_handler(message):
    if ADMIN_ID not in user_states:
        return

    state = user_states[ADMIN_ID]

    if state.get("state") == "add_words_group":
        lines = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
        added = 0

        for line in lines:
            if "|" not in line or "-" not in line:
                continue
            try:
                # Format: Level | Section | English - Uzbek
                left, uz = [x.strip() for x in line.split("-", 1)]
                parts = [x.strip() for x in left.split("|")]
                
                if len(parts) == 3:
                    level, section, english = parts
                elif len(parts) == 2:
                    level = parts[0]
                    section = "General"
                    english = parts[1]
                else:
                    continue

                c.execute("""INSERT OR IGNORE INTO words 
                             (level, section, english, uz_meaning) 
                             VALUES (?, ?, ?, ?)""", (level, section, english, uz))
                added += 1
            except Exception as e:
                continue

        conn.commit()
        bot.send_message(message.chat.id, f"✅ <b>{added} ta so‘z qo‘shildi!</b>", parse_mode='HTML')
        user_states.pop(ADMIN_ID, None)

    # Boshqa admin holatlari (Broadcast va h.k.) kerak bo'lsa qo'shsa bo'ladi

# ==================== BOSHQA KOMANDALAR ====================
@bot.message_handler(commands=['myid'])
def my_id(message):
    bot.send_message(message.chat.id, f"Sizning ID: <code>{message.from_user.id}</code>", parse_mode='HTML')

# ==================== BOT ISHGA TUSHIRISH ====================
print("🚀 WORD TEST BOT ishga tushdi (Admin panel to‘g‘rilangan)")
bot.infinity_polling()