from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Document
from aiogram.filters import Command
from config import START_MESSAGE, HELP_MESSAGE, ABOUT_MESSAGE
from utils.keyboards import get_start_keyboard, get_source_selection_keyboard
import logging
import os

router = Router()
logger = logging.getLogger(__name__)

# ID администратора (замените на ваш Telegram ID)
ADMIN_ID = None  # Будет установлен автоматически при первой команде /upload_cookies

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        START_MESSAGE,
        reply_markup=get_start_keyboard(),
        parse_mode="Markdown"
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    await message.answer(
        HELP_MESSAGE,
        parse_mode="Markdown"
    )

@router.message(Command("about"))
async def cmd_about(message: Message):
    """Обработчик команды /about"""
    await message.answer(
        ABOUT_MESSAGE,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "start_search")
async def callback_start_search(callback: CallbackQuery):
    """Обработчик кнопки 'Начать поиск'"""
    await callback.message.edit_text(
        "🎵 **Отправьте название трека или исполнителя**\n\n"
        "Примеры:\n"
        "• Imagine Dragons Believer\n"
        "• Coldplay\n"
        "• The Beatles Yesterday\n"
        "• Eminem Lose Yourself\n\n"
        "После отправки запроса выберите источник для поиска.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "new_search")
async def callback_new_search(callback: CallbackQuery):
    """Обработчик кнопки 'Новый поиск'"""
    await callback.message.edit_text(
        "🎵 **Отправьте название трека или исполнителя**\n\n"
        "Примеры:\n"
        "• Imagine Dragons Believer\n"
        "• Coldplay\n"
        "• The Beatles Yesterday\n"
        "• Eminem Lose Yourself\n\n"
        "После отправки запроса выберите источник для поиска.",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Обработчик кнопки 'Помощь'"""
    await callback.message.answer(
        HELP_MESSAGE,
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "noop")
async def callback_noop(callback: CallbackQuery):
    """Обработчик для кнопок без действия (например, индикатор страницы)"""
    await callback.answer()

@router.message(Command("upload_cookies", "auth_youtube"))
async def cmd_upload_cookies(message: Message):
    """Обработчик команды /upload_cookies и /auth_youtube для загрузки cookies файла"""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📖 Инструкция (yt-dlp wiki)",
            url="https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies"
        )],
        [InlineKeyboardButton(
            text="🔗 Расширение для Chrome",
            url="https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc"
        )],
        [InlineKeyboardButton(
            text="🦊 Расширение для Firefox",
            url="https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/"
        )]
    ])

    await message.answer(
        "🔐 **Авторизация YouTube Music**\n\n"
        "Для скачивания музыки с YouTube Music нужны cookies вашего аккаунта.\n\n"
        "**Как это работает:**\n"
        "1️⃣ Установите расширение для браузера (ссылки ниже)\n"
        "2️⃣ Откройте [YouTube](https://youtube.com) и войдите в аккаунт\n"
        "3️⃣ **Важно:** Откройте в НОВОЙ вкладке инкогнито!\n"
        "4️⃣ Перейдите на https://youtube.com/robots.txt в той же вкладке\n"
        "5️⃣ Нажмите на расширение и экспортируйте cookies\n"
        "6️⃣ Сохраните файл как `youtube_cookies.txt`\n"
        "7️⃣ **ЗАКРОЙТЕ** окно инкогнито\n"
        "8️⃣ Отправьте файл мне\n\n"
        "⚠️ **Важно:** Экспортируйте cookies с youtube.com/robots.txt в инкогнито, "
        "чтобы они не ротировались!\n\n"
        "🔒 Ваши cookies **не передаются** третьим лицам и используются "
        "только для скачивания музыки.\n\n"
        "📎 Просто отправьте файл `youtube_cookies.txt` следующим сообщением.",
        parse_mode="Markdown",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@router.message(F.document)
async def handle_document(message: Message):
    """Обработчик загрузки документов (cookies файла)"""
    document: Document = message.document

    # Проверяем имя файла
    if not document.file_name or 'cookies' not in document.file_name.lower():
        # Не отвечаем, чтобы не мешать другим обработчикам
        return
    
    try:
        # Показываем статус
        status_msg = await message.answer("⏳ Загружаю cookies файл...")
        
        # Скачиваем файл
        file = await message.bot.get_file(document.file_id)
        file_path = f"/opt/telegram-cover-bot/youtube_cookies.txt"
        
        await message.bot.download_file(file.file_path, file_path)
        
        # Проверяем содержимое файла
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Базовая валидация
        if 'youtube.com' not in content:
            await status_msg.edit_text(
                "❌ **Ошибка:** Файл не содержит YouTube cookies.\n\n"
                "Убедитесь, что вы экспортировали cookies с сайта YouTube."
            )
            os.remove(file_path)
            return
        
        # Подсчитываем количество cookies
        cookie_count = len([line for line in content.split('\n') if line.strip() and not line.startswith('#')])
        
        logger.info(f"Cookies file uploaded by user {message.from_user.id}: {cookie_count} cookies")
        
        await status_msg.edit_text(
            f"✅ **Cookies успешно загружены!**\n\n"
            f"📊 Статистика:\n"
            f"• Файл: `{document.file_name}`\n"
            f"• Размер: {document.file_size} байт\n"
            f"• Cookies: {cookie_count}\n\n"
            f"🔄 Перезапускаю бота для применения изменений...",
            parse_mode="Markdown"
        )
        
        # Перезапускаем бота
        import subprocess
        subprocess.run(['systemctl', 'restart', 'telegram-cover-bot'])
        
        await message.answer(
            "🎉 **Готово!**\n\n"
            "Бот перезапущен с новыми cookies.\n"
            "Теперь YouTube скачивание должно работать!\n\n"
            "Попробуйте скачать трек для проверки.",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error uploading cookies: {e}")
        await message.answer(
            f"❌ **Ошибка при загрузке cookies:**\n\n"
            f"`{str(e)}`\n\n"
            f"Попробуйте еще раз или обратитесь к документации.",
            parse_mode="Markdown"
        )
