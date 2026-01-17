import asyncio
import logging
import os
from typing import List, Dict, Any, Optional, Tuple

from config import YANDEX_MUSIC_TOKEN

logger = logging.getLogger(__name__)


class YandexMusicService:
    def __init__(self):
        """Инициализация Yandex Music API"""
        self.client = None
        self.is_authenticated = False
        self.auth_error_message = None

        try:
            if YANDEX_MUSIC_TOKEN:
                from yandex_music import Client
                logger.info("Initializing Yandex Music with token")
                # Инициализируем клиент с токеном
                self.client = Client(YANDEX_MUSIC_TOKEN).init()
                self.is_authenticated = True
                logger.info("Yandex Music service initialized successfully")
            else:
                logger.error("YANDEX_MUSIC_TOKEN not set in environment")
                self.auth_error_message = "YANDEX_MUSIC_TOKEN not configured"

        except Exception as e:
            logger.error(f"Yandex Music initialization error: {e}", exc_info=True)
            self.auth_error_message = f"Initialization error: {e}"

    async def search(self, query: str, max_results: int = 50) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Поиск треков в Yandex Music

        Args:
            query: Поисковый запрос
            max_results: Максимальное количество результатов

        Returns:
            Кортеж (список треков, сообщение об ошибке или None)
        """
        if not self.is_authenticated:
            error_msg = f"Auth: {self.auth_error_message}"
            logger.error(f"Yandex Music не авторизован: {self.auth_error_message}")
            return [], error_msg

        try:
            logger.info(f"Searching Yandex Music for: {query}")

            # Выполняем поиск в отдельном потоке (yandex-music синхронный)
            tracks = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._search_sync(query, max_results)
            )

            result_count = len(tracks)
            logger.info(f"Yandex Music search for '{query}' returned {result_count} results")

            if result_count == 0:
                error_details = f"Query: '{query}'\nMax results: {max_results}\nReturned: 0 tracks"
                return [], error_details

            return tracks, None

        except Exception as e:
            import traceback
            error_msg = f"Error: {type(e).__name__}\nMessage: {str(e)}\nQuery: '{query}'\nTraceback:\n{traceback.format_exc()}"
            logger.error(f"Ошибка поиска Yandex Music: {e}", exc_info=True)
            return [], error_msg

    def _search_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Синхронный поиск (вызывается через executor)"""
        try:
            logger.debug(f"Calling yandex_music search with query='{query}'")

            # Поиск через yandex-music
            search_result = self.client.search(query, type_='track')

            if not search_result or not search_result.tracks:
                logger.info("Yandex Music search returned no tracks")
                return []

            tracks_result = search_result.tracks.results
            logger.info(f"Yandex Music returned {len(tracks_result)} tracks")

            tracks = []
            seen_ids = set()

            for i, track in enumerate(tracks_result[:max_results]):
                try:
                    formatted = self._format_yandex_track(track, i)
                    if formatted:
                        track_id = formatted.get('id')
                        if track_id not in seen_ids:
                            seen_ids.add(track_id)
                            tracks.append(formatted)
                            logger.debug(f"Formatted track {i}: {formatted.get('artist')} - {formatted.get('title')}")
                        else:
                            logger.debug(f"Skipping duplicate track {i}: {track_id}")
                except Exception as track_error:
                    logger.warning(f"Failed to format track {i}: {track_error}", exc_info=True)
                    continue

            logger.info(f"Successfully formatted {len(tracks)} unique tracks")
            return tracks

        except Exception as e:
            logger.error(f"Yandex _search_sync error: {e}", exc_info=True)
            return []

    def _format_yandex_track(self, track, index: int) -> Optional[Dict[str, Any]]:
        """
        Форматирует результат yandex-music в единый формат

        Args:
            track: Объект Track от yandex-music
            index: Индекс трека в результатах

        Returns:
            Отформатированный словарь с данными трека
        """
        try:
            # Получаем ID трека
            track_id = str(track.id)

            # Получаем исполнителей
            artists = ', '.join([artist.name for artist in track.artists]) if track.artists else 'Unknown Artist'

            # Получаем длительность в секундах (в API это миллисекунды)
            duration = track.duration_ms // 1000 if track.duration_ms else 0

            # Получаем обложку альбома
            thumbnail = None
            if track.albums and track.albums[0].cover_uri:
                thumbnail = f"https://{track.albums[0].cover_uri.replace('%%', '400x400')}"

            # Получаем название альбома
            album = track.albums[0].title if track.albums else None

            return {
                'id': track_id,
                'title': track.title or 'Unknown Title',
                'artist': artists,
                'duration': duration,
                'quality': 'high',
                'source': 'yandex_music',
                'url': f"https://music.yandex.ru/track/{track_id}",
                'thumbnail': thumbnail,
                'album': album,
                # Сохраняем оригинальный объект для скачивания
                '_track_obj': track
            }

        except Exception as e:
            logger.error(f"Error formatting Yandex track {index}: {e}", exc_info=True)
            return None

    async def download(self, track_info: Dict[str, Any], output_path: str) -> bool:
        """
        Скачивает трек из Yandex Music

        Args:
            track_info: Информация о треке
            output_path: Путь для сохранения файла

        Returns:
            True если успешно, False в случае ошибки
        """
        try:
            track_id = track_info.get('id')
            title = track_info.get('title', 'Unknown')

            if not track_id:
                logger.error(f"No track ID provided for download: {title}")
                return False

            logger.info(f"Starting Yandex Music download: {title} (ID: {track_id})")

            # Скачиваем в отдельном потоке
            success = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._download_sync(track_id, output_path)
            )

            return success

        except Exception as e:
            logger.error(f"Yandex Music download error: {e}", exc_info=True)
            return False

    def _download_sync(self, track_id: str, output_path: str) -> bool:
        """Синхронное скачивание (вызывается через executor)"""
        try:
            # Получаем трек по ID
            tracks = self.client.tracks([track_id])
            if not tracks:
                logger.error(f"Track not found: {track_id}")
                return False

            track = tracks[0]

            # Получаем информацию о скачивании
            download_info = track.get_download_info()
            if not download_info:
                logger.error(f"No download info for track: {track_id}")
                return False

            # Выбираем лучшее качество (mp3 320kbps если доступно)
            best_quality = None
            for info in download_info:
                if info.codec == 'mp3':
                    if best_quality is None or info.bitrate_in_kbps > best_quality.bitrate_in_kbps:
                        best_quality = info

            # Если mp3 не найден, берем любой формат
            if not best_quality and download_info:
                best_quality = download_info[0]

            if not best_quality:
                logger.error(f"No suitable download format for track: {track_id}")
                return False

            logger.info(f"Downloading track with codec={best_quality.codec}, bitrate={best_quality.bitrate_in_kbps}kbps")

            # Скачиваем файл
            # Убираем расширение .mp3 если оно есть, т.к. download() добавит своё
            base_path = output_path
            if output_path.endswith('.mp3'):
                base_path = output_path[:-4]

            best_quality.download(base_path)

            # Проверяем, что файл создан (может быть с другим расширением)
            if os.path.exists(base_path):
                # Переименуем в .mp3 если нужно
                if not output_path.endswith('.mp3'):
                    os.rename(base_path, output_path)
                else:
                    os.rename(base_path, output_path)
                logger.info(f"Successfully downloaded Yandex Music track to {output_path}")
                return True
            elif os.path.exists(output_path):
                logger.info(f"Successfully downloaded Yandex Music track to {output_path}")
                return True
            else:
                # Проверяем с различными расширениями
                for ext in ['.mp3', '.m4a', '.aac']:
                    check_path = base_path + ext
                    if os.path.exists(check_path):
                        if check_path != output_path:
                            os.rename(check_path, output_path)
                        logger.info(f"Successfully downloaded Yandex Music track to {output_path}")
                        return True

                logger.error(f"Downloaded file not found at expected location")
                return False

        except Exception as e:
            logger.error(f"Yandex _download_sync error: {e}", exc_info=True)
            return False

    async def close(self):
        """Очистка ресурсов"""
        # yandex-music не требует явного закрытия соединений
        pass
