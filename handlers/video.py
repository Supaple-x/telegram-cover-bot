from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Filter
import logging
import os
import asyncio
import time
import re
from typing import Dict, Any

from config import DOWNLOADS_DIR, MAX_FILE_SIZE_MB
from services.youtube_video_service import YouTubeVideoService, VIDEO_QUALITIES

router = Router()
logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """Экранирует специальные символы HTML"""
    if not text:
        return ""
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# Кэш информации о видео
video_cache: Dict[str, Dict[str, Any]] = {}

# Активные загрузки видео: download_key -> {"cancelled": False}
active_video_downloads: Dict[str, Dict[str, Any]] = {}

# Минимальный интервал между обновлениями прогресса (секунды)
PROGRESS_UPDATE_INTERVAL = 3


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

        # Экранируем спецсимволы в названии и канале
        safe_title = escape_html(video_info['title'])
        safe_channel = escape_html(video_info['channel'])

        info_text = (
            f"🎬 <b>{safe_title}</b>\n\n"
            f"📺 Канал: {safe_channel}\n"
            f"⏱ Длительность: {duration_str}\n"
            f"👁 Просмотры: {views_str}\n\n"
            f"Выберите качество для скачивания:"
        )

        # Создаем клавиатуру с качествами
        keyboard = create_quality_keyboard(video_info['id'], video_info['available_qualities'], video_info.get('quality_sizes'))

        await status_msg.edit_text(info_text, reply_markup=keyboard, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error handling YouTube URL: {e}", exc_info=True)
        error_text = escape_html(str(e)[:300])
        await status_msg.edit_text(
            f"❌ Произошла ошибка при обработке видео.\n\n"
            f"<code>{error_text}</code>",
            parse_mode="HTML"
        )


def create_quality_keyboard(video_id: str, available_qualities: list, quality_sizes: Dict[str, int] = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру выбора качества с примерными размерами"""
    buttons = []

    for quality in available_qualities:
        if quality in VIDEO_QUALITIES:
            label = VIDEO_QUALITIES[quality]['label']
            # Add estimated size
            size = (quality_sizes or {}).get(quality, 0)
            if size > 0:
                label += f" ~{format_size(size)}"
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

        active_video_downloads[download_key] = {"cancelled": False}

        # Показываем статус
        safe_title = escape_html(video_info['title'])
        await callback.message.edit_text(
            f"⏳ <b>Скачиваю видео...</b>\n\n"
            f"🎬 {safe_title}\n"
            f"📊 Качество: {VIDEO_QUALITIES.get(quality, {}).get('label', quality)}\n\n"
            f"Это может занять некоторое время...",
            parse_mode="HTML"
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


@router.callback_query(F.data.startswith("video_stop::"))
async def handle_cancel_download(callback: CallbackQuery):
    """Обработчик кнопки отмены загрузки"""
    download_key = callback.data.replace("video_stop::", "")

    if download_key in active_video_downloads:
        active_video_downloads[download_key]["cancelled"] = True
        await callback.answer("⏹ Отменяю загрузку...")
    else:
        await callback.answer("Загрузка уже завершена")


def format_size(bytes_count: int) -> str:
    """Форматирует размер в человекочитаемый формат"""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    elif bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"


def format_speed(bytes_per_sec: float) -> str:
    """Форматирует скорость загрузки"""
    if not bytes_per_sec:
        return "..."
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"


def format_eta(seconds: int) -> str:
    """Форматирует оставшееся время"""
    if not seconds or seconds < 0:
        return "..."
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


async def download_and_send_video(message, video_info: Dict[str, Any], quality: str, download_key: str):
    """Скачивает и отправляет видео"""
    file_path = None
    last_update_time = [0]  # Используем список для изменения из вложенной функции
    loop = asyncio.get_event_loop()

    async def update_progress_message(progress_info: Dict[str, Any]):
        """Обновляет сообщение с прогрессом"""
        current_time = time.time()

        # Ограничиваем частоту обновлений
        if current_time - last_update_time[0] < PROGRESS_UPDATE_INTERVAL:
            return

        last_update_time[0] = current_time

        if progress_info.get('status') == 'downloading':
            downloaded = progress_info.get('downloaded_bytes', 0)
            total = progress_info.get('total_bytes', 0)
            speed = progress_info.get('speed', 0)
            eta = progress_info.get('eta', 0)

            # Формируем прогресс-бар
            if total > 0:
                percent = (downloaded / total) * 100
                filled = int(percent / 5)
                bar = '█' * filled + '░' * (20 - filled)
                size_info = f"{format_size(downloaded)} / {format_size(total)}"
            else:
                bar = '░' * 20
                size_info = format_size(downloaded)
                percent = 0

            safe_title = escape_html(video_info['title'][:50])
            cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏹ Отменить загрузку", callback_data=f"video_stop::{download_key}")]
            ])
            progress_text = (
                f"⏳ <b>Скачиваю видео...</b>\n\n"
                f"🎬 {safe_title}...\n"
                f"📊 Качество: {VIDEO_QUALITIES.get(quality, {}).get('label', quality)}\n\n"
                f"<code>[{bar}] {percent:.1f}%</code>\n"
                f"📥 {size_info}\n"
                f"⚡ Скорость: {format_speed(speed)}\n"
                f"⏱ Осталось: {format_eta(eta)}"
            )

            try:
                await message.edit_text(progress_text, parse_mode="HTML", reply_markup=cancel_kb)
            except Exception as e:
                # Игнорируем ошибки обновления (например, message not modified)
                logger.debug(f"Progress update skipped: {e}")

    def progress_callback(progress_info: Dict[str, Any]):
        """Callback для yt-dlp, вызывается из синхронного кода"""
        if progress_info.get('status') == 'downloading':
            # Планируем обновление в asyncio loop
            asyncio.run_coroutine_threadsafe(
                update_progress_message(progress_info),
                loop
            )

    try:
        service = YouTubeVideoService()

        # Показываем статус "записывает видео..."
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="record_video"
        )

        # Функция проверки отмены
        def is_cancelled():
            state = active_video_downloads.get(download_key)
            return state is not None and state.get("cancelled", False)

        # Скачиваем видео с отображением прогресса
        file_path, download_error = await service.download(
            video_info['url'],
            quality,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled
        )

        if not file_path or not os.path.exists(file_path):
            if download_error == "CANCELLED":
                await message.edit_text("⏹ <b>Загрузка отменена</b>", parse_mode="HTML")
                return
            error_detail = escape_html(download_error or "Неизвестная ошибка")
            await message.edit_text(
                f"❌ <b>Ошибка скачивания</b>\n\n"
                f"<code>{error_detail}</code>\n\n"
                f"Попробуйте другое качество или повторите позже.",
                parse_mode="HTML"
            )
            return

        # Проверяем размер файла
        file_size = os.path.getsize(file_path)
        file_size_mb = file_size / (1024 * 1024)

        if file_size_mb > MAX_FILE_SIZE_MB:
            await message.edit_text(
                f"❌ <b>Файл слишком большой</b>\n\n"
                f"Размер: {file_size_mb:.1f} MB\n"
                f"Лимит: {MAX_FILE_SIZE_MB} MB\n\n"
                f"Попробуйте выбрать более низкое качество.",
                parse_mode="HTML"
            )
            return

        # Обновляем статус
        safe_title = escape_html(video_info['title'])
        await message.edit_text(
            f"📤 <b>Отправляю видео...</b>\n\n"
            f"🎬 {safe_title}\n"
            f"📁 Размер: {file_size_mb:.1f} MB",
            parse_mode="HTML"
        )

        # Показываем статус отправки
        is_audio_only = VIDEO_QUALITIES.get(quality, {}).get('audio_only', False)
        await message.bot.send_chat_action(
            chat_id=message.chat.id,
            action="upload_document" if is_audio_only else "upload_video"
        )

        # Отправляем файл
        is_audio_only = VIDEO_QUALITIES.get(quality, {}).get('audio_only', False)
        send_file = FSInputFile(file_path)
        caption = f"🎬 {safe_title}\n📺 {escape_html(video_info['channel'])}"

        if is_audio_only:
            await message.answer_audio(
                audio=send_file,
                caption=caption,
                parse_mode="HTML",
                duration=int(video_info.get('duration', 0)),
                title=video_info['title'],
                performer=video_info.get('channel', ''),
            )
        else:
            await message.answer_video(
                video=send_file,
                caption=caption,
                parse_mode="HTML",
                duration=int(video_info.get('duration', 0)),
                supports_streaming=True
            )

        # Показываем успех
        fmt_label = VIDEO_QUALITIES.get(quality, {}).get('label', quality)
        await message.edit_text(
            f"✅ <b>Готово!</b>\n\n"
            f"🎬 {safe_title}\n"
            f"📊 {'Формат' if is_audio_only else 'Качество'}: {fmt_label}\n"
            f"📁 Размер: {file_size_mb:.1f} MB",
            parse_mode="HTML"
        )

        logger.info(f"Successfully sent video: {video_info['title']} ({file_size_mb:.1f} MB)")

    except Exception as e:
        logger.error(f"Error downloading/sending video: {e}", exc_info=True)
        error_text = escape_html(str(e)[:200])
        await message.edit_text(
            f"❌ <b>Ошибка</b>\n\n"
            f"Не удалось отправить видео:\n<code>{error_text}</code>",
            parse_mode="HTML"
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
