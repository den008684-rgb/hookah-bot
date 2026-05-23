#!/usr/bin/env python3
"""
🍃 Hookah Bar Bot — бронирование столиков, выбор кальяна, акции
Требует: pip install python-telegram-bot==20.7
"""

import logging
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from functools import lru_cache
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ─── Логирование ───────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Состояния диалога ─────────────────────────────────────────────────────────
(
    MAIN_MENU,
    BOOKING_DATE, BOOKING_TIME, BOOKING_GUESTS, BOOKING_NAME, BOOKING_PHONE, BOOKING_PROMO, BOOKING_CONFIRM,
    HOOKAH_CATEGORY, HOOKAH_ITEM,
    PROMO_VIEW,
    MY_BOOKINGS,
    LOYALTY_MENU,
) = range(13)

# ─── Данные заведения ──────────────────────────────────────────────────────────
HOOKAHS = {
    "🍓 Фруктовые": [
        {"name": "Клубника & Мята", "price": 1200, "desc": "Свежая клубника с холодной мятой"},
        {"name": "Манго & Маракуйя", "price": 1300, "desc": "Тропический микс с кислинкой"},
        {"name": "Арбуз & Лёд", "price": 1100, "desc": "Летний освежающий вкус"},
        {"name": "Виноград & Фейхоа & Мята", "price": 1200, "desc": "Нежный фруктовый дуэт"},
    ],
    "🌿 Классические": [
        {"name": "Двойное яблоко", "price": 900, "desc": "Классика всех времён"},
        {"name": "Виноград & Мята", "price": 1000, "desc": "Сочный виноград с холодком"},
        {"name": "Мята", "price": 850, "desc": "Чистая прохладная мята"},
    ],
    "🔥 Крепкие": [
        {"name": "Табак Bonche", "price": 1100, "desc": "Насыщенный карибский табак"},
        {"name": "Tangiers", "price": 1200, "desc": "Дымный ягодный табак"},
        {"name": "WTO", "price": 1050, "desc": "Десертный день"},
    ],
    "✨ Авторские": [
        {"name": "Космос", "price": 1500, "desc": "Голубика, лёд, мята — улетишь"},
        {"name": "Нуар", "price": 1600, "desc": "Вишня, шоколад"},
        {"name": "Закат в Дубае", "price": 1700, "desc": "Роза, игристое, яблоко, ананас"},
        {"name": "Зелёный дракон", "price": 1550, "desc": "Зелёное яблоко, базилик, ананас, виноградный чупо-чупс"},
    ],
}

PROMOS = [
    {
        "emoji": "☀️",
        "title": "Дневной Happy DAY",
        "desc": "С 14:00 до 18:00 — кальян+чай=1800",
        "valid": "Каждый день",
        "code": "DAY50",
        "discount": 0,
    },
    {
        "emoji": "👥",
        "title": "Компания 4+",
        "desc": "При заказе от 4 кальянов — бесплатные закуски",
        "valid": "Пятница–Воскресенье",
        "code": "GANG4",
        "discount": 0,
    },
    {
        "emoji": "🎂",
        "title": "День рождения",
        "desc": "Именинник получает скидку 20%",
        "valid": "В день рождения ±3 дня",
        "code": "BDAY",
        "discount": 20,
    },
    {
        "emoji": "📱",
        "title": "Бронь через бот",
        "desc": "Скидка 10% на первое посещение",
        "valid": "Всегда",
        "code": "BOT10",
        "discount": 10,
    },
]

AVAILABLE_TIMES = ["14:00", "15:00", "16:00", "17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00"]

# ─── Хранилище броней и лояльности ─────────────────────────────────────────────
BOOKED_SLOTS = {}  # {"2024-01-20_19:00": [{"phone": "+79991234567", "name": "..."}]}
LOYALTY_DATA = {}  # {"+79991234567": {"visits": 5, "last_visit": "2024-01-20", "free_hookah_available": False}}
BOOKINGS_FILE = Path("bookings.json")
LOYALTY_FILE = Path("loyalty.json")

def load_bookings():
    """Загружает брони из файла"""
    global BOOKED_SLOTS
    if BOOKINGS_FILE.exists():
        try:
            data = json.loads(BOOKINGS_FILE.read_text(encoding='utf-8'))
            BOOKED_SLOTS = data
            logger.info(f"Загружено {sum(len(v) for v in BOOKED_SLOTS.values())} броней")
        except Exception as e:
            logger.error(f"Ошибка загрузки броней: {e}")
            BOOKED_SLOTS = {}

