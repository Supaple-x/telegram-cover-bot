import asyncio
import logging
import os
import re
from typing import Dict, Any, Optional, List, Callable, Tuple
import yt_dlp

from config import DOWNLOADS_DIR, VK_LOGIN, VK_PASSWORD

logger = logging.getLogger(__name__)

# WARP прокси для обхода блокировок YouTube
WARP_PROXY = 'socks5h://127.0.0.1:40000'

# Паттерны для YouTube ссылок
YOUTUBE_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
]

# Паттерны для Rutube ссылок
RUTUBE_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?rutube\.ru/video/([a-f0-9]+)',
    r'(?:https?://)?(?:www\.)?rutube\.ru/shorts/([a-f0-9]+)',
    r'(?:https?://)?(?:www\.)?rutube\.ru/play/embed/([a-f0-9]+)',
]

# Паттерны для VK Video ссылок
VK_VIDEO_URL_PATTERNS = [
    r'(?:https?://)?(?:www\.)?vkvideo\.ru/video(-?\d+_\d+)',
    r'(?:https?://)?(?:www\.)?vkvideo\.ru/clip(-?\d+_\d+)',
    r'(?:https?://)?(?:www\.)?vk\.com/video(-?\d+_\d+)',
    r'(?:https?://)?(?:www\.)?vk\.com/clip(-?\d+_\d+)',
    r'(?:https?://)?(?:www\.)?vk\.com/video\?z=video(-?\d+_\d+)',
]

# Доступные качества видео
VIDEO_QUALITIES = {
    'audio': {'format': 'bestaudio/best', 'label': '🎵 Только аудио (MP3)', 'audio_only': True},
    '360p': {'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]', 'label': '360p (SD)'},
    '480p': {'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]', 'label': '480p (SD)'},
    '720p': {'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]', 'label': '720p (HD)'},
    '1080p': {'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]', 'label': '1080p (Full HD)'},
    'best': {'format': 'bestvideo+bestaudio/best', 'label': 'Best Quality'},
}


