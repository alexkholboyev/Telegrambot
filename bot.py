import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import date, timedelta

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"   # ← BotFatherdan oling
ADMIN_ID = 5932847351                # ← O'zingizning Telegram ID
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN)

# Database
conn = sqlite3.connect('word_test_bot.db', check_same_thread=False)
c = conn.cursor()

# Jadval yaratish
c.executescript('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    total_tests INTEGER DEFAULT 0,
    total_correct INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_test_date TEXT,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY,
    level TEXT,
    section TEXT DEFAULT 'General',
    english TEXT,
    uz_meaning TEXT,
    UNIQUE(level, section, english)
);

CREATE TABLE IF NOT EXISTS user_weak (
    user_id INTEGER,
    word_id INTEGER,
    error_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY,
    name TEXT,
    date TEXT,
    price INTEGER,
    prize INTEGER,
    participants TEXT DEFAULT '[]'
);
''')
conn.commit()

# Namuna so'zlar
c.execute("SELECT COUNT(*) FROM words")
if c.fetchone()[0] == 0:
    samples = [
        ("A1", "Daily Life", "hello", "salom"), ("A1", "Daily Life", "apple", "olma"),
        ("A1", "Animals", "cat", "mushuk"), ("A1", "Animals", "dog", "it"),
        ("A2", "School", "school", "maktab"), ("A2", "Travel", "travel", "sayohat"),
        ("B1", "General", "important", "muhim"), ("B1", "Environment", "environment", "atrof-muhit"),
        ("IELTS", "Academic", "sustainable", "barqaror"), ("IELTS", "Academic", "innovation", "innovatsiya"),
    ]
    for lvl, sec, en, uz in samples:
        c.execute("INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)", 
                  (lvl, sec, en, uz))
    conn.commit()

user_states = {}

# ==================== KEYBOARDS ====================
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
        "Level va Section tanlab inglizcha so'zlarni o'rganing!",
        parse_mode='HTML', reply_markup=main_keyboard())

# ==================== MENU HANDLER ====================
@bot.message_handler(func=lambda m: m.text in ["📘 Test", "📊 My Statistics", "❗ My Weak Words", "🏆 Leaders", "💰 Earn Challenge"])
def menu_handler(message):
    text = message.text
    if text == "📘 Test":
        show_levels(message)
    elif text == "📊 My Statistics":
        show_statistics(message)
    elif text == "❗ My Weak Words":
        show_weak_words(message)
    elif text == "🏆 Leaders":
        show_leaders(message)
    elif text == "💰 Earn Challenge":
        show_challenges(message)

# ==================== TEST - LEVEL VA SECTION TANLASH ====================
def show_levels(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for lvl in ["A1", "A2", "B1", "B2", "IELTS"]:
        markup.add(types.InlineKeyboardButton(lvl, callback_data=f"level:{lvl}"))
    bot.send_message(message.chat.id, "📘 Qaysi **darajadan** test boshlaymiz?", 
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
        text=f"📘 {level} darajasi\n\nQaysi **bo'lim** dan test qilamiz?",
        parse_mode='HTML', reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("start_test:"))
def start_test(call):
    _, level, section = call.data.split(":")
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    c.execute("""SELECT id, english, uz_meaning FROM words 
                 WHERE level = ? AND section = ? 
                 ORDER BY RANDOM() LIMIT 10""", (level, section))
    questions_raw = c.fetchall()

    if len(questions_raw) < 5:
        bot.answer_callback_query(call.id, "❌ Bu bo'limda yetarli so'z yo'q!")
        return

    test_data = []
    for wid, en, uz in questions_raw:
        c.execute("""SELECT uz_meaning FROM words 
                     WHERE level=? AND section=? AND id != ? 
                     ORDER BY RANDOM() LIMIT 3""", (level, section, wid))
        others = [r[0] for r in c.fetchall()]
        options = [uz] + others[:3]
        random.shuffle(options)

        test_data.append({
            "word_id": wid,
            "english": en,
            "correct": uz,
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
           f"<b>{state['level']}</b> • <b>{state['section']}</b>\n\n" \
           f"So‘z: <b>{q['english']}</b>\nMa’nosini tanlang:"

    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

def end_test(chat_id, user_id):
    state = user_states.pop(user_id, None)
    if not state:
        return

    score = state["score"]
    total = len(state["questions"])
    percent = round(score / total * 100)

    # Yangilash
    c.execute("UPDATE users SET total_tests = total_tests + 1, total_correct = total_correct + ? WHERE user_id = ?", 
              (score, user_id))
    c.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (score * 10, user_id))
    c.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    new_xp = c.fetchone()[0]
    new_lvl = (new_xp // 1000) + 1
    c.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_lvl, user_id))

    # Zaif so'zlar
    for wid in state.get("wrong", []):
        c.execute("""INSERT INTO user_weak (user_id, word_id, error_count) 
                     VALUES (?, ?, 1) ON CONFLICT(user_id, word_id) 
                     DO UPDATE SET error_count = error_count + 1""", (user_id, wid))

    # Streak
    today = date.today().isoformat()
    c.execute("SELECT last_test_date, streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    last = row[0] if row else None
    streak = row[1] if row else 0

    if last != today:
        if last and date.fromisoformat(last) == date.today() - timedelta(days=1):
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak = ?, last_test_date = ? WHERE user_id = ?", 
                  (streak, today, user_id))

    conn.commit()

    bot.send_message(chat_id,
        f"🎉 <b>Test tugadi!</b>\n\n"
        f"Daraja: <b>{state['level']}</b> | Bo‘lim: <b>{state['section']}</b>\n"
        f"To‘g‘ri javob: <b>{score}/{total}</b> ({percent}%)\n"
        f"XP: +{score*10} | Streak: 🔥 {streak} kun",
        parse_mode='HTML', reply_markup=main_keyboard())

# ==================== JAVOB QABUL QILISH ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("answer:"))
def process_answer(call):
    user_id = call.from_user.id
    try:
        _, q_idx, opt_idx = call.data.split(":")
        q_idx = int(q_idx)
        opt_idx = int(opt_idx)
    except:
        return

    state = user_states.get(user_id)
    if not state:
        return

    q = state["questions"][q_idx]
    if q["options"][opt_idx] == q["correct"]:
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

# ==================== STATISTIKA ====================
def show_statistics(message):
    user_id = message.from_user.id
    c.execute("SELECT total_tests, total_correct, xp, level, streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row or row[0] == 0:
        bot.send_message(message.chat.id, "Siz hali test ishlamagansiz. 📘 Test bo‘limidan boshlang!")
        return

    tests, correct, xp, lvl, streak = row
    perc = round(correct / tests * 100) if tests else 0
    bot.send_message(message.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"Testlar: <b>{tests}</b>\n"
        f"To‘g‘ri javoblar: <b>{correct}</b>\n"
        f"O‘rtacha: <b>{perc}%</b>\n"
        f"XP: <b>{xp}</b> | Level: <b>{lvl}</b>\n"
        f"Streak: 🔥 <b>{streak} kun</b>",
        parse_mode='HTML')

# ==================== ZAIF SO‘ZLAR ====================
def show_weak_words(message):
    user_id = message.from_user.id
    c.execute("""SELECT w.english, w.uz_meaning, uw.error_count 
                 FROM user_weak uw 
                 JOIN words w ON uw.word_id = w.id 
                 WHERE uw.user_id = ? 
                 ORDER BY uw.error_count DESC""", (user_id,))
    rows = c.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "✅ Sizda zaif so‘zlar yo‘q! Ajoyib!")
        return

    text = "❗ <b>Zaif so‘zlaringiz</b>\n\n"
    for en, uz, err in rows:
        text += f"• <b>{en}</b> — {uz} (<b>{err} marta</b>)\n"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Shu so‘zlardan test", callback_data="repeat_weak"))

    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "repeat_weak")
def repeat_weak(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    c.execute("""SELECT w.id, w.english, w.uz_meaning 
                 FROM user_weak uw 
                 JOIN words w ON uw.word_id = w.id 
                 WHERE uw.user_id = ? 
                 ORDER BY RANDOM() LIMIT 10""", (user_id,))
    questions_raw = c.fetchall()

    if not questions_raw:
        bot.answer_callback_query(call.id, "Zaif so‘z topilmadi!")
        return

    test_data = []
    for wid, en, uz in questions_raw:
        c.execute("SELECT uz_meaning FROM words WHERE id != ? ORDER BY RANDOM() LIMIT 3", (wid,))
        others = [r[0] for r in c.fetchall()]
        options = [uz] + others[:3]
        random.shuffle(options)
        test_data.append({"word_id": wid, "english": en, "correct": uz, "options": options})

    user_states[user_id] = {
        "state": "test",
        "level": "Weak",
        "section": "Weak Words",
        "questions": test_data,
        "current": 0,
        "score": 0,
        "wrong": []
    }

    bot.answer_callback_query(call.id)
    send_next_question(chat_id, user_id)

# ==================== LIDERLAR ====================
def show_leaders(message):
    c.execute("""SELECT username, total_correct, total_tests 
                 FROM users 
                 WHERE total_tests > 0 
                 ORDER BY (total_correct * 1.0 / total_tests) DESC LIMIT 10""")
    rows = c.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "Hali liderlar yo‘q!")
        return

    text = "🏆 <b>Top 10 Liderlar</b>\n\n"
    for i, (name, corr, tot) in enumerate(rows, 1):
        perc = round(corr / tot * 100) if tot else 0
        text += f"{i}. <b>{name or 'Anonymous'}</b> — <b>{perc}%</b> ({corr}/{tot})\n"

    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== CHALLENGES ====================
def show_challenges(message):
    c.execute("SELECT id, name, date, price, prize FROM challenges")
    rows = c.fetchall()

    if not rows:
        c.execute("INSERT INTO challenges (name, date, price, prize) VALUES (?, ?, ?, ?)",
                  ("Weekly Word Master", "2026-04-12", 10000, 100000))
        conn.commit()
        rows = c.fetchall()  # qayta o'qish

    text = "💰 <b>Mavjud Challenge'lar</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch_id, name, ch_date, price, prize in rows:
        text += f"🔥 <b>{name}</b>\nSana: {ch_date}\nNarx: {price} so‘m\nMukofot: {prize} so‘m\n\n"
        markup.add(types.InlineKeyboardButton(f"Join {name}", callback_data=f"join_ch:{ch_id}"))

    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

# ==================== ADMIN PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Admin emassiz!")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Add Words (Group)", "📋 View Users")
    markup.add("📢 Broadcast", "💰 Manage Challenges")
    bot.send_message(message.chat.id, "🛠 <b>ADMIN PANEL</b>", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Add Words (Group)")
def add_words_group(message):
    bot.send_message(message.chat.id,
        "Quyidagi formatda yuboring:\n\n"
        "<b>Level | Section | English - Uzbek</b>\n\n"
        "Misol:\n"
        "A1 | Daily Life | hello - salom\n"
        "IELTS | Academic | sustainable - barqaror\n\n"
        "Bir nechta qator yozing.")
    user_states[ADMIN_ID] = {"state": "add_words_group"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_state_handler(message):
    if ADMIN_ID not in user_states:
        return
    st = user_states[ADMIN_ID]

    if st.get("state") == "add_words_group":
        added = 0
        for line in message.text.strip().split("\n"):
            if "|" not in line or "-" not in line:
                continue
            try:
                left, uz = [x.strip() for x in line.split("-", 1)]
                parts = [x.strip() for x in left.split("|")]
                if len(parts) == 3:
                    level, section, english = parts
                elif len(parts) == 2:
                    level, section, english = parts[0], "General", parts[1]
                else:
                    continue

                c.execute("INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)",
                          (level, section, english, uz))
                added += 1
            except:
                continue

        conn.commit()
        bot.send_message(message.chat.id, f"✅ {added} ta so‘z qo‘shildi!", parse_mode='HTML')
        user_states.pop(ADMIN_ID, None)

# ==================== BOSHQA ====================
@bot.message_handler(commands=['myid'])
def my_id(message):
    bot.send_message(message.chat.id, f"Sizning ID: <code>{message.from_user.id}</code>", parse_mode='HTML')

# ==================== BOTNI ISHGA TUSHIRISH ====================
print("🚀 WORD TEST BOT to'liq ishga tushdi!")
bot.infinity_polling()