import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import date, timedelta
import time

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"  # BotFather dan oling
ADMIN_ID = 5932847351              # O'zingizning Telegram ID-ingiz (botga /myid yozib bilib oling)
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN)

# DB yaratish
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
    english TEXT UNIQUE,
    uz_meaning TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_weak (
    user_id INTEGER,
    word_id INTEGER,
    error_count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, word_id)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    level TEXT,
    score INTEGER,
    total_questions INTEGER,
    date TEXT
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

# Agar so'zlar bo'sh bo'lsa, namuna so'zlar qo'shish (A1 dan IELTS gacha)
c.execute("SELECT COUNT(*) FROM words")
if c.fetchone()[0] == 0:
    samples = [
        # A1
        ("A1", "hello", "salom"), ("A1", "apple", "olma"), ("A1", "book", "kitob"),
        ("A1", "cat", "mushuk"), ("A1", "dog", "it"), ("A1", "house", "uy"),
        ("A1", "water", "suv"), ("A1", "food", "ovqat"), ("A1", "friend", "do'st"),
        # A2
        ("A2", "happy", "baxtli"), ("A2", "school", "maktab"), ("A2", "family", "oilasi"),
        ("A2", "work", "ish"), ("A2", "city", "shahar"), ("A2", "travel", "sayohat"),
        # B1
        ("B1", "important", "muhim"), ("B1", "knowledge", "bilim"), ("B1", "success", "muvaffaqiyat"),
        ("B1", "challenge", "qiyinchilik"), ("B1", "environment", "atrof-muhit"),
        # B2
        ("B2", "analysis", "tahlil"), ("B2", "technology", "texnologiya"), ("B2", "global", "global"),
        # IELTS
        ("IELTS", "sustainable", "barqaror"), ("IELTS", "innovation", "innovatsiya"),
        ("IELTS", "impact", "ta'sir"), ("IELTS", "perspective", "nuqtai nazar"),
    ]
    for lvl, en, uz in samples:
        c.execute("INSERT OR IGNORE INTO words (level, english, uz_meaning) VALUES (?, ?, ?)", (lvl, en, uz))
    conn.commit()

# Foydalanuvchi holatlari (FSM)
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

# ==================== START ====================
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

# ==================== MENU HANDLER ====================
@bot.message_handler(func=lambda m: m.text in ["📘 Test", "📊 My Statistics", "❗ My Weak Words", "🏆 Leaders", "💰 Earn Challenge"])
def menu_handler(message):
    text = message.text
    user_id = message.from_user.id

    if text == "📘 Test":
        markup = types.InlineKeyboardMarkup(row_width=2)
        levels = ["A1", "A2", "B1", "B2", "IELTS"]
        for lvl in levels:
            markup.add(types.InlineKeyboardButton(lvl, callback_data=f"start_test:{lvl}"))
        bot.send_message(message.chat.id, "📘 Qaysi darajadan test boshlaymiz?", reply_markup=markup)

    elif text == "📊 My Statistics":
        show_statistics(message)

    elif text == "❗ My Weak Words":
        show_weak_words(message)

    elif text == "🏆 Leaders":
        show_leaders(message)

    elif text == "💰 Earn Challenge":
        show_challenges(message)

# ==================== TEST BOSHLASH ====================
def start_test(message, level, user_id):
    c.execute("SELECT id, english, uz_meaning FROM words WHERE level = ? ORDER BY RANDOM() LIMIT 10", (level,))
    questions_raw = c.fetchall()
    if len(questions_raw) < 5:
        bot.send_message(message.chat.id, f"❌ {level} darajada yetarli so'z yo'q. Admin so'z qo'shsin!")
        return

    test_data = []
    for q in questions_raw:
        word_id, english, correct = q
        # 3 ta noto'g'ri variant olish
        c.execute("SELECT uz_meaning FROM words WHERE level = ? AND id != ? ORDER BY RANDOM() LIMIT 3", (level, word_id))
        others = [row[0] for row in c.fetchall()]
        while len(others) < 3:
            others.append("boshqa variant")
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
        "questions": test_data,
        "current": 0,
        "score": 0,
        "wrong": []
    }
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

    text = f"❓ Savol {state['current'] + 1}/10\n\n" \
           f"So‘z: <b>{q['english']}</b>\n\nMa’nosini tanlang:"
    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

