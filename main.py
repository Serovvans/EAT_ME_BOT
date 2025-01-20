import csv
import pandas as pd
import os
import json
import pytz
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from utils.config import bot_token, PROFILE_DIR, STORAGE_DIR
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from utils.ai_tools import create_meal_and_coocking_plan

logging.basicConfig(level=logging.INFO)

bot = Bot(token=bot_token)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
scheduler = AsyncIOScheduler()

if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)
    os.makedirs(os.path.join(STORAGE_DIR, "feedback"))
CSV_FILE = os.path.join(STORAGE_DIR, 'user_data.csv')
if not os.path.exists(CSV_FILE):
    columns = ["user_id", "meal_plan_link", "user_info_file", "cook_file_path"]
    df = pd.DataFrame(columns=columns)

    df.to_csv(CSV_FILE, index=False)


# Функция для загрузки данных из CSV
def load_registered_users():
    users = set()
    if os.path.exists(CSV_FILE):
        users_info = pd.read_csv(CSV_FILE)
        for _, row in users_info.iterrows():
                users.add(int(row['user_id']))
    return users


# Функция для загрузки профиля пользователя из JSON
def load_user_profile(user_id):
    profile_file_path = os.path.join(PROFILE_DIR, f'user_{user_id}.json')
    if os.path.exists(profile_file_path):
        with open(profile_file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


# Функция для добавления нового пользователя в CSV
def add_user_to_csv(user_id, profile_file_path, meal_plan_link='', shopping_schedule_link=''):
    user_found = False

    users_info = pd.read_csv(CSV_FILE)
    for _, row in users_info.iterrows():
        if int(row['user_id']) == user_id:
            # Обновляем значения в строке
            row['plan_file_path'] = meal_plan_link
            row['cook_file_path'] = shopping_schedule_link
            user_found = True

    # Если пользователь не найден в CSV, добавляем новую строку
    if not user_found:
        new_user = pd.DataFrame({"user_id": [user_id], "meal_plan_link": [meal_plan_link],
                                "user_info_file": [profile_file_path], "cook_file_path": [shopping_schedule_link]})
        users_info = pd.concat([users_info, new_user], ignore_index=True)
        
    users_info.to_csv(CSV_FILE)

    logging.info(f"Данные пользователя (user_id: {user_id}) успешно обновлены в CSV.")


registered_users = load_registered_users()


user_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
user_keyboard.row(
    KeyboardButton("/start 🏠"),
    KeyboardButton("/edit_profile ✏️")
)
user_keyboard.row(
    KeyboardButton("/generate_plan 📝"),
    KeyboardButton("/delete_plan ❌")
)
user_keyboard.row(
    KeyboardButton("/edit_plan 🛠️"),
    KeyboardButton("/view_plan 👀")
)
user_keyboard.row(
    KeyboardButton("/list_reminders ⏰"),
)


class RegistrationForm(StatesGroup):
    about_user = State()  # Пол, возраст, цель плана питания
    forbidden_products = State()  # Аллергии, нелюбимые продукты
    favorite_products = State()  # Любимая еда
    cooking_preferences = State()  # Время на готовку и способы приготовления


class EditProfileForm(StatesGroup):
    choose_field = State()  # Выбор поля для редактирования
    new_value = State()  # Ввод нового значения


class PlanEditForm(StatesGroup):
    new_prompt = State()  # Ввод нового промта для изменения плана
    
    
class FeedbackForm(StatesGroup):
    quality = State()  # Вопрос о качестве
    usability = State()  # Вопрос об удобстве использования
    compliance = State()  # Вопрос о соответствии требованиям


# Middleware для проверки регистрации
class RegistrationMiddleware(BaseMiddleware):
    async def on_pre_process_message(self, message: Message, data: dict):
        user_id = message.from_user.id
        state = dp.current_state(user=user_id)
        current_state = await state.get_state()
        if user_id not in registered_users and not current_state:
            keyboard = InlineKeyboardMarkup()
            register_button = InlineKeyboardButton("Register", callback_data="register")
            keyboard.add(register_button)

            await message.answer("Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь, чтобы продолжить:",
                                 reply_markup=keyboard)

            raise CancelHandler()


dp.middleware.setup(RegistrationMiddleware())


# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id

    await message.answer("👋 Привет! Этот бот поможет тебе составить план питания 🥗")

    if user_id in registered_users:
        profile = load_user_profile(user_id)
        if profile:
            profile_text = (
                f"📋 Вы зарегистрированы в системе.\n\n"
                f"👥 Пол, возраст, цель: {profile.get('about_user', 'не указано')}\n"
                f"☠ Аллергии и нелюбимые продукты: {profile.get('forbidden_products', 'не указано')}\n"
                f"🍲 Любимая еда: {profile.get('favorite_products', 'не указано')}\n"
                f"⏲️ Время на готовку и способы приготовления: {profile.get('cooking_preferences', 'не указано')}"
            )
            await message.answer(profile_text, reply_markup=user_keyboard)
        else:
            keyboard = InlineKeyboardMarkup()
            register_button = InlineKeyboardButton("Register", callback_data="register")
            keyboard.add(register_button)
            await message.answer("Ваш профиль не найден.", reply_markup=keyboard)
    else:
        # Если пользователь не зарегистрирован, предлагаем регистрацию
        keyboard = InlineKeyboardMarkup()
        register_button = InlineKeyboardButton("Register", callback_data="register")
        keyboard.add(register_button)
        await message.answer("Вы не зарегистрированы. Пожалуйста, зарегистрируйтесь, чтобы продолжить:",
                             reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data == 'start')
async def process_start_button(callback_query: types.CallbackQuery):
    await cmd_start(callback_query.message)
    await bot.answer_callback_query(callback_query.id)


# Обработчик нажатия на кнопку "Register"
@dp.callback_query_handler(lambda c: c.data == 'register')
async def process_register(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    if user_id not in registered_users:
        await bot.send_message(user_id,
                               "Давайте начнем регистрацию. Введите ваш пол, возраст и цель плана питания (например: "
                               "Мужчина, 25, Набор массы):")
        await RegistrationForm.about_user.set()  # Переходим к первому состоянию FSM
    else:
        await bot.send_message(user_id, "Вы уже зарегистрированы.")

    await bot.answer_callback_query(callback_query.id)


# Шаги регистрации
@dp.message_handler(state=RegistrationForm.about_user)
async def process_about_user(message: types.Message, state: FSMContext):
    await state.update_data(about_user=message.text)
    await message.answer("Теперь укажите, есть ли у вас аллергии или нелюбимые продукты (через запятую):")
    await RegistrationForm.forbidden_products.set()


@dp.message_handler(state=RegistrationForm.forbidden_products)
async def process_forbidden_products(message: types.Message, state: FSMContext):
    await state.update_data(forbidden_products=message.text)
    await message.answer("Какая у вас любимая еда?")
    await RegistrationForm.favorite_products.set()


@dp.message_handler(state=RegistrationForm.favorite_products)
async def process_favorite_products(message: types.Message, state: FSMContext):
    await state.update_data(favorite_products=message.text)
    await message.answer("Сколько времени вы можете уделять готовке и какие способы приготовления у вас имеются?")
    await RegistrationForm.cooking_preferences.set()


@dp.message_handler(state=RegistrationForm.cooking_preferences)
async def process_cooking_preferences(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.update_data(cooking_preferences=message.text)
    user_data = await state.get_data()

    profile_data = {
        'about_user': user_data['about_user'],
        'forbidden_products': user_data['forbidden_products'],
        'favorite_products': user_data['favorite_products'],
        'cooking_preferences': user_data['cooking_preferences']
    }

    if not os.path.exists(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)

    # Сохраняем профиль пользователя в JSON
    profile_file_path = os.path.join(PROFILE_DIR, f'user_{user_id}.json')
    with open(profile_file_path, 'w', encoding='utf-8') as f:
        json.dump(profile_data, f, ensure_ascii=False, indent=4)

    add_user_to_csv(user_id, profile_file_path)
    registered_users.add(user_id)

    await state.finish()

    await message.answer(
        "Регистрация завершена! Ваш профиль сохранен. Теперь вам доступен весь список команд.",
        reply_markup=user_keyboard
    )


# Обработчик команды /edit_profile
@dp.message_handler(commands=['edit_profile'])
async def cmd_edit_profile(message: types.Message):
    user_id = message.from_user.id
    if user_id not in registered_users:
        await message.answer("Вы не зарегистрированы. Используйте команду /start для начала.")
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("Пол, возраст, цель", callback_data="edit_about_user"),
        InlineKeyboardButton("Аллергии и нелюбимые продукты", callback_data="edit_forbidden_products"),
        InlineKeyboardButton("Любимая еда", callback_data="edit_favorite_products"),
        InlineKeyboardButton("Время на готовку и способы приготовления", callback_data="edit_cooking_preferences")
    )
    await message.answer("Что вы хотите изменить?", reply_markup=keyboard)
    await EditProfileForm.choose_field.set()


# Обработчик выбора поля для редактирования
@dp.callback_query_handler(state=EditProfileForm.choose_field)
async def process_edit_field_choice(callback_query: types.CallbackQuery, state: FSMContext):
    field_map = {
        "edit_about_user": "about_user",
        "edit_forbidden_products": "forbidden_products",
        "edit_favorite_products": "favorite_products",
        "edit_cooking_preferences": "cooking_preferences"
    }

    chosen_field = callback_query.data
    if chosen_field in field_map:
        await state.update_data(field_to_edit=field_map[chosen_field])
        await bot.send_message(callback_query.from_user.id,
                               f"Введите новое значение для поля \"{field_map[chosen_field]}\":")
        await EditProfileForm.new_value.set()
    else:
        await bot.send_message(callback_query.from_user.id, "Ошибка: неизвестное поле для редактирования.")
        await state.finish()

    await bot.answer_callback_query(callback_query.id)


# Обработчик ввода нового значения для выбранного поля
@dp.message_handler(state=EditProfileForm.new_value)
async def process_new_value(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    new_value = message.text
    user_data = await state.get_data()

    field_to_edit = user_data.get("field_to_edit")
    if not field_to_edit:
        await message.answer("Произошла ошибка. Попробуйте снова.")
        await state.finish()
        return

    # Загрузить текущий профиль пользователя
    profile = load_user_profile(user_id)
    if not profile:
        await message.answer("Ваш профиль не найден. Пожалуйста, зарегистрируйтесь снова.")
        await state.finish()
        return

    # Обновить профиль с новым значением
    profile[field_to_edit] = new_value

    # Сохранить обновленный профиль
    profile_file_path = os.path.join(PROFILE_DIR, f'user_{user_id}.json')
    with open(profile_file_path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=4)

    await message.answer(f"Поле \"{field_to_edit}\" успешно обновлено на \"{new_value}\".")
    await state.finish()


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    help_text = (
        "❓ Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать список команд\n"
        "/edit_profile - Изменить данные профиля\n"
        "/generate_plan - Создать план питания и график покупок\n"
        "/delete_plan - Удалить текущий план и расписание\n"
    )
    await message.answer(help_text)
    
    
week_days = {
    'Понедельник': 0,
    'Вторник': 1,
    'Среда': 2,
    'Четверг': 3,
    'Пятница': 4,
    'Суббота': 5,
    'Воскресенье': 6
}

# Функция для генерации блоков дней
def generate_blocks_from_schedule(shopping_schedule):
    blocks = []
    total_days = len(shopping_schedule)
    days_per_block = 7 // total_days  # сколько дней в каждом блоке
    start_day = 0

    for i in range(total_days):
        # Определяем, сколько дней будет в текущем блоке
        end_day = start_day + days_per_block - 1
        if i == total_days - 1:  # последний блок может быть меньше
            end_day = 6  # до воскресенья включительно

        # Определяем дни недели для блока
        block_days = list(week_days.keys())[start_day:end_day+1]
        blocks.append(f"{block_days[0]}-{block_days[-1]}")

        start_day = end_day + 1  # следующий блок начинается на следующем дне

    return blocks

# Функция для создания напоминаний на основе этих блоков
def create_reminders_for_shopping_schedule(user_id, shopping_schedule):
    reminders = []
    today = datetime.now(pytz.timezone("Europe/Moscow"))

    blocks = generate_blocks_from_schedule(shopping_schedule)

    for i in range(len(blocks)):
        block = blocks[i]
        days = block.split('-')
        start_day = days[0]

        # Находим ближайший start_day в будущем
        start_day_week = week_days[start_day]
        delta_days = (start_day_week - today.weekday()) % 7
        first_day_of_block = today + timedelta(days=delta_days)
        first_day_of_block = first_day_of_block.replace(hour=9, minute=0, second=0, microsecond=0)

        # Создаем напоминание
        reminder = {
            "date": first_day_of_block,
            "message": f"Напоминаем о покупках для блока {block}:\n{shopping_schedule[i]}",
            "user_id": user_id  # добавляем идентификатор пользователя
        }

        # Добавляем задачу в планировщик с меткой user_id
        scheduler.add_job(
            send_reminder,
            CronTrigger(year='*', month='*', day='*', hour='23', minute='0', second='0', day_of_week=str(first_day_of_block.weekday())),
            args=[reminder["message"]],
            id=f"reminder_{user_id}_{block}",  # используем уникальный идентификатор задачи
            replace_existing=True  # если задача с таким ID уже существует, она будет заменена
        )

        reminders.append(reminder)

    return reminders

# Перезапуск планировщика
def restart_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)  # Остановка с возможностью завершения задач
    scheduler.start()  # Новый запуск

# Функция для создания и отправки напоминаний
async def schedule_reminders(reminders):
    
    for reminder in reminders:
        scheduler.add_job(
            send_reminder, 
            CronTrigger(year='*', month='*', day='*', hour='22', minute='30', second='0', day_of_week=str(reminder['date'].weekday())),
            args=[reminder["message"]]
        )
    
    restart_scheduler()

# Отправка напоминания
async def send_reminder(message: str):
    await bot.send_message(chat_id=message.chat.id, text=message)
    
    
# Функция для получения списка всех напоминаний для пользователя
def get_all_reminders_for_user(user_id):
    reminders = []

    for job in scheduler.get_jobs():
        if f"reminder_{user_id}_" in job.id:  # Проверяем, если job.id содержит user_id
            reminder_time = job.next_run_time
            reminder_message = job.args[0]  # Сообщение задачи
            reminders.append(f"Напоминание: {reminder_message} | Время: {reminder_time.strftime('%Y-%m-%d %H:%M:%S')}")

    return reminders


# Команда для вывода всех напоминаний
@dp.message_handler(commands=['list_reminders'])
async def cmd_list_reminders(message: types.Message):
    user_id = message.from_user.id
    logging.info(f"Fetching all reminders for user: {user_id}")

    reminders = get_all_reminders_for_user(user_id)

    if reminders:
        # Выводим все напоминания
        await message.answer("\n".join(reminders))
    else:
        await message.answer("У вас нет активных напоминаний.")
    
    
# Функция для удаления всех напоминаний для пользователя
def remove_all_reminders_for_user(user_id):
    # Получаем все задачи с идентификатором, содержащим user_id
    for job in scheduler.get_jobs():
        if f"reminder_{user_id}_" in job.id:
            job.remove()

@dp.message_handler(commands=['generate_plan'])
async def cmd_generate_plan(message: types.Message):
    user_id = message.from_user.id
    logging.info(f"Handling /generate_plan command from user: {user_id}")

    if user_id not in registered_users:
        await message.answer("Вы не зарегистрированы. Пожалуйста, используйте команду /start для начала.")
        return

    # Проверяем, есть ли уже сгенерированный план
    meal_plan_file_path = os.path.join(STORAGE_DIR, f'meal_plan_{user_id}.json')
    shopping_schedule_file_path = os.path.join(STORAGE_DIR, f'shopping_schedule_{user_id}.json')
    

    if os.path.exists(meal_plan_file_path) or os.path.exists(shopping_schedule_file_path):
        await message.answer(
            "У вас уже есть сгенерированный план. Перед созданием нового плана удалите старый с помощью команды /delete_plan."
        )
        return
    
    with open(meal_plan_file_path, 'w', encoding='utf-8') as f:
        json.dump([], f)

    with open(shopping_schedule_file_path, 'w', encoding='utf-8') as f:
         json.dump([], f)

    # Загружаем профиль пользователя
    profile = load_user_profile(user_id)
    if not profile:
        await message.answer("Ваш профиль не найден. Пожалуйста, зарегистрируйтесь снова.")
        return

    loading_message = await message.answer("Создаем Ваш план ... 🛒")

    meal_plan, shopping_schedule = create_meal_and_coocking_plan(user_id, user_info=profile)
    
    logging.info("Generated meal plan and shopping schedule.")

    with open(meal_plan_file_path, 'w', encoding='utf-8') as f:
        json.dump(meal_plan, f)

    with open(shopping_schedule_file_path, 'w', encoding='utf-8') as f:
         json.dump(shopping_schedule, f)
         
    # Создаем напоминания на основе расписания покупок
    reminders = create_reminders_for_shopping_schedule(user_id, shopping_schedule)
    
    # Запускаем планирование напоминаний
    await schedule_reminders(reminders)
    await message.answer(f"Созданы напоминания по датам покупок продуктов")

    # Обновляем данные пользователя в CSV
    add_user_to_csv(user_id, load_user_profile(user_id), meal_plan_file_path, shopping_schedule_file_path)

    await bot.delete_message(chat_id=message.chat.id, message_id=loading_message.message_id)

    await message.answer(f"Ваш план питания на неделю:")
    for i in range(len(meal_plan)): 
        await message.answer(meal_plan[i], parse_mode="Markdown")
        
    await message.answer(f"Ваш график закупок на неделю:")
    for i in range(len(meal_plan)): 
        await message.answer(shopping_schedule[i], parse_mode="Markdown")
        
        
@dp.message_handler(commands=['view_plan'])
async def cmd_view_plan(message: types.Message):
    user_id = message.from_user.id
    
    # Путь к файлам плана питания и графика покупок
    meal_plan_file_path = os.path.join(STORAGE_DIR, f'meal_plan_{user_id}.json')
    shopping_schedule_file_path = os.path.join(STORAGE_DIR, f'shopping_schedule_{user_id}.json')
    
    if not os.path.exists(meal_plan_file_path) or not os.path.exists(shopping_schedule_file_path):
        await message.answer("Ваш план питания ещё не создан, используйте команду /generate_plan для создания вашего файла")
        return
    
    with open(meal_plan_file_path, "r", encoding="utf-8") as f:
        meal_plan = json.load(f)
        
    with open(shopping_schedule_file_path, "r", encoding="utf-8") as f:
        shopping_schedule = json.load(f)
        
    await message.answer(f"# Ваш план питания на неделю:", parse_mode="Markdown")
    for i in range(len(meal_plan)): 
        await message.answer(meal_plan[i], parse_mode="Markdown")
        
    await message.answer(f"# Ваш график закупок на неделю:", parse_mode="Markdown")
    for i in range(len(meal_plan)): 
        await message.answer(shopping_schedule[i], parse_mode="Markdown")
    

@dp.message_handler(commands=['edit_plan'])
async def process_edit_plan(message: types.Message):
    await message.answer("Введите текст, описывающий, что вы хотите изменить в плане:")
    await PlanEditForm.new_prompt.set()


# Обработчик нового промта для изменения плана
@dp.message_handler(state=PlanEditForm.new_prompt)
async def process_new_prompt(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    new_prompt = message.text
    await state.update_data(user_prompt=new_prompt)
    await message.answer(
        "Промт для изменения плана сохранен. Создаем новый план")
    
    meal_plan_file_path = os.path.join(STORAGE_DIR, f'meal_plan_{user_id}.json')
    shopping_schedule_file_path = os.path.join(STORAGE_DIR, f'shopping_schedule_{user_id}.json')
    
    profile = load_user_profile(user_id)
    if not profile:
        await message.answer("Ваш профиль не найден. Пожалуйста, зарегистрируйтесь снова.")
        return

    remove_all_reminders_for_user(user_id)
    loading_message = await message.answer("Создаем Ваш план ... 🛒")

    meal_plan, shopping_schedule = create_meal_and_coocking_plan(user_id, user_info=profile, prompt=new_prompt)
    
    reminders = create_reminders_for_shopping_schedule(user_id, shopping_schedule)
    
    await schedule_reminders(reminders)
    await message.answer(f"Созданы напоминания по датам покупок продуктов")
    
    logging.info("Generated meal plan and shopping schedule.")

    with open(meal_plan_file_path, 'w', encoding='utf-8') as f:
        json.dump(meal_plan, f)

    with open(shopping_schedule_file_path, 'w', encoding='utf-8') as f:
         json.dump(shopping_schedule, f)

    # Обновляем данные пользователя в CSV
    add_user_to_csv(user_id, load_user_profile(user_id), meal_plan_file_path, shopping_schedule_file_path)

    await bot.delete_message(chat_id=message.chat.id, message_id=loading_message.message_id)

    await message.answer(f"Ваш план питания на неделю:")
    for i in range(len(meal_plan)): 
        await message.answer(meal_plan[i], parse_mode="Markdown")
        
    await message.answer(f"Ваш график закупок на неделю:")
    for i in range(len(meal_plan)): 
        await message.answer(shopping_schedule[i], parse_mode="Markdown")
    await state.finish()


@dp.message_handler(commands=['delete_plan'])
async def cmd_delete_plan(message: types.Message):
    user_id = message.from_user.id

    if user_id not in registered_users:
        await message.answer("Вы не зарегистрированы. Пожалуйста, используйте команду /start для начала.")
        return

    # Путь к файлам плана питания и графика покупок
    meal_plan_file_path = os.path.join(STORAGE_DIR, f'meal_plan_{user_id}.json')
    shopping_schedule_file_path = os.path.join(STORAGE_DIR, f'shopping_schedule_{user_id}.json')

    # Удаляем файлы, если они существуют
    if os.path.exists(meal_plan_file_path):
        os.remove(meal_plan_file_path)

    if os.path.exists(shopping_schedule_file_path):
        os.remove(shopping_schedule_file_path)

    # Обновляем CSV, очищая пути к файлам для пользователя
    file_updated = False

    users_info = pd.read_csv(CSV_FILE)
    for _, row in users_info.iterrows():
        if int(row['user_id']) == user_id:
            row['meal_plan_file_path'] = ''
            row['cook_file_path'] = ''
            file_updated = True

    if file_updated:
        remove_all_reminders_for_user(user_id)
        await message.answer(
            "Ваш текущий план и график покупок были успешно удалены. Теперь вы можете создать новый план с помощью команды /generate_plan.")

        feedback_button = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Пройти анкету", callback_data="feedback_survey")
        )
        await message.answer(
            "Мы будем благодарны, если вы оцените наш сервис, пройдя небольшую анкету. Нажмите на кнопку ниже.",
            reply_markup=feedback_button
        )
    else:
        await message.answer("У вас не найдено сохраненных данных для удаления.")


@dp.callback_query_handler(lambda c: c.data == "feedback_survey")
async def start_feedback_survey(callback_query: types.CallbackQuery):
    await callback_query.message.answer(
        "Спасибо, что решили оценить наш сервис! Давайте начнем.\n\n"
        "Оцените качество составления плана (от 1 до 5):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )
    await FeedbackForm.quality.set()  # Переходим к первому состоянию
    await callback_query.answer()  # Убираем "часики" с кнопки


@dp.message_handler(state=FeedbackForm.quality)
async def feedback_quality(message: types.Message, state: FSMContext):
    # Проверяем корректность ввода
    if message.text not in ['1', '2', '3', '4', '5']:
        await message.answer("Пожалуйста, введите число от 1 до 5.")
        return

    # Сохраняем ответ
    await state.update_data(quality=int(message.text))

    # Переходим к следующему вопросу
    await message.answer(
        "Оцените удобство использования бота (от 1 до 5):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )
    await FeedbackForm.usability.set()


@dp.message_handler(state=FeedbackForm.usability)
async def feedback_usability(message: types.Message, state: FSMContext):
    # Проверяем корректность ввода
    if message.text not in ['1', '2', '3', '4', '5']:
        await message.answer("Пожалуйста, введите число от 1 до 5.")
        return

    # Сохраняем ответ
    await state.update_data(usability=int(message.text))

    # Переходим к последнему вопросу
    await message.answer(
        "Соответствовал ли план вашим требованиям? (да/нет):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton("Да"), KeyboardButton("Нет")]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )
    await FeedbackForm.compliance.set()


@dp.message_handler(state=FeedbackForm.compliance)
async def feedback_compliance(message: types.Message, state: FSMContext):
    # Проверяем корректность ввода
    if message.text.lower() not in ['да', 'нет']:
        await message.answer("Пожалуйста, ответьте 'да' или 'нет'.")
        return

    await state.update_data(compliance=message.text.lower())

    data = await state.get_data()

    feedback_summary = (
        f"Спасибо за ваш отзыв!\n\n"
        f"1. Качество плана: {data['quality']} / 5\n"
        f"2. Удобство использования: {data['usability']} / 5\n"
        f"3. Соответствие требованиям: {'Да' if data['compliance'] == 'да' else 'Нет'}"
    )
    
    with open(os.path.join(STORAGE_DIR, "feedback", f"{ message.from_user.id}_feedback.txt"), "w", encoding="utf-8") as f:
        f.write(feedback_summary) 

    # Отправляем итоги
    await message.answer(feedback_summary, reply_markup=user_keyboard)

    await state.finish()


# Обработчик произвольного текста
@dp.message_handler()
async def echo_message(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("❓ Помощь (/help)", callback_data="cmd_help"),
    )
    await message.answer("Я вас не понял. Выберите команду:", reply_markup=keyboard)


# Обработчик нажатия на кнопку "Помощь"
@dp.callback_query_handler(lambda c: c.data == 'cmd_help')
async def process_help_callback(callback_query: types.CallbackQuery):
    await cmd_help(callback_query.message)
    await bot.answer_callback_query(callback_query.id)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