def load_loyalty():
    """Загружает данные о лояльности из файла"""
    global LOYALTY_DATA
    if LOYALTY_FILE.exists():
        try:
            data = json.loads(LOYALTY_FILE.read_text(encoding='utf-8'))
            LOYALTY_DATA = data
            logger.info(f"Загружены данные лояльности для {len(LOYALTY_DATA)} пользователей")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных лояльности: {e}")
            LOYALTY_DATA = {}

def save_loyalty():
    """Сохраняет данные о лояльности в файл"""
    try:
        LOYALTY_FILE.write_text(
            json.dumps(LOYALTY_DATA, indent=2, ensure_ascii=False, default=str),
            encoding='utf-8'
        )
        logger.info("Данные лояльности сохранены")
    except Exception as e:
        logger.error(f"Ошибка сохранения данных лояльности: {e}")

def save_booking_to_file(slot_key: str, booking: dict):
    """Сохраняет бронь в файл"""
    try:
        if slot_key not in BOOKED_SLOTS:
            BOOKED_SLOTS[slot_key] = []
        
        BOOKED_SLOTS[slot_key].append(booking)
        
        # Сохраняем в файл
        BOOKINGS_FILE.write_text(
            json.dumps(BOOKED_SLOTS, indent=2, ensure_ascii=False, default=str),
            encoding='utf-8'
        )
        logger.info(f"Бронь сохранена: {slot_key}")
    except Exception as e:
        logger.error(f"Ошибка сохранения брони: {e}")

def update_loyalty(phone: str, visit_date: str):
    """Обновляет данные лояльности пользователя"""
    if phone not in LOYALTY_DATA:
        LOYALTY_DATA[phone] = {
            "visits": 0,
            "last_visit": None,
            "free_hookah_available": False,
            "visit_history": []
        }
    
    user_loyalty = LOYALTY_DATA[phone]
    user_loyalty["visits"] += 1
    user_loyalty["last_visit"] = visit_date
    user_loyalty["visit_history"].append(visit_date)
    
    # Проверяем, не настало ли 7-е посещение
    if user_loyalty["visits"] % 7 == 0:
        user_loyalty["free_hookah_available"] = True
        logger.info(f"Пользователь {phone} получил право на бесплатный кальян (посещение #{user_loyalty['visits']})")
    
    save_loyalty()
    return user_loyalty["visits"] % 7 == 0  # Возвращает True, если юбилейное посещение

def get_loyalty_info(phone: str) -> dict:
    """Возвращает информацию о лояльности пользователя"""
    if phone not in LOYALTY_DATA:
        return {
            "visits": 0,
            "next_free": 7,
            "free_available": False,
            "last_visit": None
        }
    
    user_data = LOYALTY_DATA[phone]
    visits_until_free = 7 - (user_data["visits"] % 7)
    if visits_until_free == 7:
        visits_until_free = 0
    
    return {
        "visits": user_data["visits"],
        "next_free": visits_until_free,
        "free_available": user_data.get("free_hookah_available", False),
        "last_visit": user_data.get("last_visit")
    }

def use_free_hookah(phone: str) -> bool:
    """Использовать бесплатный кальян"""
    if phone in LOYALTY_DATA and LOYALTY_DATA[phone].get("free_hookah_available", False):
        LOYALTY_DATA[phone]["free_hookah_available"] = False
        save_loyalty()
        return True
    return False

def get_admin_chat_id():
    """Возвращает ID чата администратора"""
    return 6704733768  # Ваш ID

# ─── Валидация ────────────────────────────────────────────────────────────────
def validate_name(name: str) -> bool:
    """Проверяет корректность имени"""
    return len(name.strip()) >= 2 and not name.isdigit() and name.strip().replace(" ", "").replace("-", "").isalpha()

def validate_phone(phone: str) -> bool:
    """Проверяет корректность номера телефона"""
    # Удаляем пробелы, скобки, дефисы
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
    # Проверяем: +7, 8 или 9 и затем 10 цифр
    pattern = r'^(\+7|8|9)\d{9,10}$'
    return bool(re.match(pattern, clean_phone))

def is_slot_available(date: str, time: str, guests: str) -> tuple:
    """Проверяет доступность слота. Возвращает (доступно, причина)"""
    slot_key = f"{date}_{time}"
    
    if slot_key not in BOOKED_SLOTS:
        return True, "Свободно"
    
    # Максимум 4 брони на одно время
    if len(BOOKED_SLOTS[slot_key]) >= 4:
        return False, "Это время уже полностью занято"
    
    # Проверяем количество гостей (максимум 20 человек на слот)
    total_guests = sum(b.get('guests', 0) for b in BOOKED_SLOTS[slot_key])
    guests_num = int(guests) if guests != "6+" else 6
    
    if total_guests + guests_num > 20:
        return False, f"Уже занято на {total_guests} гостей, свободно мест: {20 - total_guests}"
    
    return True, "Доступно"

