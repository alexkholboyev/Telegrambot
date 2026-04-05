import telebot
from telebot import types
import sqlite3
import random
import json
from datetime import date, timedelta

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8660534874:AAG-qTma8aY8bfOywi7BHLQdYZC8xWiGkx0"
ADMIN_ID = 5932847351
ADMIN_CARD_NUMBER = "9860036673467175"   # ← O'Z KARTANGIZ RAQAMINI YOZING
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

conn = sqlite3.connect('word_test_bot.db', check_same_thread=False)
c = conn.cursor()

c.executescript('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    total_tests INTEGER DEFAULT 0,
    total_correct INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    last_test_date TEXT,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    coins INTEGER DEFAULT 0
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
    participants TEXT DEFAULT '[]',
    winner_id INTEGER DEFAULT NULL,
    winner_paid INTEGER DEFAULT 0
);
''')
conn.commit()

# Namuna so'zlar (ko'paytirildi, endi har bir bo'limda yetarli so'z bor)
c.execute("SELECT COUNT(*) FROM words")
if c.fetchone()[0] == 0:
    samples = [
        ("A1", "Daily Life", "hello", "salom"), ("A1", "Daily Life", "goodbye", "xayr"),
        ("A1", "Daily Life", "apple", "olma"), ("A1", "Daily Life", "water", "suv"),
        ("A1", "Animals", "cat", "mushuk"), ("A1", "Animals", "dog", "it"),
        ("A1", "Animals", "bird", "qush"), ("A1", "Animals", "fish", "baliq"),
        ("A2", "School", "school", "maktab"), ("A2", "School", "teacher", "o'qituvchi"),
        ("A2", "School", "book", "kitob"), ("A2", "School", "student", "o'quvchi"),
        ("A2", "Travel", "travel", "sayohat"), ("A2", "Travel", "hotel", "mehmonxona"),
        ("A2", "Travel", "ticket", "bileta"), ("A2", "Travel", "airport", "aeroport"),
        ("B1", "General", "important", "muhim"), ("B1", "General", "happy", "baxtli"),
        ("B1", "Environment", "environment", "atrof-muhit"), ("B1", "Environment", "pollution", "ifloslanish"),
        ("IELTS", "Academic", "sustainable", "barqaror"), ("IELTS", "Academic", "innovation", "innovatsiya"),
        ("IELTS", "Academic", "research", "tadqiqot"), ("IELTS", "Academic", "analysis", "tahlil"),
    ]
    for lvl, sec, en, uz in samples:
        c.execute("INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)", (lvl, sec, en, uz))
    conn.commit()

user_states = {}

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📘 Test", "📊 My Statistics")
    markup.add("❗ My Weak Words", "🏆 Leaders")
    markup.add("💰 Earn Challenge", "💰 My Coins")
    return markup

# ==================== START ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    bot.send_message(message.chat.id, "👋 Xush kelibsiz <b>WORD TEST BOT</b> ga!\n\nTest ishlang → XOS coin ishlang → Challenge da pul ishlang!", reply_markup=main_keyboard())

# ==================== MENU ====================
@bot.message_handler(func=lambda m: m.text in ["📘 Test", "📊 My Statistics", "❗ My Weak Words", "🏆 Leaders", "💰 Earn Challenge", "💰 My Coins"])
def menu_handler(message):
    if message.text == "📘 Test": show_levels(message)
    elif message.text == "📊 My Statistics": show_statistics(message)
    elif message.text == "❗ My Weak Words": show_weak_words(message)
    elif message.text == "🏆 Leaders": show_leaders(message)
    elif message.text == "💰 Earn Challenge": show_challenges(message)
    elif message.text == "💰 My Coins": show_coins(message)

# ==================== MY COINS ====================
def show_coins(message):
    user_id = message.from_user.id
    c.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    coins = row[0] if row else 0
    bot.send_message(message.chat.id, f"💰 <b>Sizning XOS coinlaringiz</b>\n\n💎 Jami: <b>{coins}</b> XOS coin\n\nHar bir toʻgʻri javob = +1 coin!")

# ==================== TEST ====================
def show_levels(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for lvl in ["A1", "A2", "B1", "B2", "IELTS"]:
        markup.add(types.InlineKeyboardButton(lvl, callback_data=f"level:{lvl}"))
    bot.send_message(message.chat.id, "📘 Qaysi <b>darajadan</b> test boshlaymiz?", reply_markup=markup)

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
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"📘 {level} darajasi\n\nQaysi <b>bo'lim</b>dan test qilamiz?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("start_test:"))
def start_test(call):
    _, level, section = call.data.split(":")
    user_id = call.from_user.id
    if user_id in user_states and user_states[user_id].get("state") == "test":
        bot.answer_callback_query(call.id, "Siz allaqachon testda turibsiz!")
        return
    c.execute("SELECT id, english, uz_meaning FROM words WHERE level = ? AND section = ? ORDER BY RANDOM() LIMIT 10", (level, section))
    questions_raw = c.fetchall()
    if len(questions_raw) == 0:  # Tuzatildi: endi kam so'z bo'lsa ham test boshlanadi (oldingi <5 tufayli test ishlamayotgan edi)
        bot.answer_callback_query(call.id, "Bu bo'limda so'z yo'q!")
        return

    test_data = []
    for wid, en, uz in questions_raw:
        c.execute("SELECT uz_meaning FROM words WHERE level=? AND section=? AND id != ? ORDER BY RANDOM() LIMIT 3", (level, section, wid))
        others = [r[0] for r in c.fetchall()]
        options = [uz] + others
        random.shuffle(options)
        test_data.append({"word_id": wid, "english": en, "correct": uz, "options": options})

    user_states[user_id] = {"state": "test", "level": level, "section": section, "questions": test_data, "current": 0, "score": 0, "wrong": []}
    bot.answer_callback_query(call.id, "✅ Test boshlandi!")
    send_next_question(call.message.chat.id, user_id)

def send_next_question(chat_id, user_id):
    state = user_states.get(user_id)
    if not state or state["current"] >= len(state["questions"]):
        end_test(chat_id, user_id)
        return
    q = state["questions"][state["current"]]
    markup = types.InlineKeyboardMarkup(row_width=2)
    for i, opt in enumerate(q["options"]):
        markup.add(types.InlineKeyboardButton(opt, callback_data=f"answer:{state['current']}:{i}"))
    text = f"❓ Savol <b>{state['current'] + 1}/{len(state['questions'])}</b>\n\n<b>{state['level']}</b> • <b>{state['section']}</b>\n\nSo‘z: <b>{q['english']}</b>\nMa’nosini tanlang:"
    bot.send_message(chat_id, text, reply_markup=markup)

def end_test(chat_id, user_id):
    state = user_states.pop(user_id, None)
    if not state: return
    score = state["score"]
    total = len(state["questions"])
    percent = round(score / total * 100) if total else 0

    c.execute("""UPDATE users SET total_tests = total_tests + 1, total_correct = total_correct + ?, xp = xp + ?, coins = coins + ? WHERE user_id = ?""", 
              (score, score * 10, score, user_id))

    c.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
    new_xp = c.fetchone()[0]
    new_lvl = (new_xp // 1000) + 1
    c.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_lvl, user_id))

    for wid in state.get("wrong", []):
        c.execute("""INSERT INTO user_weak (user_id, word_id, error_count) VALUES (?, ?, 1) ON CONFLICT(user_id, word_id) DO UPDATE SET error_count = error_count + 1""", (user_id, wid))

    today = date.today().isoformat()
    c.execute("SELECT last_test_date, streak FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone() or (None, 0)
    last, streak = row
    if last != today:
        if last and date.fromisoformat(last) == date.today() - timedelta(days=1):
            streak += 1
        else:
            streak = 1
        c.execute("UPDATE users SET streak = ?, last_test_date = ? WHERE user_id = ?", (streak, today, user_id))

    conn.commit()
    bot.send_message(chat_id, f"🎉 <b>Test tugadi!</b>\n\nDaraja: <b>{state['level']}</b> | Bo‘lim: <b>{state['section']}</b>\nTo‘g‘ri: <b>{score}/{total}</b> ({percent}%)\n💎 +{score} XOS coin | XP: +{score*10} | Streak: 🔥 {streak} kun", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("answer:"))
def process_answer(call):
    user_id = call.from_user.id
    try:
        _, q_idx, opt_idx = call.data.split(":")
        q_idx = int(q_idx)
        opt_idx = int(opt_idx)
    except: return
    state = user_states.get(user_id)
    if not state or q_idx >= len(state["questions"]): return
    q = state["questions"][q_idx]
    if q["options"][opt_idx] == q["correct"]:
        state["score"] += 1
        bot.answer_callback_query(call.id, "✅ To‘g‘ri! +1 XOS coin")
    else:
        state["wrong"].append(q["word_id"])
        bot.answer_callback_query(call.id, f"❌ Xato! To‘g‘ri: {q['correct']}")
    state["current"] += 1
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_next_question(call.message.chat.id, user_id)

# ==================== STATISTIKA, ZAIF SO'ZLAR, LIDERLAR ====================
def show_statistics(message):
    user_id = message.from_user.id
    c.execute("SELECT total_tests, total_correct, xp, level, streak, coins FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row or row[0] == 0:
        bot.send_message(message.chat.id, "Siz hali test ishlamagansiz. 📘 Test bo‘limidan boshlang!")
        return
    tests, correct, xp, lvl, streak, coins = row
    perc = round(correct / tests * 100) if tests > 0 else 0
    bot.send_message(message.chat.id, f"📊 <b>Sizning statistikangiz</b>\n\nTestlar: <b>{tests}</b>\nTo‘g‘ri: <b>{correct}</b> ({perc}%)\nXP: <b>{xp}</b> | Level: <b>{lvl}</b>\nStreak: 🔥 <b>{streak}</b> kun\n💎 XOS Coins: <b>{coins}</b>")

def show_weak_words(message):
    user_id = message.from_user.id
    c.execute("""SELECT w.english, w.uz_meaning, uw.error_count FROM user_weak uw JOIN words w ON uw.word_id = w.id WHERE uw.user_id = ? ORDER BY uw.error_count DESC""", (user_id,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "✅ Sizda zaif so‘zlar yo‘q! Ajoyib!")
        return
    text = "❗ <b>Zaif so‘zlaringiz</b>\n\n"
    for en, uz, err in rows:
        text += f"• <b>{en}</b> — {uz} (<b>{err} marta</b>)\n"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Shu so‘zlardan test", callback_data="repeat_weak"))
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "repeat_weak")
def repeat_weak(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    c.execute("""SELECT w.id, w.english, w.uz_meaning FROM user_weak uw JOIN words w ON uw.word_id = w.id WHERE uw.user_id = ? ORDER BY RANDOM() LIMIT 10""", (user_id,))
    questions_raw = c.fetchall()
    if not questions_raw:
        bot.answer_callback_query(call.id, "Zaif so‘z topilmadi!")
        return
    test_data = []
    for wid, en, uz in questions_raw:
        c.execute("SELECT uz_meaning FROM words WHERE id != ? ORDER BY RANDOM() LIMIT 3", (wid,))
        others = [r[0] for r in c.fetchall()]
        options = [uz] + others
        random.shuffle(options)
        test_data.append({"word_id": wid, "english": en, "correct": uz, "options": options})
    user_states[user_id] = {"state": "test", "level": "Weak", "section": "Weak Words", "questions": test_data, "current": 0, "score": 0, "wrong": []}
    bot.answer_callback_query(call.id)
    send_next_question(chat_id, user_id)

def show_leaders(message):
    c.execute("""SELECT username, total_correct, total_tests, coins FROM users WHERE total_tests > 0 ORDER BY (total_correct * 1.0 / total_tests) DESC LIMIT 10""")
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Hali liderlar yo‘q!")
        return
    text = "🏆 <b>Top 10 Liderlar</b>\n\n"
    for i, (name, corr, tot, coins) in enumerate(rows, 1):
        perc = round(corr / tot * 100) if tot else 0
        text += f"{i}. <b>{name or 'Anonymous'}</b> — <b>{perc}%</b> ({corr}/{tot}) | 💎 {coins} coin\n"
    bot.send_message(message.chat.id, text)

# ==================== CHALLENGES ====================
def show_challenges(message):
    c.execute("SELECT id, name, date, price, prize FROM challenges")
    rows = c.fetchall()
    if not rows:
        c.execute("INSERT INTO challenges (name, date, price, prize) VALUES (?, ?, ?, ?)", ("Weekly Word Master", "2026-04-12", 10000, 100000))
        conn.commit()
        c.execute("SELECT id, name, date, price, prize FROM challenges")
        rows = c.fetchall()
    text = "💰 <b>Mavjud Challenge'lar</b>\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch_id, name, ch_date, price, prize in rows:
        text += f"🔥 <b>{name}</b>\nSana: {ch_date}\nNarx: {price:,} so‘m\nMukofot: {prize:,} so‘m\n\n"
        markup.add(types.InlineKeyboardButton(f"Join → {name}", callback_data=f"join_ch:{ch_id}"))
    text += f"\n💳 <b>To'lov kartasi:</b> <code>{ADMIN_CARD_NUMBER}</code>\nPul o'tkazgandan keyin screenshotni Admin ga yuboring!"
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("join_ch:"))
def join_challenge(call):
    ch_id = int(call.data.split(":")[1])
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    c.execute("SELECT name, price FROM challenges WHERE id = ?", (ch_id,))
    row = c.fetchone()
    if not row:
        bot.answer_callback_query(call.id, "Challenge topilmadi!")
        return
    name, price = row
    c.execute("SELECT participants FROM challenges WHERE id = ?", (ch_id,))
    participants = json.loads(c.fetchone()[0] or '[]')
    if user_id not in participants:
        participants.append(user_id)
        c.execute("UPDATE challenges SET participants = ? WHERE id = ?", (json.dumps(participants), ch_id))
        conn.commit()
    bot.answer_callback_query(call.id, "✅ Roʻyxatga qoʻshildingiz!")
    bot.send_message(chat_id, f"🎟 <b>{name}</b> challenge ga qo‘shildingiz!\n\n💳 To'lov: <b>{price:,} so‘m</b>\n💳 Karta: <code>{ADMIN_CARD_NUMBER}</code>\n\n✅ To'lov qiling va screenshotni Admin ga yuboring!")

# ==================== ADMIN PANEL ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "❌ Admin emassiz!")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("➕ Add Words (Group)", "📋 View Users")
    markup.add("📢 Broadcast", "💰 Manage Challenges")
    markup.add("🏆 New Challenge", "👑 Set Winner")
    bot.send_message(message.chat.id, "🛠 <b>ADMIN PANEL — Mukammal</b>", reply_markup=markup)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "➕ Add Words (Group)")
def add_words_group(message):
    bot.send_message(message.chat.id, "Quyidagi formatda yuboring:\n\nLevel | Section | English - Uzbek\nMisol: A1 | Daily Life | hello - salom")
    user_states[ADMIN_ID] = {"state": "add_words_group"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📋 View Users")
def view_users(message):
    c.execute("SELECT user_id, username, level, xp, coins, total_tests FROM users ORDER BY xp DESC LIMIT 20")
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Hali foydalanuvchilar yo‘q.")
        return
    text = "👥 <b>Top 20 Foydalanuvchilar</b>\n\n"
    for uid, uname, lvl, xp, coins, tests in rows:
        text += f"• <b>{uname}</b> (ID: <code>{uid}</code>) — Lvl {lvl} | XP: {xp} | Coins: {coins} | Test: {tests}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 Broadcast")
def broadcast(message):
    bot.send_message(message.chat.id, "✉️ Barchaga yubormoqchi bo‘lgan xabarni yozing:")
    user_states[ADMIN_ID] = {"state": "broadcast"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "🏆 New Challenge")
def new_challenge(message):
    bot.send_message(message.chat.id, "Yangi challenge:\nName | Date | Price | Prize\nMasalan: Monthly Master | 2026-05-01 | 15000 | 150000")
    user_states[ADMIN_ID] = {"state": "new_challenge"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "💰 Manage Challenges")
def manage_challenges(message):
    c.execute("SELECT id, name, date, price, prize, participants FROM challenges")
    rows = c.fetchall()
    text = "💰 <b>Challenge'lar ro‘yxati</b>\n\n"
    for ch_id, name, ch_date, price, prize, parts in rows:
        parts_list = json.loads(parts or '[]')
        text += f"ID: <b>{ch_id}</b> | {name} | {ch_date} | Narx: {price:,} | Mukofot: {prize:,} | Ishtirokchilar: {len(parts_list)}\n"
    bot.send_message(message.chat.id, text or "Hali challenge yo‘q")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "👑 Set Winner")
def set_winner(message):
    bot.send_message(message.chat.id, "Challenge ID va g‘olib user ID ni yuboring:\nMasalan: 1 987654321")
    user_states[ADMIN_ID] = {"state": "set_winner"}

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID)
def admin_state_handler(message):
    if ADMIN_ID not in user_states: return
    st = user_states[ADMIN_ID]
    if st.get("state") == "add_words_group":
        added = 0
        for line in message.text.strip().split("\n"):
            if "|" not in line or "-" not in line: continue
            try:
                left, uz = [x.strip() for x in line.split("-", 1)]
                parts = [x.strip() for x in left.split("|")]
                level = parts[0]
                section = parts[1] if len(parts) > 1 else "General"
                english = parts[2] if len(parts) > 2 else parts[1]
                c.execute("INSERT OR IGNORE INTO words (level, section, english, uz_meaning) VALUES (?, ?, ?, ?)", (level, section, english, uz))
                added += 1
            except: continue
        conn.commit()
        bot.send_message(message.chat.id, f"✅ {added} ta so‘z qo‘shildi!")
        user_states.pop(ADMIN_ID, None)
    elif st.get("state") == "broadcast":
        c.execute("SELECT user_id FROM users")
        users = [row[0] for row in c.fetchall()]
        sent = 0
        for uid in users:
            try:
                bot.send_message(uid, message.text)
                sent += 1
            except: pass
        bot.send_message(message.chat.id, f"✅ {sent} ta foydalanuvchiga yetkazildi!")
        user_states.pop(ADMIN_ID, None)
    elif st.get("state") == "new_challenge":
        try:
            name, date_str, price, prize = [x.strip() for x in message.text.split("|")]
            c.execute("INSERT INTO challenges (name, date, price, prize) VALUES (?, ?, ?, ?)", (name, date_str, int(price), int(prize)))
            conn.commit()
            bot.send_message(message.chat.id, f"✅ <b>{name}</b> challenge qo‘shildi!")
        except:
            bot.send_message(message.chat.id, "❌ Format xato!")
        user_states.pop(ADMIN_ID, None)
    elif st.get("state") == "set_winner":
        try:
            parts = message.text.strip().split()
            if len(parts) != 2:
                raise ValueError
            ch_id = int(parts[0])
            winner_id = int(parts[1])
            c.execute("UPDATE challenges SET winner_id = ? WHERE id = ?", (winner_id, ch_id))
            conn.commit()
            bot.send_message(message.chat.id, f"✅ Challenge ID {ch_id} uchun g‘olib {winner_id} belgilandi!")
        except:
            bot.send_message(message.chat.id, "❌ Format xato! Masalan: 1 987654321")
        user_states.pop(ADMIN_ID, None)

print("✅ BOT ISHLADI! Test endi to'g'ri ishlaydi.")
bot.infinity_polling()