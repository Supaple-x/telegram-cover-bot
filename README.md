# Telegram Media Transfer Bot

Telegram bot for searching/downloading music and videos. Built with aiogram 3, yt-dlp, deployed on Hetzner VPS.

## Features

- **Video downloads**: YouTube, Rutube (360p-1080p, audio-only MP3)
- **Music search**: YouTube Music, SoundCloud, VK Music, Yandex Music
- **Large files**: Up to 2 GB via Local Bot API
- **YouTube cookies**: Update via `/cookies` command (text paste or file upload)
- **Download controls**: Quality selection, estimated file sizes, cancel button, progress bar

## Quick Start

1. Clone and set up:
```bash
git clone git@github.com:Supaple-x/telegram-cover-bot.git
cd telegram-cover-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your tokens
```

2. Install ffmpeg:
```bash
# Ubuntu
sudo apt install ffmpeg
# Mac
brew install ffmpeg
```

3. Run:
```bash
python bot.py
```

## Project Structure

```
bot.py                          # Entry point
config.py                       # Config, messages, env vars
handlers/
  start.py                      # /start, /help, /about, /cookies
  video.py                      # Video URL handling (YouTube, Rutube)
  search.py                     # Music search
  download.py                   # Music download callbacks
services/
  youtube_video_service.py      # yt-dlp wrapper (YouTube, Rutube)
  youtube_music_service.py      # YouTube Music
  vk_music_service.py           # VK Music
  yandex_music_service.py       # Yandex Music
  soundcloud_service.py         # SoundCloud
utils/
  keyboards.py                  # Inline keyboard builders
```

## Environment Variables

See `.env.example` for the full list.

## Deployment

```bash
scp <file> root@SERVER_IP:/opt/telegram-cover-bot/<path>/
ssh root@SERVER_IP "systemctl restart telegram-cover-bot"
```

## License

MIT