def is_user_already_booked(phone: str, date: str, time: str) -> bool:
    """Проверяет, не забронировал ли пользователь уже этот слот"""
    slot_key = f"{date}_{time}"
    if slot_key in BOOKED_SLOTS:
        for booking in BOOKED_SLOTS[slot_key]:
            if booking.get('phone') == phone:
                return True
    return False

@lru_cache(maxsize=100)
def get_available_dates(days: int = 7):
    """Генерирует доступные даты (с кэшированием)"""
    today = datetime.now()
    dates = []
    for i in range(days):
        d = today + timedelta(days=i)
        dates.append(d)
    return dates

# ─── Вспомогательные функции ───────────────────────────────────────────────────
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🪑 Забронировать столик", callback_data="book")],
        [InlineKeyboardButton("🌿 Меню кальянов", callback_data="hookah")],
        [InlineKeyboardButton("🎁 Акции", callback_data="promos")],
        [InlineKeyboardButton("⭐ Моя лояльность", callback_data="loyalty")],
        [InlineKeyboardButton("📋 Мои брони", callback_data="my_bookings")],
        [InlineKeyboardButton("📍 Контакты", callback_data="contacts")],
    ])

def back_keyboard(target="main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=f"back_{target}")]])

async def notify_admin(application: Application, booking: dict, is_free_hookah: bool = False):
    """Отправляет уведомление администратору о новой брони"""
    admin_id = get_admin_chat_id()
    
    text = (
        f"🔔 *НОВОЕ БРОНИРОВАНИЕ!*\n\n"
        f"📅 Дата: *{booking['date']}*\n"
        f"🕐 Время: *{booking['time']}*\n"
        f"👥 Гостей: *{booking['guests']}*\n"
        f"👤 Имя: *{booking['name']}*\n"
        f"📞 Телефон: *{booking['phone']}*\n"
    )
    
    if is_free_hookah:
        text += "🎁 *БЕСПЛАТНЫЙ КАЛЬЯН ПО ПРОГРАММЕ ЛОЯЛЬНОСТИ!*\n"
    
    if booking.get('promo'):
        text += f"🎫 Промокод: *{booking['promo']}*\n"
        if booking.get('discount'):
            text += f"💰 Скидка: *{booking['discount']}%*\n"
    
    text += f"\n🕐 Забронировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    try:
        await application.bot.send_message(
            chat_id=admin_id,
            text=text,
            parse_mode="Markdown"
        )
        logger.info(f"Уведомление отправлено администратору {admin_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления администратору: {e}")

# ─── Обработчик ошибок ─────────────────────────────────────────────────────────
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=True)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ *Произошла техническая ошибка.*\n\n"
                "Пожалуйста, попробуйте позже или свяжитесь с администратором.\n"
                "Мы уже работаем над исправлением! 🛠️",
                parse_mode="Markdown"
            )
        except:
            pass

