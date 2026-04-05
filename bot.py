import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import date, timedelta

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"
ADMIN_ID = 5932847351
# =====================================================

bot = telebot.TeleBot(BOT_TOKEN)

# ==================== DB YARATISH ====================
conn = sqlite3.connect('word_test_bot.db', check_same_thread=False)
c = conn.cursor()

# Users jadvali
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

# Words jadvali
c.execute('''CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY,
    level TEXT,
    section TEXT DEFAULT 'General',
    english TEXT UNIQUE,
    uz_meaning TEXT
)''')

# User zaif so‘zlari
c.execute('''CREATE TABLE IF NOT EXISTS user_weak (
    user_id INTEGER,
    word_id INTEGER,
    error_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
)''')

# Challenges jadvali
c.execute('''CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY,
    name TEXT,
    date TEXT,
    price INTEGER,
    prize INTEGER,
    participants TEXT DEFAULT '[]'
)''')

conn.commit()

# ==================== SAMPLE SO'ZLAR ====================
c.execute("SELECT COUNT(*) FROM words")
if c.fetchone()[0] == 0:
    samples = [
        ("A1", "Greetings", "hello", "salom"),
        ("A1", "Greetings", "hi", "salom"),
        ("A1", "Food", "apple", "olma"),
        ("A1", "Food", "water", "suv"),
        ("A1", "Animals", "cat", "mushuk"),
        ("A1", "Animals", "dog", "it"),
        ("A2", "Work", "job", "ish"),
        ("A2", "Work", "school", "maktab"),
        ("A2", "Travel", "travel", "sayohat"),
        ("B1", "General", "important", "muhim"),
        ("B1", "General", "knowledge", "bilim"),
        ("B2", "Technology", "analysis", "tahlil"),
        ("IELTS", "Advanced", "sustainable", "barqaror"),
        ("IELTS", "Advanced", "innovation", "innovatsiya"),
    ]
    for lvl, section, en, uz in samples:
        c.execute(
            "INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)",
            (lvl, section, en, uz)
        )
    conn.commit()

# ==================== USER FSM ====================
user_states = {}

# ==================== ASOSIY KEYBOARD ====================
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📘 Test"),
        types.KeyboardButton("📊 My Statistics"),
        types.KeyboardButton("❗ My Weak Words")
    )
    markup.add(
        types.KeyboardButton("🏆 Leaders"),
        types.KeyboardButton("💰 Earn Challenge")
    )
    return markup

# ===================== START =====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    bot.send_message(
        message.chat.id,
        "👋 Xush kelibsiz <b>WORD TEST BOT</b> ga!\n\n"
        "So'zlarni test qiling, statistikangizni kuzating, zaif so'zlaringizni toping va reytingda yetakchi bo'ling!\n\n"
        "📘 Test bo'limidan boshlang!",
        parse_mode='HTML',
        reply_markup=main_keyboard()
    )

# ===================== MENU HANDLER =====================
@bot.message_handler(func=lambda m: m.text in ["📘 Test", "📊 My Statistics", "❗ My Weak Words", "🏆 Leaders", "💰 Earn Challenge"])
def menu_handler(message):
    text = message.text
    user_id = message.from_user.id

    if text == "📘 Test":
        markup = types.InlineKeyboardMarkup(row_width=2)
        levels = ["A1", "A2", "B1", "B2", "IELTS"]
        for lvl in levels:
            markup.add(types.InlineKeyboardButton(lvl, callback_data=f"choose_section:{lvl}"))
        bot.send_message(message.chat.id, "📘 Qaysi darajadan test boshlaymiz?", reply_markup=markup)

    elif text == "📊 My Statistics":
        show_statistics(message)

    elif text == "❗ My Weak Words":
        show_weak_words(message)

    elif text == "🏆 Leaders":
        show_leaders(message)

    elif text == "💰 Earn Challenge":
        show_challenges(message)

