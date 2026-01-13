import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
import aiohttp
import vk_api
from vk_api.exceptions import AuthError, Captcha

from config import VK_TOKEN, VK_LOGIN, VK_PASSWORD

logger = logging.getLogger(__name__)

class VKMusicService:
    def __init__(self):
        """Инициализация VK API с токеном или логином/паролем"""
        self.vk_session = None
        self.vk = None  # VK API object for direct calls
        self.is_authenticated = False
        self.auth_error_message = None

        try:
            # Приоритет 1: Используем токен если доступен
            if VK_TOKEN:
                logger.info("Using VK token for authentication")
                self.vk_session = vk_api.VkApi(token=VK_TOKEN)
                self.vk = self.vk_session.get_api()
                self.is_authenticated = True
                logger.info("VK Music service initialized successfully with token")
                return

            # Приоритет 2: Используем логин/пароль
            if VK_LOGIN and VK_PASSWORD:
                logger.info("Using VK login/password for authentication")
                self.vk_session = vk_api.VkApi(
                    login=VK_LOGIN,
                    password=VK_PASSWORD,
                    auth_handler=self._auth_handler,
                    captcha_handler=self._captcha_handler
                )
                self.vk_session.auth()
                self.vk = self.vk_session.get_api()
                self.is_authenticated = True
                logger.info("VK Music service initialized successfully with login/password")
                return

            # Нет credentials
            logger.error("Neither VK_TOKEN nor VK_LOGIN/VK_PASSWORD are set")
            self.auth_error_message = "VK credentials not configured"

        except AuthError as e:
            logger.error(f"VK authentication failed: {e}")
            self.auth_error_message = f"Authentication failed: {e}"
        except Exception as e:
            logger.error(f"VK Music initialization error: {e}")
            self.auth_error_message = f"Initialization error: {e}"

    def _auth_handler(self):
        """
        Обработчик двухфакторной аутентификации.
        В production окружении код должен вводиться пользователем.
        """
        logger.warning("VK 2FA required but cannot be handled automatically")
        logger.warning("Please disable 2FA or implement interactive 2FA input")

        # Для автоматизированного окружения возвращаем пустой код
        # В реальности нужно реализовать интерактивный ввод
        key = input("Enter 2FA code from SMS: ")
        remember_device = True
        return key, remember_device

    def _captcha_handler(self, captcha):
        """
        Обработчик капчи.
        В production окружении капча должна решаться пользователем или сервисом.
        """
        logger.error(f"VK Captcha required: {captcha.get_url()}")
        logger.error("Captcha handling not implemented. Consider using anti-captcha service.")

        # Поднимаем исключение, чтобы прервать операцию
        raise Captcha(captcha.sid, captcha)

    async def search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Поиск треков в VK Music

        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов

        Returns:
            Список треков в формате:
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
            logger.error(f"VK Music search failed: {self.auth_error_message}")
            return []

        try:
            # Выполняем поиск в отдельном потоке (vk_api синхронный)
            tracks = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._search_sync(query, max_results)
            )

            logger.info(f"VK Music search for '{query}' returned {len(tracks)} results")
            return tracks

        except Captcha as e:
            logger.error(f"VK Music search blocked by captcha: {e}")
            return []
        except Exception as e:
            logger.error(f"VK Music search error: {e}")
            return []

    def _search_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Синхронный поиск (вызывается через executor)"""
        try:
            # Используем прямой API вызов для поиска
            # audio.search возвращает словарь с ключом 'items'
            response = self.vk.audio.search(
                q=query,
                count=min(max_results, 300),  # VK ограничивает до 300
                auto_complete=1
            )

            if not response or 'items' not in response:
                logger.warning(f"VK search returned no items for query: {query}")
                return []

            raw_results = response['items']
            logger.info(f"VK API returned {len(raw_results)} items for query: {query}")

            tracks = []
            for i, audio in enumerate(raw_results):
                # Пропускаем объекты, которые не являются треками
                if not isinstance(audio, dict):
                    logger.debug(f"Skipping non-dict object at index {i}")
                    continue

                try:
                    track = self._format_vk_track(audio, i)
                    if track:
                        tracks.append(track)
                except Exception as track_error:
                    logger.warning(f"Failed to format track at index {i}: {track_error}")
                    continue

            logger.info(f"Formatted {len(tracks)} tracks from VK search")
            return tracks
        except Exception as e:
            logger.error(f"VK _search_sync error: {e}", exc_info=True)
            return []

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

            # Проверяем, что URL все еще актуален
            # VK URLs действуют ограниченное время

            # Скачиваем файл через aiohttp
            success = await self._download_from_url(track_url, output_path)

            if success:
                logger.info(f"Successfully downloaded from VK: {track_info.get('title', 'Unknown')}")
                return True
            else:
                # Пробуем обновить URL и скачать заново
                logger.warning("Download failed, attempting to refresh URL...")
                fresh_url = await self._refresh_track_url(track_info)
                if fresh_url:
                    success = await self._download_from_url(fresh_url, output_path)
                    if success:
                        logger.info("Successfully downloaded after URL refresh")
                        return True

                logger.error(f"Failed to download from VK: {track_info.get('title', 'Unknown')}")
                return False

        except Exception as e:
            logger.error(f"VK download error for {track_info.get('title', 'Unknown')}: {e}")
            return False

    async def _download_from_url(self, url: str, output_path: str) -> bool:
        """
        Скачивает файл по URL асинхронно

        Args:
            url: Прямая ссылка на MP3 файл
            output_path: Путь для сохранения

        Returns:
            True если успешно
        """
        try:
            timeout = aiohttp.ClientTimeout(total=300)  # 5 минут

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download: HTTP {response.status}")
                        return False

                    # Скачиваем файл по частям
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)

            # Проверяем, что файл создан и не пустой
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            else:
                logger.error("Downloaded file is empty or doesn't exist")
                return False

        except asyncio.TimeoutError:
            logger.error("Download timeout")
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False

    async def _refresh_track_url(self, track_info: Dict[str, Any]) -> Optional[str]:
        """
        Обновляет URL трека если он истек

        Args:
            track_info: Информация о треке с owner_id и track_id

        Returns:
            Новый URL или None при ошибке
        """
        try:
            owner_id = track_info.get('owner_id')
            track_id = track_info.get('track_id')

            if not owner_id or not track_id:
                logger.error("Missing owner_id or track_id for URL refresh")
                return None

            # Получаем свежий URL через прямой API вызов
            audio_id = f"{owner_id}_{track_id}"
            fresh_audios = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.vk.audio.getById(audios=[audio_id])
            )

            if fresh_audios and len(fresh_audios) > 0:
                fresh_audio = fresh_audios[0]
                if fresh_audio.get('url'):
                    logger.info("Successfully refreshed VK track URL")
                    return fresh_audio.get('url')

            logger.error("Failed to get fresh URL from VK")
            return None

        except Exception as e:
            logger.error(f"Failed to refresh VK URL: {e}")
            return None

    def _format_vk_track(self, audio: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """
        Форматирует результат поиска VK в единый формат

        Args:
            audio: Словарь с данными трека от VK API
            index: Индекс трека в результатах

        Returns:
            Отформатированный словарь с данными трека
        """
        try:
            # Проверяем, что это трек, а не плейлист или другой объект
            if not isinstance(audio, dict):
                logger.debug(f"Skipping non-dict object at index {index}")
                return None

            # Пропускаем плейлисты - у них есть ключ 'playlist' вместо 'artist'
            if 'playlist' in audio or 'playlists' in audio:
                logger.debug(f"Skipping playlist object at index {index}")
                return None

            # Пропускаем объекты без базовых полей трека
            if 'artist' not in audio or 'title' not in audio:
                logger.debug(f"Skipping object without artist/title at index {index}")
                return None

            # Проверяем наличие URL - некоторые треки могут не иметь URL из-за ограничений
            url = audio.get('url', '')
            if not url:
                logger.debug(f"VK track {index} '{audio.get('artist')} - {audio.get('title')}' has no URL, skipping")
                return None

            # Извлекаем данные
            track_id = audio.get('id', index)
            owner_id = audio.get('owner_id', 0)
            artist = audio.get('artist', 'Unknown Artist')
            title = audio.get('title', 'Unknown Title')
            duration = audio.get('duration', 0)

            # Создаем уникальный ID
            unique_id = f"{owner_id}_{track_id}"

            track_data = {
                'id': unique_id,
                'title': title,
                'artist': artist,
                'duration': duration,
                'quality': 'MP3 320kbps',
                'source': 'vk_music',
                'url': url,
                'owner_id': owner_id,
                'track_id': track_id
            }

            logger.debug(f"Formatted track {index}: {artist} - {title}")
            return track_data

        except KeyError as e:
            logger.warning(f"Missing key in VK track at index {index}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error formatting VK track at index {index}: {e}")
            return None