async def disabled_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на недоступное время"""
    q = update.callback_query
    await q.answer("❌ Это время недоступно для бронирования!", show_alert=True)

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отменяет текущую операцию"""
    ctx.user_data.clear()
    await update.message.reply_text(
        "❌ Операция отменена.\n\nВозвращаюсь в главное меню.",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# ─── Обработчики ───────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    user = update.effective_user
    text = (
        f"Привет, *{user.first_name}*! 👋\n\n"
        "Добро пожаловать в *ДымДомДам Lounge* 🍃\n\n"
        "━━━━━━━━━━━━━━━\n"
        "🕐 Работаем: 14:00 – 02:00\n"
        "📍 Аминьевское шоссе, 4д к2\n"
        "━━━━━━━━━━━━━━━\n\n"
        "⭐ *Программа лояльности:*\n"
        "Каждое 7-е посещение — кальян в подарок!\n\n"
        "Чем могу помочь?"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    else:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    return MAIN_MENU

# ── Лояльность ──────────────────────────────────────────────────────────────────
async def loyalty_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о лояльности пользователя"""
    q = update.callback_query
    await q.answer()
    
    # Запрашиваем номер телефона
    ctx.user_data["loyalty_search"] = True
    
    await q.edit_message_text(
        "⭐ *Программа лояльности*\n\n"
        "🎁 *Условия:*\n"
        "• Каждое 7-е посещение — кальян в подарок!\n"
        "• Бесплатный кальян можно использовать в любое время\n"
        "• Подарок не суммируется с другими акциями\n\n"
        "📱 *Для проверки вашего статуса*\n"
        "Введите номер телефона, который вы указываете при бронировании:\n"
        "Например: +7 999 123 45 67",
        parse_mode="Markdown",
        reply_markup=back_keyboard("main")
    )
    return LOYALTY_MENU

async def show_loyalty_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показывает информацию о лояльности по номеру телефона"""
    phone = update.message.text.strip()
    
    if not validate_phone(phone):
        await update.message.reply_text(
            "❌ *Неверный номер телефона*\n\n"
            "Пожалуйста, введите корректный номер: +7 999 123 45 67",
            parse_mode="Markdown"
        )
        return LOYALTY_MENU
    
    # Получаем информацию о лояльности
    loyalty_info = get_loyalty_info(phone)
    
    # Создаем прогресс-бар
    visits = loyalty_info['visits']
    progress = visits % 7
    if progress == 0 and visits > 0:
        progress = 7
    
    progress_bar = "🟢" * progress + "⚪" * (7 - progress) if progress < 7 else "🟢" * 7
    
    text = (
        f"⭐ *Ваш статус лояльности*\n\n"
        f"📞 Номер: `{phone}`\n\n"
        f"📊 *Статистика посещений:*\n"
        f"• Всего посещений: *{visits}*\n"
        f"• До бесплатного кальяна: *{loyalty_info['next_free']}*\n\n"
        f"{progress_bar}\n\n"
    )
    
    if loyalty_info['free_available']:
        text += (
            "🎉 *У вас есть бесплатный кальян!*\n"
            "При следующем бронировании вы можете его активировать.\n\n"
            "💡 *Как активировать:*\n"
            "При бронировании столика выберите опцию «Использовать бесплатный кальян»."
        )
    else:
        if visits > 0:
            text += f"Осталось *{loyalty_info['next_free']}* посещений до бесплатного кальяна!\n\n"
            text += "🎁 Приходите к нам ещё, чтобы получать подарки!"
        else:
            text += "🎁 *Сделайте первое бронирование*, чтобы начать копить посещения!\n\n"
            text += "Каждое 7-е посещение — кальян в подарок!"
    
    if loyalty_info['last_visit']:
        text += f"\n\n📅 Последнее посещение: {loyalty_info['last_visit']}"
    
    buttons = [
        [InlineKeyboardButton("🪑 Забронировать столик", callback_data="book")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")],
    ]
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return MAIN_MENU

# ── Мои брони ──────────────────────────────────────────────────────────────────
async def my_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показывает брони пользователя"""
    q = update.callback_query
    await q.answer()
    
    await q.edit_message_text(
        "📋 *Поиск ваших броней*\n\n"
        "Введите номер телефона, который указывали при бронировании:\n"
        "Например: +7 999 123 45 67",
        parse_mode="Markdown",
        reply_markup=back_keyboard("main")
    )
    return MY_BOOKINGS

async def search_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ищет брони по номеру телефона"""
    phone = update.message.text.strip()
    
    # Находим все брони с этим номером
    user_bookings = []
    for slot_key, bookings in BOOKED_SLOTS.items():
        for booking in bookings:
            if booking.get('phone') == phone:
                date, time = slot_key.split('_')
                user_bookings.append({
                    'date': date,
                    'time': time,
                    'guests': booking.get('guests'),
                    'name': booking.get('name'),
                    'created_at': booking.get('created_at')
                })
    
    if not user_bookings:
        await update.message.reply_text(
            "❌ *Брони не найдены*\n\n"
            "Возможно, вы ввели другой номер телефона или у вас пока нет броней.\n\n"
            "Хотите забронировать столик?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🪑 Забронировать", callback_data="book")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")]
            ])
        )
        return MAIN_MENU
    
    # Формируем ответ
    text = f"📋 *Ваши брони* (найдено {len(user_bookings)})\n\n"
    for i, booking in enumerate(user_bookings, 1):
        text += (
            f"{i}. 📅 {booking['date']} в {booking['time']}\n"
            f"   👥 {booking['guests']} чел.\n"
            f"   🕐 Забронировано: {booking['created_at'][:16] if booking['created_at'] else '—'}\n\n"
        )
    
    text += "Вы можете отменить бронь, позвонив нам по телефону +7 (929) 650-44-88"
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🪑 Новая бронь", callback_data="book")],
            [InlineKeyboardButton("⭐ Проверить лояльность", callback_data="loyalty")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")]
        ])
    )
    return MAIN_MENU