class YouTubeVideoService:
    def __init__(self):
        self.cookies_file = None

        # Проверяем наличие файла cookies
        cookies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'youtube_cookies.txt')
        if os.path.exists(cookies_path):
            self.cookies_file = cookies_path
            logger.info(f"YouTube Video: cookies file found: {cookies_path}")
        else:
            logger.warning(f"YouTube Video: cookies file not found: {cookies_path}")

    def extract_video_id(self, url: str) -> Optional[str]:
        """Извлекает ID видео из YouTube URL"""
        for pattern in YOUTUBE_URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def extract_rutube_id(self, url: str) -> Optional[str]:
        """Извлекает ID видео из Rutube URL"""
        for pattern in RUTUBE_URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def extract_vk_video_id(self, url: str) -> Optional[str]:
        """Извлекает ID видео из VK Video URL"""
        for pattern in VK_VIDEO_URL_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def is_youtube_url(self, text: str) -> bool:
        """Проверяет, является ли текст YouTube ссылкой"""
        return self.extract_video_id(text) is not None

    def is_rutube_url(self, text: str) -> bool:
        """Проверяет, является ли текст Rutube ссылкой"""
        return self.extract_rutube_id(text) is not None

    def is_vk_video_url(self, text: str) -> bool:
        """Проверяет, является ли текст VK Video ссылкой"""
        return self.extract_vk_video_id(text) is not None

    def is_supported_video_url(self, text: str) -> bool:
        """Проверяет, является ли текст поддерживаемой видео-ссылкой"""
        return self.is_youtube_url(text) or self.is_rutube_url(text) or self.is_vk_video_url(text)

    def detect_platform(self, url: str) -> Optional[str]:
        """Определяет платформу по URL"""
        if self.is_youtube_url(url):
            return 'youtube'
        elif self.is_rutube_url(url):
            return 'rutube'
        elif self.is_vk_video_url(url):
            return 'vkvideo'
        return None

    async def get_video_info(self, url: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Получает информацию о видео

        Returns:
            Tuple[video_info, error_message] - информация о видео или None, сообщение об ошибке или None
        """
        try:
            platform = self.detect_platform(url)

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                # Обход блокировок
                'nocheckcertificate': True,
                'geo_bypass': True,
                'age_limit': None,
                # Retry настройки
                'extractor_retries': 3,
                'socket_timeout': 30,
            }

            # WARP прокси и cookies только для YouTube
            if platform == 'youtube':
                ydl_opts['proxy'] = WARP_PROXY
                if self.cookies_file:
                    ydl_opts['cookiefile'] = self.cookies_file
                    logger.info(f"Using cookies for video info: {self.cookies_file}")

            def _extract(opts):
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)

            async def _extract_with_fallback(opts: dict) -> dict:
                """Extract info, retrying with format='best' if format unavailable."""
                try:
                    return await asyncio.get_event_loop().run_in_executor(None, lambda: _extract(opts))
                except Exception as e:
                    if 'Requested format is not available' in str(e):
                        logger.warning("Format unavailable, retrying with format='best'")
                        fallback = {**opts, 'format': 'best'}
                        return await asyncio.get_event_loop().run_in_executor(None, lambda: _extract(fallback))
                    raise

            info = None
            if platform == 'vkvideo':
                # Try without auth first to avoid login rate limits for public videos
                try:
                    info = await _extract_with_fallback(ydl_opts)
                except Exception as e:
                    err = str(e)
                    if '429' in err:
                        logger.warning("VK 429 without auth, waiting 5s and retrying...")
                        await asyncio.sleep(5)
                        info = await _extract_with_fallback(ydl_opts)
                    elif VK_LOGIN and VK_PASSWORD and ('login' in err.lower() or 'sign in' in err.lower() or 'followers' in err.lower() or '403' in err):
                        logger.info("VK video requires auth, retrying with credentials...")
                        auth_opts = {**ydl_opts, 'username': VK_LOGIN, 'password': VK_PASSWORD}
                        info = await _extract_with_fallback(auth_opts)
                    else:
                        raise
            else:
                info = await _extract_with_fallback(ydl_opts)

            if not info:
                return None, "Не удалось получить информацию о видео"

            # Определяем доступные качества
            available_qualities, quality_sizes = self._get_available_qualities(info)

            return {
                'id': info.get('id'),
                'title': info.get('title', 'Unknown'),
                'channel': info.get('uploader', info.get('channel', 'Unknown')),
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail'),
                'url': url,
                'platform': platform,
                'available_qualities': available_qualities,
                'quality_sizes': quality_sizes,
                'is_short': '/shorts/' in url or info.get('duration', 0) <= 60,
            }, None

        except Exception as e:
            logger.error(f"Error getting video info: {e}", exc_info=True)
            error_msg = str(e)
            if "reloaded" in error_msg.lower():
                error_msg = "NEEDS_RELOAD"
            elif "429" in error_msg:
                error_msg = "HTTP 429: Слишком много запросов. Попробуйте через минуту"
            elif "403" in error_msg:
                error_msg = "HTTP 403: Доступ запрещён (возможно, нужны свежие cookies)"
            elif "404" in error_msg:
                error_msg = "HTTP 404: Видео не найдено"
            elif "Sign in" in error_msg or "age_limit" in error_msg.lower() or "age restrict" in error_msg.lower():
                error_msg = "Требуется авторизация (возрастное ограничение)"
            elif "Private video" in error_msg:
                error_msg = "Приватное видео"
            elif "only available to followers" in error_msg.lower():
                error_msg = "Видео доступно только подписчикам"
            elif "unavailable" in error_msg.lower():
                error_msg = "Видео недоступно"
            return None, error_msg

    def _get_available_qualities(self, info: Dict) -> Tuple[List[str], Dict[str, int]]:
        """Определяет доступные качества и примерные размеры для видео"""
        formats = info.get('formats', [])
        heights = set()
        duration = info.get('duration', 0)

        # Collect best video+audio filesize per height
        video_sizes: Dict[int, int] = {}  # height -> best filesize
        best_audio_size = 0

        for fmt in formats:
            height = fmt.get('height')
            if height:
                heights.add(height)
                size = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                vcodec = fmt.get('vcodec', 'none')
                acodec = fmt.get('acodec', 'none')

                if vcodec != 'none' and acodec == 'none':
                    # Video-only stream
                    if height not in video_sizes or size > video_sizes[height]:
                        video_sizes[height] = size
                elif vcodec != 'none' and acodec != 'none':
                    # Combined stream
                    if height not in video_sizes or size > video_sizes[height]:
                        video_sizes[height] = size

            # Track best audio size
            if fmt.get('acodec', 'none') != 'none' and fmt.get('vcodec', 'none') == 'none':
                asize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
                if asize > best_audio_size:
                    best_audio_size = asize

        available = ['audio']  # Audio always available
        quality_sizes: Dict[str, int] = {}

        # Audio size
        if best_audio_size:
            quality_sizes['audio'] = best_audio_size
        elif duration > 0:
            quality_sizes['audio'] = int(192_000 * duration / 8)  # ~192kbps estimate

        for quality in ['360p', '480p', '720p', '1080p']:
            target_height = int(quality[:-1])
            if any(h >= target_height for h in heights):
                available.append(quality)
                # Find closest height >= target
                matching = [h for h in sorted(heights) if h >= target_height]
                if matching:
                    closest = matching[0]
                    vsize = video_sizes.get(closest, 0)
                    if vsize:
                        quality_sizes[quality] = vsize + best_audio_size
                    elif duration > 0:
                        # Rough estimate: bitrate * duration
                        bitrates = {'360p': 700_000, '480p': 1_200_000, '720p': 2_500_000, '1080p': 5_000_000}
                        quality_sizes[quality] = int(bitrates.get(quality, 1_000_000) * duration / 8)

        available.append('best')
        # Best quality = largest video + audio
        if video_sizes:
            quality_sizes['best'] = max(video_sizes.values()) + best_audio_size
        elif duration > 0:
            quality_sizes['best'] = int(5_000_000 * duration / 8)

        return available, quality_sizes

    async def download(
        self,
        url: str,
        quality: str,
        output_dir: str = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Скачивает видео (YouTube, Rutube, VK Video)

        Args:
            url: Video URL (YouTube, Rutube or VK Video)
            quality: Качество видео (360p, 480p, 720p, 1080p, best)
            output_dir: Директория для сохранения
            progress_callback: Функция обратного вызова для отображения прогресса
                              Получает словарь с ключами: downloaded_bytes, total_bytes, speed, eta

        Returns:
            Tuple[file_path, error_message] - путь к файлу или None, сообщение об ошибке или None
        """
        try:
            if output_dir is None:
                output_dir = DOWNLOADS_DIR

            os.makedirs(output_dir, exist_ok=True)

            # Получаем формат для выбранного качества
            format_spec = VIDEO_QUALITIES.get(quality, VIDEO_QUALITIES['best'])['format']

            output_template = os.path.join(output_dir, '%(title)s.%(ext)s')

            # Progress hook для yt-dlp
            def progress_hook(d):
                # Check if download was cancelled
                if is_cancelled and is_cancelled():
                    raise yt_dlp.utils.DownloadCancelled("Download cancelled by user")

                if d['status'] == 'downloading' and progress_callback:
                    progress_info = {
                        'status': 'downloading',
                        'downloaded_bytes': d.get('downloaded_bytes', 0),
                        'total_bytes': d.get('total_bytes') or d.get('total_bytes_estimate', 0),
                        'speed': d.get('speed', 0),
                        'eta': d.get('eta', 0),
                        'filename': d.get('filename', ''),
                    }
                    progress_callback(progress_info)
                elif d['status'] == 'finished' and progress_callback:
                    progress_callback({
                        'status': 'finished',
                        'filename': d.get('filename', ''),
                    })

            is_audio_only = VIDEO_QUALITIES.get(quality, {}).get('audio_only', False)

            if is_audio_only:
                postprocessors = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '320',
                }]
            else:
                postprocessors = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }]

            platform = self.detect_platform(url)

            ydl_opts = {
                'format': format_spec,
                'outtmpl': output_template,
                'merge_output_format': None if is_audio_only else 'mp4',
                'quiet': True,
                'no_warnings': True,
                'postprocessors': postprocessors,
                # Retry настройки
                'retries': 10,
                'fragment_retries': 10,
                'socket_timeout': 60,
                # Progress hook
                'progress_hooks': [progress_hook],
            }

            # WARP прокси и cookies только для YouTube
            if platform == 'youtube':
                ydl_opts['proxy'] = WARP_PROXY
                if self.cookies_file:
                    ydl_opts['cookiefile'] = self.cookies_file
                    logger.info(f"Using cookies file: {self.cookies_file}")

            downloaded_file = None

            def _download(opts=None):
                nonlocal downloaded_file
                with yt_dlp.YoutubeDL(opts or ydl_opts) as ydl:
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

            if platform == 'vkvideo':
                # Try without auth first to avoid login rate limits for public videos
                try:
                    await asyncio.get_event_loop().run_in_executor(None, lambda: _download(ydl_opts))
                except yt_dlp.utils.DownloadCancelled:
                    raise
                except Exception as e:
                    err = str(e)
                    if '429' in err:
                        logger.warning("VK download 429, waiting 5s and retrying...")
                        await asyncio.sleep(5)
                        await asyncio.get_event_loop().run_in_executor(None, lambda: _download(ydl_opts))
                    elif VK_LOGIN and VK_PASSWORD and ('login' in err.lower() or 'sign in' in err.lower() or 'followers' in err.lower() or '403' in err):
                        logger.info("VK download requires auth, retrying with credentials...")
                        auth_opts = {**ydl_opts, 'username': VK_LOGIN, 'password': VK_PASSWORD}
                        await asyncio.get_event_loop().run_in_executor(None, lambda: _download(auth_opts))
                    else:
                        raise
            else:
                await asyncio.get_event_loop().run_in_executor(None, lambda: _download(ydl_opts))

            # Проверяем что файл существует
            if downloaded_file and os.path.exists(downloaded_file):
                file_size = os.path.getsize(downloaded_file)
                logger.info(f"Downloaded video: {downloaded_file} ({file_size / 1024 / 1024:.2f} MB)")
                return downloaded_file, None

            # Ищем скачанный файл в директории
            search_ext = '.mp3' if is_audio_only else '.mp4'
            for file in os.listdir(output_dir):
                if file.endswith(search_ext):
                    full_path = os.path.join(output_dir, file)
                    if os.path.getmtime(full_path) > asyncio.get_event_loop().time() - 60:
                        logger.info(f"Found downloaded video: {full_path}")
                        return full_path, None

            logger.error("Downloaded file not found")
            return None, "Файл не найден после скачивания"

        except yt_dlp.utils.DownloadCancelled:
            logger.info(f"Download cancelled by user: {url}")
            return None, "CANCELLED"

        except Exception as e:
            logger.error(f"Error downloading video: {e}", exc_info=True)
            error_msg = str(e)
            # Извлекаем понятное сообщение об ошибке
            if "cancelled" in error_msg.lower():
                return None, "CANCELLED"
            elif "429" in error_msg:
                error_msg = "HTTP 429: Слишком много запросов. Попробуйте через минуту"
            elif "403" in error_msg:
                error_msg = "HTTP 403: Доступ запрещён (возможно, нужны свежие cookies)"
            elif "404" in error_msg:
                error_msg = "HTTP 404: Видео не найдено"
            elif "Sign in" in error_msg or "age_limit" in error_msg.lower() or "age restrict" in error_msg.lower():
                error_msg = "Требуется авторизация (возрастное ограничение)"
            elif "Private video" in error_msg:
                error_msg = "Приватное видео"
            elif "only available to followers" in error_msg.lower():
                error_msg = "Видео доступно только подписчикам"
            elif "unavailable" in error_msg.lower():
                error_msg = "Видео недоступно"
            return None, error_msg

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
