# YouTube Advanced Setup - PO Token & Cookies

## Проблема

YouTube может блокировать скачивание с сообщением:
```
ERROR: Sign in to confirm you're not a bot
```

## Решения (по приоритету)

### Вариант 1: Cookies (Рекомендуется, простейший способ)

**Шаг 1:** Установить расширение для браузера
- Chrome/Edge: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

**Шаг 2:** Экспортировать cookies
1. Открыть [youtube.com](https://youtube.com) в браузере
2. Войти в аккаунт Google (если требуется)
3. Кликнуть на расширение
4. Нажать "Export" → Сохранить как `youtube_cookies.txt`

**Шаг 3:** Загрузить на сервер
```bash
scp youtube_cookies.txt root@65.109.142.30:/opt/telegram-cover-bot/
```

**Шаг 4:** Перезапустить бота
```bash
ssh root@65.109.142.30 "systemctl restart telegram-cover-bot"
```

### Вариант 2: PO Token (Продвинутый)

**Что такое PO Token?**
- Proof of Origin Token - специальный токен для обхода блокировок YouTube
- Генерируется BotGuard (Web), DroidGuard (Android), iOSGuard (iOS)
- Требуется для некоторых IP-адресов, заблокированных YouTube

**Как получить PO Token:**

1. **Через браузер (Web PO Token):**
   - Использовать инструменты разработчика браузера
   - Перехватить запросы к YouTube API
   - Извлечь `po_token` и `visitorData` из запросов

2. **Через Android (рекомендуется для музыки):**
   - Установить YTDLnis на Android
   - Использовать встроенный генератор PO Token
   - Скопировать сгенерированный токен

**Применение PO Token в коде:**

```python
# В youtube_service.py, добавить в ydl_opts['extractor_args']['youtube']:
'po_token': 'YOUR_PO_TOKEN_HERE',
'visitor_data': 'YOUR_VISITOR_DATA_HERE'
```

### Вариант 3: Множественные Player Clients (Уже реализовано)

Наш бот уже использует стратегию YTDLnis:
- `android_creator` - для обычных видео
- `mediaconnect` - для защищенного контента
- `android` - базовый Android клиент
- `ios` - iOS клиент
- `default` - стандартный клиент (с cookies)

## Текущая реализация

Бот автоматически использует:

**С cookies:**
```python
player_client: ['default', 'mediaconnect', 'android']
player_skip: ['webpage', 'configs']
```

**Без cookies:**
```python
player_client: ['android_creator', 'mediaconnect', 'android', 'ios']
player_skip: ['webpage', 'configs']
```

## Отладка

Проверить логи на сервере:
```bash
ssh root@65.109.142.30 "tail -f /opt/telegram-cover-bot/logs/bot.log | grep -i youtube"
```

## Ссылки

- [YTDLnis GitHub](https://github.com/deniscerri/ytdlnis)
- [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide)
- [YouTube Bot Detection Issue](https://github.com/yt-dlp/yt-dlp/issues/13067)