# ── Бронирование ────────────────────────────────────────────────────────────────
async def book_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["booking"] = {}
    ctx.user_data["use_free_hookah"] = False
    
    # Генерируем даты на 7 дней вперёд
    dates = get_available_dates(7)
    buttons = []
    for i, d in enumerate(dates):
        label = d.strftime("%d %b") + (" (сегодня)" if i == 0 else " (завтра)" if i == 1 else "")
        buttons.append([InlineKeyboardButton(label, callback_data=f"date_{d.strftime('%Y-%m-%d')}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    
    await q.edit_message_text(
        "🗓 *Выберите дату бронирования:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return BOOKING_DATE

async def booking_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    date_str = q.data.replace("date_", "")
    ctx.user_data["booking"]["date"] = date_str
    
    buttons = []
    for t in AVAILABLE_TIMES:
        available, reason = is_slot_available(date_str, t, "1")
        if available:
            buttons.append([InlineKeyboardButton(f"✅ {t}", callback_data=f"time_{t}")])
        else:
            buttons.append([InlineKeyboardButton(f"❌ {t}", callback_data="disabled")])
    
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="book")])
    
    await q.edit_message_text(
        f"🕐 *Выберите время:*\nДата: {date_str}\n\n✅ — свободно, ❌ — занято",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return BOOKING_TIME

async def booking_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    if q.data == "disabled":
        await q.answer("❌ Это время недоступно!", show_alert=True)
        return BOOKING_TIME
    
    time_str = q.data.replace("time_", "")
    ctx.user_data["booking"]["time"] = time_str
    
    buttons = [
        [InlineKeyboardButton("1", callback_data="guests_1"), InlineKeyboardButton("2", callback_data="guests_2")],
        [InlineKeyboardButton("3", callback_data="guests_3"), InlineKeyboardButton("4", callback_data="guests_4")],
        [InlineKeyboardButton("5", callback_data="guests_5"), InlineKeyboardButton("6+", callback_data="guests_6")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"date_{ctx.user_data['booking']['date']}")],
    ]
    await q.edit_message_text(
        f"👥 *Сколько гостей?*\nДата: {ctx.user_data['booking']['date']} в {time_str}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return BOOKING_GUESTS

async def booking_guests(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    guests = q.data.replace("guests_", "")
    ctx.user_data["booking"]["guests"] = guests
    
    # Проверяем доступность с учётом количества гостей
    b = ctx.user_data["booking"]
    available, reason = is_slot_available(b['date'], b['time'], guests)
    
    if not available:
        await q.edit_message_text(
            f"❌ *Извините, это время недоступно!*\n\n"
            f"Причина: {reason}\n\n"
            f"Пожалуйста, выберите другое время или дату.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🕐 Выбрать другое время", callback_data=f"date_{b['date']}")],
                [InlineKeyboardButton("📅 Другая дата", callback_data="book")],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_main")]
            ])
        )
        return BOOKING_DATE
    
    await q.edit_message_text(
        "✍️ *Введите ваше имя:*\n\n"
        "❗ Имя должно содержать хотя бы 2 буквы",
        parse_mode="Markdown",
        reply_markup=back_keyboard("book")
    )
    return BOOKING_NAME

async def booking_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    
    if not validate_name(name):
        await update.message.reply_text(
            "❌ *Неверное имя*\n\n"
            "Имя должно содержать хотя бы 2 буквы и не может состоять только из цифр.\n"
            "Пожалуйста, введите корректное имя:",
            parse_mode="Markdown"
        )
        return BOOKING_NAME
    
    ctx.user_data["booking"]["name"] = name
    
    await update.message.reply_text(
        "📞 *Введите номер телефона:*\n"
        "Например: +7 999 123 45 67 или 89123456789\n\n"
        "❗ Номер должен быть российским (начинаться на +7, 8 или 9)",
        parse_mode="Markdown"
    )
    return BOOKING_PHONE

