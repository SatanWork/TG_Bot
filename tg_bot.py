import os
import json
import telebot
import gspread
import matplotlib.pyplot as plt
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from io import BytesIO
import re
import time
import traceback  # Для логирования ошибок

USERS_FILE = os.path.join(os.getcwd(), "users.json")

# Функция загрузки пользователей из файла (без перезаписи)
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as file:
                users = json.load(file)
                print(f"🔍 Загруженные пользователи: {users}")  # Для отладки
                return users
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"❌ Ошибка загрузки users.json: {e}")
            return {}
    else:
        print("❌ Файл users.json не найден!")
        return {}

# Загружаем пользователей ОДИН РАЗ при запуске бота
registered_users = load_users()

# Функция проверки регистрации
def is_user_registered(user_id):
    return str(user_id) in registered_users

# 🔑 Подключение к Google Sheets
print("🔄 Подключаемся к Google Sheets...")
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_json = os.getenv("GOOGLE_CREDENTIALS")

if not creds_json:
    raise ValueError("❌ Ошибка: GOOGLE_CREDENTIALS не найдены!")

creds_dict = json.loads(creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

spreadsheet_id = "1DpbYJ5f6zdhIl1zDtn6Z3aCHZRDFTaqhsCrkzNM9Iqo"
log_sheet = client.open_by_key(spreadsheet_id).worksheet("Changes Log")

# 🔵 Настройка бота
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

ADMIN_ID = 929686990  # ID администратора, куда отправлять ошибки

# 📜 Список пользователей
@bot.message_handler(commands=["users"])
def list_users(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав на выполнение этой команды.")
        return

    if not registered_users:
        bot.reply_to(message, "ℹ️ Список пользователей пуст.")
        return

    # Экранируем спецсимволы MarkdownV2
    def escape_markdown(text):
        return re.sub(r"([_*\[\]()~`>#\+\-=|{}.!])", r"\\\1", text)

    user_list = "\n".join([f"🔹 {escape_markdown(username)}" for username in registered_users.values()])
    bot.reply_to(message, f"📜 *Список пользователей:*\n{user_list}", parse_mode="MarkdownV2")

# ✅ Регистрация пользователя
@bot.message_handler(commands=["adduser"])
def add_user(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав на выполнение этой команды.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "⚠️ Использование: /adduser @username", parse_mode="Markdown")
        return

    username = args[1].strip("@")
    user_id = str(message.chat.id)

    registered_users[user_id] = username
    save_users(registered_users)

    bot.reply_to(message, f"✅ Пользователь @{username} добавлен в список.")

# ❌ Удаление пользователя
@bot.message_handler(commands=["removeuser"])
def remove_user(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ У вас нет прав на выполнение этой команды.")
        return

    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "⚠️ Использование: /removeuser @username", parse_mode="Markdown")
        return

    username = args[1].strip("@")
    
    user_id_to_remove = None
    for user_id, stored_username in registered_users.items():
        if stored_username == username:
            user_id_to_remove = user_id
            break

    if user_id_to_remove:
        del registered_users[user_id_to_remove]
        save_users(registered_users)
        bot.reply_to(message, f"🗑️ Пользователь @{username} удалён.")
    else:
        bot.reply_to(message, f"⚠️ Пользователь @{username} не найден.")

# 📅 Функция преобразования даты
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None

# 📊 Функция получения статистики
def get_statistics(start_date, end_date):
    all_logs = log_sheet.get_all_values()[1:]
    stats = {
        "Бан приложения": 0,
        "Приложение появилось в сторе": 0,
        "Загружено новое приложение": 0,
        "Приложение вернулось в стор": 0
    }

    for row in all_logs:
        if len(row) >= 2:
            log_date, log_type = row[0], row[1]
            if start_date <= log_date <= end_date and log_type in stats:
                stats[log_type] += 1

    return stats

# 🎨 Функция построения графика
def generate_pie_chart(stats):
    labels, sizes, colors = [], [], []
    color_map = {
        "Бан приложения": "red",
        "Приложение появилось в сторе": "green",
        "Загружено новое приложение": "blue",
        "Приложение вернулось в стор": "yellow"
    }

    for category, count in stats.items():
        if count > 0:
            labels.append(f"{category} ({count})")
            sizes.append(count)
            colors.append(color_map.get(category, "gray"))

    plt.figure(figsize=(8, 6))
    plt.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%", startangle=140, wedgeprops={'edgecolor': 'white'})
    plt.gca().add_artist(plt.Circle((0, 0), 0.5, color="white"))
    plt.title("Изменения в сторе")

    buf = BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return buf

# 🤖 Команда /stats
@bot.message_handler(commands=["stats"])
def send_stats(message):
    user_id = str(message.from_user.id)

    if not is_user_registered(user_id):
        bot.reply_to(message, "❌ У вас нет доступа к боту. Обратитесь к администратору!")
        return

    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "⚠️ Использование: /stats DD-MM-YYYY DD-MM-YYYY\n📌 Пример: /stats 01-03-2024 07-03-2024", parse_mode="Markdown")
            return

        start_date = parse_date(args[1])
        end_date = parse_date(args[2])

        if not start_date or not end_date:
            bot.reply_to(message, "❌ Ошибка: Некорректный формат даты. Используйте DD-MM-YYYY.", parse_mode="Markdown")
            return

        stats = get_statistics(start_date, end_date)  # 💡 Получаем статистику из Google Sheets

        if sum(stats.values()) == 0:
            bot.reply_to(message, f"ℹ️ За период {args[1]} - {args[2]} изменений не найдено.", parse_mode="Markdown")
            return

        bot.reply_to(message, f"✅ Запрашиваю статистику за период {start_date} - {end_date}...")

        # 📊 Генерируем и отправляем график
        chart = generate_pie_chart(stats)
        bot.send_photo(message.chat.id, chart, caption=f"📊 Изменения за {args[1]} - {args[2]}")

        # 📄 Отправляем текстовую статистику
        stats_text = "\n".join([f"🔹 *{key}*: {value}" for key, value in stats.items()])
        bot.send_message(message.chat.id, f"📊 *Статистика изменений:*\n{stats_text}", parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        


# 🚀 **Функция запуска бота**
def start_bot():
    try:
        print("✅ Бот запущен. Ожидание сообщений...")
        bot.polling(none_stop=True, timeout=120, long_polling_timeout=100)
    except Exception as e:
        error_message = f"⚠️ Бот упал с ошибкой:\n```{traceback.format_exc()}```"
        print(error_message)

        # 🔔 Отправка сообщения админу о падении бота
        try:
            bot.send_message(ADMIN_ID, error_message, parse_mode="Markdown")
        except:
            print("❌ Ошибка при отправке сообщения админу.")

        exit(1)  # ❌ Выход из программы, чтобы Render не перезапускал автоматически

# 🚀 **Запуск бота**
start_bot()