def end_test(chat_id, user_id):
    state = user_states.pop(user_id, None)
    if not state:
        return
    score = state["score"]
    total = len(state["questions"])
    percent = round(score / total * 100)

    # Umumiy statistika yangilash
    c.execute("UPDATE users SET total_tests = total_tests + 1, total_correct = total_correct + ? WHERE user_id = ?",
              (score, user_id))
    # XP va level
    xp_gain = score * 10
    c.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (xp_gain, user_id))
    c.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    new_xp = c.fetchone()[0]
    new_level = (new_xp // 1000) + 1
    c.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))

    # Zaif so'zlar
    for w_id in state["wrong"]:
        c.execute("""INSERT INTO user_weak (user_id, word_id, error_count) 
                     VALUES (?, ?, 1) 
                     ON CONFLICT(user_id, word_id) DO UPDATE SET error_count = error_count + 1""",
                  (user_id, w_id))
    conn.commit()

    # Streak
    today = date.today().isoformat()
    c.execute("SELECT last_test_date, streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    last_date = row[0]
    streak = row[1] if row else 0
    if last_date == today:
        pass  # bugun allaqachon test qilgan
    else:
        if last_date and date.fromisoformat(last_date) == date.today() - timedelta(days=1):
            streak += 1
        else:
            streak = 1
    c.execute("UPDATE users SET streak = ?, last_test_date = ? WHERE user_id = ?", (streak, today, user_id))
    conn.commit()

    bot.send_message(
        chat_id,
        f"🎉 <b>Test tugadi!</b>\n\n"
        f"To‘g‘ri javoblar: <b>{score}/{total}</b> ({percent}%)\n"
        f"XP olingan: +{score*10}\n"
        f"Streak: 🔥 {streak} kun\n\n"
        f"Zaif so‘zlar: {len(state['wrong'])} ta",
        parse_mode='HTML',
        reply_markup=main_keyboard()
    )

# ==================== CALLBACK HANDLER (TEST JAVOBLARI) ====================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    data = call.data

    # TEST JAVOBI
    if data.startswith("answer:"):
        _, q_idx_str, opt_idx_str = data.split(":")
        q_idx = int(q_idx_str)
        opt_idx = int(opt_idx_str)
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
        # Eski xabarni o‘chirish va yangi savolni yuborish
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        send_next_question(call.message.chat.id, user_id)

    # WEAK WORDS REPEAT TEST
    elif data == "repeat_weak":
        show_weak_test(call.message.chat.id, user_id)

    # CHALLENGE JOIN
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
                bot.send_message(call.message.chat.id, "💰 To‘lov muvaffaqiyatli (Click/Payme/Crypto mock). Challenge ga qo‘shildingiz!")
            else:
                bot.answer_callback_query(call.id, "Siz allaqachon qo‘shilgansiz!")

    # ADMIN CALLBACK (keyinroq)
    elif call.from_user.id == ADMIN_ID and data.startswith("admin_"):
        pass  # keyin kengaytiriladi

# ==================== STATISTIKA ====================
def show_statistics(message):
    user_id = message.from_user.id
    c.execute("SELECT total_tests, total_correct, xp, level, streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row or row[0] == 0:
        bot.send_message(message.chat.id, "📊 Siz hali hech qanday test qilmagansiz. 📘 Test bo‘limidan boshlang!")
        return
    tests, correct, xp, lvl, streak = row
    percent = round(correct / tests * 100) if tests else 0
    bot.send_message(
        message.chat.id,
        f"📊 <b>Sizning statistikangiz</b>\n\n"
        f"Testlar soni: <b>{tests}</b>\n"
        f"To‘g‘ri javoblar: <b>{correct}</b>\n"
        f"O‘rtacha natija: <b>{percent}%</b>\n"
        f"XP: <b>{xp}</b>  |  Level: <b>{lvl}</b>\n"
        f"Streak: 🔥 <b>{streak} kun</b>",
        parse_mode='HTML'
    )

# ==================== ZAIF SO‘ZLAR ====================
def show_weak_words(message):
    user_id = message.from_user.id
    c.execute("""SELECT w.english, w.uz_meaning, uw.error_count 
                 FROM user_weak uw 
                 JOIN words w ON uw.word_id = w.id 
                 WHERE uw.user_id = ? AND uw.error_count > 0 
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
                 WHERE uw.user_id = ? AND uw.error_count > 0 
                 ORDER BY RANDOM() LIMIT 10""", (user_id,))
    questions_raw = c.fetchall()
    if not questions_raw:
        bot.send_message(chat_id, "Zaif so‘zlar topilmadi!")
        return

    test_data = []
    for q in questions_raw:
        word_id, english, correct = q
        c.execute("SELECT uz_meaning FROM words WHERE id != ? ORDER BY RANDOM() LIMIT 3", (word_id,))
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
        "level": "Weak Words",
        "questions": test_data,
        "current": 0,
        "score": 0,
        "wrong": []
    }
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
    for rank, (name, corr, tot) in enumerate(rows, 1):
        perc = round(corr / tot * 100) if tot else 0
        text += f"{rank}. <b>{name or 'Anonymous'}</b> — <b>{perc}%</b> ({corr}/{tot})\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ==================== CHALLENGE ====================
def show_challenges(message):
    c.execute("SELECT id, name, date, price, prize FROM challenges")
    rows = c.fetchall()
    if not rows:
        # Namuna challenge yaratish
        c.execute("INSERT INTO challenges (name, date, price, prize) VALUES (?, ?, ?, ?)",
                  ("Weekly Word Master", "2026-04-12", 10000, 100000))
        conn.commit()
        rows = c.fetchall()  # qayta o‘qish

    text = "💰 <b>Mavjud Challenge‘lar</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch_id, name, ch_date, price, prize in rows:
        text += f"🔥 <b>{name}</b>\nSana: {ch_date}\nNarx: {price} so‘m\nMukofot: {prize} so‘m\n\n"
        markup.add(types.InlineKeyboardButton(f"Join {name}", callback_data=f"join_ch:{ch_id}"))
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

# ==================== ADMIN PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Siz admin emassiz!")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("➕ Add Word"),
        types.KeyboardButton("📋 View All Users"),
        types.KeyboardButton("📢 Broadcast"),
        types.KeyboardButton("💰 Manage Challenges")
    )
    bot.send_message(message.chat.id, "🛠 <b>ADMIN PANEL</b>", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text in ["➕ Add Word", "📋 View All Users", "📢 Broadcast", "💰 Manage Challenges"])