async def booking_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    
    if not validate_phone(phone):
        await update.message.reply_text(
            "❌ *Неверный номер телефона*\n\n"
            "Пожалуйста, введите корректный российский номер:\n"
            "• +7 999 123 45 67\n"
            "• 89123456789\n"
            "• 9123456789",
            parse_mode="Markdown"
        )
        return BOOKING_PHONE
    
    ctx.user_data["booking"]["phone"] = phone
    
    # Проверяем, есть ли у пользователя бесплатный кальян
    loyalty_info = get_loyalty_info(phone)
    if loyalty_info['free_available']:
        buttons = ReplyKeyboardMarkup(
            [["✅ Да, использовать", "❌ Нет, спасибо"]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text(
            "🎁 *У вас есть бесплатный кальян!*\n\n"
            "Хотите использовать его при этом посещении?\n\n"
            "Бесплатный кальян можно получить вместо обычного.",
            parse_mode="Markdown",
            reply_markup=buttons
        )
        return BOOKING_PROMO  # Переходим к выбору бесплатного кальяна
    
    # Если нет бесплатного кальяна, спрашиваем промокод
    await update.message.reply_text(
        "🎫 *Есть промокод?*\n\n"
        "Введите промокод или нажмите кнопку «Пропустить»:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["Пропустить"]], 
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return BOOKING_PROMO

async def booking_promo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    promo_input = update.message.text.strip()
    
    # Проверяем, хочет ли пользователь использовать бесплатный кальян
    if promo_input == "✅ Да, использовать":
        ctx.user_data["use_free_hookah"] = True
        ctx.user_data["booking"]["promo"] = "FREE_HOOKAH_LOYALTY"
        ctx.user_data["booking"]["discount"] = 100  # 100% скидка
        
        await update.message.reply_text(
            "🎉 *Отлично! Бесплатный кальян активирован!*\n\n"
            "Вы получите один кальян в подарок при посещении.\n\n"
            "Продолжим бронирование...",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Переходим к подтверждению
        b = ctx.user_data["booking"]
        summary = (
            "📋 *Подтверждение бронирования*\n\n"
            f"📅 Дата: *{b['date']}*\n"
            f"🕐 Время: *{b['time']}*\n"
            f"👥 Гостей: *{b['guests']}*\n"
            f"👤 Имя: *{b['name']}*\n"
            f"📞 Телефон: *{b['phone']}*\n"
            f"🎁 *Бесплатный кальян по программе лояльности!*\n\n"
            "Всё верно?"
        )
        buttons = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes")],
            [InlineKeyboardButton("✏️ Изменить", callback_data="book")],
            [InlineKeyboardButton("❌ Отмена", callback_data="back_main")],
        ]
        await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return BOOKING_CONFIRM
    
    elif promo_input == "❌ Нет, спасибо":
        ctx.user_data["use_free_hookah"] = False
        
        await update.message.reply_text(
            "Хорошо! В следующий раз обязательно воспользуйтесь подарком.\n\n"
            "Теперь введите промокод, если он у вас есть, или нажмите «Пропустить»:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["Пропустить"]], 
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return BOOKING_PROMO
    
    elif promo_input == "Пропустить":
        ctx.user_data["booking"]["promo"] = None
        ctx.user_data["booking"]["discount"] = 0
    else:
        # Проверяем промокод
        found_promo = None
        for promo in PROMOS:
            if promo['code'].upper() == promo_input.upper():
                found_promo = promo
                break
        
        if found_promo:
            ctx.user_data["booking"]["promo"] = found_promo['code']
            ctx.user_data["booking"]["discount"] = found_promo.get('discount', 0)
            
            discount_msg = f"Скидка: {found_promo.get('discount', 0)}%" if found_promo.get('discount', 0) > 0 else "Акция активирована"
            
            await update.message.reply_text(
                f"✅ *Промокод активирован!*\n\n"
                f"{discount_msg}\n"
                f"Акция: {found_promo['title']}\n\n"
                f"Скидка будет применена при посещении.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                "❌ *Неверный промокод*\n\n"
                "Вы можете продолжить без промокода или попробовать снова.\n"
                "Актуальные акции можно посмотреть в разделе «Акции».",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(
                    [["Пропустить", "Ввести снова"]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
            return BOOKING_PROMO
    
    b = ctx.user_data["booking"]
    discount_text = f"\n💰 Скидка: *{b.get('discount', 0)}%*" if b.get('discount', 0) > 0 else ""
    
    summary = (
        "📋 *Подтверждение бронирования*\n\n"
        f"📅 Дата: *{b['date']}*\n"
        f"🕐 Время: *{b['time']}*\n"
        f"👥 Гостей: *{b['guests']}*\n"
        f"👤 Имя: *{b['name']}*\n"
        f"📞 Телефон: *{b['phone']}*{discount_text}\n\n"
        "Всё верно?"
    )
    buttons = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes")],
        [InlineKeyboardButton("✏️ Изменить", callback_data="book")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_main")],
    ]
    await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    return BOOKING_CONFIRM

async def booking_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    b = ctx.user_data["booking"]
    use_free = ctx.user_data.get("use_free_hookah", False)
    
    # Проверка на дублирование брони
    if is_user_already_booked(b['phone'], b['date'], b['time']):
        await q.edit_message_text(
            "❌ *Вы уже забронировали этот слот!*\n\n"
            "Нельзя бронировать несколько столиков на одно время.\n\n"
            "Пожалуйста, выберите другое время.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🪑 Выбрать другое время", callback_data=f"date_{b['date']}")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")]
            ])
        )
        return MAIN_MENU
    
    # Финальная проверка доступности
    slot_key = f"{b['date']}_{b['time']}"
    available, reason = is_slot_available(b['date'], b['time'], b['guests'])
    
    if not available:
        await q.edit_message_text(
            f"❌ *Извините, это время уже занято!*\n\n"
            f"Причина: {reason}\n\n"
            f"Пожалуйста, выберите другое время.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🪑 Попробовать снова", callback_data="book")],
                [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")]
            ])
        )
        return MAIN_MENU
    
    # Если используется бесплатный кальян, списываем его
    if use_free:
        if use_free_hookah(b['phone']):
            logger.info(f"Пользователь {b['phone']} использовал бесплатный кальян")
        else:
            await q.edit_message_text(
                "❌ *Ошибка!*\n\n"
                "Не удалось активировать бесплатный кальян.\n"
                "Возможно, он уже был использован.\n\n"
                "Пожалуйста, продолжите без него.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🪑 Продолжить бронирование", callback_data="book")],
                    [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")]
                ])
            )
            return MAIN_MENU
    
    # Обновляем данные лояльности
    is_milestone = update_loyalty(b['phone'], b['date'])
    
    # Сохраняем бронь
    booking_data = {
        "name": b['name'],
        "phone": b['phone'],
        "guests": int(b['guests']) if b['guests'] != "6+" else 6,
        "date": b['date'],
        "time": b['time'],
        "created_at": datetime.now().isoformat(),
        "promo": b.get('promo'),
        "discount": b.get('discount', 0),
        "free_hookah_used": use_free
    }
    
    save_booking_to_file(slot_key, booking_data)
    logger.info(f"НОВОЕ БРОНИРОВАНИЕ: {b}")
    
    # Отправляем уведомление администратору
    await notify_admin(ctx.application, booking_data, use_free)
    
    # Формируем сообщение для пользователя
    discount_message = ""
    loyalty_message = ""
    
    if b.get('discount', 0) > 0:
        discount_message = f"\n🎉 *Ваша скидка {b['discount']}% уже активирована!*"
    
    if use_free:
        discount_message = "\n🎁 *Вы получите один кальян в подарок!*"
    
    if is_milestone:
        loyalty_message = "\n\n🏆 *ПОЗДРАВЛЯЕМ!*\nЭто ваше 7-е посещение!\nСледующий бесплатный кальян через 7 посещений."
    
    await q.edit_message_text(
        "🎉 *Бронирование подтверждено!*\n\n"
        f"Ждём вас *{b['date']}* в *{b['time']}*\n"
        f"Столик на *{b['guests']}* чел. забронирован на имя *{b['name']}*\n"
        f"Наш менеджер позвонит за 30 минут для подтверждения.{discount_message}{loyalty_message}\n\n"
        "💡 *Совет:* Сохраните это сообщение как подтверждение брони.\n"
        "⭐ *Напоминание:* Каждое 7-е посещение — кальян в подарок!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ Проверить статус лояльности", callback_data="loyalty")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="back_main")]
        ])
    )
    return MAIN_MENU

