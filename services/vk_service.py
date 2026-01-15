import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
import aiohttp
import vk_api
from vk_api.audio import VkAudio
from vk_api.exceptions import AuthError, Captcha

from config import VK_TOKEN, VK_LOGIN, VK_PASSWORD

logger = logging.getLogger(__name__)

class VKMusicService:
    def __init__(self):
        """Инициализация VK API с токеном или логином/паролем"""
        self.vk_session = None
        self.vk_audio = None
        self.is_authenticated = False
        self.auth_error_message = None

        try:
            # Приоритет 1: Используем токен если доступен
            if VK_TOKEN:
                logger.info("Using VK token for authentication")
                self.vk_session = vk_api.VkApi(token=VK_TOKEN)
                self.vk_audio = VkAudio(self.vk_session)
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
                self.vk_audio = VkAudio(self.vk_session)
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

    async def search(self, query: str, max_results: int = 50) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Поиск треков в VK Music

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
            error_msg = f"VK не авторизован: {self.auth_error_message}"
            logger.error(error_msg)
            return [], error_msg

        try:
            logger.info(f"Searching VK Music for: {query}")

            # Выполняем поиск в отдельном потоке (vk_api синхронный)
            tracks = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._search_sync(query, max_results)
            )

            logger.info(f"VK Music search for '{query}' returned {len(tracks)} results")
            return tracks, None

        except Captcha as e:
            error_msg = f"VK Music заблокирован капчей: {e.get_url()}"
            logger.error(error_msg)
            return [], error_msg
        except Exception as e:
            error_msg = f"Ошибка поиска VK Music: {e}"
            logger.error(error_msg)
            return [], error_msg

    def _search_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Синхронный поиск (вызывается через executor)"""
        try:
            # Используем search для получения результатов
            raw_results = list(self.vk_audio.search(q=query, count=max_results))

            tracks = []
            for i, audio in enumerate(raw_results):
                # Пропускаем плейлисты и другие объекты, которые не являются треками
                if not isinstance(audio, dict):
                    logger.debug(f"Skipping non-dict object at index {i}: {type(audio)}")
                    continue

                # Проверяем, что это трек (есть обязательные поля), а не плейлист
                if 'playlist' in str(type(audio)).lower() or not audio.get('id'):
                    logger.debug(f"Skipping playlist or invalid object at index {i}")
                    continue

                try:
                    track = self._format_vk_track(audio, i)
                    if track:
                        tracks.append(track)
                except Exception as track_error:
                    logger.warning(f"Failed to format track at index {i}: {track_error}")
                    continue

            return tracks
        except Exception as e:
            logger.error(f"VK _search_sync error: {e}", exc_info=True)
            return []

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
                'quality': 'high',  # VK обычно предоставляет хорошее качество
                'source': 'vk_music',
                'url': url,
                'owner_id': owner_id,
                'track_id': track_id
            }

        except Exception as e:
            logger.error(f"Error formatting VK track {index}: {e}")
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

            # Проверяем, что URL все еще актуален
            # VK URLs действуют ограниченное время

            # Скачиваем файл через aiohttp
            success = await self._download_from_url(track_url, output_path)

            if success:
                logger.info(f"Successfully downloaded VK track to {output_path}")
            else:
                logger.error(f"Failed to download VK track from {track_url}")

            return success

        except Exception as e:
            logger.error(f"VK download error: {e}")
            return False

    async def _download_from_url(self, url: str, output_path: str) -> bool:
        """Скачивает файл по URL через aiohttp"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download: HTTP {response.status}")
                        return False

                    # Скачиваем и записываем файл
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)

                    return True

        except asyncio.TimeoutError:
            logger.error(f"Download timeout for {url}")
            return False
        except Exception as e:
            logger.error(f"Download error: {e}")
            return False

    async def close(self):
        """Очистка ресурсов"""
        # vk_api не требует явного закрытия соединений
        pass
