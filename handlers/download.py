from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
import logging
import os
import asyncio
from typing import Dict, Any

from config import DOWNLOADS_DIR, STATUS_DOWNLOADING, STATUS_UPLOADING, STATUS_COMPLETE, MAX_FILE_SIZE_MB
from utils.formatters import format_download_status, format_error_message, format_audio_metadata, clean_filename
from utils.keyboards import get_error_keyboard
from services.youtube_service import YouTubeService
from services.soundcloud_service import SoundCloudService
from handlers.search import search_cache

router = Router()
logger = logging.getLogger(__name__)

# Хранилище активных загрузок
active_downloads: Dict[str, Dict[str, Any]] = {}

@router.callback_query(F.data.startswith("download::"))
async def handle_download_request(callback: CallbackQuery, state: FSMContext):
    """Обработчик запроса на скачивание трека"""
    try:
        # Парсим callback_data: download::source::trackid
        parts = callback.data.split("::", 2)
        if len(parts) < 3:
            await callback.answer("❌ Ошибка: неверный формат запроса")
            return

        source = parts[1]
        track_id = parts[2]
        user_id = callback.from_user.id
        
        # Проверяем, не идет ли уже загрузка для этого пользователя
        download_key = f"{user_id}_{source}_{track_id}"
        if download_key in active_downloads:
            await callback.answer("⏳ Загрузка уже выполняется...")
            return
        
        # Находим информацию о треке в кэше
        track_info = await find_track_in_cache(user_id, source, track_id)
        if not track_info:
            await callback.message.edit_text(
                "❌ Информация о треке не найдена. Выполните новый поиск.",
                reply_markup=get_error_keyboard()
            )
            await callback.answer()
            return
        
        # Отмечаем начало загрузки
        active_downloads[download_key] = {
            'user_id': user_id,
            'track_info': track_info,
            'status': 'downloading'
        }
        
        # Показываем статус "печатает..."
        await callback.message.bot.send_chat_action(
            chat_id=callback.message.chat.id,
            action="typing"
        )
        
        # Показываем статус загрузки
        title = track_info.get('title', 'Unknown Track')
        await callback.message.edit_text(
            format_download_status(title),
            parse_mode="Markdown"
        )
        await callback.answer()
        
        # Запускаем загрузку в фоне
        asyncio.create_task(download_and_send_track(
            callback.message, source, track_info, download_key
        ))
        
    except Exception as e:
        logger.error(f"Download request error for user {callback.from_user.id}: {e}")
        await callback.message.edit_text(
            format_error_message("unknown", str(e)),
            reply_markup=get_error_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer()

@router.callback_query(F.data == "cancel_download")
async def handle_cancel_download(callback: CallbackQuery):
    """Обработчик отмены загрузки"""
    user_id = callback.from_user.id
    
    # Находим активную загрузку пользователя
    download_key = None
    for key, download_info in active_downloads.items():
        if download_info['user_id'] == user_id:
            download_key = key
            break
    
    if download_key:
        # Отмечаем загрузку как отмененную
        active_downloads[download_key]['status'] = 'cancelled'
        await callback.message.edit_text(
            "❌ **Загрузка отменена**",
            reply_markup=get_error_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            "ℹ️ Нет активных загрузок для отмены.",
            reply_markup=get_error_keyboard()
        )
    
    await callback.answer()

async def find_track_in_cache(user_id: int, source: str, track_id: str) -> Dict[str, Any]:
    """Находит информацию о треке в кэше поиска"""
    logger.debug(f"Looking for track_id='{track_id}' for user_id={user_id}, source={source}")

    for cache_key, cache_data in search_cache.items():
        if cache_key.startswith(f"{user_id}_{source}_") and cache_data['source'] == source:
            logger.debug(f"Checking cache_key: {cache_key}, tracks count: {len(cache_data['tracks'])}")
            for track in cache_data['tracks']:
                track_id_str = str(track.get('id', ''))
                page_index_str = str(track.get('page_index', ''))
                logger.debug(f"  Track: id={track_id_str}, page_index={page_index_str}, title={track.get('title')}")

                if track_id_str == track_id or page_index_str == track_id:
                    logger.info(f"Found track in cache: {track.get('title')}")
                    return track

    logger.warning(f"Track not found in cache: track_id={track_id}, user_id={user_id}, source={source}")
    return None

async def download_and_send_track(message, source: str, track_info: Dict[str, Any], download_key: str):
    """Скачивает и отправляет трек пользователю"""
    file_path = None
    try:
        # Проверяем, не была ли отменена загрузка
        if download_key not in active_downloads or active_downloads[download_key]['status'] == 'cancelled':
            return
        
        # Получаем сервис для загрузки
        service = get_download_service(source)
        if not service:
            await message.edit_text(
                format_error_message("unknown", f"Источник {source} не поддерживается"),
                reply_markup=get_error_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        # Создаем директорию для загрузок если не существует
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        
        # Генерируем имя файла
        title = track_info.get('title', 'Unknown Track')
        artist = track_info.get('artist', '')
        filename = clean_filename(f"{artist} - {title}" if artist else title)
        file_path = os.path.join(DOWNLOADS_DIR, f"{filename}.mp3")
        
        # Обновляем статус
        active_downloads[download_key]['status'] = 'downloading'
        
        # Показываем статус "записывает аудио..." во время скачивания
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="record_audio"
        )
        
        # Скачиваем трек
        success = await service.download(track_info, file_path)
        
        if not success:
            await message.edit_text(
                format_error_message("download_failed", "Не удалось скачать трек"),
                reply_markup=get_error_keyboard(),
                parse_mode="Markdown"
            )
            return
        
        # Проверяем размер файла
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
                await message.edit_text(
                    format_error_message("file_too_large"),
                    reply_markup=get_error_keyboard(),
                    parse_mode="Markdown"
                )
                return
        
        # Проверяем, не была ли отменена загрузка
        if download_key not in active_downloads or active_downloads[download_key]['status'] == 'cancelled':
            return
        
        # Показываем статус "отправляет аудио..."
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="upload_audio"
        )
        
        # Обновляем статус на "отправка"
        await message.edit_text(
            STATUS_UPLOADING,
            parse_mode="Markdown"
        )
        
        # Подготавливаем метаданные
        metadata = format_audio_metadata(track_info)
        
        # Отправляем аудио файл
        audio_file = FSInputFile(file_path)
        await message.answer_audio(
            audio=audio_file,
            title=metadata['title'],
            performer=metadata['performer'],
            duration=metadata.get('duration', 0)
        )
        
        # Показываем статус завершения
        await message.edit_text(
            STATUS_COMPLETE,
            parse_mode="Markdown"
        )
        
        logger.info(f"Successfully sent track to user {active_downloads[download_key]['user_id']}: {title}")
        
    except Exception as e:
        logger.error(f"Download and send error: {e}")
        await message.edit_text(
            format_error_message("download_failed", str(e)),
            reply_markup=get_error_keyboard(),
            parse_mode="Markdown"
        )
    
    finally:
        # Очищаем временный файл
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up file {file_path}: {e}")
        
        # Удаляем из активных загрузок
        if download_key in active_downloads:
            del active_downloads[download_key]

def get_download_service(source: str):
    """Возвращает сервис для скачивания из указанного источника"""
    if source in ["youtube", "youtube_music"]:
        return YouTubeService()
    elif source == "soundcloud":
        return SoundCloudService()
    elif source == "vk_music":
        from services.vk_service import VKMusicService
        service = VKMusicService()

        if not service.is_authenticated:
            logger.error(f"VK Music not authenticated: {service.auth_error_message}")
            return None

        return service
    elif source == "yandex_music":
        # TODO: Реализовать Yandex Music сервис
        return None
    else:
        return None

# Очистка активных загрузок (вызывается периодически)
async def cleanup_active_downloads():
    """Очищает зависшие загрузки"""
    import time
    current_time = time.time()
    
    keys_to_remove = []
    for key, download_info in active_downloads.items():
        # Удаляем загрузки старше 10 минут
        if current_time - download_info.get('start_time', current_time) > 600:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del active_downloads[key]
    
    if keys_to_remove:
        logger.info(f"Cleaned up {len(keys_to_remove)} stale downloads")
