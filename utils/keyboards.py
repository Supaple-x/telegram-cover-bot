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
        from utils.formatters import format_duration

        track_number = f"{i + 1}️⃣"
        title = track.get('title', 'Unknown')
        artist = track.get('artist', '')
        duration = format_duration(track.get('duration'))
        quality = track.get('quality', 'N/A')

        # Формируем текст кнопки: исполнитель - название | длительность | качество
        if artist:
            full_name = f"{artist} - {title}"
        else:
            full_name = title

        button_text = f"{track_number} {full_name}"

        # Обрезаем название если слишком длинное (оставляем место для длительности и качества)
        if len(button_text) > 35:
            button_text = button_text[:32] + "..."

        # Добавляем длительность и качество
        button_text += f" | ⏱️ {duration}"
        if quality != 'N/A':
            button_text += f" | 🎧 {quality}"

        track_id = track.get('id', i)
        # Используем :: как разделитель чтобы избежать конфликта с _ в source названиях
        callback_data = f"download::{source}::{track_id}"

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
