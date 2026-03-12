import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Local Bot API (for files > 50MB)
USE_LOCAL_BOT_API = os.getenv('USE_LOCAL_BOT_API', 'false').lower() == 'true'
LOCAL_BOT_API_URL = os.getenv('LOCAL_BOT_API_URL', 'http://localhost:8081')

# YouTube
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# VK (Token has priority over login/password)
VK_TOKEN = os.getenv('VK_TOKEN')
VK_LOGIN = os.getenv('VK_LOGIN')
VK_PASSWORD = os.getenv('VK_PASSWORD')

# Yandex Music
YANDEX_MUSIC_TOKEN = os.getenv('YANDEX_MUSIC_TOKEN')

# Admin
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) or None

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

# Settings
MAX_RESULTS_PER_PAGE = 5
MAX_FILE_SIZE_MB = 2000 if USE_LOCAL_BOT_API else 50  # 2GB with local API, 50MB otherwise
AUDIO_FORMAT = 'mp3'
AUDIO_QUALITY = '320'

# Messages
START_MESSAGE = """
🎵 **Добро пожаловать в Music Finder Bot!**

Я помогу вам найти и скачать музыку из разных источников.

**Как пользоваться:**
1. Отправьте мне название трека или исполнителя
2. Выберите источник для поиска
3. Нажмите на нужный трек для скачивания

**Доступные источники:**
🎬 YouTube
📺 Rutube
📹 VK Видео
🎵 YouTube Music
🎶 VK Music
🎧 Yandex Music
🔊 SoundCloud

Начните с команды /help для подробной инструкции!
"""

HELP_MESSAGE = """
🆘 **Подробная инструкция по использованию**

**Команды:**
/start - Начать работу с ботом
/help - Показать эту справку
/about - Информация о боте
/cookies - Обновить YouTube cookies

**Как искать музыку:**
1. Отправьте название трека или исполнителя
2. Выберите источник для поиска
3. Нажмите на нужный трек для скачивания

**Как скачать видео с YouTube, Rutube или VK Видео:**
Отправьте ссылку на видео — бот предложит выбрать качество.

**Поддерживаемые источники:**
🎬 **YouTube** - видео и аудио контент
📺 **Rutube** - видео
📹 **VK Видео** - видео
🎵 **YouTube Music** - музыкальные треки
🎶 **VK Music** - музыка из ВКонтакте
🎧 **Yandex Music** - треки из Яндекс.Музыки
🔊 **SoundCloud** - независимые исполнители

**Ограничения:**
• Максимальный размер файла: 2 ГБ
• Формат аудио: MP3 (320 kbps)
• Максимум 10 результатов на странице

**Навигация:**
◀️ Назад / ▶️ Вперед - листать результаты
🔍 Новый поиск - начать заново

Если у вас возникли проблемы, попробуйте другой источник или измените запрос.
"""

ABOUT_MESSAGE = """
ℹ️ **О боте MediaTransfer**

**Возможности:**
• Поиск и скачивание музыки из 5 источников
• Скачивание видео с YouTube, Rutube и VK Видео (до 2 ГБ)
• Высокое качество аудио (MP3 320kbps)
• Выбор качества видео (360p — 1080p)
• Прогресс-бар загрузки

**Поддерживаемые источники:**
🎬 YouTube - видео и аудио
📺 Rutube - видео
📹 VK Видео - видео
🎵 YouTube Music - музыкальные треки
🎶 VK Music - музыка из ВКонтакте
🎧 Yandex Music - треки из Яндекс.Музыки
🔊 SoundCloud - независимые артисты

**Конфиденциальность:**
Бот не сохраняет ваши запросы и личные данные.
Все скачанные файлы удаляются после отправки.
"""

# Error messages
ERROR_TRACK_NOT_FOUND = "😔 Ничего не найдено. Попробуйте другой запрос или источник"
ERROR_DOWNLOAD_FAILED = "❌ Ошибка скачивания"
ERROR_NETWORK = "🌐 Проблема с соединением. Попробуйте позже"
ERROR_API_LIMIT = "⏱️ Превышен лимит запросов. Попробуйте через несколько минут"
ERROR_FILE_TOO_LARGE = "📁 Файл слишком большой (>50MB). Попробуйте другой трек"

# Status messages
STATUS_SEARCHING = "🔎 Ищу в {source}..."
STATUS_DOWNLOADING = "⏳ Скачиваю: {title}"
STATUS_UPLOADING = "📤 Отправляю аудио..."
STATUS_COMPLETE = "✅ Готово!"

# Source names
SOURCES = {
    'youtube': '🎬 YouTube',
    'youtube_music': '🎵 YouTube Music',
    'vk_music': '🎶 VK Music',
    'yandex_music': '🎧 Yandex Music',
    'soundcloud': '🔊 SoundCloud'
}
