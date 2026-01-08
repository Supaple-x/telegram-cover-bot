# 🚀 Развертывание Telegram Music Bot

Подробная инструкция по развертыванию бота на сервере Ubuntu 20.04.6 LTS.

## 📋 Информация о сервере

- **Сервер:** Ubuntu 20.04.6 LTS
- **IP:** 65.109.142.30
- **Путь проекта:** `/opt/telegram-cover-bot/`
- **Пользователь:** root

## 🔑 Токены и ключи

```bash
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=8402191828:AAGfs0rKUBJmmDo2vkPQd4GszSqgLBD81xg

# YouTube Data API v3 Key
YOUTUBE_API_KEY=AIzaSyCaKNRlYtKNEqHTtpoFMm0s9jYdAYmtVmE
```

## 📝 Пошаговая инструкция

### Шаг 1: Подключение к серверу

```bash
ssh root@65.109.142.30
```

### Шаг 2: Обновление системы и установка зависимостей

```bash
# Обновление системы
apt update && apt upgrade -y

# Установка Python и необходимых пакетов
apt install python3 python3-pip python3-venv ffmpeg git curl -y

# Проверка версий
python3 --version
pip3 --version
ffmpeg -version
```

### Шаг 3: Создание структуры проекта

```bash
# Создание директории проекта
mkdir -p /opt/telegram-cover-bot
cd /opt/telegram-cover-bot

# Создание поддиректорий
mkdir -p handlers services utils logs downloads systemd
```

### Шаг 4: Загрузка файлов проекта

```bash
# Если у вас есть Git репозиторий:
# git clone https://github.com/YOUR_USERNAME/telegram-cover-bot.git /opt/telegram-cover-bot

# Или скопируйте файлы вручную с локальной машины:
# scp -r telegram-cover-bot/* root@65.109.142.30:/opt/telegram-cover-bot/
```

### Шаг 5: Создание виртуального окружения

```bash
cd /opt/telegram-cover-bot

# Создание виртуального окружения
python3 -m venv venv

# Активация виртуального окружения
source venv/bin/activate

# Обновление pip
pip install --upgrade pip
```

### Шаг 6: Установка зависимостей

```bash
# Установка Python пакетов
pip install -r requirements.txt

# Проверка установленных пакетов
pip list
```

### Шаг 7: Настройка переменных окружения

```bash
# Создание .env файла
nano .env
```

Содержимое `.env` файла:
```bash
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=8402191828:AAGfs0rKUBJmmDo2vkPQd4GszSqgLBD81xg

# YouTube Data API v3 Key
YOUTUBE_API_KEY=AIzaSyCaKNRlYtKNEqHTtpoFMm0s9jYdAYmtVmE

# VK API Token (опционально)
VK_TOKEN=

# Yandex Music Token (опционально)
YANDEX_MUSIC_TOKEN=
```

Сохраните файл: `Ctrl+X`, затем `Y`, затем `Enter`

### Шаг 8: Настройка прав доступа

```bash
# Установка прав на директории
chmod 755 /opt/telegram-cover-bot
chmod 755 /opt/telegram-cover-bot/logs
chmod 755 /opt/telegram-cover-bot/downloads

# Установка прав на исполняемые файлы
chmod +x /opt/telegram-cover-bot/bot.py

# Проверка прав
ls -la /opt/telegram-cover-bot/
```

### Шаг 9: Тестовый запуск

```bash
cd /opt/telegram-cover-bot
source venv/bin/activate

# Тестовый запуск бота
python3 bot.py
```

**Ожидаемый вывод:**
```
[2025-01-05 04:30:00] [INFO] [__main__] Starting bot...
[2025-01-05 04:30:01] [INFO] [__main__] Bot started: @your_bot_username (Your Bot Name)
[2025-01-05 04:30:01] [INFO] [__main__] Bot ID: 8402191828
[2025-01-05 04:30:01] [INFO] [__main__] Bot commands set successfully
```

Если бот запустился успешно, остановите его: `Ctrl+C`

### Шаг 10: Настройка systemd сервиса

```bash
# Копирование unit файла
cp /opt/telegram-cover-bot/systemd/telegram-cover-bot.service /etc/systemd/system/

# Перезагрузка systemd
systemctl daemon-reload

# Включение автозапуска
systemctl enable telegram-cover-bot

# Запуск сервиса
systemctl start telegram-cover-bot

# Проверка статуса
systemctl status telegram-cover-bot
```

**Ожидаемый статус:**
```
● telegram-cover-bot.service - Telegram Cover Bot - Music Search and Download Bot
   Loaded: loaded (/etc/systemd/system/telegram-cover-bot.service; enabled; vendor preset: enabled)
   Active: active (running) since Sat 2025-01-05 04:30:00 UTC; 10s ago
 Main PID: 12345 (python3)
    Tasks: 3 (limit: 2048)
   Memory: 45.2M
   CGroup: /system.slice/telegram-cover-bot.service
           └─12345 /usr/bin/python3 /opt/telegram-cover-bot/bot.py
```

