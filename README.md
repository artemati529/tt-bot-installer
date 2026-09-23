# tt-bot installer

[![TrustTunnel](https://img.shields.io/badge/for-TrustTunnel-blue?logo=github)](https://github.com/TrustTunnel/TrustTunnel)
[![tests](https://github.com/artemati529/tt-bot-installer/actions/workflows/tests.yml/badge.svg)](https://github.com/artemati529/tt-bot-installer/actions/workflows/tests.yml)

Устанавливает Telegram-бот администрирования [TrustTunnel](https://github.com/TrustTunnel/TrustTunnel)
VPN на чистую Debian/Ubuntu VM. **Не устанавливает и не настраивает сам
TrustTunnel** — это отдельный шаг, см. [официальный проект](https://github.com/TrustTunnel/TrustTunnel).

## Предварительные условия

- TrustTunnel уже установлен и настроен в `/opt/trusttunnel`: бинарник
  `trusttunnel_endpoint`, `vpn.toml`, `hosts.toml`, `credentials.toml`,
  `trusttunnel.service` активен.
- Классический (не Docker) деплой: бот управляет TrustTunnel через
  `systemctl` и прямой вызов бинарника на хосте — с контейнеризованным
  TrustTunnel сейчас не работает.
- Python 3.11+.
- Root-доступ на VM.
- Токен Telegram-бота (`@BotFather`) и свой числовой Telegram ID (`@userinfobot`).

## Установка

Одной командой (нужен root; не root — добавь `sudo` перед `bash`):

```bash
curl -fsSL https://raw.githubusercontent.com/artemati529/tt-bot-installer/main/install.sh | bash -s -
```

Или из клона:

```bash
git clone https://github.com/artemati529/tt-bot-installer.git
cd tt-bot-installer
./install.sh
```

Скрипт спросит `BOT_TOKEN`, `ALLOWED_USER_ID`, адрес VPN-эндпоинта
(`host:port`, должен совпадать с тем, что в `hosts.toml`/`vpn.toml`),
имя сервера для клиентских конфигов, порт мониторинга (по умолчанию
берётся из `listen_address` в `vpn.toml`) и настроено ли уже автообновление
сертификата — если нет, предложит выпустить его через certbot и сам
пропишет пути в `hosts.toml` (подробнее ниже). Если TrustTunnel не найден
в `/opt/trusttunnel` — установка остановится с понятной ошибкой.

## Сертификат

Карточка сертификата в боте читает `certbot.timer` и лог
`/var/log/letsencrypt/letsencrypt.log` — если сертификат для TrustTunnel
выпущен не через certbot (или через certbot, но без автообновления), она
будет показывать неполные данные. Установщик спрашивает про это отдельно:

- **уже настроено** — просто ставит пакет `certbot`, ничего не меняет;
- **не настроено, выпустить сейчас** — спросит домен (по умолчанию берёт
  `hostname` из `hosts.toml`) и e-mail, выпустит сертификат
  (`certbot certonly --standalone`, нужен свободный порт 80), пропишет
  `cert_chain_path`/`private_key_path` в `hosts.toml` (старый файл
  сохраняется рядом как `.bak-<дата>`), поставит deploy-hook на
  перезагрузку `trusttunnel.service` при продлении и перечитает
  конфиг сразу;
- **не настроено, пропустить** — ничего не делает, карточка сертификата
  в боте будет неполной, пока не настроишь вручную.

## Что делает

- ставит `python3-venv` и `certbot`;
- создаёт venv в `/opt/tt-bot/.venv`;
- ставит зависимости из `requirements.txt` (версии зафиксированы);
- копирует `bot.py` в `/opt/tt-bot/bot.py` (0700);
- пишет `/opt/tt-bot/.env` (0600) с введёнными значениями;
- создаёт, включает и (пере)запускает `tt-bot.service` (systemd).

Повторный запуск безопасен: прежний `.env` сохраняется как `.env.bak-<дата>`,
ключи, которые установщик не спрашивает (`BACKUP_KEEP_*`, `BOT_LOCK_PATH`,
`METRICS_CLIENTS_URL`), переносятся, бот перезапускается с новым `bot.py`.

## Обновление бота на сервере

```bash
git pull
sudo cp bot.py /opt/tt-bot/bot.py
sudo systemctl restart tt-bot.service
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

Покрытие `bot.py` — около 80% строк (точное: `pytest --cov=. tests/`), чистые mypy/ruff/pyflakes.

## Файлы

- `install.sh` — установщик.
- `bot.py` — исходник бота.
- `requirements.txt` — зафиксированные версии зависимостей.
- `requirements-dev.txt`, `tests/` — тесты для `bot.py`.

## Ссылки

- [TrustTunnel](https://github.com/TrustTunnel/TrustTunnel) — сам VPN-протокол и `trusttunnel_endpoint`, которым управляет этот бот.
- [trusttunnel.org](https://trusttunnel.org/) — официальный сайт проекта.
