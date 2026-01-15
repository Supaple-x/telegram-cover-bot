import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from vkpymusic import Service

from config import VK_TOKEN, VK_LOGIN, VK_PASSWORD

logger = logging.getLogger(__name__)

# Kate Mobile User-Agent для VK API
KATE_MOBILE_USER_AGENT = 'KateMobileAndroid/56 lite-460 (Android 4.4.2; SDK 19; x86; unknown Android SDK built for x86; en)'

class VKMusicService:
    def __init__(self):
        """Инициализация VK Music через vkpymusic с токеном"""
        self.service = None
        self.is_authenticated = False
        self.auth_error_message = None

        try:
            if VK_TOKEN:
                logger.info("Initializing VK Music with token via vkpymusic")
                self.service = Service(KATE_MOBILE_USER_AGENT, VK_TOKEN)
                self.is_authenticated = True
                logger.info("VK Music service initialized successfully with vkpymusic")
            else:
                logger.error("VK_TOKEN not set in environment")
                self.auth_error_message = "VK_TOKEN not configured"

        except Exception as e:
            logger.error(f"VK Music initialization error: {e}", exc_info=True)
            self.auth_error_message = f"Initialization error: {e}"

    async def search(self, query: str, max_results: int = 50) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Поиск треков в VK Music через vkpymusic

        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов

        Returns:
            Кортеж (список треков, сообщение об ошибке или None)
            Формат трека:
            [{
                'id': str,
                'title': str,
                'artist': str,
                'duration': int,
                'quality': str,
                'source': str,
                'url': str,
                'owner_id': int,
                'track_id': int
            }]
        """
        if not self.is_authenticated:
            error_msg = f"Auth: {self.auth_error_message}\nToken: {VK_TOKEN[:20] if VK_TOKEN else 'NOT_SET'}..."
            logger.error(f"VK не авторизован: {self.auth_error_message}")
            return [], error_msg

        try:
            logger.info(f"Searching VK Music for: {query}")

            # Выполняем поиск в отдельном потоке (vkpymusic синхронный)
            tracks = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._search_sync(query, max_results)
            )

            result_count = len(tracks)
            logger.info(f"VK Music search for '{query}' returned {result_count} results")

            # Если треков нет, возвращаем детальную информацию
            if result_count == 0:
                error_details = f"Query: '{query}'\nMax results: {max_results}\nReturned: 0 tracks\nLibrary: vkpymusic v3.5.1\nUser-Agent: Kate Mobile"
                return [], error_details

            return tracks, None

        except Exception as e:
            import traceback
            error_msg = f"Error: {type(e).__name__}\nMessage: {str(e)}\nQuery: '{query}'\nLibrary: vkpymusic\nTraceback:\n{traceback.format_exc()}"
            logger.error(f"Ошибка поиска VK Music: {e}", exc_info=True)
            return [], error_msg

    def _search_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Синхронный поиск (вызывается через executor)"""
        try:
            logger.debug(f"Calling vkpymusic search_songs_by_text with query='{query}', count={max_results}")

            # Поиск через vkpymusic
            songs = self.service.search_songs_by_text(query, max_results)
            logger.info(f"vkpymusic returned {len(songs)} songs")

            tracks = []
            seen_ids = set()  # Отслеживаем уникальные ID треков

            for i, song in enumerate(songs):
                try:
                    track = self._format_vk_track(song, i)
                    if track:
                        track_id = track.get('id')
                        # Пропускаем дубликаты
                        if track_id not in seen_ids:
                            seen_ids.add(track_id)
                            tracks.append(track)
                            logger.debug(f"Formatted track {i}: {track.get('artist')} - {track.get('title')}")
                        else:
                            logger.debug(f"Skipping duplicate track {i}: {track_id}")
                except Exception as track_error:
                    logger.warning(f"Failed to format track {i}: {track_error}", exc_info=True)
                    continue

            logger.info(f"Successfully formatted {len(tracks)} unique tracks (filtered from {len(songs)} total)")
            return tracks

        except Exception as e:
            logger.error(f"VK _search_sync error: {e}", exc_info=True)
            return []

    def _format_vk_track(self, song, index: int) -> Optional[Dict[str, Any]]:
        """
        Форматирует результат vkpymusic в единый формат

        Args:
            song: Объект Song от vkpymusic
            index: Индекс трека в результатах

        Returns:
            Отформатированный словарь с данными трека
        """
        try:
            # Проверяем наличие URL
            if not song.url:
                logger.warning(f"Track {index} has no URL, skipping")
                return None

            # Создаем уникальный ID из owner_id и track_id
            unique_id = f"{song.owner_id}_{song.track_id}"

            return {
                'id': unique_id,
                'title': song.title or 'Unknown Title',
                'artist': song.artist or 'Unknown Artist',
                'duration': song.duration or 0,
                'quality': 'high',
                'source': 'vk_music',
                'url': song.url,
                'owner_id': song.owner_id,
                'track_id': song.track_id
            }

        except Exception as e:
            logger.error(f"Error formatting track {index}: {e}", exc_info=True)
            return None

    async def download(self, track_info: Dict[str, Any], output_path: str) -> bool:
        """
        Скачивает трек из VK Music

        Args:
            track_info: Информация о треке (должна содержать 'url')
            output_path: Путь для сохранения файла

        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            track_url = track_info.get('url')
            if not track_url:
                logger.error("No URL provided for VK download")
                return False

            # Скачиваем файл через aiohttp
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(track_url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download: HTTP {response.status}")
                        return False

                    # Скачиваем и записываем файл
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)

                    logger.info(f"Successfully downloaded VK track to {output_path}")
                    return True

        except asyncio.TimeoutError:
            logger.error(f"Download timeout for {track_url}")
            return False
        except Exception as e:
            logger.error(f"VK download error: {e}", exc_info=True)
            return False

    async def close(self):
        """Очистка ресурсов"""
        # vkpymusic не требует явного закрытия соединений
        pass