def admin_commands(message):
    if message.text == "➕ Add Word":
        bot.send_message(message.chat.id, "Level kiriting (A1/A2/B1/B2/IELTS):")
        user_states[ADMIN_ID] = {"state": "add_word_level"}
    elif message.text == "📋 View All Users":
        c.execute("SELECT user_id, username, total_tests, total_correct FROM users LIMIT 20")
        rows = c.fetchall()
        text = "👥 Foydalanuvchilar:\n\n"
        for uid, un, t, c_ in rows:
            text += f"ID: {uid} | @{un} | Test: {t} | Correct: {c_}\n"
        bot.send_message(message.chat.id, text)
    elif message.text == "📢 Broadcast":
        bot.send_message(message.chat.id, "Barchaga yuboriladigan matnni yozing (yoki /cancel):")
        user_states[ADMIN_ID] = {"state": "broadcast"}
    elif message.text == "💰 Manage Challenges":
        bot.send_message(message.chat.id, "Challenge nomi, sana (YYYY-MM-DD), narx, mukofot kiriting (vergul bilan):\nMisol: Weekly, 2026-04-20, 15000, 150000")
        user_states[ADMIN_ID] = {"state": "new_challenge"}

# Admin holatlarini qayta ishlash
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_state_handler(message):
    state = user_states.get(ADMIN_ID, {})
    if state.get("state") == "add_word_level":
        user_states[ADMIN_ID] = {"state": "add_word_en", "level": message.text}
        bot.send_message(message.chat.id, "English so‘zni kiriting:")
    elif state.get("state") == "add_word_en":
        user_states[ADMIN_ID]["english"] = message.text
        bot.send_message(message.chat.id, "Uzbekcha ma’nosini kiriting:")
        user_states[ADMIN_ID]["state"] = "add_word_uz"
    elif state.get("state") == "add_word_uz":
        level = state["level"]
        en = state["english"]
        uz = message.text
        c.execute("INSERT OR IGNORE INTO words (level, english, uz_meaning) VALUES (?, ?, ?)", (level, en, uz))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ So‘z qo‘shildi!\n{level} | {en} — {uz}")
        user_states.pop(ADMIN_ID, None)
    elif state.get("state") == "broadcast":
        if message.text == "/cancel":
            user_states.pop(ADMIN_ID, None)
            return
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
        for uid in users:
            try:
                bot.send_message(uid[0], message.text)
            except:
                pass
        bot.send_message(message.chat.id, f"✅ {len(users)} ta foydalanuvchiga yuborildi!")
        user_states.pop(ADMIN_ID, None)
    elif state.get("state") == "new_challenge":
        try:
            name, ch_date, price, prize = [x.strip() for x in message.text.split(",")]
            c.execute("INSERT INTO challenges (name, date, price, prize) VALUES (?, ?, ?, ?)",
                      (name, ch_date, int(price), int(prize)))
            conn.commit()
            bot.send_message(message.chat.id, "✅ Challenge yaratildi!")
        except:
            bot.send_message(message.chat.id, "❌ Format xato! Qayta urinib ko‘ring.")
        user_states.pop(ADMIN_ID, None)

# ==================== BOSHQA KOMANDALAR ====================
@bot.message_handler(commands=['myid'])
def my_id(message):
    bot.send_message(message.chat.id, f"Sizning ID: <code>{message.from_user.id}</code>", parse_mode='HTML')

# ==================== BOTNI ISHGA TUSHIRISH ====================
print("🚀 WORD TEST BOT ishga tushdi...")
bot.infinity_polling()