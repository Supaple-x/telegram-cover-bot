# Telegram Media Transfer Bot

## Overview
Telegram bot for searching/downloading music and YouTube videos. Built with aiogram 3, yt-dlp, deployed on Hetzner VPS.

## Architecture

### Server
- **Host**: 65.109.142.30 (Hetzner VPS, 2GB RAM, Ubuntu)
- **Bot process**: systemd service `telegram-cover-bot`
- **Local Bot API**: `telegram-bot-api` on port 8081 (allows files up to 2GB)
- **WARP proxy**: Cloudflare WARP in proxy mode on port 40000 (socks5h://127.0.0.1:40000) — used for YouTube downloads to bypass geo-restrictions
- **bgutil-provider**: Docker container with `--network host`, provides PO Tokens for YouTube on port 4416. Must use host network to access WARP proxy.
- **Xray (VLESS)**: VPN server on the same host

### Key Files
```
bot.py                          # Entry point, router registration, startup
config.py                       # All config, messages, env vars
handlers/
  start.py                      # /start, /help, /about, /cookies, file upload
  video.py                      # YouTube URL handling, quality selection, download with progress
  search.py                     # Music search across sources
  download.py                   # Music download callbacks
services/
  youtube_video_service.py      # yt-dlp wrapper for video downloads
  youtube_music_service.py      # YouTube Music search/download
  vk_music_service.py           # VK Music
  yandex_music_service.py       # Yandex Music
  soundcloud_service.py         # SoundCloud
utils/
  keyboards.py                  # Inline keyboard builders
```

### Important Technical Details

**YouTube Video Downloads** (`services/youtube_video_service.py`):
- All YouTube requests go through WARP proxy (socks5h://127.0.0.1:40000)
- Cookies file: `/opt/telegram-cover-bot/youtube_cookies.txt` (Netscape format)
- PO Tokens provided by bgutil Docker container on port 4416
- JS challenges solved by deno + yt-dlp-ejs package
- Supports: video download (360p-1080p), audio-only (MP3 320kbps), cancel button, progress bar
- download() returns Tuple[Optional[str], Optional[str]] — (file_path, error_message)

**Cookies Management** (`handlers/start.py`):
- `/cookies` command — two options: paste text (ytdlnis format) or upload file
- FSM state `CookiesStates.waiting_for_cookies` for text input
- Bot restarts with 2s delay after cookie update (`sleep 2 && systemctl restart`)

**HTML Escaping**:
- All Telegram messages in video handler use `parse_mode="HTML"` (not Markdown!)
- `escape_html()` function in `handlers/video.py` for safe text display
- Markdown caused persistent parsing errors with special characters in video titles

**Local Bot API**:
- `USE_LOCAL_BOT_API=true` in .env
- Allows sending files up to 2GB (vs 50MB standard limit)
- Running as separate process: `telegram-bot-api --api-id=... --api-hash=... --dir=/var/lib/telegram-bot-api --local`

### Deployment
```bash
# Deploy changes
scp <file> root@65.109.142.30:/opt/telegram-cover-bot/<path>/
ssh root@65.109.142.30 "systemctl restart telegram-cover-bot"

# Check logs
ssh root@65.109.142.30 "journalctl -u telegram-cover-bot -n 50 --no-pager"

# Check WARP
ssh root@65.109.142.30 "warp-cli --accept-tos status"

# Check bgutil PO Token provider
ssh root@65.109.142.30 "docker logs bgutil-provider --tail 10"

# Restart bgutil (if needed, must use --network host)
docker run -d --name bgutil-provider --network host --restart=always \
  -e PROXY='socks5h://127.0.0.1:40000' \
  brainicism/bgutil-ytdlp-pot-provider
```

### Environment Variables (.env)
```
TELEGRAM_BOT_TOKEN    # Bot token
YOUTUBE_API_KEY       # YouTube Data API v3
VK_TOKEN              # VK API token
VK_LOGIN / VK_PASSWORD # VK fallback auth
YANDEX_MUSIC_TOKEN    # Yandex Music OAuth token
USE_LOCAL_BOT_API     # true/false
LOCAL_BOT_API_URL     # http://localhost:8081
ADMIN_ID              # Telegram user ID for admin commands (optional)
```

### Common Issues
- **YouTube 403**: Cookies expired — update via `/cookies` command or upload fresh file
- **Slow YouTube downloads**: Check bgutil-provider is running and responsive (`curl -X POST http://127.0.0.1:4416/get_pot -H 'Content-Type: application/json' -d '{"client": "web"}'`)
- **SSH to wrong server**: Production is 65.109.142.30, NOT 31.129.33.233
- **Bot restart after cookies**: Use `sleep 2 && systemctl restart` to avoid ServerDisconnectedError
- **Markdown parse errors**: Always use HTML parse_mode for video handler messages
