from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Filter
import logging
import os
import asyncio
from typing import Dict, Any

from config import DOWNLOADS_DIR, MAX_FILE_SIZE_MB
from services.youtube_video_service import YouTubeVideoService, VIDEO_QUALITIES

router = Router()
logger = logging.getLogger(__name__)

# Кэш информации о видео
video_cache: Dict[str, Dict[str, Any]] = {}

# Активные загрузки видео
active_video_downloads: Dict[str, bool] = {}


class YouTubeURLFilter(Filter):
    """Фильтр для YouTube ссылок"""

    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return False
        service = YouTubeVideoService()
        return service.is_youtube_url(message.text)


@router.message(YouTubeURLFilter())
async def handle_youtube_url(message: Message):
    """Обработчик YouTube ссылок"""
    url = message.text.strip()
    user_id = message.from_user.id

    logger.info(f"User {user_id} sent YouTube URL: {url}")

    # Показываем статус загрузки
    status_msg = await message.answer("🔍 Получаю информацию о видео...")

    try:
        service = YouTubeVideoService()

        # Получаем информацию о видео
        video_info = await service.get_video_info(url)

        if not video_info:
            await status_msg.edit_text(
                "❌ Не удалось получить информацию о видео.\n"
                "Проверьте ссылку или попробуйте позже."
            )
            return

        # Сохраняем в кэш
        cache_key = f"{user_id}_{video_info['id']}"
        video_cache[cache_key] = video_info

        # Формируем сообщение с информацией
        duration_str = service.format_duration(video_info['duration'])
        views_str = service.format_views(video_info['view_count'])

        info_text = (
            f"🎬 **{video_info['title']}**\n\n"
            f"📺 Канал: {video_info['channel']}\n"
            f"⏱ Длительность: {duration_str}\n"
            f"👁 Просмотры: {views_str}\n\n"
            f"Выберите качество для скачивания:"
        )

        # Создаем клавиатуру с качествами
        keyboard = create_quality_keyboard(video_info['id'], video_info['available_qualities'])

        await status_msg.edit_text(info_text, reply_markup=keyboard, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error handling YouTube URL: {e}", exc_info=True)
        await status_msg.edit_text(
            f"❌ Произошла ошибка при обработке видео.\n"
            f"Попробуйте позже."
        )


def create_quality_keyboard(video_id: str, available_qualities: list) -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора качества"""
    buttons = []

    for quality in available_qualities:
        if quality in VIDEO_QUALITIES:
            label = VIDEO_QUALITIES[quality]['label']
            callback_data = f"video::{quality}::{video_id}"
            buttons.append([InlineKeyboardButton(text=f"📹 {label}", callback_data=callback_data)])

    # Кнопка отмены
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="video::cancel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("video::"))
async def handle_quality_selection(callback: CallbackQuery):
    """Обработчик выбора качества видео"""
    try:
        parts = callback.data.split("::")

        if len(parts) < 2:
            await callback.answer("❌ Ошибка")
            return

        action = parts[1]

        if action == "cancel":
            await callback.message.edit_text("❌ Загрузка отменена")
            await callback.answer()
            return

        quality = parts[1]
        video_id = parts[2] if len(parts) > 2 else None

        if not video_id:
            await callback.answer("❌ Видео не найдено")
            return

        user_id = callback.from_user.id
        cache_key = f"{user_id}_{video_id}"

        # Получаем информацию из кэша
        video_info = video_cache.get(cache_key)
        if not video_info:
            await callback.message.edit_text(
                "❌ Информация о видео устарела.\n"
                "Отправьте ссылку заново."
            )
            await callback.answer()
            return

        # Проверяем, не идет ли уже загрузка
        download_key = f"{user_id}_{video_id}"
        if download_key in active_video_downloads:
            await callback.answer("⏳ Загрузка уже выполняется...")
            return

        active_video_downloads[download_key] = True

        # Показываем статус
        await callback.message.edit_text(
            f"⏳ **Скачиваю видео...**\n\n"
            f"🎬 {video_info['title']}\n"
            f"📊 Качество: {VIDEO_QUALITIES.get(quality, {}).get('label', quality)}\n\n"
            f"Это может занять некоторое время...",
            parse_mode="Markdown"
        )
        await callback.answer()

        # Запускаем загрузку в фоне
        asyncio.create_task(
            download_and_send_video(callback.message, video_info, quality, download_key)
        )

    except Exception as e:
        logger.error(f"Error in quality selection: {e}", exc_info=True)
        await callback.message.edit_text("❌ Произошла ошибка")
        await callback.answer()


async def download_and_send_video(message, video_info: Dict[str, Any], quality: str, download_key: str):
    """Скачивает и отправляет видео"""
    file_path = None
    try:
        service = YouTubeVideoService()

        # Показываем статус "записывает видео..."
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="record_video"
        )

        # Скачиваем видео
        file_path = await service.download(video_info['url'], quality)

        if not file_path or not os.path.exists(file_path):
            await message.edit_text(
                "❌ **Ошибка скачивания**\n\n"
                "Не удалось скачать видео. Попробуйте другое качество или повторите позже.",
                parse_mode="Markdown"
            )
            return

        # Проверяем размер файла
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)

        if file_size_mb > MAX_FILE_SIZE_MB:
            await message.edit_text(
                f"❌ **Файл слишком большой**\n\n"
                f"Размер: {file_size_mb:.1f} MB\n"
                f"Лимит: {MAX_FILE_SIZE_MB} MB\n\n"
                f"Попробуйте выбрать более низкое качество.",
                parse_mode="Markdown"
            )
            return

        # Обновляем статус
        await message.edit_text(
            f"📤 **Отправляю видео...**\n\n"
            f"🎬 {video_info['title']}\n"
            f"📁 Размер: {file_size_mb:.1f} MB",
            parse_mode="Markdown"
        )

        # Показываем статус "отправляет видео..."
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="upload_video"
        )

        # Отправляем видео
        video_file = FSInputFile(file_path)
        await message.answer_video(
            video=video_file,
            caption=f"🎬 {video_info['title']}\n📺 {video_info['channel']}",
            duration=int(video_info.get('duration', 0)),
            supports_streaming=True
        )

        # Показываем успех
        await message.edit_text(
            f"✅ **Готово!**\n\n"
            f"🎬 {video_info['title']}\n"
            f"📊 Качество: {VIDEO_QUALITIES.get(quality, {}).get('label', quality)}\n"
            f"📁 Размер: {file_size_mb:.1f} MB",
            parse_mode="Markdown"
        )

        logger.info(f"Successfully sent video: {video_info['title']} ({file_size_mb:.1f} MB)")

    except Exception as e:
        logger.error(f"Error downloading/sending video: {e}", exc_info=True)
        await message.edit_text(
            f"❌ **Ошибка**\n\n"
            f"Не удалось отправить видео: {str(e)[:100]}",
            parse_mode="Markdown"
        )

    finally:
        # Очищаем временный файл
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up video file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up video file: {e}")

        # Удаляем из активных загрузок
        if download_key in active_video_downloads:
            del active_video_downloads[download_key]