# ── Меню кальянов ───────────────────────────────────────────────────────────────
async def hookah_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    buttons = [[InlineKeyboardButton(cat, callback_data=f"cat_{i}")] for i, cat in enumerate(HOOKAHS.keys())]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    
    await q.edit_message_text(
        "🌿 *Меню кальянов*\n\nВыберите категорию:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return HOOKAH_CATEGORY

async def hookah_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat_idx = int(q.data.replace("cat_", ""))
    categories = list(HOOKAHS.keys())
    cat_name = categories[cat_idx]
    ctx.user_data["hookah_cat"] = cat_name
    
    items = HOOKAHS[cat_name]
    buttons = [
        [InlineKeyboardButton(f"{item['name']} — {item['price']}₽", callback_data=f"item_{j}")]
        for j, item in enumerate(items)
    ]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="hookah")])
    
    await q.edit_message_text(
        f"*{cat_name}*\n\nВыберите кальян:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return HOOKAH_ITEM

async def hookah_item(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    item_idx = int(q.data.replace("item_", ""))
    cat_name = ctx.user_data["hookah_cat"]
    item = HOOKAHS[cat_name][item_idx]
    
    text = (
        f"🌿 *{item['name']}*\n\n"
        f"_{item['desc']}_\n\n"
        f"💰 Цена: *{item['price']}₽*\n\n"
        "Хотите забронировать столик и заказать этот кальян?"
    )
    buttons = [
        [InlineKeyboardButton("🪑 Забронировать столик", callback_data="book")],
        [InlineKeyboardButton("◀️ Ко всем кальянам", callback_data="hookah")],
        [InlineKeyboardButton("◀️ Назад к категории", callback_data=f"cat_{list(HOOKAHS.keys()).index(cat_name)}")],
    ]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    return HOOKAH_ITEM

# ── Акции ────────────────────────────────────────────────────────────────────────
async def promos_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    text = "🎁 *Акции и спецпредложения*\n\n"
    for p in PROMOS:
        text += (
            f"{p['emoji']} *{p['title']}*\n"
            f"  {p['desc']}\n"
            f"  📅 {p['valid']}\n"
            f"  🏷 Промокод: `{p['code']}`\n\n"
        )
    text += "⭐ *Программа лояльности:* Каждое 7-е посещение — кальян в подарок!\n\n"
    text += "Покажите промокод при посещении или введите при бронировании."
    
    await q.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🪑 Забронировать со скидкой", callback_data="book")],
            [InlineKeyboardButton("⭐ Моя лояльность", callback_data="loyalty")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
        ])
    )
    return PROMO_VIEW

