import asyncio
import logging
import os
import re
from typing import Dict, Any, Optional, List
import yt_dlp

from config import DOWNLOADS_DIR

logger = logging.getLogger(__name__)

# Паттерны для YouTube ссылок
YOUTUBE_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
]

# Доступные качества видео
VIDEO_QUALITIES = {
    '360p': {'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]', 'label': '360p (SD)'},
    '480p': {'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]', 'label': '480p (SD)'},
    '720p': {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]', 'label': '720p (HD)'},
    '1080p': {'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 'label': '1080p (Full HD)'},
    'best': {'format': 'bestvideo+bestaudio/best', 'label': 'Best Quality'},
}


class YouTubeVideoService:
    def __init__(self):
        self.cookies_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'youtube_cookies.txt')
        if not os.path.exists(self.cookies_file):
            self.cookies_file = None

    def extract_video_id(self, url: str) -> Optional[str]:
        """Извлекает ID видео из YouTube URL"""
        for pattern in YOUTUBE_URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def is_youtube_url(self, text: str) -> bool:
        """Проверяет, является ли текст YouTube ссылкой"""
        return self.extract_video_id(text) is not None

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Получает информацию о видео"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            if self.cookies_file:
                ydl_opts['cookiefile'] = self.cookies_file

            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await asyncio.get_event_loop().run_in_executor(None, _extract)

            if not info:
                return None

            # Определяем доступные качества
            available_qualities = self._get_available_qualities(info)

            return {
                'id': info.get('id'),
                'title': info.get('title', 'Unknown'),
                'channel': info.get('uploader', info.get('channel', 'Unknown')),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail'),
                'url': url,
                'available_qualities': available_qualities,
                'is_short': '/shorts/' in url or info.get('duration', 0) <= 60,
            }

        except Exception as e:
            logger.error(f"Error getting video info: {e}", exc_info=True)
            return None

    def _get_available_qualities(self, info: Dict) -> List[str]:
        """Определяет доступные качества для видео"""
        formats = info.get('formats', [])
        heights = set()

        for fmt in formats:
            height = fmt.get('height')
            if height:
                heights.add(height)

        available = []
        for quality in ['360p', '480p', '720p', '1080p']:
            target_height = int(quality[:-1])
            # Качество доступно, если есть формат с такой или большей высотой
            if any(h >= target_height for h in heights):
                available.append(quality)

        # Всегда добавляем "best"
        available.append('best')

        return available

    async def download(self, url: str, quality: str, output_dir: str = None) -> Optional[str]:
        """
        Скачивает видео с YouTube

        Args:
            url: YouTube URL
            quality: Качество видео (360p, 480p, 720p, 1080p, best)
            output_dir: Директория для сохранения

        Returns:
            Путь к скачанному файлу или None при ошибке
        """
        try:
            if output_dir is None:
                output_dir = DOWNLOADS_DIR

            os.makedirs(output_dir, exist_ok=True)

            # Получаем формат для выбранного качества
            format_spec = VIDEO_QUALITIES.get(quality, VIDEO_QUALITIES['best'])['format']

            output_template = os.path.join(output_dir, '%(title)s.%(ext)s')

            ydl_opts = {
                'format': format_spec,
                'outtmpl': output_template,
                'merge_output_format': 'mp4',
                'quiet': False,
                'no_warnings': False,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                # Retry настройки
                'retries': 10,
                'fragment_retries': 10,
                'socket_timeout': 60,
            }

            if self.cookies_file:
                ydl_opts['cookiefile'] = self.cookies_file
                logger.info(f"Using cookies file: {self.cookies_file}")

            downloaded_file = None

            def _download():
                nonlocal downloaded_file
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        # Получаем путь к скачанному файлу
                        if 'requested_downloads' in info:
                            downloaded_file = info['requested_downloads'][0]['filepath']
                        else:
                            # Пробуем построить путь
                            ext = info.get('ext', 'mp4')
                            title = info.get('title', 'video')
                            # Очищаем название от недопустимых символов
                            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
                            downloaded_file = os.path.join(output_dir, f"{safe_title}.{ext}")

            await asyncio.get_event_loop().run_in_executor(None, _download)

            # Проверяем что файл существует
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                logger.info(f"Downloaded video: {downloaded_file} ({file_size / 1024 / 1024:.2f} MB)")
                return downloaded_file

            # Ищем скачанный файл в директории
            for file in os.listdir(output_dir):
                if file.endswith('.mp4'):
                    full_path = os.path.join(output_dir, file)
                    if os.path.getmtime(full_path) > asyncio.get_event_loop().time() - 60:
                        logger.info(f"Found downloaded video: {full_path}")
                        return full_path

            logger.error("Downloaded file not found")
            return None

        except Exception as e:
            logger.error(f"Error downloading video: {e}", exc_info=True)
            return None

    def format_duration(self, seconds: int) -> str:
        """Форматирует длительность в читаемый формат"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}:{secs:02d}"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            secs = seconds % 60
            return f"{hours}:{minutes:02d}:{secs:02d}"

    def format_views(self, count: int) -> str:
        """Форматирует количество просмотров"""
        if count < 1000:
            return str(count)
        elif count < 1000000:
            return f"{count / 1000:.1f}K"
        else:
            return f"{count / 1000000:.1f}M"
