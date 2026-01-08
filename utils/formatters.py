import re
from typing import List, Dict, Any

def format_duration(seconds):
    """Форматирует длительность из секунд в MM:SS формат"""
    if not seconds or seconds == 0:
        return "N/A"
    
    try:
        seconds = int(seconds)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    except (ValueError, TypeError):
        return "N/A"

def format_file_size(size_bytes):
    """Форматирует размер файла в человекочитаемый формат"""
    if not size_bytes:
        return "N/A"
    
    try:
        size_bytes = int(size_bytes)
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
    except (ValueError, TypeError):
        return "N/A"

def format_track_title(title, artist=None, max_length=50):
    """Форматирует название трека для отображения"""
    if not title:
        return "Unknown Track"
    
    # Очищаем название от лишних символов
    title = re.sub(r'[^\w\s\-\(\)\[\].,!?]', '', title)
    
    if artist:
        formatted = f"{artist} - {title}"
    else:
        formatted = title
    
    # Обрезаем если слишком длинное
    if len(formatted) > max_length:
        formatted = formatted[:max_length-3] + "..."
    
    return formatted

def format_search_results_message(tracks: List[Dict[Any, Any]], source: str, query: str, page: int = 0, total_pages: int = 1):
    """Форматирует сообщение с результатами поиска"""
    source_emoji = {
        'youtube': '🎬',
        'youtube_music': '🎵',
        'vk_music': '🎶',
        'yandex_music': '🎧',
        'soundcloud': '🔊'
    }
    
    emoji = source_emoji.get(source, '🎵')
    source_name = source.replace('_', ' ').title()
    
    # Экранируем query для безопасного отображения
    safe_query = escape_markdown(query)
    
    message = f"{emoji} **{source_name}** | Результаты для: \"{safe_query}\"\n\n"
    
    if not tracks:
        message += "😔 Ничего не найдено. Попробуйте другой запрос."
        return message
    
    for i, track in enumerate(tracks, 1):
        title = track.get('title', 'Unknown')
        duration = format_duration(track.get('duration'))
        quality = track.get('quality', 'N/A')
        
        # Обрезаем название если слишком длинное
        if len(title) > 40:
            title = title[:37] + "..."
        
        # Экранируем title для безопасного отображения в Markdown
        safe_title = escape_markdown(title)
        
        message += f"{i}️⃣ **{safe_title}**\n"
        message += f"   ⏱️ {duration}"
        
        if quality != 'N/A':
            message += f" | 🎧 {quality}"
        
        message += "\n\n"
    
    # Добавляем информацию о страницах
    if total_pages > 1:
        message += f"📄 Страница {page + 1} из {total_pages}"
    
    return message

def format_progress_bar(progress: float, length: int = 10):
    """Создает прогресс-бар из символов"""
    if progress < 0:
        progress = 0
    elif progress > 100:
        progress = 100
    
    filled = int((progress / 100) * length)
    empty = length - filled
    
    bar = "▓" * filled + "░" * empty
    return f"[{bar}] {progress:.0f}%"

def format_download_status(title: str, progress: float = None):
    """Форматирует статус скачивания"""
    if progress is not None:
        progress_bar = format_progress_bar(progress)
        return f"⏳ **Скачиваю:** {title}\n{progress_bar}"
    else:
        return f"⏳ **Скачиваю:** {title}"

def format_error_message(error_type: str, details: str = None):
    """Форматирует сообщение об ошибке"""
    error_messages = {
        'not_found': "😔 **Трек не найден**\n\nПопробуйте изменить запрос или выбрать другой источник.",
        'download_failed': "❌ **Ошибка скачивания**",
        'network_error': "🌐 **Проблема с соединением**\n\nПроверьте интернет-соединение и попробуйте позже.",
        'api_limit': "⏱️ **Превышен лимит запросов**\n\nПопробуйте через несколько минут.",
        'file_too_large': "📁 **Файл слишком большой**\n\nРазмер файла превышает 50MB. Попробуйте другой трек.",
        'unknown': "❓ **Неизвестная ошибка**"
    }
    
    message = error_messages.get(error_type, error_messages['unknown'])
    
    if details:
        message += f"\n\n> **Детали:** {details}"
    
    return message

def clean_filename(filename: str):
    """Очищает имя файла от недопустимых символов"""
    # Удаляем недопустимые символы для имени файла
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Заменяем множественные пробелы на один
    filename = re.sub(r'\s+', ' ', filename)
    # Убираем пробелы в начале и конце
    filename = filename.strip()
    
    # Если имя файла пустое, используем дефолтное
    if not filename:
        filename = "audio"
    
    return filename

def format_audio_metadata(track_info: Dict[str, Any]):
    """Форматирует метаданные аудио для отправки"""
    title = track_info.get('title', 'Unknown Track')
    artist = track_info.get('artist', 'Unknown Artist')
    duration = track_info.get('duration', 0)
    
    return {
        'title': title,
        'performer': artist,
        'duration': duration
    }

def escape_markdown(text: str):
    """Экранирует специальные символы для Markdown"""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text