### Шаг 11: Мониторинг и логи

```bash
# Просмотр логов в реальном времени
journalctl -u telegram-cover-bot -f

# Или файловые логи
tail -f /opt/telegram-cover-bot/logs/bot.log

# Просмотр последних 50 строк логов
journalctl -u telegram-cover-bot -n 50

# Просмотр логов за последний час
journalctl -u telegram-cover-bot --since "1 hour ago"
```

## 🛠️ Управление сервисом

```bash
# Запуск сервиса
systemctl start telegram-cover-bot

# Остановка сервиса
systemctl stop telegram-cover-bot

# Перезапуск сервиса
systemctl restart telegram-cover-bot

# Статус сервиса
systemctl status telegram-cover-bot

# Включить автозапуск
systemctl enable telegram-cover-bot

# Отключить автозапуск
systemctl disable telegram-cover-bot
```

## 🔧 Обновление бота

```bash
# Остановка сервиса
systemctl stop telegram-cover-bot

# Переход в директорию проекта
cd /opt/telegram-cover-bot

# Активация виртуального окружения
source venv/bin/activate

# Обновление кода (если используется Git)
git pull origin main

# Обновление зависимостей (если изменились)
pip install -r requirements.txt --upgrade

# Запуск сервиса
systemctl start telegram-cover-bot

# Проверка статуса
systemctl status telegram-cover-bot
```

## 🐛 Устранение неполадок

### Проблема: Бот не запускается

**Решение:**
```bash
# Проверьте логи
journalctl -u telegram-cover-bot -n 20

# Проверьте .env файл
cat /opt/telegram-cover-bot/.env

# Проверьте права доступа
ls -la /opt/telegram-cover-bot/

# Попробуйте запустить вручную
cd /opt/telegram-cover-bot
source venv/bin/activate
python3 bot.py
```

### Проблема: Ошибки при скачивании

**Решение:**
```bash
# Проверьте установку ffmpeg
ffmpeg -version

# Проверьте права на папку downloads
ls -la /opt/telegram-cover-bot/downloads/

# Проверьте свободное место на диске
df -h
```

### Проблема: YouTube API лимиты

**Решение:**
1. Получите собственный YouTube API ключ
2. Или используйте только YouTube Music (не требует API ключа)
3. Временно отключите YouTube источник в коде

### Проблема: Высокое потребление памяти

**Решение:**
```bash
# Проверьте использование памяти
free -h
ps aux | grep python

# Перезапустите сервис
systemctl restart telegram-cover-bot

# Настройте ротацию логов
logrotate -f /etc/logrotate.conf
```

## 📊 Мониторинг производительности

```bash
# Использование ресурсов
htop

# Статистика сервиса
systemctl show telegram-cover-bot

# Размер логов
du -sh /opt/telegram-cover-bot/logs/

# Размер временных файлов
du -sh /opt/telegram-cover-bot/downloads/
```

## 🔒 Безопасность

```bash
# Настройка файрвола (если нужно)
ufw allow ssh
ufw enable

# Проверка открытых портов
netstat -tulpn

# Обновление системы
apt update && apt upgrade -y
```

## 📋 Чек-лист развертывания

- [ ] ✅ Подключение к серверу
- [ ] ✅ Установка зависимостей (Python, ffmpeg)
- [ ] ✅ Создание структуры проекта
- [ ] ✅ Загрузка файлов проекта
- [ ] ✅ Создание виртуального окружения
- [ ] ✅ Установка Python пакетов
- [ ] ✅ Настройка .env файла
- [ ] ✅ Тестовый запуск бота
- [ ] ✅ Настройка systemd сервиса
- [ ] ✅ Проверка автозапуска
- [ ] ✅ Настройка мониторинга логов
- [ ] ✅ Тестирование функционала бота

## 🎯 Финальная проверка

1. **Проверьте статус сервиса:**
   ```bash
   systemctl status telegram-cover-bot
   ```

2. **Проверьте логи:**
   ```bash
   tail -f /opt/telegram-cover-bot/logs/bot.log
   ```

3. **Протестируйте бота в Telegram:**
   - Найдите бота по username
   - Отправьте `/start`
   - Попробуйте найти и скачать трек

4. **Проверьте автозапуск:**
   ```bash
   systemctl reboot
   # После перезагрузки:
   systemctl status telegram-cover-bot
   ```

## 📞 Поддержка

Если возникли проблемы:

1. Проверьте логи: `journalctl -u telegram-cover-bot -f`
2. Убедитесь что все зависимости установлены
3. Проверьте токены в .env файле
4. Создайте issue в GitHub репозитории

---

**🎉 Поздравляем! Ваш Telegram Music Bot успешно развернут и готов к работе!**
