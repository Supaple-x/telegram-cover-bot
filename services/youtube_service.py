import asyncio
import logging
import os
import re
from typing import List, Dict, Any, Optional
import yt_dlp
from ytmusicapi import YTMusic

from config import YOUTUBE_API_KEY, AUDIO_FORMAT, AUDIO_QUALITY
from utils.formatters import format_duration

logger = logging.getLogger(__name__)

class YouTubeService:
    def __init__(self):
        self.ytmusic = None
        self.cookies_file = None
        
        # Проверяем наличие файла cookies
        cookies_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'youtube_cookies.txt')
        if os.path.exists(cookies_path):
            self.cookies_file = cookies_path
            logger.info(f"YouTube cookies file found: {cookies_path}")
        else:
            logger.warning(f"YouTube cookies file not found: {cookies_path}")
            logger.warning("Download may fail due to YouTube bot protection. See COOKIES_SETUP.md for instructions.")
        
        try:
            # Инициализируем YTMusic без авторизации
            self.ytmusic = YTMusic()
        except Exception as e:
            logger.warning(f"Failed to initialize YTMusic: {e}")
    
    async def search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск в YouTube"""
        try:
            # Настройки yt-dlp для поиска
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': 'ytsearch50:',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Выполняем поиск
                search_results = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                )
                
                tracks = []
                if search_results and 'entries' in search_results:
                    for i, entry in enumerate(search_results['entries'][:max_results]):
                        if entry:
                            track = self._format_youtube_track(entry, i)
                            if track:
                                tracks.append(track)
                
                logger.info(f"YouTube search for '{query}' returned {len(tracks)} results")
                return tracks
                
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return []
    
    async def search_music(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск в YouTube Music"""
        if not self.ytmusic:
            logger.warning("YTMusic not initialized, falling back to regular YouTube search")
            return await self.search(query, max_results)

        try:
            logger.debug(f"Searching YouTube Music for: '{query}', max_results={max_results}")

            # Поиск в YouTube Music
            search_results = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self.ytmusic.search(query, filter="songs", limit=max_results)
            )

            logger.info(f"YouTube Music API returned {len(search_results)} results")

            tracks = []
            seen_ids = set()  # Отслеживаем уникальные ID треков

            for i, result in enumerate(search_results[:max_results]):
                try:
                    track = self._format_ytmusic_track(result, i)
                    if track:
                        track_id = track.get('id')
                        # Пропускаем дубликаты
                        if track_id not in seen_ids:
                            seen_ids.add(track_id)
                            tracks.append(track)
                            logger.debug(f"Formatted track {i}: {track.get('artist')} - {track.get('title')} (ID: {track_id})")
                        else:
                            logger.debug(f"Skipping duplicate track {i}: {track_id}")
                except Exception as track_error:
                    logger.warning(f"Failed to format track {i}: {track_error}", exc_info=True)
                    continue

            logger.info(f"YouTube Music search for '{query}' returned {len(tracks)} unique tracks (filtered from {len(search_results)} total)")
            return tracks

        except Exception as e:
            logger.error(f"YouTube Music search error: {e}", exc_info=True)
            # Fallback to regular YouTube search
            return await self.search(query, max_results)
    
    async def download(self, track_info: Dict[str, Any], output_path: str) -> bool:
        """Скачивает трек"""
        try:
            video_id = track_info.get('id')
            title = track_info.get('title', 'Unknown')

            if not video_id:
                logger.error(f"No video ID provided for download: {title}")
                return False

            logger.info(f"Starting download: {title} (ID: {video_id})")

            # Настройки yt-dlp с улучшенным обходом блокировок (как YTDLnis)
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',  # Предпочитаем m4a
                'outtmpl': output_path.replace('.mp3', '.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': AUDIO_FORMAT,
                    'preferredquality': AUDIO_QUALITY,
                }],
                'quiet': True,
                'no_warnings': True,
                # Обход блокировок и защиты
                'nocheckcertificate': True,
                'geo_bypass': True,
                'age_limit': None,
                'force_ipv4': True,  # Принудительно IPv4
                # Улучшенная обработка ошибок и повторных попыток
                'extractor_retries': 5,
                'fragment_retries': 10,  # Увеличено с 5 до 10
                'file_access_retries': 5,
                'skip_unavailable_fragments': False,  # НЕ пропускаем фрагменты
                'ignoreerrors': False,
                'retries': 10,  # Общие retry
                # Дополнительные опции для обхода ограничений
                'socket_timeout': 60,  # Увеличено с 30 до 60
                'http_chunk_size': 10485760,  # 10MB chunks
                'http_headers': {
                    'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
            }

            # Используем несколько стратегий обхода блокировок (как YTDLnis)
            if self.cookies_file and os.path.exists(self.cookies_file):
                ydl_opts['cookiefile'] = self.cookies_file
                logger.info(f"✅ Using cookies file: {self.cookies_file}")
                # С cookies можем использовать более агрессивные настройки
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['default', 'mediaconnect', 'android'],
                        'player_skip': ['webpage', 'configs'],
                    },
                    'youtubepot-bgutilhttp': {
                        'base_url': 'http://localhost:4416'
                    }
                }
            else:
                # Без cookies используем множественные клиенты (как YTDLnis)
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['android_creator', 'mediaconnect', 'android', 'ios'],
                        'player_skip': ['webpage', 'configs'],
                    },
                    'youtubepot-bgutilhttp': {
                        'base_url': 'http://localhost:4416'
                    }
                }
                logger.info("Using multiple player clients (no cookies): android_creator, mediaconnect, android, ios")

            url = f"https://www.youtube.com/watch?v={video_id}"
            logger.debug(f"Download URL: {url}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.download([url])
                )

            # Проверяем, что файл создан
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"✅ Successfully downloaded: {title} ({file_size} bytes)")
                return True
            else:
                # Ищем файл с другим расширением
                base_path = output_path.rsplit('.', 1)[0]
                for ext in ['mp3', 'm4a', 'webm', 'ogg', 'opus', 'wav']:
                    alt_path = f"{base_path}.{ext}"
                    if os.path.exists(alt_path):
                        # Переименовываем в нужное расширение
                        if ext != 'mp3':
                            os.rename(alt_path, output_path)
                            logger.info(f"Downloaded and renamed: {ext} -> mp3")
                        file_size = os.path.getsize(output_path)
                        logger.info(f"✅ Successfully downloaded: {title} ({file_size} bytes)")
                        return True

                # Проверяем наличие .mhtml файла (ошибка скачивания)
                mhtml_path = f"{base_path}.mhtml"
                if os.path.exists(mhtml_path):
                    os.remove(mhtml_path)
                    logger.error(f"❌ Downloaded HTML instead of video - authentication issue")
                    return False

                logger.error(f"❌ Download completed but file not found: {output_path}")
                return False

        except Exception as e:
            logger.error(f"❌ Download error for {track_info.get('title', 'Unknown')}: {e}", exc_info=True)
            return False
    
    def _format_youtube_track(self, entry: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """Форматирует результат поиска YouTube"""
        try:
            if not entry.get('id'):
                return None
            
            title = entry.get('title', 'Unknown Title')
            duration = entry.get('duration', 0)
            uploader = entry.get('uploader', 'Unknown')
            
            # Пытаемся извлечь исполнителя из названия
            artist = self._extract_artist_from_title(title)
            
            return {
                'id': entry['id'],
                'title': title,
                'artist': artist or uploader,
                'duration': duration,
                'quality': 'MP3 320kbps',
                'source': 'youtube',
                'url': f"https://www.youtube.com/watch?v={entry['id']}",
                'thumbnail': entry.get('thumbnail'),
                'view_count': entry.get('view_count', 0)
            }
            
        except Exception as e:
            logger.warning(f"Error formatting YouTube track: {e}")
            return None
    
    def _format_ytmusic_track(self, result: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """Форматирует результат поиска YouTube Music"""
        try:
            video_id = result.get('videoId')
            if not video_id:
                logger.warning(f"Track {index} has no videoId, skipping")
                return None

            title = result.get('title', 'Unknown Title')
            artists = result.get('artists', [])
            artist = artists[0]['name'] if artists else 'Unknown Artist'
            duration_text = result.get('duration', '0:00')

            # Конвертируем длительность в секунды
            duration = self._parse_duration(duration_text)

            formatted = {
                'id': video_id,
                'title': title,
                'artist': artist,
                'duration': duration,
                'quality': 'high',
                'source': 'youtube_music',
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'thumbnail': result.get('thumbnails', [{}])[-1].get('url'),
                'album': result.get('album', {}).get('name') if result.get('album') else None
            }

            logger.debug(f"Formatted YouTube Music track: {artist} - {title} (ID: {video_id}, duration: {duration}s)")
            return formatted

        except Exception as e:
            logger.error(f"Error formatting YouTube Music track {index}: {e}", exc_info=True)
            return None
    
    def _extract_artist_from_title(self, title: str) -> Optional[str]:
        """Пытается извлечь исполнителя из названия видео"""
        # Общие паттерны для извлечения исполнителя
        patterns = [
            r'^([^-]+)\s*-\s*(.+)$',  # "Artist - Title"
            r'^([^–]+)\s*–\s*(.+)$',  # "Artist – Title" (em dash)
            r'^([^|]+)\s*\|\s*(.+)$',  # "Artist | Title"
            r'^([^:]+):\s*(.+)$',     # "Artist: Title"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, title.strip())
            if match:
                artist = match.group(1).strip()
                # Проверяем, что это не слишком длинное название
                if len(artist) < 50 and not any(word in artist.lower() for word in ['official', 'video', 'lyrics', 'audio']):
                    return artist
        
        return None
    
    def _parse_duration(self, duration_str: str) -> int:
        """Парсит строку длительности в секунды"""
        try:
            if not duration_str:
                return 0
            
            # Формат: "MM:SS" или "H:MM:SS"
            parts = duration_str.split(':')
            if len(parts) == 2:
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            elif len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            else:
                return 0
                
        except (ValueError, AttributeError):
            return 0