# ── Контакты ────────────────────────────────────────────────────────────────────
async def contacts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    text = (
        "📍 *ДымДомДам Lounge*\n\n"
        "🏠 Адрес: Аминьевское шоссе, 4д к2\n"
        "📞 Телефон: +7 (929) 650-44-88\n"
        "🕐 *Режим работы:*\n"
        "Ежедневно: 14:00 – 02:00\n\n"
        "⭐ *Программа лояльности:*\n"
        "Каждое 7-е посещение — кальян в подарок!\n\n"
        "📍 [Открыть на карте](https://yandex.ru/maps/org/dymdomdam_laundzh/160715128197/?indoorLevel=1&ll=37.468038%2C55.700106&z=17)"
    )
    await q.edit_message_text(
        text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=back_keyboard("main")
    )

# ── Навигация «Назад» ───────────────────────────────────────────────────────────
async def back_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    target = q.data.replace("back_", "")
    
    if target == "main":
        return await start(update, ctx)
    elif target == "book":
        return await book_start(update, ctx)
    elif target == "hookah":
        return await hookah_menu(update, ctx)

# ─── Запуск бота ───────────────────────────────────────────────────────────────
def main():
    # Загружаем сохранённые брони и данные лояльности
    load_bookings()
    load_loyalty()
    
    # Ваш токен
    TOKEN = "8807731170:AAEkH1zRMBwV5a74MmPANFIK-sw-qrrXEKY"
    
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем глобальный обработчик ошибок
    app.add_error_handler(error_handler)
    
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(book_start, pattern="^book$"),
                CallbackQueryHandler(hookah_menu, pattern="^hookah$"),
                CallbackQueryHandler(promos_menu, pattern="^promos$"),
                CallbackQueryHandler(loyalty_menu, pattern="^loyalty$"),
                CallbackQueryHandler(my_bookings, pattern="^my_bookings$"),
                CallbackQueryHandler(contacts, pattern="^contacts$"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
                CallbackQueryHandler(disabled_callback, pattern="^disabled$"),
            ],
            BOOKING_DATE: [
                CallbackQueryHandler(booking_date, pattern="^date_"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            BOOKING_TIME: [
                CallbackQueryHandler(booking_time, pattern="^time_"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
                CallbackQueryHandler(book_start, pattern="^book$"),
                CallbackQueryHandler(disabled_callback, pattern="^disabled$"),
            ],
            BOOKING_GUESTS: [
                CallbackQueryHandler(booking_guests, pattern="^guests_"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            BOOKING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_name),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            BOOKING_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_phone),
            ],
            BOOKING_PROMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, booking_promo),
            ],
            BOOKING_CONFIRM: [
                CallbackQueryHandler(booking_confirm, pattern="^confirm_yes$"),
                CallbackQueryHandler(book_start, pattern="^book$"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            HOOKAH_CATEGORY: [
                CallbackQueryHandler(hookah_category, pattern="^cat_"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            HOOKAH_ITEM: [
                CallbackQueryHandler(hookah_item, pattern="^item_"),
                CallbackQueryHandler(hookah_category, pattern="^cat_"),
                CallbackQueryHandler(book_start, pattern="^book$"),
                CallbackQueryHandler(hookah_menu, pattern="^hookah$"),
            ],
            PROMO_VIEW: [
                CallbackQueryHandler(book_start, pattern="^book$"),
                CallbackQueryHandler(loyalty_menu, pattern="^loyalty$"),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            MY_BOOKINGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, search_bookings),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
            LOYALTY_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, show_loyalty_info),
                CallbackQueryHandler(back_handler, pattern="^back_"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )
    
    app.add_handler(conv)
    
    print("🚀 Бот запущен. Нажмите Ctrl+C для остановки.")
    print("📁 Брони будут сохраняться в файл bookings.json")
    print("⭐ Данные лояльности будут сохраняться в файл loyalty.json")
    print("📍 Заведение: ДымДомДам Lounge")
    print("🕐 Режим работы: 14:00 – 02:00")
    print("🎁 Программа лояльности: Каждое 7-е посещение - кальян в подарок!")
    print("👤 Уведомления администратору будут отправляться в ID: 6704733768")
    app.run_webhook(drop_pending_updates=True)

if __name__ == "__main__":
    main()