# ===================== CALLBACK HANDLER =====================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    data = call.data

    if data.startswith("choose_section:"):
        level = data.split(":")[1]
        c.execute("SELECT DISTINCT section FROM words WHERE level = ?", (level,))
        sections = [row[0] for row in c.fetchall()]
        if not sections:
            bot.answer_callback_query(call.id, f"{level} darajada section yo‘q!")
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for sec in sections:
            markup.add(types.InlineKeyboardButton(sec, callback_data=f"start_test:{level}:{sec}"))
        bot.send_message(call.message.chat.id, f"📂 {level} darajasidagi sectionni tanlang:", reply_markup=markup)

    elif data.startswith("start_test:"):
        _, level, section = data.split(":")
        start_test(call.message, level, section, user_id)

    elif data.startswith("answer:"):
        _, q_idx_str, opt_idx_str = data.split(":")
        q_idx = int(q_idx_str)
        opt_idx = int(opt_idx_str)
        state = user_states.get(user_id)
        if not state:
            bot.answer_callback_query(call.id, "⚠ Testni boshlang!")
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

    elif data == "repeat_weak":
        show_weak_test(call.message.chat.id, user_id)

    elif data.startswith("join_ch:"):
        ch_id = int(data.split(":")[1])
        c.execute("SELECT participants FROM challenges WHERE id = ?", (ch_id,))
        row = c.fetchone()
        if row:
            participants = json.loads(row[0])
            if user_id not in participants:
                participants.append(user_id)
                c.execute("UPDATE challenges SET participants = ? WHERE id = ?", (json.dumps(participants), ch_id))
                conn.commit()
                bot.answer_callback_query(call.id, "✅ Ro‘yxatga olindingiz! (To‘lov mock)")
                bot.send_message(call.message.chat.id, "💰 To‘lov muvaffaqiyatli! Challenge ga qo‘shildingiz!")
            else:
                bot.answer_callback_query(call.id, "Siz allaqachon qo‘shilgansiz!")

# ===================== TEST FUNKSIYALARI =====================
def start_test(message, level, section, user_id):
    c.execute("SELECT id, english, uz_meaning FROM words WHERE level=? AND section=? ORDER BY RANDOM()", (level, section))
    questions_raw = c.fetchall()
    if len(questions_raw) < 3:
        bot.send_message(message.chat.id, f"❌ {level} {section} darajada yetarli so'z yo'q!")
        return

    limit = min(10, len(questions_raw))
    questions_raw = questions_raw[:limit]

    test_data = []
    for q in questions_raw:
        word_id, english, correct = q
        c.execute("SELECT uz_meaning FROM words WHERE level=? AND id!=? ORDER BY RANDOM() LIMIT 3", (level, word_id))
        others = [row[0] for row in c.fetchall()]
        while len(others) < 3:
            others.append("boshqa variant")
        options = [correct] + others[:3]
        random.shuffle(options)
        test_data.append({"word_id": word_id, "english": english, "correct": correct, "options": options})

    user_states[user_id] = {"state": "test", "level": level, "section": section, "questions": test_data, "current": 0, "score": 0, "wrong": []}
    send_next_question(message.chat.id, user_id)

def send_next_question(chat_id, user_id):
    state = user_states.get(user_id)
    if not state or state["current"] >= len(state["questions"]):
        end_test(chat_id, user_id)
        return
    q = state["questions"][state["current"]]
    markup = types.InlineKeyboardMarkup(row_width=2)
    for i, opt in enumerate(q["options"]):
        markup.add(types.InlineKeyboardButton(opt, callback_data=f"answer:{state['current']}:{i}"))
    text = f"❓ Savol {state['current']+1}/{len(state['questions'])}\n\nSo‘z: <b>{q['english']}</b>\n\nMa’nosini tanlang:"
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

