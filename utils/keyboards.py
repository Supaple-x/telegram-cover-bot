from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import SOURCES

def get_source_selection_keyboard():
    """Создает клавиатуру для выбора источника поиска"""
    builder = InlineKeyboardBuilder()
    
    # Первый ряд: YouTube и YouTube Music
    builder.row(
        InlineKeyboardButton(text="🎬 YouTube", callback_data="source_youtube"),
        InlineKeyboardButton(text="🎵 YT Music", callback_data="source_youtube_music")
    )
    
    # Второй ряд: VK Music и Yandex Music
    builder.row(
        InlineKeyboardButton(text="🎶 VK Music", callback_data="source_vk_music"),
        InlineKeyboardButton(text="🎧 Yandex Music", callback_data="source_yandex_music")
    )
    
    # Третий ряд: SoundCloud
    builder.row(
        InlineKeyboardButton(text="🔊 SoundCloud", callback_data="source_soundcloud")
    )
    
    return builder.as_markup()

def get_search_results_keyboard(tracks, page=0, total_pages=1, source="", query=""):
    """Создает клавиатуру с результатами поиска"""
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки для каждого трека
    for i, track in enumerate(tracks):
        track_number = f"{i + 1}️⃣"
        track_title = f"{track.get('title', 'Unknown')} [{track.get('duration', 'N/A')}]"
        
        # Обрезаем название если слишком длинное
        if len(track_title) > 50:
            track_title = track_title[:47] + "..."
        
        button_text = f"{track_number} {track_title}"
        callback_data = f"download_{source}_{track.get('id', i)}"
        
        builder.row(
            InlineKeyboardButton(text=button_text, callback_data=callback_data)
        )
    
    # Навигационные кнопки
    nav_buttons = []
    
    # Кнопка "Назад" (если не первая страница)
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"page_{source}_{page-1}_{query}")
        )
    
    # Индикатор страницы
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"Стр. {page+1}/{total_pages}", callback_data="noop")
        )
    
    # Кнопка "Вперед" (если не последняя страница)
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="Вперед ▶️", callback_data=f"page_{source}_{page+1}_{query}")
        )
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    # Кнопка "Новый поиск"
    builder.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="new_search")
    )
    
    return builder.as_markup()

def get_start_keyboard():
    """Создает клавиатуру для команды /start"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🎵 Начать поиск", callback_data="start_search")
    )
    
    return builder.as_markup()

def get_progress_keyboard():
    """Создает клавиатуру с кнопкой отмены для процесса скачивания"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_download")
    )
    
    return builder.as_markup()

def get_error_keyboard():
    """Создает клавиатуру для сообщений об ошибках"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🔍 Попробовать снова", callback_data="new_search"),
        InlineKeyboardButton(text="🆘 Помощь", callback_data="help")
    )
    
    return builder.as_markup()
