import asyncio
import logging
import os
import json
import re
import html as html_lib
from typing import List, Dict, Any, Optional, Tuple
from http.cookiejar import MozillaCookieJar
import aiohttp
from yarl import URL
from urllib.parse import urlencode, quote

logger = logging.getLogger(__name__)

class VKMusicService:
    def __init__(self):
        """Инициализация VK Music через cookies"""
        self.cookies = {}
        self.is_authenticated = False
        self.auth_error_message = None
        self.session = None
        self.last_error_details = None

        # Путь к файлу cookies
        cookies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'vk_cookies.txt')

        try:
            if os.path.exists(cookies_path):
                logger.info("Loading VK cookies from file")
                self._load_cookies(cookies_path)
                if 'remixsid' in self.cookies:
                    self.is_authenticated = True
                    logger.info("VK Music service initialized with cookies")
                else:
                    self.auth_error_message = "Cookies не содержат remixsid - требуется повторный экспорт"
                    logger.error(self.auth_error_message)
            else:
                logger.error(f"VK cookies file not found: {cookies_path}")
                self.auth_error_message = "Файл vk_cookies.txt не найден"
        except Exception as e:
            logger.error(f"VK Music initialization error: {e}")
            self.auth_error_message = f"Ошибка загрузки cookies: {e}"

    def _load_cookies(self, cookies_path: str):
        """Загружает cookies из файла Netscape format"""
        try:
            jar = MozillaCookieJar(cookies_path)
            jar.load(ignore_discard=True, ignore_expires=True)

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
                'Accept': '*/*',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://vk.com',
                'Referer': 'https://vk.com/audio',
            }

            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )

            for name, value in self.cookies.items():
                self.session.cookie_jar.update_cookies({name: value}, response_url=URL('https://vk.com'))

        return self.session

    async def search(self, query: str, max_results: int = 50) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Поиск треков в VK Music через внутренний API

        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов

        Returns:
            Tuple[List[tracks], Optional[error_details]]
        """
        self.last_error_details = None

        if not self.is_authenticated:
            error = f"VK не авторизован: {self.auth_error_message}"
            logger.error(error)
            return [], error

        try:
            session = await self._get_session()
            logger.info(f"Searching VK Music for: {query}")

            # Используем внутренний API al_audio.php
            data = {
                'act': 'section',
                'al': '1',
                'claim': '0',
                'is_layer': '0',
                'owner_id': '0',
                'section': 'search',
                'q': query,
            }

            async with session.post('https://vk.com/al_audio.php', data=data) as response:
                if response.status != 200:
                    error = f"VK вернул статус {response.status}"
                    logger.error(error)
                    return [], error

                text = await response.text()
                logger.debug(f"VK response length: {len(text)}")

                # Парсим JSON ответ
                try:
                    resp_data = json.loads(text)
                except json.JSONDecodeError as e:
                    error = f"Ошибка парсинга ответа VK: {e}"
                    logger.error(error)
                    return [], error

                # Проверяем структуру ответа
                payload = resp_data.get('payload', [])
                if not payload or len(payload) < 2:
                    error = f"Неверная структура ответа VK (payload len={len(payload)})"
                    logger.error(error)
                    return [], error

                # Проверяем код ошибки
                error_code = payload[0]
                if error_code == "3" or (isinstance(payload[1], list) and len(payload[1]) < 2):
                    error = "Сессия VK истекла. Требуется обновить cookies (войдите в VK в браузере и экспортируйте cookies снова)"
                    logger.error(error)
                    return [], error

                inner = payload[1]
                if not isinstance(inner, list) or not inner:
                    error = "VK не вернул данные для поиска"
                    logger.error(error)
                    return [], error

                html = inner[0] if isinstance(inner[0], str) else ""
                if len(html) < 100:
                    error = f"VK вернул пустой ответ (len={len(html)}). Сессия могла истечь"
                    logger.error(error)
                    return [], error

                # Парсим треки из HTML
                tracks = self._parse_audio_from_html(html)

                if not tracks:
                    # Проверяем, есть ли сообщение "ничего не найдено"
                    if 'ничего не найдено' in html.lower() or 'audio_not_found' in html.lower():
                        return [], None  # Нет ошибки, просто нет результатов
                    else:
                        error = f"Треки не найдены в ответе VK (HTML len={len(html)})"
                        logger.warning(error)
                        return [], error

                tracks = tracks[:max_results]
                logger.info(f"VK Music search returned {len(tracks)} tracks")
                return tracks, None

        except aiohttp.ClientError as e:
            error = f"Сетевая ошибка VK: {e}"
            logger.error(error)
            return [], error
        except Exception as e:
            error = f"Ошибка поиска VK: {e}"
            logger.error(error, exc_info=True)
            return [], error

    def _parse_audio_from_html(self, html: str) -> List[Dict[str, Any]]:
        """
        Парсит аудио из HTML ответа VK API

        Args:
            html: HTML с результатами поиска

        Returns:
            Список треков
        """
        tracks = []

        try:
            # Ищем data-audio атрибуты
            pattern = r'data-audio="([^"]+)"'
            matches = re.findall(pattern, html)

            for i, match in enumerate(matches):
                try:
                    # Декодируем HTML entities и парсим JSON
                    decoded = html_lib.unescape(match)
                    audio_data = json.loads(decoded)

                    if not isinstance(audio_data, list) or len(audio_data) < 6:
                        continue

                    # Формат VK audio: [owner_id, audio_id, url, title, artist, duration, ...]
                    owner_id = audio_data[0]
                    audio_id = audio_data[1]
                    url = audio_data[2] or ''
                    title = audio_data[3] or 'Unknown'
                    artist = audio_data[4] or 'Unknown'
                    duration = audio_data[5] if isinstance(audio_data[5], int) else 0

                    track = {
                        'id': f"{owner_id}_{audio_id}",
                        'title': title,
                        'artist': artist,
                        'duration': duration,
                        'quality': 'MP3',
                        'source': 'vk_music',
                        'url': url,
                        'owner_id': owner_id,
                        'track_id': audio_id,
                        'full_data': audio_data  # Для reload_audio
                    }

                    tracks.append(track)
                    logger.debug(f"Parsed: {artist} - {title}")

                except (json.JSONDecodeError, IndexError) as e:
                    logger.warning(f"Failed to parse audio {i}: {e}")
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
