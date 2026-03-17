import os
import sqlite3
import telebot
from telebot import types
from groq import Groq
from datetime import datetime, timedelta

# ──────────────── Настройки ────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

FREE_LIMIT = 3       # Кол-во бесплатных толкований
STARS_PRICE = 250    # Цена в Telegram Stars (~299 рублей)

# ──────────────── База данных ────────────────

def init_db():
    conn = sqlite3.connect("dreams.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            free_uses   INTEGER DEFAULT 3,
            sub_end     TEXT DEFAULT NULL,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id, username=None):
    conn = sqlite3.connect("dreams.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute(
            "INSERT INTO users (user_id, username, free_uses) VALUES (?, ?, ?)",
            (user_id, username, FREE_LIMIT)
        )
        conn.commit()
        user = (user_id, username, FREE_LIMIT, None, datetime.now().isoformat())
    conn.close()
    return user

def has_access(user_id):
    """
    Возвращает: (доступ: bool, тип: 'free'/'subscription'/None, осталось бесплатных: int)
    """
    user = get_user(user_id)
    free_uses = user[2]
    sub_end = user[3]

    if free_uses > 0:
        return True, "free", free_uses

    if sub_end:
        try:
            if datetime.now() < datetime.fromisoformat(sub_end):
                return True, "subscription", 0
        except:
            pass

    return False, None, 0

def spend_free_use(user_id):
    conn = sqlite3.connect("dreams.db")
    c = conn.cursor()
    c.execute("UPDATE users SET free_uses = free_uses - 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def activate_subscription(user_id):
    conn = sqlite3.connect("dreams.db")
    c = conn.cursor()
    c.execute("SELECT sub_end FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    current_end = None
    if row and row[0]:
        try:
            dt = datetime.fromisoformat(row[0])
            if dt > datetime.now():
                current_end = dt
        except:
            pass

    start = current_end if current_end else datetime.now()
    new_end = (start + timedelta(days=30)).isoformat()

    c.execute("UPDATE users SET sub_end = ? WHERE user_id = ?", (new_end, user_id))
    conn.commit()
    conn.close()
    return new_end

# ──────────────── ИИ-толкование ────────────────

def interpret_dream(dream_text):
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — мистический толкователь снов с многовековой мудростью. "
                    "Твой стиль: таинственный, глубокий, немного поэтичный. "
                    "Структура ответа:\n"
                    "1. Ключевые символы — разбери 2-3 главных образа из сна\n"
                    "2. Общее значение — что говорит этот сон о жизни человека\n"
                    "3. Послание — практический совет или предупреждение\n\n"
                    "Отвечай только на русском языке. Объём — 200-300 слов."
                )
            },
            {
                "role": "user",
                "content": f"Растолкуй мой сон: {dream_text}"
            }
        ],
        temperature=0.85,
        max_tokens=600
    )
    return response.choices[0].message.content

# ──────────────── Клавиатуры ────────────────

def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🌙 Рассказать сон"))
    markup.add(
        types.KeyboardButton("📊 Мой статус"),
        types.KeyboardButton("💳 Подписка")
    )
    return markup

# ──────────────── Команды ────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    name = message.from_user.first_name
    get_user(message.from_user.id, message.from_user.username)
    bot.send_message(
        message.chat.id,
        f"🌙 Добро пожаловать, {name}!\n\n"
        "Я раскрываю тайный смысл снов с помощью древней мудрости и искусственного интеллекта.\n\n"
        f"✨ Тебе доступно {FREE_LIMIT} бесплатных толкования.\n"
        "После этого — подписка за 299 руб/мес.\n\n"
        "Просто опиши свой сон — и я открою его значение 👇",
        reply_markup=main_keyboard()
    )

@bot.message_handler(commands=["status"])
def cmd_status(message):
    show_status(message)

@bot.message_handler(commands=["subscribe"])
def cmd_subscribe(message):
    show_subscribe(message)

@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.send_message(
        message.chat.id,
        "🌙 Как пользоваться ботом:\n\n"
        "1. Опиши свой сон подробно\n"
        "2. Бот проанализирует символы и образы\n"
        "3. Получи мистическое толкование\n\n"
        "Команды:\n"
        "/status — проверить статус аккаунта\n"
        "/subscribe — оформить подписку\n"
        "/help — эта справка",
        reply_markup=main_keyboard()
    )

# ──────────────── Кнопки меню ────────────────

