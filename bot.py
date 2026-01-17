import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode


# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import TELEGRAM_BOT_TOKEN, LOGS_DIR, DOWNLOADS_DIR, USE_LOCAL_BOT_API, LOCAL_BOT_API_URL
from handlers import start, search, download, video

# Настройка логирования
def setup_logging():
    """Настраивает логирование для бота"""
    # Создаем директорию для логов если не существует
    os.makedirs(LOGS_DIR, exist_ok=True)
    
    # Настройка форматирования
    log_format = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Настройка логгера
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            # Логи в файл
            logging.FileHandler(
                os.path.join(LOGS_DIR, 'bot.log'),
                encoding='utf-8'
            ),
            # Логи в консоль
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Отключаем избыточные логи от библиотек
    logging.getLogger('aiogram').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('yt_dlp').setLevel(logging.ERROR)

async def create_bot_and_dispatcher():
    """Создает и настраивает бота и диспетчер"""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен в переменных окружения")

    logger = logging.getLogger(__name__)

    # Настройка для локального Bot API (позволяет отправлять файлы до 2GB)
    if USE_LOCAL_BOT_API:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer

        local_server = TelegramAPIServer.from_base(LOCAL_BOT_API_URL)
        session = AiohttpSession(api=local_server)

        bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            parse_mode=ParseMode.MARKDOWN,
            session=session
        )
        logger.info(f"Using local Bot API server: {LOCAL_BOT_API_URL}")
    else:
        # Стандартный режим через api.telegram.org
        bot = Bot(
            token=TELEGRAM_BOT_TOKEN,
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("Using standard Telegram Bot API")

    
    # Создаем диспетчер с хранилищем в памяти
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем роутеры
    # ВАЖНО: video router должен быть перед search, чтобы YouTube ссылки обрабатывались первыми
    dp.include_router(start.router)
    dp.include_router(video.router)
    dp.include_router(search.router)
    dp.include_router(download.router)
    
    return bot, dp

async def on_startup(bot: Bot):
    """Выполняется при запуске бота"""
    logger = logging.getLogger(__name__)
    
    # Создаем необходимые директории
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"Bot started: @{bot_info.username} ({bot_info.full_name})")
    logger.info(f"Bot ID: {bot_info.id}")
    
    # Устанавливаем команды бота
    from aiogram.types import BotCommand
    commands = [
        BotCommand(command="start", description="🎵 Начать работу с ботом"),
        BotCommand(command="help", description="🆘 Помощь и инструкции"),
        BotCommand(command="about", description="ℹ️ О боте"),
        BotCommand(command="upload_cookies", description="🍪 Загрузить YouTube cookies"),
    ]
    
    await bot.set_my_commands(commands)
    logger.info("Bot commands set successfully")

async def on_shutdown(bot: Bot):
    """Выполняется при остановке бота"""
    logger = logging.getLogger(__name__)
    logger.info("Bot is shutting down...")
    
    # Очищаем временные файлы
    try:
        if os.path.exists(DOWNLOADS_DIR):
            for file in os.listdir(DOWNLOADS_DIR):
                file_path = os.path.join(DOWNLOADS_DIR, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            logger.info("Cleaned up temporary files")
    except Exception as e:
        logger.warning(f"Failed to clean up temporary files: {e}")
    
    await bot.session.close()
    logger.info("Bot stopped")

async def periodic_cleanup():
    """Периодическая очистка кэша и временных файлов"""
    logger = logging.getLogger(__name__)
    
    while True:
        try:
            # Ждем 30 минут
            await asyncio.sleep(1800)
            
            # Очищаем кэш поиска
            from handlers.search import cleanup_search_cache
            await cleanup_search_cache()
            
            # Очищаем активные загрузки
            from handlers.download import cleanup_active_downloads
            await cleanup_active_downloads()
            
            # Очищаем старые временные файлы
            if os.path.exists(DOWNLOADS_DIR):
                import time
                current_time = time.time()
                
                for file in os.listdir(DOWNLOADS_DIR):
                    file_path = os.path.join(DOWNLOADS_DIR, file)
                    if os.path.isfile(file_path):
                        # Удаляем файлы старше 1 часа
                        if current_time - os.path.getmtime(file_path) > 3600:
                            os.remove(file_path)
                            logger.info(f"Removed old temporary file: {file}")
            
            logger.info("Periodic cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during periodic cleanup: {e}")

async def main():
    """Главная функция запуска бота"""
    # Настраиваем логирование
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Создаем бота и диспетчер
        bot, dp = await create_bot_and_dispatcher()
        
        # Регистрируем обработчики событий
        dp.startup.register(on_startup)
        dp.shutdown.register(on_shutdown)
        
        # Запускаем периодическую очистку в фоне
        cleanup_task = asyncio.create_task(periodic_cleanup())
        
        logger.info("Starting bot...")
        
        # Запускаем бота
        try:
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        finally:
            # Отменяем задачу очистки при остановке
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
    
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)
