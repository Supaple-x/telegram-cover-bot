import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
import aiohttp
import vk_api
from vk_api.audio import VkAudio
from vk_api.exceptions import AuthError, Captcha

from config import VK_LOGIN, VK_PASSWORD

logger = logging.getLogger(__name__)

class VKMusicService:
    def __init__(self):
        """Инициализация VK API с логином/паролем"""
        self.vk_session = None
        self.vk_audio = None
        self.is_authenticated = False
        self.auth_error_message = None

        # Проверяем наличие учетных данных
        if not VK_LOGIN or not VK_PASSWORD:
            logger.error("VK_LOGIN or VK_PASSWORD not set in environment variables")
            self.auth_error_message = "VK credentials not configured"
            return

        try:
            # Создаем сессию с обработчиком 2FA
            self.vk_session = vk_api.VkApi(
                login=VK_LOGIN,
                password=VK_PASSWORD,
                auth_handler=self._auth_handler,
                captcha_handler=self._captcha_handler
            )

            # Выполняем аутентификацию
            self.vk_session.auth()

            # Получаем доступ к VkAudio
            self.vk_audio = VkAudio(self.vk_session)

            self.is_authenticated = True
            logger.info("VK Music service initialized successfully")

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
            # Используем search для получения результатов
            raw_results = list(self.vk_audio.search(q=query, count=max_results))

            tracks = []
            for i, audio in enumerate(raw_results):
                track = self._format_vk_track(audio, i)
                if track:
                    tracks.append(track)

            return tracks
        except Exception as e:
            logger.error(f"VK _search_sync error: {e}")
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

            # Получаем свежий URL через audio.get_by_id
            fresh_audio = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.vk_audio.get_audio_by_id(owner_id, track_id)
            )

            if fresh_audio and fresh_audio.get('url'):
                logger.info("Successfully refreshed VK track URL")
                return fresh_audio.get('url')
            else:
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
            if not audio.get('url'):
                logger.warning(f"VK track {index} has no URL, skipping")
                return None

            # Извлекаем данные
            track_id = audio.get('id', index)
            owner_id = audio.get('owner_id', 0)
            artist = audio.get('artist', 'Unknown Artist')
            title = audio.get('title', 'Unknown Title')
            duration = audio.get('duration', 0)
            url = audio.get('url', '')

            # Создаем уникальный ID
            unique_id = f"{owner_id}_{track_id}"

            return {
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

        except Exception as e:
            logger.warning(f"Error formatting VK track: {e}")
            return None