def show_status(message):
    user = get_user(message.from_user.id)
    free_uses = user[2]
    sub_end = user[3]

    if free_uses > 0:
        text = (
            f"✨ Бесплатных толкований осталось: {free_uses} из {FREE_LIMIT}\n\n"
            "Когда они закончатся, оформи подписку — /subscribe"
        )
    elif sub_end:
        try:
            end_dt = datetime.fromisoformat(sub_end)
            if end_dt > datetime.now():
                days_left = (end_dt - datetime.now()).days
                end_date = end_dt.strftime("%d.%m.%Y")
                text = (
                    f"✅ Подписка активна\n"
                    f"Действует до: {end_date} (осталось {days_left} дн.)"
                )
            else:
                text = "❌ Подписка истекла.\n\nОформи новую — /subscribe"
        except:
            text = "❌ Бесплатные попытки закончились.\n\nОформи подписку — /subscribe"
    else:
        text = "❌ Бесплатные попытки закончились.\n\nОформи подписку — /subscribe"

    bot.send_message(message.chat.id, text, reply_markup=main_keyboard())

def show_subscribe(message):
    bot.send_message(
        message.chat.id,
        "💳 Подписка на Сонник\n\n"
        "✅ Неограниченные толкования\n"
        "✅ 30 дней доступа\n"
        "✅ Оплата через Telegram Stars\n\n"
        "Стоимость: 250 Stars (~299 руб.)"
    )
    bot.send_invoice(
        chat_id=message.chat.id,
        title="🌙 Сонник — подписка на 30 дней",
        description="Неограниченные толкования снов на 30 дней",
        invoice_payload="sub_30days",
        provider_token="",
        currency="XTR",
        prices=[types.LabeledPrice("Подписка 30 дней", STARS_PRICE)]
    )

# ──────────────── Оплата ────────────────

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=["successful_payment"])
def payment_done(message):
    new_end = activate_subscription(message.from_user.id)
    end_date = datetime.fromisoformat(new_end).strftime("%d.%m.%Y")
    bot.send_message(
        message.chat.id,
        f"🎉 Подписка активирована!\n\n"
        f"Действует до: {end_date}\n\n"
        "Теперь можешь толковать сны без ограничений 🌙",
        reply_markup=main_keyboard()
    )

# ──────────────── Обработка текста ────────────────

@bot.message_handler(func=lambda m: m.text == "🌙 Рассказать сон")
def ask_dream(message):
    bot.send_message(
        message.chat.id,
        "🌙 Опиши свой сон как можно подробнее.\n\nЧто ты видел? Какие были ощущения? Кто присутствовал?",
        reply_markup=types.ReplyKeyboardRemove()
    )

@bot.message_handler(func=lambda m: m.text == "📊 Мой статус")
def status_button(message):
    show_status(message)

@bot.message_handler(func=lambda m: m.text == "💳 Подписка")
def subscribe_button(message):
    show_subscribe(message)

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_dream(message):
    user_id = message.from_user.id
    dream_text = message.text.strip()

    if len(dream_text) < 15:
        bot.send_message(
            message.chat.id,
            "🌙 Опиши сон подробнее — напиши хотя бы пару предложений.",
            reply_markup=main_keyboard()
        )
        return

    access, access_type, free_left = has_access(user_id)

    if not access:
        bot.send_message(
            message.chat.id,
            "😔 Бесплатные толкования закончились.\n\n"
            "Оформи подписку за 299 руб/мес чтобы продолжить — /subscribe",
            reply_markup=main_keyboard()
        )
        return

    thinking_msg = bot.send_message(
        message.chat.id,
        "🔮 Читаю твой сон...",
    )

    try:
        interpretation = interpret_dream(dream_text)

        if access_type == "free":
            spend_free_use(user_id)
            free_left -= 1
            if free_left > 0:
                footer = f"\n\n— — —\n✨ Бесплатных толкований осталось: {free_left}"
            else:
                footer = (
                    "\n\n— — —\n"
                    "⚠️ Это было последнее бесплатное толкование.\n"
                    "Оформи подписку чтобы продолжить — /subscribe"
                )
        else:
            footer = ""

        bot.delete_message(message.chat.id, thinking_msg.message_id)
        bot.send_message(
            message.chat.id,
            f"🌙 Толкование сна\n\n{interpretation}{footer}",
            reply_markup=main_keyboard()
        )

    except Exception as e:
        bot.delete_message(message.chat.id, thinking_msg.message_id)
        bot.send_message(
            message.chat.id,
            "⚠️ Произошла ошибка. Попробуй ещё раз через минуту.",
            reply_markup=main_keyboard()
        )
        print(f"Ошибка: {e}")

# ──────────────── Запуск ────────────────

if __name__ == "__main__":
    init_db()
    print("🌙 Бот запущен...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
