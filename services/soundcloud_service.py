import asyncio
import logging
import os
import re
from typing import List, Dict, Any, Optional
import yt_dlp

from config import AUDIO_FORMAT, AUDIO_QUALITY
from utils.formatters import format_duration

logger = logging.getLogger(__name__)

class SoundCloudService:
    def __init__(self):
        pass
    
    async def search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Поиск в SoundCloud"""
        try:
            # Настройки yt-dlp для поиска в SoundCloud
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'default_search': f'scsearch{max_results}:',
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Выполняем поиск
                search_results = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(f"scsearch{max_results}:{query}", download=False)
                )
                
                tracks = []
                if search_results and 'entries' in search_results:
                    for i, entry in enumerate(search_results['entries'][:max_results]):
                        if entry:
                            track = self._format_soundcloud_track(entry, i)
                            if track:
                                tracks.append(track)
                
                logger.info(f"SoundCloud search for '{query}' returned {len(tracks)} results")
                return tracks
                
        except Exception as e:
            logger.error(f"SoundCloud search error: {e}")
            return []
    
    async def download(self, track_info: Dict[str, Any], output_path: str) -> bool:
        """Скачивает трек из SoundCloud"""
        try:
            track_url = track_info.get('url')
            if not track_url:
                logger.error("No URL provided for SoundCloud download")
                return False
            
            # Настройки yt-dlp для скачивания
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_path.replace('.mp3', '.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': AUDIO_FORMAT,
                    'preferredquality': AUDIO_QUALITY,
                }],
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.download([track_url])
                )
            
            # Проверяем, что файл создан
            if os.path.exists(output_path):
                logger.info(f"Successfully downloaded from SoundCloud: {track_info.get('title', 'Unknown')}")
                return True
            else:
                # Ищем файл с другим расширением
                base_path = output_path.rsplit('.', 1)[0]
                for ext in ['mp3', 'm4a', 'webm', 'ogg']:
                    alt_path = f"{base_path}.{ext}"
                    if os.path.exists(alt_path):
                        # Переименовываем в нужное расширение
                        os.rename(alt_path, output_path)
                        logger.info(f"Downloaded and renamed: {alt_path} -> {output_path}")
                        return True
                
                logger.error(f"SoundCloud download completed but file not found: {output_path}")
                return False
                
        except Exception as e:
            logger.error(f"SoundCloud download error for {track_info.get('title', 'Unknown')}: {e}")
            return False
    
    def _format_soundcloud_track(self, entry: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
        """Форматирует результат поиска SoundCloud"""
        try:
            if not entry.get('url'):
                return None
            
            title = entry.get('title', 'Unknown Title')
            duration = entry.get('duration', 0)
            uploader = entry.get('uploader', 'Unknown Artist')
            
            # Пытаемся извлечь исполнителя из названия
            artist = self._extract_artist_from_title(title)
            if not artist:
                artist = uploader
            
            # Генерируем уникальный ID из URL
            track_id = self._extract_id_from_url(entry.get('url', ''))
            
            return {
                'id': track_id or f"sc_{index}",
                'title': title,
                'artist': artist,
                'duration': duration,
                'quality': 'MP3 320kbps',
                'source': 'soundcloud',
                'url': entry['url'],
                'thumbnail': entry.get('thumbnail'),
                'play_count': entry.get('view_count', 0),
                'description': entry.get('description', '')
            }
            
        except Exception as e:
            logger.warning(f"Error formatting SoundCloud track: {e}")
            return None
    
    def _extract_artist_from_title(self, title: str) -> Optional[str]:
        """Пытается извлечь исполнителя из названия трека"""
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
                if len(artist) < 50:
                    return artist
        
        return None
    
    def _extract_id_from_url(self, url: str) -> Optional[str]:
        """Извлекает ID трека из URL SoundCloud"""
        try:
            # SoundCloud URL обычно имеет формат: https://soundcloud.com/user/track-name
            if 'soundcloud.com' in url:
                # Берем последнюю часть URL как ID
                parts = url.rstrip('/').split('/')
                if len(parts) >= 2:
                    return f"{parts[-2]}_{parts[-1]}"
            
            # Если не удалось извлечь, используем хэш URL
            return str(hash(url))
            
        except Exception:
            return None
