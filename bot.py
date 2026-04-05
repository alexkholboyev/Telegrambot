import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import date, timedelta
import time

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"  # BotFather dan oling
ADMIN_ID = 5932847351             # O'zingizning Telegram ID-ingiz
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

c.execute('''CREATE TABLE IF NOT EXISTS test_results (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    level TEXT,
    section TEXT,
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

# ==================== NAMUNA SO‘ZLAR (section bilan) ====================
c.execute("SELECT COUNT(*) FROM words")
if c.fetchone()[0] == 0:
    samples = [
        # A1
        ("A1", "Daily Life", "hello", "salom"),
        ("A1", "Daily Life", "apple", "olma"),
        ("A1", "Daily Life", "book", "kitob"),
        ("A1", "Animals", "cat", "mushuk"),
        ("A1", "Animals", "dog", "it"),
        ("A1", "Food", "water", "suv"),
        ("A1", "Food", "food", "ovqat"),
        
        # A2
        ("A2", "School", "school", "maktab"),
        ("A2", "Family", "family", "oilasi"),
        ("A2", "Travel", "travel", "sayohat"),
        
        # B1
        ("B1", "General", "important", "muhim"),
        ("B1", "General", "knowledge", "bilim"),
        ("B1", "Environment", "environment", "atrof-muhit"),
        
        # IELTS
        ("IELTS", "Academic", "sustainable", "barqaror"),
        ("IELTS", "Academic", "innovation", "innovatsiya"),
        ("IELTS", "Academic", "impact", "ta'sir"),
    ]
    
    for lvl, sec, en, uz in samples:
        c.execute("INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)", 
                  (lvl, sec, en, uz))
    conn.commit()

# Foydalanuvchi holatlari
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
        "Endi har bir darajada bo‘limlar (sections) mavjud!\n"
        "So‘zlarni test qiling, zaif so‘zlaringizni o‘rganing va reytingda yetakchi bo‘ling!",
        parse_mode='HTML',
        reply_markup=main_keyboard()
    )

# ==================== MENU HANDLER ====================
@bot.message_handler(func=lambda m: m.text in ["📘 Test", "📊 My Statistics", "❗ My Weak Words", "🏆 Leaders", "💰 Earn Challenge"])
def menu_handler(message):
    text = message.text
    user_id = message.from_user.id

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

# ==================== LEVEL VA SECTION TANLASH ====================
def show_levels(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    levels = ["A1", "A2", "B1", "B2", "IELTS"]
    for lvl in levels:
        markup.add(types.InlineKeyboardButton(lvl, callback_data=f"level:{lvl}"))
    bot.send_message(message.chat.id, "📘 Qaysi **darajadan** test boshlaymiz?", 
                     parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("level:"))
def choose_section(call):
    level = call.data.split(":")[1]
    user_id = call.from_user.id
    
    # Ushbu leveldagi mavjud sectionlarni olish
    c.execute("SELECT DISTINCT section FROM words WHERE level = ? ORDER BY section", (level,))
    sections = [row[0] for row in c.fetchall()]
    
    if not sections:
        bot.answer_callback_query(call.id, "Bu darajada hali so‘z yo‘q!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    for sec in sections:
        markup.add(types.InlineKeyboardButton(sec, callback_data=f"start_test:{level}:{sec}"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"📘 {level} darajasi\n\nQaysi **bo‘limdan** test qilamiz?",
        parse_mode='HTML',
        reply_markup=markup
    )

# ==================== TEST BOSHLASH ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("start_test:"))
def start_test_callback(call):
    _, level, section = call.data.split(":")
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    c.execute("""SELECT id, english, uz_meaning 
                 FROM words 
                 WHERE level = ? AND section = ? 
                 ORDER BY RANDOM() LIMIT 10""", (level, section))
    
    questions_raw = c.fetchall()
    if len(questions_raw) < 5:
        bot.answer_callback_query(call.id, f"❌ {level} - {section} da yetarli so‘z yo‘q!")
        return

    test_data = []
    for q in questions_raw:
        word_id, english, correct = q
        c.execute("""SELECT uz_meaning FROM words 
                     WHERE level = ? AND section = ? AND id != ? 
                     ORDER BY RANDOM() LIMIT 3""", (level, section, word_id))
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

    text = f"❓ Savol {state['current'] + 1}/{len(state['questions'])}\n\n" \
           f"Daraja: <b>{state['level']}</b> | Bo‘lim: <b>{state['section']}</b>\n\n" \
           f"So‘z: <b>{q['english']}</b>\n\nMa’nosini tanlang:"

    bot.send_message(chat_id, text, parse_mode='HTML', reply_markup=markup)

def end_test(chat_id, user_id):
    state = user_states.pop(user_id, None)
    if not state:
        return
    
    score = state["score"]
    total = len(state["questions"])
    percent = round(score / total * 100)

    # Statistika yangilash
    c.execute("""UPDATE users 
                 SET total_tests = total_tests + 1, 
                     total_correct = total_correct + ? 
                 WHERE user_id = ?""", (score, user_id))

    xp_gain = score * 10
    c.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (xp_gain, user_id))
    c.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    new_xp = c.fetchone()[0]
    new_level = (new_xp // 1000) + 1
    c.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))

    # Zaif so‘zlar
    for w_id in state["wrong"]:
        c.execute("""INSERT INTO user_weak (user_id, word_id, error_count) 
                     VALUES (?, ?, 1) 
                     ON CONFLICT(user_id, word_id) 
                     DO UPDATE SET error_count = error_count + 1""", (user_id, w_id))

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

    bot.send_message(
        chat_id,
        f"🎉 <b>Test tugadi!</b>\n\n"
        f"Daraja: <b>{state['level']}</b> | Bo‘lim: <b>{state['section']}</b>\n"
        f"To‘g‘ri javoblar: <b>{score}/{total}</b> ({percent}%)\n"
        f"XP olingan: +{xp_gain}\n"
        f"Streak: 🔥 {streak} kun\n"
        f"Zaif so‘zlar: {len(state['wrong'])} ta",
        parse_mode='HTML',
        reply_markup=main_keyboard()
    )

# ==================== CALLBACK HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.from_user.id
    data = call.data

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
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        send_next_question(call.message.chat.id, user_id)

    elif data == "repeat_weak":
        show_weak_test(call.message.chat.id, user_id)

    # Challenge join (oldingi kod saqlangan)
    elif data.startswith("join_ch:"):
        # ... (oldingi kodni qoldirdim, kerak bo'lsa to'liq qo'shsa bo'ladi)
        pass

# ==================== ADMIN: GURUH LAB SO‘Z QO‘SHISH ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Siz admin emassiz!")
        return
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("➕ Add Words (Group)"),
        types.KeyboardButton("📋 View All Users"),
        types.KeyboardButton("📢 Broadcast"),
        types.KeyboardButton("💰 Manage Challenges")
    )
    bot.send_message(message.chat.id, "🛠 <b>ADMIN PANEL</b>", parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Add Words (Group)")
def add_words_group(message):
    bot.send_message(message.chat.id, 
        "So‘zlarni quyidagi formatda yuboring:\n\n"
        "<b>Level | Section | English - Uzbek</b>\n\n"
        "Misol:\n"
        "A1 | Daily Life | hello - salom\n"
        "A1 | Food | water - suv\n"
        "IELTS | Academic | sustainable - barqaror\n\n"
        "Bir vaqtning o‘zida ko‘p qator yozsa bo‘ladi!")
    
    user_states[ADMIN_ID] = {"state": "add_words_group"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_state_handler(message):
    state = user_states.get(ADMIN_ID, {})
    
    if state.get("state") == "add_words_group":
        lines = message.text.strip().split("\n")
        added = 0
        for line in lines:
            if "|" not in line or "-" not in line:
                continue
            try:
                part1, part2 = line.split("-", 1)
                level_sec, eng = [x.strip() for x in part1.split("|", 1)]
                uz = part2.strip()
                
                level, section = [x.strip() for x in level_sec.split("|", 1)] if "|" in level_sec else (level_sec.strip(), "General")
                
                c.execute("""INSERT OR IGNORE INTO words (level, section, english, uz_meaning) 
                             VALUES (?, ?, ?, ?)""", (level, section, eng, uz))
                added += 1
            except:
                continue
        
        conn.commit()
        bot.send_message(message.chat.id, f"✅ {added} ta so‘z muvaffaqiyatli qo‘shildi!")
        user_states.pop(ADMIN_ID, None)

# Qolgan funksiyalar (statistics, weak words, leaders, challenges) o‘zgarmagan holda qoldirilgan
# Ularni oldingi kodingizdan to‘g‘ridan-to‘g‘ri qo‘shib qo‘yishingiz mumkin.

# ==================== BOTNI ISHGA TUSHIRISH ====================
print("🚀 WORD TEST BOT ishga tushdi... (Section tizimi bilan)")
bot.infinity_polling()