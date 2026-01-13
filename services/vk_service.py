import asyncio
import logging
import os
import json
import re
from typing import List, Dict, Any, Optional
from http.cookiejar import MozillaCookieJar
import aiohttp
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class VKMusicService:
    def __init__(self):
        """Инициализация VK Music через cookies"""
        self.cookies = {}
        self.is_authenticated = False
        self.auth_error_message = None
        self.session = None

        # Путь к файлу cookies
        cookies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vk_cookies.txt')

        try:
            if os.path.exists(cookies_path):
                logger.info("Loading VK cookies from file")
                self._load_cookies(cookies_path)
                self.is_authenticated = True
                logger.info("VK Music service initialized successfully with cookies")
            else:
                logger.error(f"VK cookies file not found: {cookies_path}")
                self.auth_error_message = "VK cookies file not found"
        except Exception as e:
            logger.error(f"VK Music initialization error: {e}")
            self.auth_error_message = f"Initialization error: {e}"

    def _load_cookies(self, cookies_path: str):
        """Загружает cookies из файла Netscape format"""
        try:
            jar = MozillaCookieJar(cookies_path)
            jar.load(ignore_discard=True, ignore_expires=True)

            # Конвертируем в словарь для aiohttp
            for cookie in jar:
                self.cookies[cookie.name] = cookie.value

            logger.info(f"Loaded {len(self.cookies)} cookies from file")
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            raise

    async def _get_session(self) -> aiohttp.ClientSession:
        """Получает или создает aiohttp сессию с cookies"""
        if self.session is None or self.session.closed:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            cookie_jar = aiohttp.CookieJar()
            self.session = aiohttp.ClientSession(
                headers=headers,
                cookie_jar=cookie_jar,
                timeout=aiohttp.ClientTimeout(total=30)
            )

            # Добавляем cookies в сессию
            for name, value in self.cookies.items():
                self.session.cookie_jar.update_cookies({name: value}, response_url=aiohttp.URL('https://vk.com'))

        return self.session

    async def search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Поиск треков в VK Music через web-интерфейс

        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов

        Returns:
            Список треков
        """
        if not self.is_authenticated:
            logger.error(f"VK Music search failed: {self.auth_error_message}")
            return []

        try:
            session = await self._get_session()

            # Используем VK Mobile API endpoint для поиска аудио
            # Этот endpoint работает через cookies и не требует токена
            search_url = f"https://m.vk.com/audio?act=search&q={query}"

            logger.info(f"Searching VK Music for: {query}")

            async with session.get(search_url) as response:
                if response.status != 200:
                    logger.error(f"VK search failed with status {response.status}")
                    return []

                html = await response.text()

                # Парсим аудио из HTML
                tracks = self._parse_audio_from_html(html)

                # Ограничиваем количество результатов
                tracks = tracks[:max_results]

                logger.info(f"VK Music search for '{query}' returned {len(tracks)} results")
                return tracks

        except Exception as e:
            logger.error(f"VK Music search error: {e}", exc_info=True)
            return []

    def _parse_audio_from_html(self, html: str) -> List[Dict[str, Any]]:
        """
        Парсит аудио из HTML страницы VK

        Args:
            html: HTML страницы с результатами поиска

        Returns:
            Список треков
        """
        tracks = []

        try:
            # Ищем JavaScript объекты с данными аудио
            # VK хранит данные в формате: AudioPage.init(...)
            pattern = r'data-audio="([^"]+)"'
            matches = re.findall(pattern, html)

            for i, match in enumerate(matches):
                try:
                    # Декодируем HTML entities
                    audio_data = match.replace('&quot;', '"').replace('&amp;', '&')
                    audio_parts = audio_data.split(',')

                    if len(audio_parts) < 3:
                        continue

                    # Формат: owner_id,audio_id,url,title,artist,duration,...
                    owner_id = audio_parts[0]
                    audio_id = audio_parts[1]
                    url = audio_parts[2] if len(audio_parts) > 2 else ''
                    artist = audio_parts[4] if len(audio_parts) > 4 else 'Unknown Artist'
                    title = audio_parts[3] if len(audio_parts) > 3 else 'Unknown Title'
                    duration = int(audio_parts[5]) if len(audio_parts) > 5 and audio_parts[5].isdigit() else 0

                    if not url:
                        continue

                    track = {
                        'id': f"{owner_id}_{audio_id}",
                        'title': title,
                        'artist': artist,
                        'duration': duration,
                        'quality': 'MP3',
                        'source': 'vk_music',
                        'url': url,
                        'owner_id': owner_id,
                        'track_id': audio_id
                    }

                    tracks.append(track)
                    logger.debug(f"Parsed track: {artist} - {title}")

                except Exception as e:
                    logger.warning(f"Failed to parse audio at index {i}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse audio from HTML: {e}")

        return tracks

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

            session = await self._get_session()

            # Скачиваем файл
            success = await self._download_from_url(session, track_url, output_path)

            if success:
                logger.info(f"Successfully downloaded from VK: {track_info.get('title', 'Unknown')}")
                return True
            else:
                logger.error(f"Failed to download from VK: {track_info.get('title', 'Unknown')}")
                return False

        except Exception as e:
            logger.error(f"VK download error for {track_info.get('title', 'Unknown')}: {e}")
            return False

    async def _download_from_url(self, session: aiohttp.ClientSession, url: str, output_path: str) -> bool:
        """
        Скачивает файл по URL асинхронно

        Args:
            session: aiohttp сессия
            url: Прямая ссылка на MP3 файл
            output_path: Путь для сохранения

        Returns:
            True если успешно
        """
        try:
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

    async def close(self):
        """Закрывает aiohttp сессию"""
        if self.session and not self.session.closed:
            await self.session.close()

    def __del__(self):
        """Деструктор для закрытия сессии"""
        if self.session and not self.session.closed:
            try:
                asyncio.get_event_loop().run_until_complete(self.session.close())
            except:
                pass