def end_test(chat_id, user_id):
    state = user_states.pop(user_id, None)
    if not state:
        return
    score = state["score"]
    total = len(state["questions"])
    percent = round(score / total * 100)

    # Statistika yangilash
    c.execute("UPDATE users SET total_tests=total_tests+1, total_correct=total_correct+? WHERE user_id=?", (score, user_id))
    xp_gain = score*10
    c.execute("UPDATE users SET xp = xp + ? WHERE user_id=?", (xp_gain, user_id))
    c.execute("SELECT xp FROM users WHERE user_id=?", (user_id,))
    new_xp = c.fetchone()[0]
    new_level = (new_xp//1000)+1
    c.execute("UPDATE users SET level=? WHERE user_id=?", (new_level, user_id))

    # Zaif so‘zlar
    for w_id in state["wrong"]:
        c.execute("""INSERT INTO user_weak (user_id, word_id, error_count)
                     VALUES (?, ?, 1)
                     ON CONFLICT(user_id, word_id) DO UPDATE SET error_count=error_count+1""",
                  (user_id, w_id))
    conn.commit()

    # Streak
    today = date.today().isoformat()
    c.execute("SELECT last_test_date, streak FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    last_date = row[0] if row else None
    streak = row[1] if row else 0
    if last_date != today:
        if last_date and date.fromisoformat(last_date) == date.today() - timedelta(days=1):
            streak += 1
        else:
            streak = 1
    c.execute("UPDATE users SET streak=?, last_test_date=? WHERE user_id=?", (streak, today, user_id))
    conn.commit()

    bot.send_message(chat_id,
        f"🎉 <b>Test tugadi!</b>\n\n"
        f"To‘g‘ri javoblar: <b>{score}/{total}</b> ({percent}%)\n"
        f"XP olingan: +{xp_gain}\n"
        f"Streak: 🔥 {streak} kun\n\n"
        f"Zaif so‘zlar: {len(state['wrong'])} ta",
        parse_mode='HTML',
        reply_markup=main_keyboard()
    )

# ===================== STATISTIKA, ZAIF SO'Z, LIDER, CHALLENGE =====================
def show_statistics(message):
    user_id = message.from_user.id
    c.execute("SELECT total_tests, total_correct, xp, level, streak FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row or row[0]==0:
        bot.send_message(message.chat.id, "📊 Siz hali hech qanday test qilmagansiz. 📘 Test bo‘limidan boshlang!")
        return
    tests, correct, xp, lvl, streak = row
    percent = round(correct/tests*100) if tests else 0
    bot.send_message(message.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"Testlar soni: <b>{tests}</b>\n"
        f"To‘g‘ri javoblar: <b>{correct}</b>\n"
        f"O‘rtacha natija: <b>{percent}%</b>\n"
        f"XP: <b>{xp}</b>  |  Level: <b>{lvl}</b>\n"
        f"Streak: 🔥 <b>{streak} kun</b>",
        parse_mode='HTML')

def show_weak_words(message):
    user_id = message.from_user.id
    c.execute("""SELECT w.english, w.uz_meaning, uw.error_count
                 FROM user_weak uw
                 JOIN words w ON uw.word_id = w.id
                 WHERE uw.user_id=? AND uw.error_count>0
                 ORDER BY uw.error_count DESC""", (user_id,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "✅ Sizda zaif so‘zlar yo‘q! Ajoyib natija! 🎉")
        return
    text = "❗ <b>Sizning zaif so‘zlaringiz</b>\n\n"
    for en, uz, err in rows:
        text += f"• <b>{en}</b> — {uz}  (<b>{err} marta xato</b>)\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Shu so‘zlardan test qilish", callback_data="repeat_weak"))
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

def show_weak_test(chat_id, user_id):
    c.execute("""SELECT w.id, w.english, w.uz_meaning
                 FROM user_weak uw
                 JOIN words w ON uw.word_id = w.id
                 WHERE uw.user_id=? AND uw.error_count>0
                 ORDER BY RANDOM() LIMIT 10""", (user_id,))
    questions_raw = c.fetchall()
    if not questions_raw:
        bot.send_message(chat_id, "Zaif so‘zlar topilmadi!")
        return
    test_data = []
    for q in questions_raw:
        word_id, english, correct = q
        c.execute("SELECT uz_meaning FROM words WHERE id!=? ORDER BY RANDOM() LIMIT 3", (word_id,))
        others = [row[0] for row in c.fetchall()]
        while len(others) < 3:
            others.append("boshqa variant")
        options = [correct] + others[:3]
        random.shuffle(options)
        test_data.append({"word_id": word_id, "english": english, "correct": correct, "options": options})
    user_states[user_id] = {"state":"test","level":"Weak Words","questions":test_data,"current":0,"score":0,"wrong":[]}
    send_next_question(chat_id, user_id)

def show_leaders(message):
    c.execute("""SELECT username, total_correct, total_tests
                 FROM users WHERE total_tests>0
                 ORDER BY (total_correct*1.0/total_tests) DESC LIMIT 10""")
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Hali liderlar yo‘q!")
        return
    text = "🏆 <b>Top 10 Liderlar</b>\n\n"
    for rank, (name, corr, tot) in enumerate(rows,1):
        perc = round(corr/tot*100) if tot else 0
        text += f"{rank}. <b>{name or 'Anonymous'}</b> — <b>{perc}%</b> ({corr}/{tot})\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

def show_challenges(message):
    c.execute("SELECT id, name, date, price, prize FROM challenges")
    rows = c.fetchall()

    if not rows:
        c.execute("INSERT INTO challenges (name, date, price, prize) VALUES (?,?,?,?)",
                  ("Weekly Word Master", "2026-04-12", 10000, 100000))
        conn.commit()
        c.execute("SELECT id, name, date, price, prize FROM challenges")
        rows = c.fetchall()

    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch_id, name, date_ch, price, prize in rows:
        markup.add(types.InlineKeyboardButton(
            f"{name} | {date_ch} | 💰 {prize}",
            callback_data=f"join_ch:{ch_id}"
        ))
    bot.send_message(message.chat.id, "💰 Mavjud challenge'lar:", reply_markup=markup)

# ===================== BOT POLLING =====================
if __name__ == "__main__":
    print("Bot ishga tushdi...")
    bot.infinity_polling()