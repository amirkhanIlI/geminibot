import os
import datetime
import telebot
from google import genai
from google.genai import types

# ── Загрузка ключей ─────────────────────────────────────────────────────────
def load_env(filepath=".env"):
    """Читает .env файл (если он есть локально) и кладёт переменные в os.environ."""
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY     = os.environ.get("GEMINI_KEY")

if not TELEGRAM_TOKEN or not GEMINI_KEY:
    raise ValueError("Не заданы TELEGRAM_TOKEN или GEMINI_KEY! Укажите их в файле .env или в настройках Railway.")

# ── Инициализация ─────────────────────────────────────────────────────────────
bot       = telebot.TeleBot(TELEGRAM_TOKEN)
ai_client = genai.Client(api_key=GEMINI_KEY)

# Конфиг: краткие ответы, без лишних слов
CHAT_CONFIG = types.GenerateContentConfig(
    max_output_tokens=500,
    system_instruction=(
        "Отвечай кратко, прямо, по делу. "
        "Без приветствий, вступлений и лишних слов."
    ),
)

# Хранилище чатов: { chat_id: объект чата Gemini }
user_chats: dict[int, object] = {}


def get_or_create_chat(chat_id: int):
    """Возвращает существующий чат или создаёт новый."""
    if chat_id not in user_chats:
        user_chats[chat_id] = ai_client.chats.create(
            model="gemini-3.5-flash-lite",
            config=CHAT_CONFIG,
        )
    return user_chats[chat_id]


# ── Логирование сообщений ───────────────────────────────────────────────────
def log_event(user, text, answer=""):
    """Печатает сообщение в консоль и сохраняет в messages.txt."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    username = f"@{user.username}" if user.username else "без никнейма"
    user_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Без имени"
    
    log_entry = (
        f"[{now}] Пользователь: {user_name} ({username}, ID: {user.id})\n"
        f"  Текст: {text}\n"
    )
    if answer:
        log_entry += f"  Ответ бота: {answer}\n"
    log_entry += "-" * 55

    # Вывод в cmd
    print(log_entry, flush=True)

    # Запись в файл messages.txt (всегда можно открыть в Блокноте)
    log_path = os.path.join(os.path.dirname(__file__), "messages.txt")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")


# ── Команды ───────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user_chats.pop(message.chat.id, None)   # сброс старого контекста
    get_or_create_chat(message.chat.id)     # создаём свежий чат
    log_event(message.from_user, "/start", "Готов к работе. Пишите!")
    bot.reply_to(message, "Готов к работе. Пишите!")


@bot.message_handler(commands=["reset"])
def cmd_reset(message):
    user_chats.pop(message.chat.id, None)
    get_or_create_chat(message.chat.id)
    log_event(message.from_user, "/reset", "Контекст сброшен.")
    bot.reply_to(message, "Контекст сброшен. Начнём с чистого листа.")


@bot.message_handler(commands=["help"])
def cmd_help(message):
    bot.reply_to(
        message,
        "/start — начать / сбросить контекст\n"
        "/reset — сбросить историю разговора\n"
        "/help  — это сообщение",
    )


# ── Основной обработчик сообщений ─────────────────────────────────────────────

@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    chat_id = message.chat.id

    # Показываем «печатает...» — пользователь сразу видит, что бот работает
    bot.send_chat_action(chat_id, "typing")

    try:
        chat    = get_or_create_chat(chat_id)
        response = chat.send_message(message.text)   # обычный (не стриминговый) запрос
        answer   = response.text.strip()

        if not answer:
            answer = "Не смог сформировать ответ. Попробуйте переформулировать."

    except Exception as e:
        answer = f"Ошибка: {e}"

    # Логируем (в cmd и в файл messages.txt)
    log_event(message.from_user, message.text, answer)

    # Отправляем финальный ответ одним сообщением — с уведомлением и звуком
    bot.reply_to(message, answer)


# ── Запуск ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Бот запущен. Ожидание сообщений...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
