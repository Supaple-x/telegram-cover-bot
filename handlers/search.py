from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import logging
from typing import Dict, Any

from config import SOURCES, STATUS_SEARCHING, MAX_RESULTS_PER_PAGE
from utils.keyboards import get_source_selection_keyboard, get_search_results_keyboard, get_error_keyboard
from utils.formatters import format_search_results_message, format_error_message
from services.youtube_service import YouTubeService
from services.soundcloud_service import SoundCloudService

router = Router()
logger = logging.getLogger(__name__)

class SearchStates(StatesGroup):
    waiting_for_query = State()
    showing_results = State()

# Глобальное хранилище результатов поиска (в продакшене лучше использовать Redis)
search_cache: Dict[str, Dict[str, Any]] = {}

@router.message(F.text & ~F.text.startswith('/'))
async def handle_search_query(message: Message, state: FSMContext):
    """Обработчик текстовых сообщений - запросов на поиск"""
    query = message.text.strip()
    
    if len(query) < 2:
        await message.answer(
            "❌ Запрос слишком короткий. Введите название трека или исполнителя (минимум 2 символа)."
        )
        return
    
    if len(query) > 100:
        await message.answer(
            "❌ Запрос слишком длинный. Максимум 100 символов."
        )
        return
    
    # Сохраняем запрос в состоянии
    await state.update_data(query=query)
    await state.set_state(SearchStates.waiting_for_query)
    
    # Отправляем клавиатуру выбора источника
    await message.answer(
        f"🔍 **Выберите источник для поиска:**\n\n"
        f"Запрос: \"{query}\"",
        reply_markup=get_source_selection_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("source_"))
async def handle_source_selection(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора источника для поиска"""
    source = callback.data.replace("source_", "")
    data = await state.get_data()
    query = data.get("query")
    
    if not query:
        await callback.message.edit_text(
            "❌ Ошибка: запрос не найден. Отправьте новый запрос."
        )
        await callback.answer()
        return
    
    # Показываем статус "печатает..."
    await callback.message.bot.send_chat_action(
        chat_id=callback.message.chat.id,
        action="typing"
    )
    
    # Показываем статус поиска
    source_name = SOURCES.get(source, source)
    await callback.message.edit_text(
        STATUS_SEARCHING.format(source=source_name),
        parse_mode="Markdown"
    )
    await callback.answer()
    
    try:
        # Выполняем поиск
        tracks, error_details = await perform_search(source, query)

        if not tracks:
            # Передаем детали ошибки, если они есть
            await callback.message.edit_text(
                format_error_message("not_found", error_details),
                reply_markup=get_error_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        # Сохраняем результаты в кэш
        cache_key = f"{callback.from_user.id}_{source}_{query}"
        search_cache[cache_key] = {
            'tracks': tracks,
            'source': source,
            'query': query,
            'total_pages': (len(tracks) + MAX_RESULTS_PER_PAGE - 1) // MAX_RESULTS_PER_PAGE
        }
        
        # Показываем первую страницу результатов
        await show_search_results(callback.message, cache_key, page=0)
        await state.set_state(SearchStates.showing_results)
        
    except Exception as e:
        logger.error(f"Search error for user {callback.from_user.id}: {e}")
        await callback.message.edit_text(
            format_error_message("unknown", str(e)),
            reply_markup=get_error_keyboard(),
            parse_mode="Markdown"
        )

@router.callback_query(F.data.startswith("page::"))
async def handle_page_navigation(callback: CallbackQuery):
    """Обработчик навигации по страницам результатов"""
    try:
        # Парсим данные: page::source::pagenum::query
        parts = callback.data.split("::", 3)
        if len(parts) < 4:
            await callback.answer("❌ Ошибка навигации")
            return

        source = parts[1]
        page = int(parts[2])
        query = parts[3]

        cache_key = f"{callback.from_user.id}_{source}_{query}"
        
        if cache_key not in search_cache:
            await callback.message.edit_text(
                "❌ Результаты поиска устарели. Выполните новый поиск.",
                reply_markup=get_error_keyboard()
            )
            await callback.answer()
            return
        
        await show_search_results(callback.message, cache_key, page)
        await callback.answer()
        
    except (ValueError, IndexError) as e:
        logger.error(f"Page navigation error: {e}")
        await callback.answer("❌ Ошибка навигации")

async def perform_search(source: str, query: str):
    """Выполняет поиск в указанном источнике

    Returns:
        tuple: (tracks, error_details) - список треков и детали ошибки (если есть)
    """
    try:
        if source == "youtube":
            service = YouTubeService()
            return await service.search(query), None
        elif source == "youtube_music":
            service = YouTubeService()
            return await service.search_music(query), None
        elif source == "soundcloud":
            service = SoundCloudService()
            return await service.search(query), None
        elif source == "vk_music":
            from services.vk_service import VKMusicService
            service = VKMusicService()

            if not service.is_authenticated:
                error_msg = f"VK Music: {service.auth_error_message}"
                logger.error(f"VK Music not authenticated: {service.auth_error_message}")
                return [], error_msg

            # search возвращает кортеж (tracks, error_details)
            tracks, error_details = await service.search(query)
            return tracks, error_details
        elif source == "yandex_music":
            # TODO: Реализовать Yandex Music поиск
            return [], None
        else:
            logger.warning(f"Unknown source: {source}")
            return [], None

    except Exception as e:
        logger.error(f"Search error in {source}: {e}")
        raise

async def show_search_results(message, cache_key: str, page: int):
    """Показывает результаты поиска для указанной страницы"""
    if cache_key not in search_cache:
        await message.edit_text(
            "❌ Результаты поиска не найдены.",
            reply_markup=get_error_keyboard()
        )
        return
    
    cache_data = search_cache[cache_key]
    tracks = cache_data['tracks']
    source = cache_data['source']
    query = cache_data['query']
    total_pages = cache_data['total_pages']
    
    # Проверяем валидность страницы
    if page < 0 or page >= total_pages:
        return
    
    # Получаем треки для текущей страницы
    start_idx = page * MAX_RESULTS_PER_PAGE
    end_idx = start_idx + MAX_RESULTS_PER_PAGE
    page_tracks = tracks[start_idx:end_idx]
    
    # Добавляем индексы для callback_data
    for i, track in enumerate(page_tracks):
        track['page_index'] = start_idx + i
        # Логируем ID трека для отладки
        logger.debug(f"Page track {i}: id={track.get('id')}, title={track.get('title')}")

    # Форматируем сообщение
    message_text = format_search_results_message(
        page_tracks, source, query, page, total_pages
    )
    
    # Создаем клавиатуру
    keyboard = get_search_results_keyboard(
        page_tracks, page, total_pages, source, query
    )
    
    await message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# Очистка кэша (вызывается периодически)
async def cleanup_search_cache():
    """Очищает старые записи из кэша поиска"""
    # В продакшене здесь должна быть логика очистки по времени
    # Пока просто ограничиваем размер кэша
    if len(search_cache) > 1000:
        # Удаляем половину записей (простая стратегия)
        keys_to_remove = list(search_cache.keys())[:500]
        for key in keys_to_remove:
            del search_cache[key]
        logger.info(f"Cleaned up search cache, removed {len(keys_to_remove)} entries")
