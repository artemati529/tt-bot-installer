"""tt-bot — Telegram-бот управления узлом TrustTunnel.

Creator: VNL Corporation  <tema@akado.ru>

FILE MAP (секции сверху вниз):
  1.  Settings & env              — ENV_PATH, пути конфигов, load_env, переменные,
                                    acquire_runtime_lock, _client_endpoint_address
  2.  Access & observability      — safe_callback_route, traced_callback,
                                    log_unhandled_error, is_allowed/allow_guard,
                                    reset_nav_state/cancel_add_flow
  3.  UI primitives               — busy_set/clear/label, busy_guard, cb_answer,
                                    safe_edit_message_text, upsert_ui_message,
                                    send_ui_card, send_inline_message, html-хелперы
  4.  QR & deeplink               — deeplink_qr_png, qr_page_url, reply_deeplink_with_qr
  5.  UI: text & keyboards        — UI_*, _status_emoji, confirm_kb, card_footer_row,
                                    refresh_back_row, merge_inline_kb, hub/vpn/server kb
  6.  Subprocess & caching        — CommandError, run_process/run_cmd/run_shell,
                                    cached_compute (thread-safe, single-flight)
  7.  Monitoring & server cards   — server/info card, cert card + certbot timer,
                                    clients card, logs view, metrics/ram/disk/network
  8.  Backups & restore           — create_configs_backup, restore_file/_multiple,
                                    _stamped_backup, _prune_backup_dir
  9.  Domain: credentials/rules   — atomic writes, credentials/prefix-map/profiles,
                                    rules.toml parser + append/remove/tag,
                                    audit/repair/cleanup rules sync
  10. Users & config generation   — list_usernames, validate/apply_tt_config_change,
                                    generate_deeplink/toml, _build_client_style_toml,
                                    add_user_and_make_link, rotate/delete user, versions
  11. Actions & background tasks  — build_add_conversation, run_* (backup/restore/
                                    os_upgrade/tt_upgrade/reboot), run_user_pick,
                                    _*_sync, _schedule_background_task, confirm-колбэки
                                    (backup_confirm/restore_backup/reboot/os_upgrade/
                                    update_tt/restart_tt_confirm), undo_callback
  12. Navigation & command handlers— send_home_screen, nav/srv/vpn/copyhost callbacks,
                                    user_action_* callbacks, delete_user_callback,
                                    cert_log_callback, rules_sync, user search,
                                    /start /status /myid, menu
  13. Scaffold & add-flow         — _burn_scaffold/_track_*/_cleanup_*, add_entry_cb,
                                    add_username/password/prefix/protocol,
                                    rotate/export pick, toml_export
  14. Route table & main          — CallbackRoute, CALLBACK_ROUTES,
                                    build_callback_query_handler, main()

CALLBACK_DATA REGISTRY (префикс → что открывает; полная сверка — CALLBACK_ROUTES,
секция 14; префиксы не переименовывать — старые кнопки могут висеть в чатах):
  nav:*                      — навигация (home/vpn/server/close/servercard/info/
                               clients/users:N/logs/cert)
  srv:*                      — меню «Сервер» (restart/backup/restore/ttupd/osupd/reboot)
  vpn:*                      — меню «VPN» (find/rotate/export/del); vpn:add — старт
                               ConversationHandler добавления пользователя
  addpref:*/addproto:*/addcancel — шаги ConversationHandler добавления (вне CALLBACK_ROUTES)
  copyhost:msg               — карточка с доменом endpoint
  rotpick:/exppick:/expproto: — ротация/экспорт пароля для пользователя из списка
  tc:/tp:                    — выбор протокола и выдача TOML-конфига
  delask:/del2:/deldo:/delcancel: — 2-шаговое подтверждение удаления пользователя
  resask:/resdo:/rescancel:  — подтверждение восстановления файла(ов) из бэкапа
  ttupd_yes|no, rbdo|rbcancel, osupd_yes|no, ttrst_yes|no, bak:yes|no — confirm-пары
  infor                      — обновить карточку «Сервер»
  certlog:20|50              — хвост лога certbot (N строк)
  searchcancel               — отмена поиска пользователя
  ss:/ul:/uf:/udev:          — постраничные списки клиентов/пользователей, фильтр,
                               карточка пользователя
  uqr:|ure:/utc:/ulink:/uall:/urot:/udel: — быстрые действия над юзером из списка
                               (QR/TOML/ссылка/всё сразу/ротация/удаление)
  rulesync:clean|repair|view — синхронизация rules.toml
  logf:*                     — фильтр лога (level:lines:chunk)
  undo:go                    — отмена последнего delete/rotate/restore

_SYNC КОНВЕНЦИЯ: суффикс _sync = функция блокирующая, вызывать только через
asyncio.to_thread. Не добавлять суффикс доменным функциям про файлы/данные
(create_configs_backup и т.п.) — суффикс только для функций, дёргающих
подпроцессы/systemctl/сеть.
"""

import asyncio
import base64
import contextlib
import datetime as dt
import difflib
import fcntl
import functools
import html
import io
import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import tarfile
import threading
import urllib.error
import urllib.request
import warnings
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic
from typing import Any, cast

try:
    import tomlkit
except ImportError as e:
    raise RuntimeError("Не найден tomlkit. Установи пакет: pip install 'tomlkit>=0.13,<1'") from e

try:
    import qrcode
    from qrcode import constants as qr_constants
    from qrcode.image.pil import PilImage
except ImportError as e:
    raise RuntimeError("Не найден qrcode. Установи пакет: pip install qrcode[pil]") from e

from telegram import (
    CallbackQuery,
    InaccessibleMessage,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    MaybeInaccessibleMessage,
    Message,
    ReplyKeyboardMarkup,
    Update,
)

try:
    from telegram import CopyTextButton

    _HAS_COPY_TEXT = True
except ImportError:
    CopyTextButton = None  # type: ignore[misc, assignment]
    _HAS_COPY_TEXT = False
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    Defaults,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning

# per_message=False в build_add_conversation() — намеренно (кнопки живут на
# разных сообщениях по состояниям, per_message=True сломал бы этот сценарий).
# PTB честно предупреждает об этом на каждом импорте/тесте — предупреждение
# ожидаемо и не про баг, гасим точечно только его текст.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False'.*CallbackQueryHandler.*will not be tracked",
    category=PTBUserWarning,
)

# Настройки
ENV_PATH = Path(os.environ.get("TT_BOT_ENV_PATH", "/opt/tt-bot/.env"))
TT_DIR = Path("/opt/trusttunnel")
CRED_FILE = TT_DIR / "credentials.toml"
RULES_FILE = TT_DIR / "rules.toml"
PREFIX_MAP_FILE = TT_DIR / "user_prefix_map.toml"
USER_PROFILES_FILE = TT_DIR / "user_profiles.json"
CERT_FILE = TT_DIR / "certs" / "cert.pem"
CERT_RENEW_SCRIPT = TT_DIR / "renew_trusttunnel_cert.sh"
LE_CERT_BASE_DIR = Path("/etc/letsencrypt/live")
LE_LOG_FILE = Path("/var/log/letsencrypt/letsencrypt.log")
SERVICE_NAME = "trusttunnel.service"
# Username укладывается в текст inline-кнопки (лимит Telegram 64 байта).
MAX_USERNAME_LEN = 50
TG_CAPTION_SAFE = 900
BACKUP_FILES = ["vpn.toml", "hosts.toml", "credentials.toml", "rules.toml"]

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

ASK_ADD_USERNAME, ASK_ADD_PASSWORD, ASK_ADD_PREFIX, ASK_ADD_PROTOCOL = range(4)
CRED_LOCK = asyncio.Lock()
USER_LIST_FILTER_KEY = "users_filter"
USER_LIST_FILTERS = {"all": "Все", "online": "Онлайн", "offline": "Оффлайн"}
USER_SEARCH_SCAFFOLD_KEY = "user_search_scaffold"
ADD_FLOW_SCAFFOLD_KEY = "add_flow_scaffold"
ROTATE_SCAFFOLD_KEY = "rotate_scaffold"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx/httpcore на INFO логируют КАЖДЫЙ HTTP-запрос к Telegram (в т.ч. getUpdates
# раз в 10с) — журнал тонет в шуме, реальные события (наши callback start/done,
# ошибки) теряются между ними. Нужны нам только их предупреждения/ошибки.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("tt-bot")

CALLBACK_ROUTES_WITH_USER_ARGS = {
    "udev",
    "uqr",
    "ure",
    "utc",
    "ulink",
    "uall",
    "tc",
    "tp",
    "urot",
    "udel",
    "rotpick",
    "exppick",
    "expproto",
    "delask",
    "del2",
    "deldo",
    "delcancel",
}


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def safe_callback_route(data: str | None) -> str:
    if not data:
        return "<empty>"
    parts = data.split(":")
    if parts[0] in CALLBACK_ROUTES_WITH_USER_ARGS:
        if parts[0] in {"tp", "expproto"} and len(parts) >= 3:
            return f"{parts[0]}:{parts[1]}:<arg>"
        return f"{parts[0]}:<arg>"
    # Маршрут из CALLBACK_ROUTES вне списка выше — фиксированный под-маршрут
    # без пользовательского аргумента (nav:vpn, ss:2, certlog:50), логируем целиком.
    if any(re.match(route.pattern, data) for route in CALLBACK_ROUTES):
        return data
    # Совсем неизвестный маршрут: аргумент не должен протекать в журнал как есть.
    return f"{parts[0]}:<unknown>"


def traced_callback(name: str, handler):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        route = safe_callback_route(q.data if q else None)
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id if update.effective_chat else None
        started = monotonic()
        logger.info(
            "callback start handler=%s route=%s user_id=%s chat_id=%s",
            name,
            route,
            user_id,
            chat_id,
        )
        try:
            return await handler(update, context)
        except Exception:
            logger.exception("callback failed handler=%s route=%s", name, route)
            raise
        finally:
            elapsed_ms = int((monotonic() - started) * 1000)
            logger.info(
                "callback done handler=%s route=%s elapsed_ms=%s",
                name,
                route,
                elapsed_ms,
            )

    return wrapper


async def log_unhandled_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Только лог (journalctl) — уведомление в чат убрано: сетевые обрывы были
    основным источником сообщений, а не реальные баги, и само уведомление
    ничего не даёт кроме отвлечения. Полный traceback остаётся в логах."""
    error = context.error
    route = None
    if isinstance(update, Update) and update.callback_query:
        route = safe_callback_route(update.callback_query.data)
    exc_info = None
    if error is not None:
        exc_info = (type(error), error, error.__traceback__)
    logger.error("unhandled update error route=%s", route or "n/a", exc_info=exc_info)


def _detect_tt_listen_port() -> int | None:
    vpn_path = TT_DIR / "vpn.toml"
    if not vpn_path.exists():
        return None
    try:
        doc = tomlkit.parse(vpn_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    listen = str(doc.get("listen_address", "")).strip()
    port = listen.rsplit(":", 1)[-1] if ":" in listen else ""
    return int(port) if port.isdigit() else None


env = load_env(ENV_PATH)
BOT_TOKEN = env["BOT_TOKEN"]
ALLOWED_USER_ID = int(env["ALLOWED_USER_ID"])
ADDRESS = env.get("ENDPOINT_ADDRESS", "").strip()
SERVER_NAME = env.get("SERVER_NAME", "trusttunnel").strip()
VPN_MONITOR_PORT = int(env.get("VPN_MONITOR_PORT") or _detect_tt_listen_port() or 443)
BACKUP_KEEP_CREDENTIALS = max(1, int(env.get("BACKUP_KEEP_CREDENTIALS", "40")))
BACKUP_KEEP_RULES = max(1, int(env.get("BACKUP_KEEP_RULES", "40")))
BACKUP_KEEP_RESTORE_PREV = max(1, int(env.get("BACKUP_KEEP_RESTORE_PREV", "30")))
BOT_LOCK_PATH = Path(env.get("BOT_LOCK_PATH", "/run/tt-bot.lock"))

if not ADDRESS:
    raise RuntimeError("ENDPOINT_ADDRESS пустой в /opt/tt-bot/.env (домен для -a в trusttunnel_endpoint)")


def acquire_runtime_lock():
    lock_file = BOT_LOCK_PATH.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as e:
        lock_file.close()
        raise RuntimeError(
            f"tt-bot уже запущен: lock занят ({BOT_LOCK_PATH})"
        ) from e
    lock_file.write(f"{os.getpid()}\n")
    lock_file.flush()
    return lock_file


def _client_endpoint_address(address: str) -> str:
    """Убирает явный :443 из клиентского endpoint."""
    if address.endswith(":443"):
        return address[: -len(":443")]
    return address


def is_allowed(update: Update) -> bool:
    u = update.effective_user
    chat = update.effective_chat
    if not u or not chat:
        return False
    ok = u.id == ALLOWED_USER_ID and chat.type == "private"
    if not ok:
        logger.warning("access denied user_id=%s username=%s chat_type=%s", u.id, u.username or "", getattr(chat, "type", ""))
    return ok


async def _deny_access(update: Update) -> None:
    """Единый ответ на отказ в доступе: тост для callback-query (клиенту
    нужен ответ, иначе кнопка виснет крутящимся спиннером), тишина для
    обычных сообщений/команд — не выдаём чужим, что бот вообще отвечает."""
    if update.callback_query:
        await cb_answer(update.callback_query, "Нет доступа", alert=True)


def allow_guard(handler, *, conv_end: bool = False):
    """conv_end=True — для состояний ConversationHandler, где отказ должен
    завершить диалог (ConversationHandler.END), а не просто вернуть None
    (что для states означает "остаться в том же состоянии")."""
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_allowed(update):
            await _deny_access(update)
            return ConversationHandler.END if conv_end else None
        return await handler(update, context)
    return wrapper


def _ud(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any]:
    """context.user_data типизирован PTB как Optional, но всегда dict в рантайме."""
    assert context.user_data is not None
    return context.user_data


def _chat_id(update: Update) -> int:
    assert update.effective_chat is not None
    return update.effective_chat.id


def _accessible(msg: MaybeInaccessibleMessage | None) -> Message | None:
    """InaccessibleMessage не имеет .chat_id и большинства полей Message — сводим к None."""
    if isinstance(msg, InaccessibleMessage):
        return None
    return cast("Message | None", msg)


def clear_rotate_wait(context: ContextTypes.DEFAULT_TYPE) -> None:
    _ud(context).pop("pending_rotate_username", None)


def clear_all_pending_text_waits(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Одновременно один ожидающий ввод — новый сбрасывает прежний."""
    _ud(context).pop("pending_rotate_username", None)
    _ud(context).pop("pending_user_search", None)


async def cancel_add_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "add_flow_active",
        "pending_add_username",
        "pending_add_password",
        "pending_add_random_prefix",
    ):
        _ud(context).pop(key, None)
    await _cleanup_add_flow_scaffold(context.bot, context)


async def reset_nav_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сброс состояния при уходе с текущего экрана/сценария: снимает ожидание
    ротации/поиска (с scaffold), завершает диалог добавления пользователя."""
    clear_rotate_wait(context)
    await _cleanup_rotate_scaffold(context.bot, context)
    _ud(context).pop("pending_user_search", None)
    await _cleanup_user_search_scaffold(context.bot, context)
    _ud(context).pop("pending_tt_update", None)
    await cancel_add_flow(context)


CLIP_TEXT_LIMIT = 3800
CLIP_TEXT_LIMIT_IN_BLOCKQUOTE = 3500  # запас под <blockquote>/<pre>-обвязку и остальной текст карточки


def clip_text(text: str, limit: int = CLIP_TEXT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n\n...output truncated"


def is_message_not_modified(exc: BaseException) -> bool:
    return "message is not modified" in str(exc).lower()


UI_MESSAGE_ID_KEY = "ui_message_id"
BUSY_INFO: dict[str, Any] = {}
BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()

UNDO_TTL_SEC = 300
PENDING_UNDO_KEY = "pending_undo"


def _set_pending_undo(context: ContextTypes.DEFAULT_TYPE, kind: str, payload: dict[str, Any]) -> None:
    _ud(context)[PENDING_UNDO_KEY] = {"kind": kind, "payload": payload, "at": monotonic()}


def _pop_pending_undo(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    info = _ud(context).pop(PENDING_UNDO_KEY, None)
    if not info or monotonic() - info["at"] > UNDO_TTL_SEC:
        return None
    return {"kind": info["kind"], "payload": info["payload"]}


def _with_undo_row(kb: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Отменить", callback_data="undo:go")], *kb.inline_keyboard])


BUSY_MARKER_FILE = TT_DIR / ".tt-bot-busy"


def busy_set(what: str) -> None:
    BUSY_INFO.clear()
    BUSY_INFO["what"] = what
    BUSY_INFO["started"] = monotonic()
    try:
        BUSY_MARKER_FILE.write_text(what, encoding="utf-8")
    except OSError:
        pass


def busy_clear() -> None:
    BUSY_INFO.clear()
    BUSY_MARKER_FILE.unlink(missing_ok=True)


def _consume_stale_busy_marker() -> str | None:
    """При старте: маркер занятости с прошлого процесса значит, что apt/
    systemctl-операция могла не завершиться штатно (бота убили посреди неё)."""
    try:
        what = BUSY_MARKER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    BUSY_MARKER_FILE.unlink(missing_ok=True)
    return what or None


def busy_label() -> str | None:
    if not BUSY_INFO:
        return None
    mins = int((monotonic() - BUSY_INFO["started"]) // 60)
    tail = "меньше минуты" if mins == 0 else f"{mins} мин"
    return f"{BUSY_INFO['what']} ({tail})"


async def _reject_if_busy(update: Update) -> bool:
    label = busy_label()
    if label is None:
        return False
    if update.callback_query:
        await cb_answer(update.callback_query, f"Жди: {label}")
    elif update.message:
        await update.message.reply_text(f"⏳ Жди: {label}")
    return True


def busy_guard(handler):
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await _reject_if_busy(update):
            return
        return await handler(update, context)

    return wrapper


async def cb_answer(
    q,
    text: str | None = None,
    *,
    alert: bool = False,
) -> None:
    try:
        await q.answer(text=text, show_alert=alert)
    except Exception:
        try:
            await q.answer()
        except Exception as e:
            logger.debug("Не удалось показать toast: %s", e)


async def safe_edit_message_text(message, text: str, **kwargs) -> bool:
    """Редактирует сообщение; False если Telegram считает текст неизменённым."""
    try:
        if hasattr(message, "edit_message_text"):
            await message.edit_message_text(text, **kwargs)
        elif hasattr(message, "edit_text"):
            await message.edit_text(text, **kwargs)
        else:
            raise TypeError(f"Unsupported message object for editing: {type(message)!r}")
        return True
    except BadRequest as e:
        if is_message_not_modified(e):
            return False
        raise


async def best_effort_edit(message, text: str, **kwargs) -> None:
    """Для except-блоков, которые уже сообщают об ошибке: если сам edit
    тоже падает (сообщение успели удалить), не роняем обработчик второй раз."""
    try:
        await safe_edit_message_text(message, text, **kwargs)
    except Exception:
        logger.debug("Не удалось отобразить сообщение об ошибке")


def _remember_ui_message(context: ContextTypes.DEFAULT_TYPE, message: Message | None) -> None:
    if message:
        _ud(context)[UI_MESSAGE_ID_KEY] = message.message_id


async def _delete_message_quiet(message: Message | None) -> None:
    if not message:
        return
    try:
        await message.delete()
    except Exception as e:
        logger.debug("Не удалось удалить сообщение: %s", e)


async def _delete_callback_source_quiet(q) -> None:
    await _delete_message_quiet(getattr(q, "message", None))


async def _clear_inline_keyboard_quiet(bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None,
        )
    except Exception as e:
        logger.debug("Не удалось снять inline-кнопки со старого сообщения: %s", e)


async def upsert_ui_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
    reply_markup=None,
    force_new: bool = False,
) -> None:
    msg_id = _ud(context).get(UI_MESSAGE_ID_KEY)
    if force_new and isinstance(msg_id, int):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.debug("Не удалось удалить старое UI-сообщение: %s", e)
        msg_id = None
    if isinstance(msg_id, int):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return
        except BadRequest as e:
            if is_message_not_modified(e):
                return
            await _clear_inline_keyboard_quiet(context.bot, chat_id, msg_id)
        except Exception as e:
            logger.debug("Не удалось отредактировать UI-сообщение: %s", e)
            await _clear_inline_keyboard_quiet(context.bot, chat_id, msg_id)
    msg = await send_inline_message(
        context.bot,
        chat_id,
        text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )
    _ud(context)[UI_MESSAGE_ID_KEY] = msg.message_id


def error_card(reason: str, what_next: str | None = None) -> str:
    text = f"❌ <b>{reason}</b>"
    if what_next:
        text += f"\n<i>Что делать: {what_next}</i>"
    return text


def step_card(title: str, step: int, total: int, action: str) -> str:
    return f"⏳ <b>{title}</b>\n[{step}/{total}] {action}"


async def send_ui_card(
    bot,
    cid: int,
    text: str,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    parse_mode: str | None = None,
    reply_markup=None,
    force_new: bool = False,
) -> None:
    if context is not None:
        await upsert_ui_message(
            context,
            cid,
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            force_new=force_new,
        )
        return
    await send_inline_message(
        bot,
        cid,
        text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )


async def send_inline_message(
    bot,
    chat_id: int,
    text: str,
    *,
    parse_mode: str | None = None,
    reply_markup=None,
    **kwargs,
):
    if reply_markup is not None and not isinstance(reply_markup, InlineKeyboardMarkup):
        raise TypeError(
            "send_inline_message accepts only inline keyboard markup; reply keyboard markup is not supported"
        )
    kwargs["disable_notification"] = True
    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
        **kwargs,
    )


def html_spoiler(inner: str) -> str:
    return f"<tg-spoiler>{html.escape(inner)}</tg-spoiler>"


def deeplink_spoiler_html(deeplink: str) -> str:
    """Deeplink — это credential (username+password+endpoint в query-строке).

    В чате показываем его целиком под спойлером: пароль не должен читаться
    открытым текстом, а копировать/вставить ссылку по тапу всё равно можно.
    """
    return f"<tg-spoiler><code>{html.escape(deeplink)}</code></tg-spoiler>"


def html_pre_block(body: str) -> str:
    esc = html.escape(body.strip())
    return f"<pre>{esc}</pre>"


def html_expandable_pre_block(body: str) -> str:
    esc = html.escape(body.strip())
    return f"<blockquote expandable><pre>{esc}</pre></blockquote>"


CLIENTS_PER_PAGE = 8
USERS_PER_PAGE = 6
LOG_ERR_RE = re.compile(r"(error|exception|fail|traceback|critical)", re.IGNORECASE)
LOG_WARN_RE = re.compile(r"(warn|warning|retry|timeout)", re.IGNORECASE)
MONITOR_CACHE_TTL_SEC = 8
MONITOR_CACHE: dict[str, tuple[float, Any]] = {}
METRICS_CLIENTS_URL = (env.get("METRICS_CLIENTS_URL", "") or "http://127.0.0.1:1987/clients").strip()
LOG_CHUNK_CHARS = 3200
CERT_WARN_DAYS = 14
# Только для TOML — у deeplink/QR нет поля роутинга.
SPLIT_RU_EXCLUSIONS = [
    "*.ru",
    "*.su",
    "*.yastatic.net",
    "*.yandex.net",
    "*.yandex.com",
    "*.vk.com",
    "*.vk.me",
    "www.gosuslugi.ru",
    "gu-st.ru",
]


def deeplink_qr_png(deeplink: str) -> bytes:
    """PNG с QR-кодом deeplink (tt://…)."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qr_constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(deeplink)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_page_url(deeplink: str) -> str:
    token = deeplink.replace("tt://?", "", 1)
    return f"https://trusttunnel.org/qr.html#tt={token}"


async def reply_deeplink_with_qr(
    message: Message,
    *,
    username: str,
    deeplink: str,
    action_label: str | None,
    mode_label: str | None = None,
    include_service: bool = True,
    png: bytes | None = None,
    delete_source: bool = False,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> None:
    qr_url = qr_page_url(deeplink)
    data = png if png is not None else await asyncio.to_thread(deeplink_qr_png, deeplink)
    lines: list[str] = []
    if action_label:
        lines.append(f"Действие: <code>{html.escape(action_label)}</code>")
    lines.append(f"Пользователь: <code>{html.escape(username)}</code>")
    if mode_label:
        lines.append(f"Режим: <code>{html.escape(mode_label)}</code>")
    if include_service:
        # systemctl живёт за пределами event loop — иначе зависший вызов
        # заморозит бота на весь timeout.
        svc = await asyncio.to_thread(run_cmd, ["systemctl", "is-active", SERVICE_NAME]) or "unknown"
        lines.append(f"Сервис: <code>{html.escape(svc)}</code>")
    # Ссылка несёт credential (deeplink целиком) в query — под спойлером,
    # как и текстовая выдача deeplink (см. deeplink_spoiler_html).
    cap = (
        "\n".join(lines)
        + "\n\n"
        f"<tg-spoiler><a href=\"{html.escape(qr_url)}\">Открыть deeplink trusttunnel.org/qr</a></tg-spoiler>"
    )
    if len(cap) > TG_CAPTION_SAFE:
        cap = cap[: TG_CAPTION_SAFE - 3] + "…"
    kb_rows: list[list[InlineKeyboardButton]] = [*(extra_rows or [])]
    if _HAS_COPY_TEXT and CopyTextButton is not None:
        kb_rows.append(
            [InlineKeyboardButton("📋 Копировать deeplink", copy_text=CopyTextButton(text=deeplink))]
        )
    kb_rows.append([InlineKeyboardButton("📄 TOML", callback_data=f"utc:{username}")])
    kb_rows.append([InlineKeyboardButton("🏠 Главная", callback_data="nav:home")])
    kb = InlineKeyboardMarkup(kb_rows)
    await message.reply_photo(
        photo=InputFile(io.BytesIO(data), filename="trusttunnel-qr.png"),
        caption=cap,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
        disable_notification=True,
    )
    if delete_source:
        # В сообщении мог остаться пароль, введённый вручную.
        await _delete_message_quiet(message)


# ----- UI -----
UI_WELCOME = (
    "<b>TrustTunnel</b> · панель сервера\n"
    f"<i>Узел:</i> <code>{html.escape(SERVER_NAME)}</code> · "
    f"<code>{html.escape(_client_endpoint_address(ADDRESS))}</code>"
)

UI_HOME = "<b>Главная</b>\n<i>Выбери раздел:</i>"

UI_OPEN_VPN = "👥 <b>VPN</b>\n<i>Учётные записи и конфиги клиентов.</i>"

UI_OPEN_SERVER = "⚙️ <b>Сервер</b>\n<i>Службы, бэкап, обновления.</i>"

def _status_emoji(state: str) -> str:
    s = (state or "").strip().lower()
    if s == "active":
        return "🟢"
    if s in ("failed", "inactive", "dead"):
        return "🔴"
    return "🟡"


def _copy_host_button(label: str = "📋 Домен") -> InlineKeyboardButton:
    if _HAS_COPY_TEXT and CopyTextButton is not None:
        return InlineKeyboardButton(label, copy_text=CopyTextButton(text=_client_endpoint_address(ADDRESS)))
    return InlineKeyboardButton(label, callback_data="copyhost:msg")


def confirm_kb(
    yes_cb: str,
    no_cb: str = "nav:home",
    *,
    yes_label: str = "✅ Да",
    no_label: str = "❌ Отмена",
    danger: bool = False,
) -> InlineKeyboardMarkup:
    yes_style = "danger" if danger else "success"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(yes_label, callback_data=yes_cb, style=yes_style)],
            [InlineKeyboardButton(no_label, callback_data=no_cb)],
        ]
    )


# Ключ — экран-родитель, значение — куда ведёт "Назад". "server" значит
# "родитель — хаб Сервера"; сам хаб Сервера использует ключ "home".
BACK_PARENT = {
    "home": "nav:home",
    "server": "nav:server",
    "users": "nav:vpn",
    "user": "nav:users:0",
    "rules": "nav:vpn",
    "vpn": "nav:home",
    "info": "nav:info",
}


def card_footer_row(parent: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton("⬅️ Назад", callback_data=BACK_PARENT.get(parent, "nav:home"), style="success")]


def refresh_back_row(refresh_cb: str, parent: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton("🔄 Обновить", callback_data=refresh_cb),
        *card_footer_row(parent),
    ]


def merge_inline_kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    built = [list(row) for row in rows if row]
    return InlineKeyboardMarkup(built)


def hub_inline_kb() -> InlineKeyboardMarkup:
    return merge_inline_kb(
        [
            InlineKeyboardButton("👥 VPN", callback_data="nav:vpn"),
            InlineKeyboardButton("⚙️ Сервер", callback_data="nav:server"),
        ],
        [
            InlineKeyboardButton("🖥 Нагрузка", callback_data="nav:info"),
        ],
        [
            InlineKeyboardButton("📈 Клиенты VPN", callback_data="nav:clients"),
        ],
    )


def vpn_hub_kb() -> InlineKeyboardMarkup:
    return merge_inline_kb(
        [
            InlineKeyboardButton("➕ Новый", callback_data="vpn:add"),
            InlineKeyboardButton("📋 Список", callback_data="nav:users:0"),
        ],
        [
            InlineKeyboardButton("🔍 Найти", callback_data="vpn:find"),
            InlineKeyboardButton("🔐 Пароль", callback_data="vpn:rotate"),
        ],
        [
            InlineKeyboardButton("📤 QR", callback_data="vpn:export"),
            InlineKeyboardButton("🗑 Удалить", callback_data="vpn:del"),
        ],
        [InlineKeyboardButton("🧹 Синхр. rules", callback_data="rulesync:view")],
        card_footer_row("vpn"),
    )


def server_hub_kb() -> InlineKeyboardMarkup:
    return merge_inline_kb(
        [InlineKeyboardButton("🖥 Карточка сервера", callback_data="nav:servercard")],
        [
            InlineKeyboardButton("♻️ Restart TT", callback_data="srv:restart"),
            InlineKeyboardButton("💾 Бэкап", callback_data="srv:backup"),
        ],
        [
            InlineKeyboardButton("♻️ Восстановить", callback_data="srv:restore"),
            InlineKeyboardButton("🚀 Обновить TT", callback_data="srv:ttupd"),
        ],
        [
            InlineKeyboardButton("🆙 Обновить ОС", callback_data="srv:osupd"),
            InlineKeyboardButton("🔁 Reboot", callback_data="srv:reboot"),
        ],
        [
            InlineKeyboardButton("🔐 Сертификат", callback_data="nav:cert"),
        ],
        card_footer_row("home"),
    )


# Утилиты
class CommandError(RuntimeError):
    pass


def _tail(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def _pipe_tail_reader(pipe, limit: int, out_box: list[bytes]) -> None:
    """Вычитывает pipe в память, оставляя только последние `limit` байт.

    Без этого болтливый процесс (apt-get upgrade) писал бы вывод неограниченно
    прямо на диск — лимит применялся бы лишь при чтении.
    """
    buf = bytearray()
    try:
        while True:
            chunk = pipe.read(65536)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > limit:
                del buf[: len(buf) - limit]
    finally:
        out_box.append(bytes(buf))
        try:
            pipe.close()
        except OSError:
            pass


def run_process(
    cmd: list[str],
    *,
    timeout: int = 60,
    retries: int = 0,
    cwd: Path | None = None,
    check: bool = True,
    capture_limit: int | None = None,
) -> subprocess.CompletedProcess[str]:
    assert retries >= 0
    last_err = ""
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        # Отдельная процесс-группа: по таймауту можно убить весь процесс.
        # С capture_limit stdout/stderr идут через лимитированный tail-ридер,
        # а не в безлимитные tmp-файлы.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=capture_limit is None,
            cwd=str(cwd) if cwd else None,
            start_new_session=True,
        )
        out_box: list[bytes] = []
        err_box: list[bytes] = []
        reader_threads: list[threading.Thread] = []
        if capture_limit is not None:
            for pipe, box in ((proc.stdout, out_box), (proc.stderr, err_box)):
                t = threading.Thread(
                    target=_pipe_tail_reader, args=(pipe, capture_limit, box), daemon=True
                )
                t.start()
                reader_threads.append(t)
        try:
            if capture_limit is None:
                out, err = proc.communicate(timeout=timeout)
            else:
                proc.wait(timeout=timeout)
                # Демонизирующийся потомок (например, постинст-скрипт при
                # apt upgrade) может унаследовать pipe и держать его открытым
                # даже после завершения нашего прямого потомка — тогда read()
                # никогда не получит EOF. Поэтому ждём с ограничением, а не
                # бесконечно.
                join_deadline = monotonic() + 5
                for t in reader_threads:
                    t.join(timeout=max(0.0, join_deadline - monotonic()))
                    if t.is_alive():
                        logger.warning(
                            "run_process: pipe reader still running after child exit "
                            "(cmd=%s) — a grandchild may be holding the pipe open",
                            " ".join(cmd),
                        )
                out = out_box[0].decode("utf-8", "replace") if out_box else ""
                err = err_box[0].decode("utf-8", "replace") if err_box else ""
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait()
            for t in reader_threads:
                t.join()
            last_err = f"timeout after {timeout}s"
            if attempt < attempts:
                continue
            raise CommandError(f"{' '.join(cmd)}: {last_err}") from None
        p = subprocess.CompletedProcess(cmd, proc.returncode, out, err)

        if check and p.returncode != 0:
            last_err = _tail(p.stderr or p.stdout or f"exit {p.returncode}")
            if attempt < attempts:
                continue
            raise CommandError(f"{' '.join(cmd)} failed: {last_err}") from None
        return p
    raise AssertionError("unreachable: attempts >= 1")


def run_cmd(cmd: list[str], timeout: int = 20) -> str:
    try:
        return run_process(cmd, timeout=timeout, retries=1, check=True).stdout.strip()
    except CommandError as e:
        # "" по-прежнему возвращаем (вызывающие оперются на `or "unknown"`),
        # но причину фиксируем в journalctl — «unknown» в карточке становится
        # диагностируемым, а не глотается молча. WARNING (а не DEBUG): логгер
        # по умолчанию INFO, на DEBUG сообщение бы не попало. Команды несекретные
        # (systemctl/ss/…); на healthy-сервисе ошибок нет → шума не будет.
        logger.warning("run_cmd failed: %s: %s", " ".join(cmd), e)
        return ""


def run_shell(command: str, timeout: int = 1800, *, capture_limit: int | None = None) -> tuple[int, str, str]:
    # bash -c, а не -lc: login-шелл грузит /etc/profile и ~/.profile —
    # медленнее и вносит недетерминированное окружение в детерминированные команды.
    try:
        p = run_process(
            ["bash", "-c", command],
            timeout=timeout,
            retries=0,
            check=False,
            capture_limit=capture_limit,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except CommandError as e:
        return 124, "", str(e)


# Кэш читается/пишется из разных потоков (asyncio.to_thread) и из event loop.
# _MONITOR_CACHE_LOCK хранит сам dict; _MONITOR_KEY_LOCKS даёт single-flight:
# по одному ключу одновременно считает только один поток, остальные ждут его
# результат вместо того, чтобы все запускать producer (thundering herd).
_MONITOR_CACHE_LOCK = threading.Lock()
_MONITOR_KEY_LOCKS: dict[str, threading.Lock] = {}


def _monitor_key_lock(key: str) -> threading.Lock:
    with _MONITOR_CACHE_LOCK:
        lock = _MONITOR_KEY_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _MONITOR_KEY_LOCKS[key] = lock
        return lock


def cached_compute(key: str, ttl_sec: int, producer):
    with _monitor_key_lock(key):
        now = monotonic()
        hit = MONITOR_CACHE.get(key)
        if hit and now - hit[0] <= ttl_sec:
            return hit[1]
        val = producer()
        with _MONITOR_CACHE_LOCK:
            MONITOR_CACHE[key] = (monotonic(), val)
        return val


def parse_meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, rest = line.split(":", 1)
                val = rest.strip().split()[0]
                out[key] = int(val)  # kB
    except (OSError, ValueError) as e:
        logger.debug("Не удалось разобрать /proc/meminfo: %s", e)
    return out


def kb_to_mib(kb: int) -> float:
    return kb / 1024.0


def _usage_bar(percent: float, width: int = 10) -> str:
    pct = max(0, min(100, round(percent)))
    filled = max(0, min(width, round(pct * width / 100)))
    return f"{'▓' * filled}{'░' * (width - filled)} {pct}%"


def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n %= 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def _format_uptime_seconds(seconds: float) -> str:
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        pieces = [f"{days} {_ru_plural(days, 'день', 'дня', 'дней')}"]
        if hours:
            pieces.append(f"{hours} {_ru_plural(hours, 'час', 'часа', 'часов')}")
        return ", ".join(pieces)
    if hours:
        pieces = [f"{hours} {_ru_plural(hours, 'час', 'часа', 'часов')}"]
        if minutes:
            pieces.append(f"{minutes} {_ru_plural(minutes, 'минута', 'минуты', 'минут')}")
        return ", ".join(pieces)
    if minutes:
        return f"{minutes} {_ru_plural(minutes, 'минута', 'минуты', 'минут')}"
    return "меньше минуты"


def _uptime_pretty() -> str:
    try:
        raw = Path("/proc/uptime").read_text(encoding="utf-8").split()[0]
        return _format_uptime_seconds(float(raw))
    except (OSError, ValueError, IndexError) as e:
        logger.debug("Не удалось прочитать /proc/uptime: %s", e)
        return "n/a"


def _http_get(url: str, *, timeout: int = 3, limit: int | None = None) -> str | None:
    """GET с User-Agent tt-bot; None при ошибке/не-200, иначе декодированное
    тело (обрезанное до `limit` байт, если задан)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tt-bot"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            if status != 200:
                return None
            data = resp.read(limit) if limit is not None else resp.read()
            return data.decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError) as e:
        logger.debug("Не удалось получить %s: %s", url, e)
        return None


def _http_get_sample(url: str, *, timeout: int = 3, limit: int = 256) -> str:
    return _http_get(url, timeout=timeout, limit=limit) or ""


def _disk_usage_summary() -> str:
    try:
        usage = shutil.disk_usage("/")
        if usage.total <= 0:
            return "Диск: <code>n/a</code>"
        used_percent = usage.used * 100 / usage.total
        free = html.escape(_human_bytes(usage.free, decimals=0))
        return f"Диск: <code>{_usage_bar(used_percent)}</code> · свободно <code>{free}</code>"
    except OSError as e:
        logger.debug("Не удалось получить статистику диска: %s", e)
        return "Диск: <code>n/a</code>"


def _network_iface_summary() -> str:
    iface = run_cmd(
        ["bash", "-c", "ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"dev\"){print $(i+1); exit}}'"],
    ) or "eth0"
    rx = tx = "n/a"
    rx_path = Path(f"/sys/class/net/{iface}/statistics/rx_bytes")
    tx_path = Path(f"/sys/class/net/{iface}/statistics/tx_bytes")
    try:
        if rx_path.exists() and tx_path.exists():
            rx_b = int(rx_path.read_text().strip())
            tx_b = int(tx_path.read_text().strip())
            rx, tx = _human_bytes(rx_b, decimals=0), _human_bytes(tx_b, decimals=0)
    except (OSError, ValueError) as e:
        logger.debug("Не удалось посчитать сетевую статистику: %s", e)
    return f"Сеть <code>{html.escape(iface)}</code>: ↓ <code>{rx}</code> · ↑ <code>{tx}</code>"


def get_server_card_html() -> str:
    tt_state = run_cmd(["systemctl", "is-active", SERVICE_NAME]) or "unknown"
    bot_state = run_cmd(["systemctl", "is-active", "tt-bot.service"]) or "unknown"
    ver = get_current_tt_version()
    users_n = len(list_usernames())
    return (
        "<b>⚙️ Сервер</b>\n"
        "<blockquote>"
        f"Домен: <code>{html.escape(_client_endpoint_address(ADDRESS))}</code>\n"
        f"Порт VPN: <code>{VPN_MONITOR_PORT}</code>\n"
        f"Имя в ссылке: <code>{html.escape(SERVER_NAME)}</code>\n"
        f"TrustTunnel: {_status_emoji(tt_state)} <code>{html.escape(tt_state)}</code>\n"
        f"tt-bot: {_status_emoji(bot_state)} <code>{html.escape(bot_state)}</code>\n"
        f"Версия TT: <code>{html.escape(ver)}</code>\n"
        f"Пользователей: <code>{users_n}</code>\n"
        "</blockquote>"
    )


def server_card_inline_kb() -> InlineKeyboardMarkup:
    return merge_inline_kb(
        [_copy_host_button(), InlineKeyboardButton("🔄 Обновить", callback_data="nav:servercard")],
        card_footer_row("server"),
    )


def get_info_card_html() -> str:
    load1, load5, load15 = os.getloadavg()
    uptime_human = _uptime_pretty()
    tt_state = run_cmd(["systemctl", "is-active", SERVICE_NAME], timeout=8) or "unknown"
    bot_state = run_cmd(["systemctl", "is-active", "tt-bot.service"], timeout=8) or "unknown"
    port_line = _port_listening_summary(_tt_tls_port())
    metrics_line = _endpoint_metrics_hint()

    return (
        "<b>🖥 Нагрузка</b>\n"
        "<blockquote>"
        "<b>ВМ</b>\n"
        f"Время работы: <code>{html.escape(uptime_human or 'n/a')}</code>\n"
        f"CPU: <code>{load1:.2f} / {load5:.2f} / {load15:.2f}</code>\n"
        f"{_ram_health_summary()}\n"
        f"{_disk_usage_summary()}\n"
        f"{_network_iface_summary()}\n\n"
        "<b>Состояние:</b>\n"
        f"{_status_emoji(tt_state)} TrustTunnel: <code>{html.escape(tt_state)}</code>\n"
        f"{_status_emoji(bot_state)} tt-bot: <code>{html.escape(bot_state)}</code>\n"
        f"{port_line}\n"
        f"{metrics_line}"
        "</blockquote>"
    )


_CERT_MONTH_ABBR = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _cert_days_from_not_after(not_after: str) -> int | None:
    """OpenSSL отдаёт notAfter англ. месяцами независимо от LC_TIME — месяц парсим вручную."""
    if not not_after:
        return None
    try:
        month_abbr, day, time_part, year = not_after.split()[:4]
        month = _CERT_MONTH_ABBR[month_abbr]
        hour, minute, second = (int(p) for p in time_part.split(":"))
        exp = dt.datetime(int(year), month, int(day), hour, minute, second, tzinfo=dt.timezone.utc)
        return max(0, (exp - dt.datetime.now(dt.UTC)).days)
    except (KeyError, ValueError, IndexError):
        return None


def _cert_status_label(days: int | None) -> str:
    if days is None:
        return "n/a"
    if days < 7:
        return "🚨"
    if days < CERT_WARN_DAYS:
        return "⚠️"
    return "🟢"


def _parse_openssl_cert_output(out: str, **extra: Any) -> dict[str, Any]:
    """Разбирает `key=value` строки вывода `openssl x509 -subject -enddate`."""
    info: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    not_after = info.get("notAfter", "")
    return {
        "ok": True,
        "not_after": not_after,
        "days": _cert_days_from_not_after(not_after),
        "subject": info.get("subject", ""),
        **extra,
    }


def _cert_info_from_file(cert_path: Path) -> dict[str, Any]:
    if not cert_path.is_file():
        return {"ok": False, "error": f"нет файла: {cert_path}"}
    code, out, err = run_shell(
        f"openssl x509 -in {shlex.quote(str(cert_path))} -noout -subject -enddate",
        timeout=15,
    )
    if code != 0:
        return {"ok": False, "error": (err or out or "read fail")[:120]}
    return _parse_openssl_cert_output(out, path=str(cert_path))


def _cert_info_from_tls(hostname: str, port: int = 443) -> dict[str, Any]:
    if not hostname:
        return {"ok": False, "error": "пустой host"}
    code, out, err = run_shell(
        "echo | openssl s_client -servername "
        f"{shlex.quote(hostname)} -connect {shlex.quote(hostname)}:{port} 2>/dev/null "
        "| openssl x509 -noout -subject -enddate",
        timeout=20,
    )
    if code != 0:
        return {"ok": False, "error": (err or out or "tls fail")[:120]}
    return _parse_openssl_cert_output(out, host=hostname)


def _tt_cert_file_path() -> Path:
    hosts = TT_DIR / "hosts.toml"
    if hosts.is_file():
        try:
            doc = tomlkit.parse(hosts.read_text(encoding="utf-8"))
            main_hosts = doc.get("main_hosts")
            if isinstance(main_hosts, list):
                for item in main_hosts:
                    if not isinstance(item, dict):
                        continue
                    raw = str(item.get("cert_chain_path", "")).strip()
                    if raw:
                        p = Path(raw)
                        return p if p.is_absolute() else TT_DIR / p
        except (OSError, ValueError) as e:
            logger.debug("Не удалось определить cert_chain_path из конфига: %s", e)
    le_host = (ADDRESS.split(":")[0] if ADDRESS else "").strip()
    if le_host:
        le = LE_CERT_BASE_DIR / le_host / "fullchain.pem"
        if le.is_file():
            return le
    return CERT_FILE


def _tt_tls_port() -> int:
    if ADDRESS and ":" in ADDRESS:
        try:
            return int(ADDRESS.rsplit(":", 1)[1])
        except ValueError:
            pass
    return VPN_MONITOR_PORT


def _systemd_timestamp_human(raw: str) -> str:
    """`systemctl show` *USec: сырые usec (старый systemd) или готовая строка
    (новый). Нормализует в отображаемый вид; '' если распознать не удалось."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.isdigit():
        try:
            return dt.datetime.fromtimestamp(
                int(raw) / 1_000_000, tz=dt.timezone.utc
            ).strftime("%Y-%m-%d %H:%M UTC")
        except (ValueError, OverflowError, OSError):
            return ""
    return raw


def _certbot_timer_lines() -> tuple[str, str]:
    """(last, next) срабатывания certbot.timer.

    show разбирается по Key=Value, не по позициям строк: пустые свойства
    в выводе -p пропускаются, число строк не совпадает с числом -p.
    """
    code, out, _err = run_shell(
        "systemctl show certbot.timer -p LastTriggerUSec -p NextElapseUSecRealtime -p ActiveState",
        timeout=10,
    )
    if code != 0:
        # Юнита нет (или нет доступа): скажем прямо, а не "n/a (timer n/a)".
        return "n/a", "n/a (timer не найден)"
    info: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    last_trigger = _systemd_timestamp_human(info.get("LastTriggerUSec", "")) or "ещё не запускался"
    next_trigger = _systemd_timestamp_human(info.get("NextElapseUSecRealtime", ""))
    timer_active = info.get("ActiveState", "") or "n/a"

    # LEFT-колонку берём из list-timers с зафиксированной локалью C:
    # иначе в ru-локали «6h left» превращается в «осталось 6 ч».
    list_line = run_cmd(
        ["bash", "-c", "LC_ALL=C systemctl list-timers certbot.timer --no-pager --no-legend"],
        timeout=10,
    )
    if list_line:
        parts = list_line.split()
        # Колонки вывода systemctl list-timers: NEXT(день недели, дата, время,
        # tz) LEFT(остаток, "left") LAST ...
        if len(parts) >= 6:
            left = " ".join(parts[4:6])
            scheduled = " ".join(parts[:4])
            # NEXT из list-timers — каноническая человекочитаемая отрисовка
            # того же NextElapseUSecRealtime, предпочитаем её выводу show.
            next_trigger = f"{scheduled} ({left})"
    if not next_trigger:
        next_trigger = "n/a"

    if timer_active != "active":
        next_trigger = f"{next_trigger} (timer {timer_active})"
    return last_trigger, next_trigger


def get_cert_card_data() -> tuple[str, bool]:
    tt_host = (ADDRESS.split(":")[0] if ADDRESS else "").strip()
    tt_port = _tt_tls_port()
    tt_file = _tt_cert_file_path()
    tt_file_info = _cert_info_from_file(tt_file)
    tt_tls_info = _cert_info_from_tls(tt_host, tt_port) if tt_host else {"ok": False, "error": "нет host"}

    tt_days: int | None = None
    tt_warn = False
    tt_file_days = tt_file_info.get("days")
    tt_tls_days = tt_tls_info.get("days")
    if tt_file_info.get("ok") and isinstance(tt_file_days, int):
        tt_days = tt_file_days
    elif tt_tls_info.get("ok") and isinstance(tt_tls_days, int):
        tt_days = tt_tls_days
    if tt_days is not None:
        tt_warn = tt_days < CERT_WARN_DAYS

    last_trigger, next_trigger = _certbot_timer_lines()
    renew_script = "🟢" if CERT_RENEW_SCRIPT.is_file() else "🔴"

    tt_em = _cert_status_label(tt_days)
    tt_days_txt = str(tt_days) if tt_days is not None else "n/a"
    tt_until = ""
    if tt_file_info.get("ok"):
        tt_until = str(tt_file_info.get("not_after", ""))
    elif tt_tls_info.get("ok"):
        tt_until = str(tt_tls_info.get("not_after", ""))

    text = (
        "<b>🔐 Сертификат</b>\n\n"
        "<b>TrustTunnel (certbot)</b>\n"
        "<blockquote>"
        f"Endpoint: <code>{html.escape(_client_endpoint_address(ADDRESS))}</code>\n"
        f"Файл: <code>{html.escape(str(tt_file))}</code>\n"
        f"До: <code>{html.escape(tt_until or 'n/a')}</code>\n"
        f"Осталось: {tt_em} <code>{html.escape(tt_days_txt)}</code> дн.\n"
        f"certbot.timer: последний <code>{html.escape(last_trigger)}</code>\n"
        f"следующий <code>{html.escape(next_trigger)}</code>\n"
        f"renew script: {renew_script}"
        "</blockquote>"
    )
    return text, tt_warn


def _format_client_prefix(prefix: str, max_len: int = 14) -> str:
    if len(prefix) <= max_len:
        return prefix
    return f"{prefix[: max_len - 5]}...{prefix[-2:]}"


def _human_bytes(n: int, *, decimals: int = 1) -> str:
    """Байты → KiB/MiB/… (decimals=0 — компактно)."""
    size = float(max(0, n))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024:
            nd = 0 if unit == "B" else decimals
            return f"{size:.{nd}f} {unit}"
        size /= 1024
    return f"{size:.1f} PiB"


def _fetch_metrics_clients() -> list[dict[str, Any]] | None:
    def _produce() -> list[dict[str, Any]] | None:
        text = _http_get(METRICS_CLIENTS_URL, timeout=3)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError as e:
            logger.debug("Не удалось разобрать ответ %s: %s", METRICS_CLIENTS_URL, e)
            return None

    return cached_compute("metrics_clients", MONITOR_CACHE_TTL_SEC, _produce)


def _parse_metric_item(item: dict[str, Any]) -> tuple[str, int]:
    """(username, sessions); sessions=0 если значение битое."""
    username = str(item.get("username") or "").strip()
    try:
        sessions = int(item.get("sessions") or 0)
    except (TypeError, ValueError):
        sessions = 0
    return username, sessions


def _aggregate_sessions_from_metrics(
    items: list[dict[str, Any]],
) -> tuple[Counter[str], dict[str, str]]:
    cnt: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for item in items:
        username, sessions = _parse_metric_item(item)
        if not username:
            continue
        key = f"u:{username}"
        cnt[key] = sessions
        ip = item.get("ip")

        if sessions <= 0:
            labels[key] = f"⚪ <b>{html.escape(username)}</b> · не подключён"
            continue

        ip_part = f" · {html_spoiler(str(ip))}" if ip else ""
        inbound = _human_bytes(int(item.get("inbound") or 0))
        outbound = _human_bytes(int(item.get("outbound") or 0))
        labels[key] = (
            f"🟢 <b>{html.escape(username)}</b>{ip_part}\n"
            f"    📥 <code>{inbound}</code> · 📤 <code>{outbound}</code>"
        )
    return cnt, labels


def clients_card_html(page: int) -> tuple[str, int, int, bool]:
    items = _fetch_metrics_clients()
    if items is None:
        card = (
            "<b>📈 Клиенты VPN</b>\n"
            f"<blockquote>Не удалось получить данные с <code>{html.escape(METRICS_CLIENTS_URL)}</code>.\n"
            "Проверь: секция [metrics] с per_client_metrics = true в vpn.toml, "
            "сервис trusttunnel перезапущен.</blockquote>"
        )
        return card, 1, 0, True

    cnt, labels = _aggregate_sessions_from_metrics(items)
    if not cnt:
        card = "<b>📈 Клиенты VPN</b>\n<blockquote>Нет подключений.</blockquote>"
        return card, 1, 0, True

    ranked = sorted(cnt.items(), key=lambda x: (-x[1], x[0]))
    per = CLIENTS_PER_PAGE
    total_pages = max(1, (len(ranked) + per - 1) // per)
    page = max(0, min(page, total_pages - 1))
    slice_ = ranked[page * per : (page + 1) * per]

    lines = []
    for idx, (peer_key, _) in enumerate(slice_, start=page * per + 1):
        label = labels.get(peer_key, f"<code>{html.escape(peer_key)}</code>")
        lines.append(f"{idx}. {label}")

    online_count = sum(1 for _, n in ranked if n > 0)
    inner = "\n".join(lines)
    total_sessions = sum(n for _, n in cnt.items())
    card = (
        "<b>📈 Клиенты VPN</b>\n"
        f"<i>🟢 {online_count} онлайн · ⚪ {len(ranked) - online_count} офлайн</i>\n"
        f"<blockquote>{inner}</blockquote>"
    )
    return card, total_pages, total_sessions, False


def clients_inline_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"ss:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"ss:{page + 1}"))
    refresh_back = refresh_back_row(f"ss:{page}", "home")
    if nav:
        return merge_inline_kb(nav, refresh_back)
    return merge_inline_kb(refresh_back)


def logs_inline_kb(
    level: str,
    lines: int,
    chunk: int,
    total_chunks: int,
    *,
    callback_prefix: str = "logf",
    footer_parent: str = "info",
) -> InlineKeyboardMarkup:
    presets = [
        ("ALL", "all"),
        ("ERR", "err"),
        ("WARN", "warn"),
        ("5m ERR", "5m"),
    ]
    mode_row = []
    for label, mode in presets:
        prefix = "• " if mode == level else ""
        mode_row.append(InlineKeyboardButton(f"{prefix}{label}", callback_data=f"{callback_prefix}:{mode}:{lines}:0"))

    lines_row = []
    for n in (50, 200):
        prefix = "• " if n == lines else ""
        lines_row.append(InlineKeyboardButton(f"{prefix}{n}", callback_data=f"{callback_prefix}:{level}:{n}:0"))

    rows = [mode_row, lines_row]
    if total_chunks > 1:
        nav = []
        if chunk > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"{callback_prefix}:{level}:{lines}:{chunk - 1}"))
        nav.append(InlineKeyboardButton(f"{chunk + 1}/{total_chunks}", callback_data=f"{callback_prefix}:noop:50:0"))
        if chunk < total_chunks - 1:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"{callback_prefix}:{level}:{lines}:{chunk + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔄 Обновить", callback_data=f"{callback_prefix}:{level}:{lines}:{chunk}")])
    return merge_inline_kb(*rows, card_footer_row(footer_parent))


def _fetch_logs_raw(lines: int, *, since: str | None = None) -> tuple[int, str, str]:
    def _produce() -> tuple[int, str, str]:
        if since:
            cmd = (
                f"journalctl -u {SERVICE_NAME} --since '{since}' "
                "--no-pager -o short-precise"
            )
        else:
            cmd = f"journalctl -u {SERVICE_NAME} -n {lines} --no-pager -o short-precise"
        return run_shell(cmd, timeout=25)

    cache_key = f"logs:{lines}:{since or ''}"
    return cached_compute(cache_key, MONITOR_CACHE_TTL_SEC, _produce)


def _chunk_text_by_lines(text: str, limit: int) -> list[str]:
    """Бьёт текст на части не длиннее `limit` символов, не разрывая строки.
    Строка длиннее лимита сама по себе идёт отдельным чанком как есть."""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        added_len = len(line) + (1 if current else 0)
        if current and current_len + added_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
            added_len = len(line)
        current.append(line)
        current_len += added_len
    if current:
        chunks.append("\n".join(current))
    return chunks or [text]


def build_logs_view(level: str = "all", lines: int = 50, chunk: int = 0) -> tuple[str, int, int]:
    since = "5 min ago" if level == "5m" else None
    fetch_lines = 400 if level == "5m" else lines
    code, out, err = _fetch_logs_raw(fetch_lines, since=since)
    if code != 0:
        return f"🧾 Логи trusttunnel\n\nНе удалось получить логи.\n{err or out}", 0, 1

    rows = (out or "").splitlines()
    if level in ("err", "5m"):
        rows = [ln for ln in rows if LOG_ERR_RE.search(ln)]
    elif level == "warn":
        rows = [ln for ln in rows if LOG_WARN_RE.search(ln)]

    filtered = "\n".join(rows).strip() or "Пусто по выбранному фильтру."
    chunks = _chunk_text_by_lines(filtered, LOG_CHUNK_CHARS)
    total_chunks = len(chunks)
    chunk = max(0, min(chunk, total_chunks - 1))
    level_label = {"5m": "ERROR 5m", "err": "ERROR", "warn": "WARN", "all": "ALL"}.get(level, level.upper())
    scope = "последние 5 минут" if level == "5m" else f"последние {lines}"
    header = f"🧾 Логи trusttunnel · {level_label} · {scope}"
    if total_chunks > 1:
        header += f"\nЧасть {chunk + 1}/{total_chunks}"
    return f"{header}\n\n{chunks[chunk]}", chunk, total_chunks


def create_configs_backup() -> tuple[Path, list[str]]:
    """Один файл latest-configs.tar.gz, без истории по датам — его же читает restore."""
    backup_dir = TT_DIR / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    latest_path = latest_backup_path()

    included = []

    # Атомарная сборка: при обрыве старый latest-configs.tar.gz не портится.
    tmp = NamedTemporaryFile(dir=backup_dir, prefix="configs.", suffix=".tar.gz.tmp", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        with tarfile.open(tmp_path, "w:gz") as tar:
            for name in BACKUP_FILES:
                p = TT_DIR / name
                if p.exists():
                    tar.add(p, arcname=name)
                    included.append(name)
        os.replace(tmp_path, latest_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return latest_path, included


def latest_backup_path() -> Path:
    return TT_DIR / "backup" / "latest-configs.tar.gz"


def list_files_in_latest_backup() -> list[str]:
    bp = latest_backup_path()
    if not bp.exists():
        return []
    try:
        with tarfile.open(bp, "r:gz") as tar:
            names = []
            for member in tar.getmembers():
                if member.isfile() and member.name in BACKUP_FILES:
                    names.append(member.name)
            return names
    except (tarfile.TarError, OSError):
        return []


_PASSWORD_VALUE_RE = re.compile(r'password\s*=\s*(?:"[^"]*"|\'[^\']*\')')


def _mask_passwords(text: str) -> str:
    return _PASSWORD_VALUE_RE.sub('password = "•••"', text)


def _diff_against_latest_backup() -> str:
    """Unified diff живых конфигов против latest-configs.tar.gz.

    Сравнение — на сырых значениях (иначе смена пароля с одинаковой маской
    выглядела бы как отсутствие изменений); маска накладывается на готовый
    текст диффа перед выдачей — credentials.toml не должен светить пароли
    в чат plaintext'ом.
    """
    bp = latest_backup_path()
    if not bp.exists():
        return "Бэкапа ещё нет — нечего сравнивать."
    try:
        with tarfile.open(bp, "r:gz") as tar:
            backed_up = {}
            for name in BACKUP_FILES:
                try:
                    member = tar.extractfile(name)
                except KeyError:
                    member = None
                backed_up[name] = member.read().decode("utf-8") if member else ""
    except (tarfile.TarError, OSError) as e:
        return f"Не удалось прочитать бэкап: {e}"

    diffs = []
    for name in BACKUP_FILES:
        live_path = TT_DIR / name
        live_text = live_path.read_text(encoding="utf-8") if live_path.exists() else ""
        backup_text = backed_up.get(name, "")
        if live_text == backup_text:
            continue
        diff_lines = list(
            difflib.unified_diff(
                backup_text.splitlines(keepends=True),
                live_text.splitlines(keepends=True),
                fromfile=f"backup/{name}",
                tofile=f"live/{name}",
            )
        )
        if diff_lines:
            diffs.append("".join(diff_lines))

    if not diffs:
        return "Изменений нет — конфиги совпадают с последним бэкапом."
    return _mask_passwords("\n".join(diffs))


def _read_file_snapshot(path: Path) -> tuple[bytes | None, int | None]:
    if not path.exists():
        return None, None
    return path.read_bytes(), path.stat().st_mode & 0o777


def restore_file_from_latest_backup(filename: str, *, restart_service: bool = True) -> tuple[bool, str]:
    if filename not in BACKUP_FILES:
        return False, "Недопустимое имя файла."
    bp = latest_backup_path()
    if not bp.exists():
        return False, "Бэкап не найден. Сначала сделай бэкап."

    try:
        with tarfile.open(bp, "r:gz") as tar:
            try:
                member = tar.getmember(filename)
            except KeyError:
                return False, f"Файл {filename} отсутствует в бэкапе."
            if not member.isfile():
                return False, f"{filename} в бэкапе не является обычным файлом."
            extracted = tar.extractfile(member)
            if extracted is None:
                return False, f"Не удалось прочитать {filename} из бэкапа."
            data = extracted.read()
    except (tarfile.TarError, OSError) as e:
        return False, f"Не удалось открыть бэкап: {e}"

    target = TT_DIR / filename
    restore_backup_dir = TT_DIR / "backup" / "restore-prev"
    restore_backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _backup_timestamp()

    try:
        old_mode = target.stat().st_mode & 0o777 if target.exists() else None
        if target.exists():
            prev = restore_backup_dir / f"{filename}.{stamp}"
            _atomic_write_bytes(prev, target.read_bytes(), mode=old_mode)
            _prune_backup_dir(restore_backup_dir, f"{filename}.*", BACKUP_KEEP_RESTORE_PREV)
        with NamedTemporaryFile("wb", dir=str(TT_DIR), delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target)
        if filename == "credentials.toml":
            target.chmod(0o600)
        elif old_mode is not None:
            # os.replace унаследует права tmp-файла (0600) — восстанавливаем исходные.
            target.chmod(old_mode)
        if restart_service:
            if filename == "hosts.toml":
                try:
                    mode = apply_tt_config_change(reload_tls=True)
                    return True, f"ok ({mode})"
                except CommandError:
                    pass
            apply_tt_config_change()
        return True, "ok"
    except Exception as e:
        return False, f"Ошибка восстановления: {e}"


def restore_multiple_from_latest_backup(filenames: list[str]) -> tuple[bool, str]:
    if not filenames:
        return False, "Не выбраны файлы для восстановления."
    snapshot = _snapshot_tt_files([TT_DIR / name for name in filenames])
    restored: list[str] = []
    for name in filenames:
        ok, info = restore_file_from_latest_backup(name, restart_service=False)
        if not ok:
            _restore_tt_files(snapshot)
            return False, info
        restored.append(name)
    try:
        apply_tt_config_change()
    except Exception:
        _restore_tt_files(snapshot)
        return False, "Не удалось применить восстановленные файлы — откат выполнен."
    return True, ", ".join(restored)


def _backup_timestamp() -> str:
    return dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")


def _stamped_backup(
    dir_path: Path,
    stem: str,
    suffix: str,
    data: str,
    *,
    keep: int,
    dir_mode: int | None = None,
    file_mode: int | None = None,
) -> Path:
    """Копия со штампом времени + прунинг старых: `<dir_path>/<stem>-<timestamp><suffix>`.

    dir_path.mkdir рождается с дефолтным umask до chmod(dir_mode) — окно
    короткое (одна операция), а вот файл пишем через _atomic_write_bytes:
    NamedTemporaryFile всегда 0600 независимо от umask, так что для
    file_mode=0600 (пароли) окна с широкими правами нет вообще.
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    if dir_mode is not None:
        dir_path.chmod(dir_mode)
    stamp = _backup_timestamp()
    path = dir_path / f"{stem}-{stamp}{suffix}"
    _atomic_write_bytes(path, data.encode("utf-8"), mode=file_mode)
    _prune_backup_dir(dir_path, f"{stem}-*{suffix}", keep)
    return path


def _prune_backup_dir(dir_path: Path, glob_pattern: str, keep: int) -> None:
    try:
        files = [p for p in dir_path.glob(glob_pattern) if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[keep:]:
            stale.unlink(missing_ok=True)
    except OSError:
        logger.exception("Backup prune failed for %s", dir_path)


def _load_credentials_doc() -> tuple[Any, str]:
    if not CRED_FILE.exists():
        raise RuntimeError("credentials.toml не найден")
    raw = CRED_FILE.read_text(encoding="utf-8")
    return tomlkit.parse(raw), raw


def _clients_aot(doc: Any) -> Any:
    clients = doc.get("client")
    if clients is None:
        clients = tomlkit.aot()
        doc["client"] = clients
    return clients


def _clients_list_from_doc(doc: Any) -> list[dict[str, str]]:
    clients = _clients_aot(doc)
    out: list[dict[str, str]] = []
    for client in clients:
        username = str(client.get("username", "")).strip()
        if not username:
            continue
        password = str(client.get("password", ""))
        out.append({"username": username, "password": password})
    return out


def _get_user_password(username: str) -> str | None:
    doc, _ = _load_credentials_doc()
    for client in _clients_list_from_doc(doc):
        if client["username"] == username:
            return client["password"]
    return None


def _atomic_write_credentials(new_text: str, old_text: str) -> None:
    _stamped_backup(
        TT_DIR / "backup" / "credentials",
        "credentials",
        ".toml.bak",
        old_text,
        keep=BACKUP_KEEP_CREDENTIALS,
        dir_mode=0o700,  # каталог с копиями паролей — только владельцу
        file_mode=0o600,
    )
    # NamedTemporaryFile рождается с 0600 — как раз то, что нужно файлу с
    # паролями, отдельного chmod не требуется.
    _atomic_write_bytes(CRED_FILE, new_text.encode("utf-8"))


def _atomic_write_bytes(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """Атомарная запись: tmp-файл в той же директории (для os.replace на
    одной ФС), опциональный chmod до подмены, затем os.replace."""
    with NamedTemporaryFile("wb", dir=str(path.parent), delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    if mode is not None:
        tmp_path.chmod(mode)
    os.replace(tmp_path, path)


def _atomic_write_file(path: Path, text: str) -> None:
    # tmp-файл рождается с 0600 — os.replace унаследует их, поэтому права восстанавливаем.
    old_mode = path.stat().st_mode & 0o777 if path.exists() else None
    _atomic_write_bytes(path, text.encode("utf-8"), mode=old_mode)


def _load_prefix_map() -> dict[str, str]:
    if not PREFIX_MAP_FILE.exists():
        return {}
    raw = PREFIX_MAP_FILE.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        doc = tomlkit.parse(raw)
    except ValueError:
        return {}
    tbl = doc.get("user_prefix")
    if tbl is None:
        return {}
    out: dict[str, str] = {}
    for username, prefix in dict(tbl).items():
        u = str(username).strip()
        p = str(prefix).strip().lower()
        if u and p:
            out[u] = p
    return out


def _save_prefix_map(mapping: dict[str, str]) -> None:
    doc = tomlkit.document()
    tbl = tomlkit.table()
    for username in sorted(mapping):
        tbl.add(username, mapping[username])
    doc["user_prefix"] = tbl
    text = tomlkit.dumps(doc)
    if not text.endswith("\n"):
        text += "\n"
    _atomic_write_file(PREFIX_MAP_FILE, text)


def _load_user_profiles() -> dict[str, dict[str, Any]]:
    if not USER_PROFILES_FILE.exists():
        return {}
    try:
        raw = USER_PROFILES_FILE.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for username, profile in data.items():
        if not isinstance(username, str) or not isinstance(profile, dict):
            continue
        out[username] = profile
    return out


def _save_user_profiles(profiles: dict[str, dict[str, Any]]) -> None:
    text = json.dumps(profiles, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write_file(USER_PROFILES_FILE, text)


def _get_user_profile(username: str) -> dict[str, Any]:
    return _load_user_profiles().get(username, {})


def _set_user_profile(username: str, *, protocol: str, random_prefix: bool) -> None:
    profiles = _load_user_profiles()
    profiles[username] = {
        "protocol": protocol if protocol in ("h2", "quic") else "h2",
        "random_prefix": bool(random_prefix),
        "updated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
    }
    _save_user_profiles(profiles)


def _delete_user_profile(username: str) -> None:
    profiles = _load_user_profiles()
    if username in profiles:
        profiles.pop(username, None)
        _save_user_profiles(profiles)


def _extract_allow_prefixes() -> list[str]:
    if not RULES_FILE.exists():
        return []
    raw = RULES_FILE.read_text(encoding="utf-8")
    if not raw.strip():
        return []
    try:
        doc = tomlkit.parse(raw)
    except ValueError:
        return []
    rules = doc.get("rule")
    if rules is None:
        return []
    out: list[str] = []
    for rule in rules:
        action = str(rule.get("action", "")).strip().lower()
        prefix = str(rule.get("client_random_prefix", "")).strip().lower()
        if action == "allow" and prefix:
            out.append(prefix)
    return out


def _backup_rules_file(raw: str) -> None:
    _stamped_backup(TT_DIR / "backup" / "rules", "rules", ".toml.bak", raw, keep=BACKUP_KEEP_RULES)


def _empty_rules_toml_text() -> str:
    return (
        "# Правила фильтрации подключений VPN-эндпоинта\n"
        "# Управляется автоматически tt-bot.\n"
        "# Явных блоков [[rule]] нет — действует политика TrustTunnel по умолчанию.\n"
        "\n"
    )


def _is_user_rule_tag_line(line: str) -> bool:
    return bool(re.match(r"^\s*#\s*user\s*:", line.strip(), re.IGNORECASE))


def _next_rule_block(lines: list[str], start: int) -> tuple[int, int, int] | None:
    """Возвращает (block_start, rule_start, block_end)."""
    n = len(lines)
    i = start
    while i < n:
        if lines[i].strip() == "[[rule]]":
            block_start = i
            rule_start = i
            break
        if _is_user_rule_tag_line(lines[i]) and i + 1 < n and lines[i + 1].strip() == "[[rule]]":
            block_start = i
            rule_start = i + 1
            break
        i += 1
    else:
        return None

    j = rule_start + 1
    while j < n:
        stripped = lines[j].strip()
        if stripped == "[[rule]]":
            break
        if stripped.startswith("#"):
            # Комментарий начинает следующий блок.
            break
        j += 1
    return block_start, rule_start, j


def _read_rules_raw() -> str | None:
    """Содержимое rules.toml, или None если файла нет или он пуст."""
    if not RULES_FILE.exists():
        return None
    raw = RULES_FILE.read_text(encoding="utf-8")
    return raw if raw.strip() else None


def _parse_rule_block_fields(rule_lines: list[str]) -> tuple[str, str]:
    """(action, client_random_prefix) блока, в нижнем регистре."""
    action = ""
    prefix = ""
    for ln in rule_lines:
        m_act = re.match(r'\s*action\s*=\s*"([^"]+)"', ln, re.IGNORECASE)
        if m_act:
            action = m_act.group(1).strip().lower()
        m_pref = re.match(r'\s*client_random_prefix\s*=\s*"([^"]+)"', ln, re.IGNORECASE)
        if m_pref:
            prefix = m_pref.group(1).strip().lower()
    return action, prefix


def _write_rules_file(raw: str, text: str, *, allow_empty_fallback: bool = True) -> None:
    if allow_empty_fallback and not text.strip():
        text = _empty_rules_toml_text()
    if not text.endswith("\n"):
        text += "\n"
    _backup_rules_file(raw)
    _atomic_write_file(RULES_FILE, text)


def _remove_prefix_rules_by_prefix(prefix: str) -> int:
    raw = _read_rules_raw()
    if raw is None:
        return 0
    needle = prefix.strip().lower()
    if not needle:
        return 0

    lines = raw.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        found = _next_rule_block(lines, i)
        if not found:
            out.extend(lines[i:])
            break
        block_start, rule_start, block_end = found
        out.extend(lines[i:block_start])
        block = lines[block_start:block_end]
        action, rp = _parse_rule_block_fields(lines[rule_start:block_end])
        if action == "allow" and rp == needle:
            removed += 1
        else:
            out.extend(block)
        i = block_end

    if removed == 0:
        return 0
    _write_rules_file(raw, "".join(out))
    return removed


def _remove_prefix_rule(prefix: str) -> bool:
    return _remove_prefix_rules_by_prefix(prefix) > 0


def _remove_prefix_rules_for_user(prefixes: list[str], username: str) -> int:
    raw = _read_rules_raw()
    if raw is None:
        return 0
    needles = {p.strip().lower() for p in prefixes if p and p.strip()}
    user = username.strip()
    user_tag_re = re.compile(rf'^\s*#\s*user\s*:\s*{re.escape(user)}\s*$', re.IGNORECASE) if user else None

    lines = raw.splitlines(keepends=True)
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        found = _next_rule_block(lines, i)
        if not found:
            out.extend(lines[i:])
            break
        block_start, rule_start, block_end = found
        out.extend(lines[i:block_start])
        block = lines[block_start:block_end]
        block_action, block_prefix = _parse_rule_block_fields(lines[rule_start:block_end])
        has_user_tag = bool(
            user_tag_re and block_start < rule_start and user_tag_re.match(lines[block_start].strip())
        )
        if block_action == "allow" and (block_prefix in needles or has_user_tag):
            removed += 1
        else:
            out.extend(block)
        i = block_end

    if removed == 0:
        return 0
    _write_rules_file(raw, "".join(out))
    return removed


def _append_allow_rule(prefix: str) -> None:
    raw = RULES_FILE.read_text(encoding="utf-8") if RULES_FILE.exists() else ""
    _backup_rules_file(raw)
    new_block = f'[[rule]]\nclient_random_prefix = "{prefix}"\naction = "allow"\n'
    text = new_block + ("\n" + raw if raw.strip() else "")
    if not text.endswith("\n"):
        text += "\n"
    _atomic_write_file(RULES_FILE, text)


def _tag_prefix_rule_with_username(prefix: str, username: str) -> int:
    raw = _read_rules_raw()
    if raw is None:
        return 0
    needle = prefix.strip().lower()
    user = username.strip()
    if not needle or not user:
        return 0

    lines = raw.splitlines(keepends=True)
    out: list[str] = []
    changed = 0
    i = 0
    while i < len(lines):
        found = _next_rule_block(lines, i)
        if not found:
            out.extend(lines[i:])
            break
        block_start, rule_start, block_end = found
        out.extend(lines[i:block_start])
        rule_lines = lines[rule_start:block_end]
        tagged_user = ""
        if block_start < rule_start:
            m_tag = re.match(r"^\s*#\s*user\s*:\s*(.+?)\s*$", lines[block_start].strip(), re.IGNORECASE)
            if m_tag:
                tagged_user = m_tag.group(1).strip()

        block_action, block_prefix = _parse_rule_block_fields(rule_lines)
        should_tag = block_action == "allow" and block_prefix == needle
        if should_tag:
            if tagged_user != user:
                changed += 1
            out.append(f"# user: {user}\n")
            out.extend(rule_lines)
        else:
            if tagged_user:
                out.append(lines[block_start])
            out.extend(rule_lines)
        i = block_end

    if changed == 0:
        return 0
    _write_rules_file(raw, "".join(out), allow_empty_fallback=False)
    return changed


def _prefixes_to_remove_for_user(username: str) -> list[str]:
    mapping = _load_prefix_map()
    p = str(mapping.get(username, "")).strip().lower()
    return [p] if p else []


def list_usernames() -> list[str]:
    try:
        doc, _ = _load_credentials_doc()
    except RuntimeError:
        return []
    return [row["username"] for row in _clients_list_from_doc(doc)]


def _prefix_for_username(username: str) -> str | None:
    p = _load_prefix_map().get(username, "").strip().lower()
    return p or None


def _export_context_for_username(username: str) -> tuple[str | None, str]:
    profile = _get_user_profile(username)
    proto = _normalize_protocol(str(profile.get("protocol", "h2")))
    return _prefix_for_username(username), proto


def audit_rules_sync() -> dict[str, Any]:
    users = set(list_usernames())
    mapping = _load_prefix_map()
    prefixes_in_rules = set(_extract_allow_prefixes())
    # Только активные пользователи защищают правила от очистки.
    valid_mapped_prefixes = {
        p.strip().lower() for u, p in mapping.items() if u in users and str(p).strip()
    }
    orphan_rule_prefixes = sorted(prefixes_in_rules - valid_mapped_prefixes)
    missing_rules = {
        u: p for u, p in mapping.items() if u in users and p.strip().lower() not in prefixes_in_rules
    }
    orphan_map_entries = {u: p for u, p in mapping.items() if u not in users}
    stale_profiles = [
        u
        for u in users
        if _get_user_profile(u).get("random_prefix") and u not in mapping
    ]
    return {
        "users": users,
        "orphan_rule_prefixes": orphan_rule_prefixes,
        "missing_rules": missing_rules,
        "orphan_map_entries": orphan_map_entries,
        "stale_profiles": stale_profiles,
    }


def cleanup_orphan_rules_sync() -> tuple[list[str], list[str]]:
    audit = audit_rules_sync()
    removed_rules: list[str] = []
    for prefix in audit["orphan_rule_prefixes"]:
        if _remove_prefix_rule(prefix):
            removed_rules.append(prefix)
    mapping = _load_prefix_map()
    removed_map: list[str] = []
    for username in list(audit["orphan_map_entries"].keys()):
        mapping.pop(username, None)
        removed_map.append(username)
    if removed_map:
        _save_prefix_map(mapping)
    return removed_rules, removed_map


def repair_missing_rules_sync() -> tuple[list[str], list[str]]:
    audit = audit_rules_sync()
    fixed: list[str] = []
    errors: list[str] = []
    for username, prefix in audit["missing_rules"].items():
        p = str(prefix).strip().lower()
        if not p:
            errors.append(f"{username}: пустой префикс")
            continue
        try:
            _append_allow_rule(p)
            tagged = _tag_prefix_rule_with_username(p, username)
            if tagged <= 0:
                errors.append(f"{username}: не удалось создать/пометить правило")
                continue
            fixed.append(username)
        except Exception as e:
            errors.append(f"{username}: {e}")
    if fixed:
        apply_tt_config_change()
    return fixed, errors


def _auto_cleanup_rules_orphans() -> tuple[list[str], list[str]]:
    removed_rules, removed_map = cleanup_orphan_rules_sync()
    if removed_rules or removed_map:
        logger.info(
            "Auto rules sync: removed orphan rules=%s map_users=%s",
            ",".join(removed_rules) or "-",
            ",".join(removed_map) or "-",
        )
    return removed_rules, removed_map


def build_rules_sync_report() -> str:
    audit = audit_rules_sync()
    lines = [
        "<b>🧹 Синхронизация rules.toml</b>",
        f"Пользователей в credentials: <code>{len(audit['users'])}</code>",
    ]
    if audit["orphan_rule_prefixes"]:
        lines.append(
            "<b>Лишние allow-правила (префикс не в user_prefix_map)</b>\n"
            + html_expandable_pre_block("\n".join(audit["orphan_rule_prefixes"]))
        )
    else:
        lines.append("<blockquote>Лишних allow-правил не найдено.</blockquote>")
    if audit["missing_rules"]:
        body = "\n".join(f"{u} → {p}" for u, p in audit["missing_rules"].items())
        lines.append("<b>Нет allow-правила для пользователя</b>\n" + html_expandable_pre_block(body))
    if audit["orphan_map_entries"]:
        body = "\n".join(f"{u} → {p}" for u, p in audit["orphan_map_entries"].items())
        lines.append("<b>Записи в user_prefix_map без пользователя</b>\n" + html_expandable_pre_block(body))
    if audit["stale_profiles"]:
        lines.append(
            "<b>Профиль с random_prefix, но нет в map</b>\n"
            + html_expandable_pre_block(", ".join(audit["stale_profiles"]))
        )
    if not any(
        (
            audit["orphan_rule_prefixes"],
            audit["missing_rules"],
            audit["orphan_map_entries"],
            audit["stale_profiles"],
        )
    ):
        lines.append("<blockquote>✅ Расхождений не найдено.</blockquote>")
    return "\n\n".join(lines)


def _normalize_users_filter(filter_mode: str | None) -> str:
    mode = (filter_mode or "all").strip().lower()
    return mode if mode in USER_LIST_FILTERS else "all"


def _active_usernames_from_metrics(items: list[dict[str, Any]] | None = None) -> set[str]:
    if items is None:
        items = _fetch_metrics_clients() or []
    active: set[str] = set()
    for item in items:
        username, sessions = _parse_metric_item(item)
        if username and sessions > 0:
            active.add(username)
    return active


def _user_list_button_label(username: str, active_users: set[str]) -> str:
    state = "🟢" if username in active_users else "⚪"
    return f"{state} {username}"


def build_users_list_html(page: int = 0, *, filter_mode: str | None = "all") -> tuple[str, int, list[str]]:
    all_users = sorted(list_usernames())
    mode = _normalize_users_filter(filter_mode)
    active_users = _active_usernames_from_metrics()
    if mode == "online":
        users = [u for u in all_users if u in active_users]
    elif mode == "offline":
        users = [u for u in all_users if u not in active_users]
    else:
        users = all_users
    per = USERS_PER_PAGE
    total_pages = max(1, (len(users) + per - 1) // per) if users else 1
    page = max(0, min(page, total_pages - 1))
    lines = [
        "<b>📋 Список пользователей</b>",
        (
            f"Всего: <code>{len(all_users)}</code> · Онлайн: <code>{len(active_users & set(all_users))}</code> · "
            f"Фильтр: <code>{USER_LIST_FILTERS[mode]}</code> · Стр. <code>{page + 1}/{total_pages}</code>"
        ),
    ]
    if not users:
        lines.append("<blockquote>Список пуст.</blockquote>")
    return "\n\n".join(lines), total_pages, users


def users_list_inline_kb(
    page: int,
    total_pages: int,
    users_on_page: list[str],
    *,
    filter_mode: str | None = "all",
) -> InlineKeyboardMarkup:
    mode = _normalize_users_filter(filter_mode)
    active_users = _active_usernames_from_metrics()
    rows: list[list[InlineKeyboardButton]] = []
    rows.append(
        [
            InlineKeyboardButton(("✅ " if mode == "all" else "") + USER_LIST_FILTERS["all"], callback_data="uf:all"),
            InlineKeyboardButton(("✅ " if mode == "online" else "") + USER_LIST_FILTERS["online"], callback_data="uf:online"),
            InlineKeyboardButton(("✅ " if mode == "offline" else "") + USER_LIST_FILTERS["offline"], callback_data="uf:offline"),
        ]
    )
    user_buttons = [
        InlineKeyboardButton(_user_list_button_label(username, active_users), callback_data=f"udev:{username}")
        for username in users_on_page
        if len(username) <= MAX_USERNAME_LEN
    ]
    for i in range(0, len(user_buttons), 2):
        rows.append(user_buttons[i : i + 2])
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"ul:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"ul:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append(refresh_back_row(f"ul:{page}", "users"))
    return merge_inline_kb(*rows)


def _users_filter_from_context(context: ContextTypes.DEFAULT_TYPE | None) -> str:
    if context is None:
        return "all"
    return _normalize_users_filter(_ud(context).get(USER_LIST_FILTER_KEY))


def user_detail_inline_kb(username: str) -> InlineKeyboardMarkup:
    if len(username) > MAX_USERNAME_LEN:
        return merge_inline_kb(
            card_footer_row("user"),
        )
    return merge_inline_kb(
        [
            InlineKeyboardButton("📤 QR", callback_data=f"uqr:{username}"),
            InlineKeyboardButton("📄 TOML", callback_data=f"utc:{username}"),
        ],
        [
            InlineKeyboardButton("🔗 Ссылка", callback_data=f"ulink:{username}"),
            InlineKeyboardButton("📦 Всё", callback_data=f"uall:{username}"),
        ],
        [
            InlineKeyboardButton("🔐 Пароль", callback_data=f"urot:{username}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"udel:{username}", style="danger"),
        ],
        card_footer_row("user"),
    )


def toml_share_kb(username: str) -> InlineKeyboardMarkup:
    if len(username) > MAX_USERNAME_LEN:
        return InlineKeyboardMarkup([])
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔁 TOML снова", callback_data=f"utc:{username}"),
                InlineKeyboardButton("📤 QR", callback_data=f"uqr:{username}"),
            ],
            [
                InlineKeyboardButton("🔗 Ссылка", callback_data=f"ulink:{username}"),
                InlineKeyboardButton("🏠 Главная", callback_data="nav:home"),
            ],
        ]
    )


def validate_tt_configs() -> tuple[bool, str]:
    """Проверяет TOML-синтаксис vpn.toml/hosts.toml перед restart/reload.

    Раньше звала `trusttunnel_endpoint vpn.toml hosts.toml -v` — но -v это
    --version у самого эндпоинта: печатает версию и выходит, не читая
    settings-файлы вообще (проверено по исходнику main.rs). Проверка была
    no-op и всегда возвращала успех независимо от содержимого файлов.
    """
    for name in ("vpn.toml", "hosts.toml"):
        path = TT_DIR / name
        try:
            tomlkit.parse(path.read_text(encoding="utf-8"))
        except OSError as e:
            return False, f"{name}: {e}"
        except ValueError as e:
            return False, f"{name}: некорректный TOML — {e}"
    return True, "ok"


def service_reload_tls_if_possible() -> bool:
    code, out, _ = run_shell(
        f"systemctl show {SERVICE_NAME} -p CanReload --value",
        timeout=10,
    )
    if code != 0 or out.strip().lower() != "yes":
        return False
    run_process(["systemctl", "reload", SERVICE_NAME], timeout=40, retries=1, check=True)
    run_process(["systemctl", "is-active", "--quiet", SERVICE_NAME], timeout=20, retries=2, check=True)
    return True


def apply_tt_config_change(*, reload_tls: bool = False) -> str:
    ok, msg = validate_tt_configs()
    if not ok:
        raise CommandError(f"Проверка конфигов не прошла: {msg}")
    if reload_tls and service_reload_tls_if_possible():
        return "reload"
    service_restart_checked()
    return "restart"


def rotate_password_prompt_text(username: str) -> str:
    return (
        "🔐 <b>Смена пароля</b>\n"
        f"Пользователь: <code>{html.escape(username)}</code>\n"
        "Отправь новый password одним сообщением."
    )


def rotate_password_back_kb(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=callback_data, style="success")]])


def begin_rotate_password_wait(context: ContextTypes.DEFAULT_TYPE, username: str) -> None:
    clear_all_pending_text_waits(context)
    _ud(context)["pending_rotate_username"] = username


def delete_user_confirm_text(username: str) -> str:
    return (
        "<b>Удаление</b> · шаг 1/2\n"
        f"Пользователь <code>{html.escape(username)}</code> — продолжить?"
    )


def delete_user_confirm_kb(username: str) -> InlineKeyboardMarkup:
    return confirm_kb(f"del2:{username}", f"delcancel:{username}", danger=True)


_DEEPLINK_TAG_HAS_IPV6 = 0x04


def _deeplink_read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """QUIC varint (RFC 9000 §16): 2 старших бита 1-го байта — длина 1/2/4/8."""
    first = data[offset]
    length = 1 << (first >> 6)
    value = first & 0x3F
    for b in data[offset + 1 : offset + length]:
        value = (value << 8) | b
    return value, offset + length


def _deeplink_write_varint(value: int) -> bytes:
    if value <= 0x3F:
        return bytes([value])
    if value <= 0x3FFF:
        return (0x4000 | value).to_bytes(2, "big")
    if value <= 0x3FFFFFFF:
        return (0x80000000 | value).to_bytes(4, "big")
    return (0xC000000000000000 | value).to_bytes(8, "big")


def _deeplink_force_has_ipv6_off(deeplink: str) -> str:
    """Сервер не проксирует IPv6; апстрим хардкодит has_ipv6=true в deeplink
    (TLV tag 0x04, DEEP_LINK.md), в отличие от .toml — правим TLV руками.
    Ошибка разбора — возвращаем вход как есть."""
    prefix = "tt://?"
    if not deeplink.startswith(prefix):
        return deeplink
    payload = deeplink[len(prefix):]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        data = base64.urlsafe_b64decode(padded)
    except ValueError:
        return deeplink

    out = bytearray()
    try:
        offset = 0
        while offset < len(data):
            tag, offset = _deeplink_read_varint(data, offset)
            length, offset = _deeplink_read_varint(data, offset)
            value = data[offset : offset + length]
            if len(value) != length:
                return deeplink
            offset += length
            if tag == _DEEPLINK_TAG_HAS_IPV6:
                continue
            out += _deeplink_write_varint(tag)
            out += _deeplink_write_varint(length)
            out += value
    except IndexError:
        return deeplink

    out += _deeplink_write_varint(_DEEPLINK_TAG_HAS_IPV6)
    out += _deeplink_write_varint(1)
    out += b"\x00"

    encoded = base64.urlsafe_b64encode(bytes(out)).rstrip(b"=").decode("ascii")
    return f"{prefix}{encoded}"


def _decode_deeplink_tags(deeplink: str) -> dict[int, bytes]:
    prefix = "tt://?"
    if not deeplink.startswith(prefix):
        raise ValueError("не deeplink URI (нет tt://?)")
    payload = deeplink[len(prefix):]
    padded = payload + "=" * (-len(payload) % 4)
    data = base64.urlsafe_b64decode(padded)
    tags: dict[int, bytes] = {}
    offset = 0
    while offset < len(data):
        tag, offset = _deeplink_read_varint(data, offset)
        length, offset = _deeplink_read_varint(data, offset)
        value = data[offset : offset + length]
        if len(value) != length:
            raise ValueError("TLV повреждён: длина не совпадает")
        offset += length
        tags[tag] = value
    return tags


_DEEPLINK_REQUIRED_TAGS = {0x01: "hostname", 0x02: "addresses", 0x05: "username", 0x06: "password"}


def _validate_deeplink(deeplink: str) -> None:
    """Гейт перед выдачей пользователю: обязательные поля на месте, has_ipv6
    не откатился на дефолт апстрима (сервер не проксирует IPv6)."""
    tags = _decode_deeplink_tags(deeplink)
    for tag, name in _DEEPLINK_REQUIRED_TAGS.items():
        if not tags.get(tag):
            raise ValueError(f"deeplink без обязательного поля {name}")
    if tags.get(_DEEPLINK_TAG_HAS_IPV6) != b"\x00":
        raise ValueError("deeplink с has_ipv6 != false")


def _validate_client_toml(text: str) -> None:
    """Гейт перед выдачей .toml пользователю: обязательные поля на месте,
    has_ipv6 не откатился на дефолт апстрима."""
    doc = tomlkit.parse(text)
    endpoint = doc.get("endpoint")
    if not isinstance(endpoint, dict):
        raise ValueError("TOML без секции [endpoint]")
    for field in ("hostname", "username", "password"):
        if not str(endpoint.get(field, "")).strip():
            raise ValueError(f"TOML без обязательного поля endpoint.{field}")
    if endpoint.get("has_ipv6") is not False:
        raise ValueError("TOML с has_ipv6 != false")


def generate_deeplink(
    username: str,
    *,
    generate_new_prefix: bool = False,
    client_random_prefix: str | None = None,
) -> str:
    cmd = [
        "./trusttunnel_endpoint",
        "vpn.toml",
        "hosts.toml",
        "-c",
        username,
        "-a",
        _client_endpoint_address(ADDRESS),
        "--format",
        "deeplink",
        "--name",
        SERVER_NAME,
    ]
    upstreams = _protocol_dns_values()
    for dns in upstreams:
        cmd.extend(["--dns-upstream", dns])
    if client_random_prefix:
        cmd.extend(["--client-random-prefix", client_random_prefix])
    elif generate_new_prefix:
        cmd.append("--generate-client-random-prefix")

    p = run_process(
        cmd,
        cwd=TT_DIR,
        timeout=45,
        retries=1,
    )
    for line in p.stdout.splitlines():
        if line.startswith("tt://?"):
            result = _deeplink_force_has_ipv6_off(line.strip())
            _validate_deeplink(result)
            return result
    raise RuntimeError("Не удалось получить deeplink")


def _protocol_dns_values() -> list[str]:
    # DoQ идёт своим QUIC-подключением независимо от протокола тоннеля,
    # поэтому оба апстрима нужны всегда.
    return [
        "https://dns.adguard-dns.com/dns-query",
        "quic://dns.adguard-dns.com",
    ]


def _protocol_label(protocol: str) -> str:
    return "QUIC" if (protocol or "").strip().lower() == "quic" else "HTTP/2"


def _normalize_protocol(value: str | None) -> str:
    return value if value in ("h2", "quic") else "h2"


async def _load_export_profile(username: str) -> tuple[str, bool]:
    prof = await asyncio.to_thread(_get_user_profile, username)
    protocol = _normalize_protocol(str(prof.get("protocol", "h2")))
    random_prefix = bool(prof.get("random_prefix"))
    return protocol, random_prefix


def _protocol_kb_rows(make_cb) -> list[list[InlineKeyboardButton]]:
    """Строки выбора протокола. make_cb(protocol) строит callback_data."""
    return [
        [InlineKeyboardButton("Протокол: HTTP/2", callback_data=make_cb("h2"))],
        [InlineKeyboardButton("Протокол: QUIC", callback_data=make_cb("quic"))],
    ]


def _force_ipv6_off_toml(text: str) -> str:
    if not text.strip():
        return text
    try:
        doc = tomlkit.parse(text)
    except ValueError:
        return text
    # has_ipv6 может быть топ-уровнем или внутри [endpoint].
    doc["has_ipv6"] = False
    endpoint = doc.get("endpoint")
    if endpoint is not None:
        endpoint["has_ipv6"] = False
    out = tomlkit.dumps(doc)
    if not out.endswith("\n"):
        out += "\n"
    return out


def _toml_array(values) -> Any:
    arr = tomlkit.array()
    arr.multiline(False)
    arr.extend(values)
    return arr


def _build_endpoint_table(
    val: Callable[..., Any], *, protocol: str, random_prefix: bool
) -> Any:
    endpoint = tomlkit.table()
    hostname = str(val("hostname", _client_endpoint_address(ADDRESS)))
    endpoint["hostname"] = hostname

    addresses_src = val("addresses", [f"{_client_endpoint_address(ADDRESS)}:{VPN_MONITOR_PORT}"])
    addresses = addresses_src if isinstance(addresses_src, list) else [addresses_src]
    endpoint["addresses"] = _toml_array(str(a) for a in addresses)

    endpoint["has_ipv6"] = False
    endpoint["username"] = str(val("username", ""))
    endpoint["password"] = str(val("password", ""))
    endpoint["skip_verification"] = bool(val("skip_verification", False))
    endpoint["upstream_protocol"] = "http3" if protocol == "quic" else "http2"
    endpoint["upstream_fallback_protocol"] = "http2"
    endpoint["anti_dpi"] = True
    endpoint["custom_sni"] = ""

    prefix = str(val("client_random_prefix", "")).strip()
    if random_prefix and prefix:
        endpoint["client_random_prefix"] = prefix
    return endpoint


def _build_tun_table() -> Any:
    tun = tomlkit.table()
    tun["bound_if"] = ""
    tun["included_routes"] = _toml_array(["0.0.0.0/0", "2000::/3"])
    tun["excluded_routes"] = _toml_array([
        "0.0.0.0/8",
        "10.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/3",
    ])
    tun["mtu_size"] = 1280
    tun["change_system_dns"] = True
    return tun


def _build_client_style_toml(
    base_text: str,
    *,
    protocol: str,
    random_prefix: bool,
    dns_upstreams: list[str],
) -> str:
    try:
        src = tomlkit.parse(base_text)
    except ValueError:
        return base_text

    endpoint_src = src.get("endpoint")
    endpoint_tbl = endpoint_src if isinstance(endpoint_src, dict) else src

    def _val(key: str, default: Any = "") -> Any:
        return endpoint_tbl.get(key, src.get(key, default))

    out = tomlkit.document()
    out["loglevel"] = "info"
    out["vpn_mode"] = "general"
    out["killswitch_enabled"] = True
    out["killswitch_allow_ports"] = _toml_array([])
    out["post_quantum_group_enabled"] = True
    out["exclusions"] = _toml_array(SPLIT_RU_EXCLUSIONS)
    out["dns_upstreams"] = _toml_array(dns_upstreams)
    out["endpoint"] = _build_endpoint_table(_val, protocol=protocol, random_prefix=random_prefix)

    listener = tomlkit.table()
    listener["tun"] = _build_tun_table()
    out["listener"] = listener

    text = tomlkit.dumps(out)
    if not text.endswith("\n"):
        text += "\n"
    _validate_client_toml(text)
    return text


def generate_toml_config(
    username: str,
    *,
    generate_new_prefix: bool = False,
    client_random_prefix: str | None = None,
    dns_upstreams: list[str] | None = None,
) -> str:
    cmd = [
        "./trusttunnel_endpoint",
        "vpn.toml",
        "hosts.toml",
        "-c",
        username,
        "-a",
        _client_endpoint_address(ADDRESS),
        "--format",
        "toml",
        "--name",
        SERVER_NAME,
    ]
    upstreams = dns_upstreams or []
    for dns in upstreams:
        cmd.extend(["--dns-upstream", dns])
    if client_random_prefix:
        cmd.extend(["--client-random-prefix", client_random_prefix])
    elif generate_new_prefix:
        cmd.append("--generate-client-random-prefix")

    p = run_process(cmd, cwd=TT_DIR, timeout=60, retries=1, check=True)
    text = (p.stdout or "").strip()
    if not text:
        raise RuntimeError("Не удалось получить TOML-конфиг")
    return _force_ipv6_off_toml(text + "\n")


def add_user_and_make_link(
    username: str,
    password: str,
    *,
    random_prefix: bool = False,
) -> str:
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Некорректный username")
    if len(username) > MAX_USERNAME_LEN:
        raise ValueError(f"Слишком длинный username (макс. {MAX_USERNAME_LEN} символов)")
    if not password:
        raise ValueError("Пустой password")
    if any(ch in password for ch in ("\n", "\r", "\t")):
        raise ValueError("Некорректный password")

    doc, old_text = _load_credentials_doc()
    clients_aot = _clients_aot(doc)
    existing = {str(c.get("username", "")).strip() for c in clients_aot}
    if username in existing:
        raise ValueError("Пользователь уже существует")

    new_client = tomlkit.table()
    new_client["username"] = username
    new_client["password"] = password
    clients_aot.append(new_client)
    _atomic_write_credentials(tomlkit.dumps(doc), old_text)

    # Если apply_tt_config_change упадёт ниже, после того как prefix-мап/
    # rules.toml уже обновлены — откатить и их, иначе останется привязка
    # к несуществующему пользователю.
    made_prefix_map_change = False
    made_rule_change = False
    rollback_prefix: str | None = None
    try:
        before_prefixes = set(_extract_allow_prefixes()) if random_prefix else set()
        deeplink = generate_deeplink(username, generate_new_prefix=random_prefix)
        if random_prefix:
            after_prefixes = _extract_allow_prefixes()
            new_prefixes = [p for p in after_prefixes if p not in before_prefixes]
            if not new_prefixes:
                logger.warning("No new prefix detected for user=%s after generation", username)
            else:
                if len(new_prefixes) > 1:
                    # В карту идёт первый префикс — по нему идёт очистка.
                    logger.warning(
                        "Ambiguous new prefixes for user=%s: %s — using the first one",
                        username,
                        ",".join(new_prefixes),
                    )
                rollback_prefix = new_prefixes[0]
                mapping = _load_prefix_map()
                mapping[username] = rollback_prefix
                _save_prefix_map(mapping)
                made_prefix_map_change = True
                _tag_prefix_rule_with_username(rollback_prefix, username)
                made_rule_change = True
        else:
            mapping = _load_prefix_map()
            if username in mapping:
                mapping.pop(username, None)
                _save_prefix_map(mapping)
        # Рестарт после генерации, чтобы credentials и rules применились вместе.
        _auto_cleanup_rules_orphans()
        apply_tt_config_change()
        return deeplink
    except Exception:
        _atomic_write_credentials(old_text, old_text)
        if made_rule_change and rollback_prefix:
            _remove_prefix_rules_for_user([rollback_prefix], username)
        if made_prefix_map_change:
            mapping = _load_prefix_map()
            mapping.pop(username, None)
            _save_prefix_map(mapping)
        raise


def rotate_user_password(username: str, new_password: str) -> bool:
    if not new_password:
        raise ValueError("Пустой password")
    if any(ch in new_password for ch in ("\n", "\r", "\t")):
        raise ValueError("Некорректный password")

    doc, old_text = _load_credentials_doc()
    clients_aot = _clients_aot(doc)
    changed = False
    for client in clients_aot:
        if str(client.get("username", "")).strip() == username:
            client["password"] = new_password
            changed = True
            break

    if not changed:
        return False

    _atomic_write_credentials(tomlkit.dumps(doc), old_text)
    return True


def delete_user(username: str) -> bool:
    doc, old_text = _load_credentials_doc()
    clients_aot = _clients_aot(doc)
    found_idx: int | None = None
    remaining = 0
    for i, client in enumerate(clients_aot):
        if str(client.get("username", "")).strip() == username:
            found_idx = i
        else:
            remaining += 1

    if found_idx is None:
        return False

    if remaining == 0:
        # TrustTunnel не стартует без хотя бы одного клиента.
        raise ValueError(
            "Нельзя удалить последнего пользователя — TrustTunnel не запустится "
            "с пустым credentials.toml. Сначала добавь другого пользователя."
        )

    del clients_aot[found_idx]
    _atomic_write_credentials(tomlkit.dumps(doc), old_text)
    return True


def parse_version(v: str) -> tuple[int, int, int]:
    vv = v.strip().lstrip("vV")
    parts = vv.split(".")
    nums = []
    for p in parts[:3]:
        # Числовой префикс сегмента (1.2.3-beta → 3).
        m = re.match(r"^\d+", p)
        nums.append(int(m.group()) if m else 0)
    while len(nums) < 3:
        nums.append(0)
    a, b, c = nums
    return a, b, c


def _get_current_tt_version_uncached() -> str:
    version = run_cmd([str(TT_DIR / "trusttunnel_endpoint"), "--version"])
    return version if version else "unknown"


def get_current_tt_version() -> str:
    """Кэш на 30с — subprocess-вызов не нужен на каждый рендер карточки."""
    return cached_compute("tt_version", 30, _get_current_tt_version_uncached)


def get_latest_tt_version() -> str:
    url = "https://api.github.com/repos/TrustTunnel/TrustTunnel/releases/latest"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "tt-bot"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        raise RuntimeError("Не найден tag_name в GitHub API")
    return tag


def is_newer(latest: str, current: str) -> bool:
    if current == "unknown":
        return True
    return parse_version(latest) > parse_version(current)


# Действия


def build_add_conversation() -> ConversationHandler:
    # per_message=False: кнопки "Отмена / С префиксом / Протокол" живут на
    # отдельных сообщениях — не на стартовом. Без этого inline-кнопки не сработают.
    # addcancel зарегистрирован в каждом состоянии: исходная кнопка "Отмена"
    # остаётся видна на экране весь диалог, а не только на первом шаге.
    def _addcancel_handler() -> CallbackQueryHandler:
        return CallbackQueryHandler(
            traced_callback("add_cancel_callback", busy_guard(allow_guard(add_cancel_callback, conv_end=True))),
            pattern=r"^addcancel$",
        )

    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                traced_callback("add_entry_cb", busy_guard(allow_guard(add_entry_cb, conv_end=True))),
                pattern=r"^vpn:add$",
            ),
        ],
        states={
            ASK_ADD_USERNAME: [
                _addcancel_handler(),
                MessageHandler(filters.TEXT & ~filters.COMMAND, allow_guard(add_username, conv_end=True)),
            ],
            ASK_ADD_PASSWORD: [
                _addcancel_handler(),
                MessageHandler(filters.TEXT & ~filters.COMMAND, allow_guard(add_password, conv_end=True)),
            ],
            ASK_ADD_PREFIX: [
                _addcancel_handler(),
                CallbackQueryHandler(
                    traced_callback("add_prefix_choice", busy_guard(allow_guard(add_prefix_choice, conv_end=True))),
                    pattern=r"^addpref:",
                ),
            ],
            ASK_ADD_PROTOCOL: [
                _addcancel_handler(),
                CallbackQueryHandler(
                    traced_callback("add_protocol_choice", busy_guard(allow_guard(add_protocol_choice, conv_end=True))),
                    pattern=r"^addproto:",
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", allow_guard(cancel, conv_end=True))],
        allow_reentry=True,
    )


def get_info_card_html_cached() -> str:
    return cached_compute("info_card", MONITOR_CACHE_TTL_SEC, get_info_card_html)


def info_card_inline_kb() -> InlineKeyboardMarkup:
    return merge_inline_kb(
        [
            InlineKeyboardButton("🔄 Обновить", callback_data="infor"),
            InlineKeyboardButton("🧾 Логи", callback_data="nav:logs"),
        ],
        card_footer_row("home"),
    )


def cert_card_inline_kb() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[InlineKeyboardButton("📄 Certbot log", callback_data="certlog:20")]]
    return merge_inline_kb(*rows, card_footer_row("server"))


def _endpoint_metrics_hint() -> str:
    vpn_path = TT_DIR / "vpn.toml"
    if not vpn_path.exists():
        return "🟡 метрики: vpn.toml не найден"
    addr = ""
    try:
        doc = tomlkit.parse(vpn_path.read_text(encoding="utf-8"))
        metrics = doc.get("metrics")
        if not metrics:
            return "🟡 метрики: выключены в vpn.toml"
        addr = str(metrics.get("address", "")).strip()
        if not addr:
            return "🟡 метрики: address пустой"
        url = addr if addr.startswith("http") else f"http://{addr}/metrics"
        sample = _http_get_sample(url, timeout=3)
        if sample.strip():
            return "🟢 метрики: доступны"
        return f"🔴 метрики: нет ответа · <code>{html.escape(addr)}</code>"
    except (OSError, ValueError) as e:
        logger.debug("Не удалось проверить metrics endpoint: %s", e)
        if not addr:
            return "🔴 метрики: ошибка чтения vpn.toml"
        return f"🔴 метрики: нет ответа · <code>{html.escape(addr)}</code>"


def _port_listening_summary(port: int) -> str:
    out = run_cmd(["bash", "-c", f"ss -ltn 'sport = :{port}'"], timeout=8) or ""
    listening = any(line.strip().startswith("LISTEN") for line in out.splitlines())
    return f"{'🟢' if listening else '🔴'} порт {port}: {'слушает' if listening else 'НЕ слушает'}"


def _ram_health_summary() -> str:
    mem = parse_meminfo()
    mem_total = kb_to_mib(mem.get("MemTotal", 0))
    mem_avail = kb_to_mib(mem.get("MemAvailable", 0))
    if mem_total <= 0:
        return "RAM: <code>n/a</code>"
    mem_used = max(0.0, mem_total - mem_avail)
    used_percent = mem_used * 100 / mem_total
    return (
        f"RAM: <code>{_usage_bar(used_percent)}</code> · "
        f"<code>{mem_used:.0f}/{mem_total:.0f} MiB</code>"
    )


async def run_info_card(
    bot,
    cid: int,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    edit_message: Message | None = None,
) -> None:
    try:
        text = await asyncio.to_thread(get_info_card_html_cached)
        payload = clip_text(text)
        kb = info_card_inline_kb()
        if edit_message:
            await safe_edit_message_text(edit_message, payload, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await send_ui_card(
                bot,
                cid,
                payload,
                context=context,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                force_new=True,
            )
    except Exception:
        logger.exception("Info server failed")
        await send_ui_card(
            bot,
            cid,
            error_card("Не удалось получить информацию о сервере.", "нажми «🔄 Обновить» или проверь сервис"),
            context=context,
            parse_mode=ParseMode.HTML,
            force_new=True,
        )


async def run_server_card(
    bot,
    cid: int,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    edit_message: Message | None = None,
) -> None:
    try:
        text = await asyncio.to_thread(
            cached_compute, "server_card", MONITOR_CACHE_TTL_SEC, get_server_card_html
        )
        payload = clip_text(text)
        kb = server_card_inline_kb()
        if edit_message:
            await safe_edit_message_text(edit_message, payload, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await send_ui_card(
                bot,
                cid,
                payload,
                context=context,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
                force_new=True,
            )
    except Exception:
        logger.exception("Server card failed")
        await send_ui_card(
            bot,
            cid,
            error_card("Не удалось показать карточку сервера.", "повтори запрос через меню «Сервер»"),
            context=context,
            parse_mode=ParseMode.HTML,
            force_new=True,
        )


def service_restart_checked() -> None:
    run_process(["systemctl", "restart", SERVICE_NAME], timeout=40, retries=1, check=True)
    run_process(["systemctl", "is-active", "--quiet", SERVICE_NAME], timeout=20, retries=2, check=True)


def _classify_user_pick(users: list[str]) -> tuple[str, list[str], bool]:
    """Статус списка для picker: 'empty' | 'too_long' | 'ok'."""
    if not users:
        return "empty", [], False
    safe = [u for u in users if len(u) <= MAX_USERNAME_LEN]
    if not safe:
        return "too_long", [], False
    return "ok", safe, len(safe) < len(users)


async def run_user_pick(
    bot,
    cid: int,
    *,
    context: ContextTypes.DEFAULT_TYPE | None = None,
    title: str,
    cb_prefix: str,
    button_prefix: str = "",
    button_style: str | None = None,
    empty_hint: str,
    too_long_title: str,
    too_long_hint: str,
    hidden_hint: str,
) -> None:
    """Общий пикер пользователей: rotate/export/delete отличаются только
    заголовком, префиксом callback_data, подписью кнопки и текстом подсказок."""
    try:
        users = await asyncio.to_thread(list_usernames)
        status, safe, has_hidden = _classify_user_pick(users)
        if status == "empty":
            await send_ui_card(
                bot,
                cid,
                error_card("Список пользователей пуст.", empty_hint),
                context=context,
                parse_mode=ParseMode.HTML,
                force_new=True,
            )
            return
        if status == "too_long":
            await send_ui_card(
                bot,
                cid,
                error_card(too_long_title, too_long_hint),
                context=context,
                parse_mode=ParseMode.HTML,
                force_new=True,
            )
            return
        extra = f"\n\n<i>{hidden_hint}</i>" if has_hidden else ""
        buttons = [
            InlineKeyboardButton(f"{button_prefix}{u}", callback_data=f"{cb_prefix}:{u}", style=button_style)
            for u in safe
        ]
        keyboard = [[b] for b in buttons]
        keyboard.append(card_footer_row("users"))
        await send_ui_card(
            bot,
            cid,
            f"<b>{title}</b>\nВыбери пользователя." + extra,
            context=context,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
            force_new=True,
        )
    except Exception:
        logger.exception("List users failed")
        await send_ui_card(
            bot,
            cid,
            error_card("Не удалось получить список пользователей.", "повтори запрос"),
            context=context,
            parse_mode=ParseMode.HTML,
            force_new=True,
        )


async def run_rotate_pick(bot, cid: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_rotate_wait(context)
    await run_user_pick(
        bot,
        cid,
        context=context,
        title="🔐 Смена пароля",
        cb_prefix="rotpick",
        empty_hint="сначала добавь пользователя в разделе VPN",
        too_long_title="Имена слишком длинные для inline-кнопок.",
        too_long_hint=f"сократи username (макс. {MAX_USERNAME_LEN} символов) в credentials.toml",
        hidden_hint=f"Не все клиенты в списке (имя &gt; {MAX_USERNAME_LEN} симв.) — правь файл вручную.",
    )


async def run_export_pick(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    await run_user_pick(
        bot,
        cid,
        context=context,
        title="📤 QR",
        cb_prefix="exppick",
        empty_hint="сначала добавь пользователя в разделе VPN",
        too_long_title="Кнопки экспорта недоступны: имена слишком длинные.",
        too_long_hint=f"сократи username (макс. {MAX_USERNAME_LEN} символов)",
        hidden_hint=f"Часть клиентов скрыта (имя &gt; {MAX_USERNAME_LEN} симв.).",
    )


async def run_user_delete_list(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    await run_user_pick(
        bot,
        cid,
        context=context,
        title="Удаление клиента",
        cb_prefix="delask",
        button_prefix="🗑 ",
        button_style="danger",
        empty_hint="добавь пользователя перед удалением",
        too_long_title="Удаление через кнопки недоступно.",
        too_long_hint=f"сократи username (макс. {MAX_USERNAME_LEN} символов)",
        hidden_hint=f"Скрыты клиенты с именем &gt; {MAX_USERNAME_LEN} симв. — удали вручную в файле.",
    )


def _apply_rotate_password_sync(
    username: str, password: str
) -> tuple[str | None, tuple[str, str, bytes] | None]:
    """(ошибка, (username, deeplink, png)); при успехе первая часть None."""
    try:
        _, old_text = _load_credentials_doc()
    except RuntimeError as e:
        return str(e), None
    try:
        changed = rotate_user_password(username, password)
    except ValueError as e:
        return str(e), None
    if not changed:
        return f"Пользователь '{username}' не найден.", None
    try:
        apply_tt_config_change()
    except Exception:
        _atomic_write_credentials(old_text, old_text)
        raise
    prefix, _ = _export_context_for_username(username)
    deeplink = generate_deeplink(username, client_random_prefix=prefix)
    png = deeplink_qr_png(deeplink)
    return None, (username, deeplink, png)


def _export_bundle_sync(username: str) -> tuple[str, bytes]:
    prefix, _ = _export_context_for_username(username)
    deeplink = generate_deeplink(username, client_random_prefix=prefix)
    return deeplink, deeplink_qr_png(deeplink)


def _export_toml_bundle_sync(
    username: str, protocol: str, random_prefix: bool
) -> tuple[str, bytes]:
    existing_prefix = _prefix_for_username(username)
    client_prefix = existing_prefix if (random_prefix and existing_prefix) else None
    dns_upstreams = _protocol_dns_values()
    text = generate_toml_config(
        username,
        client_random_prefix=client_prefix,
        dns_upstreams=dns_upstreams,
    )
    text = _build_client_style_toml(
        text,
        protocol=protocol,
        random_prefix=random_prefix,
        dns_upstreams=dns_upstreams,
    )
    filename = f"trusttunnel-{username}.toml"
    return filename, text.encode("utf-8")


def _add_user_bundle_sync(username: str, password: str, random_prefix: bool) -> tuple[str, bytes]:
    deeplink = add_user_and_make_link(username, password, random_prefix=random_prefix)
    return deeplink, deeplink_qr_png(deeplink)


def _snapshot_tt_files(paths: list[Path]) -> dict[Path, tuple[str, int] | None]:
    return {
        p: (p.read_text(encoding="utf-8"), p.stat().st_mode & 0o777) if p.exists() else None
        for p in paths
    }


def _restore_tt_files(snapshot: dict[Path, tuple[str, int] | None]) -> None:
    for p, saved in snapshot.items():
        if saved is None:
            p.unlink(missing_ok=True)
        else:
            text, mode = saved
            _atomic_write_bytes(p, text.encode("utf-8"), mode=mode)


def _delete_user_and_restart_sync(username: str) -> tuple[bool, int]:
    """Удаляет пользователя; возвращает (ok, число снятых allow-правил).

    Если apply_tt_config_change упадёт после того как все 4 хранилища
    (credentials/profiles/prefix-map/rules) уже изменены — откатываем все.
    """
    snapshot = _snapshot_tt_files([CRED_FILE, USER_PROFILES_FILE, PREFIX_MAP_FILE, RULES_FILE])
    if not delete_user(username):
        return False, 0
    had_prefix_profile = bool(_get_user_profile(username).get("random_prefix"))
    prefixes = _prefixes_to_remove_for_user(username)
    _delete_user_profile(username)
    mapping = _load_prefix_map()
    mapping.pop(username, None)
    _save_prefix_map(mapping)
    # За один проход: и по префиксу из map, и по тегу user.
    rules_removed = _remove_prefix_rules_for_user(prefixes, username)
    if had_prefix_profile and not prefixes:
        logger.warning(
            "User %s: random_prefix в профиле, но нет записи в user_prefix_map — rules.toml не тронут",
            username,
        )
    elif prefixes and rules_removed == 0:
        logger.warning(
            "User %s: префикс %s в map, но matching rule не найден в rules.toml",
            username,
            ",".join(prefixes),
        )
    auto_removed_rules, _ = _auto_cleanup_rules_orphans()
    rules_removed += len(auto_removed_rules)
    try:
        apply_tt_config_change()
    except Exception:
        _restore_tt_files(snapshot)
        raise
    return True, rules_removed


def _tt_stop_sync() -> None:
    run_process(["systemctl", "stop", SERVICE_NAME], timeout=40, retries=0, check=True)


def _tt_install_sync(version: str) -> tuple[int, str, str]:
    # Зафиксированная версия и пропуск интерактивных вопросов установщика.
    # Инсталлятор берём с тега release (а не с master): пользователь увидел
    # на карточке tег v1.2.3 — и получает именно его, а не HEAD ветки.
    ver = version.strip().lstrip("vV")
    tag = shlex.quote(version.strip())
    return run_shell(
        f"curl -fsSL https://raw.githubusercontent.com/TrustTunnel/TrustTunnel/refs/tags/{tag}/scripts/install.sh "
        f"| sh -s -- -a y -V {shlex.quote(ver)}",
        timeout=1800,
        capture_limit=24000,
    )


def _tt_binary_backup_path() -> Path:
    return TT_DIR / "trusttunnel_endpoint.bak"


def _backup_tt_binary() -> bool:
    src = TT_DIR / "trusttunnel_endpoint"
    if not src.is_file():
        return False
    bak = _tt_binary_backup_path()
    _atomic_write_bytes(bak, src.read_bytes(), mode=0o600)
    return True


def _restore_tt_binary_backup() -> bool:
    bak = _tt_binary_backup_path()
    if not bak.is_file():
        return False
    target = TT_DIR / "trusttunnel_endpoint"
    # 0750 затирает execute-бит сервиса, запущенного не от root — сохраняем
    # реальный режим, если он был, иначе безопасный дефолт 0755.
    old_mode = target.stat().st_mode & 0o777 if target.exists() else None
    _atomic_write_bytes(target, bak.read_bytes(), mode=old_mode if old_mode is not None else 0o755)
    return True


def _tt_start_sync() -> None:
    run_process(["systemctl", "start", SERVICE_NAME], timeout=40, retries=1, check=True)
    run_process(["systemctl", "is-active", "--quiet", SERVICE_NAME], timeout=20, retries=2, check=True)


def _tt_start_best_effort() -> None:
    """Best-effort попытка поднять сервис после сбоя апгрейда — не бросает
    исключение, если не получилось (ошибка уже сообщена отдельно)."""
    run_process(["systemctl", "start", SERVICE_NAME], timeout=40, retries=0, check=False)


async def run_backup(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    # Занятость уже проверена вызывающим (backup_confirm_callback, через
    # _reject_if_busy) — единственный caller этой функции.
    await send_ui_card(bot, cid, step_card("Бэкап конфигов", 1, 2, "Архивирую файлы…"), context=context, parse_mode=ParseMode.HTML)
    try:
        backup_path, included = await asyncio.to_thread(create_configs_backup)
        if not included:
            await send_ui_card(
                bot,
                cid,
                error_card("Файлы для бэкапа не найдены.", "проверь наличие vpn.toml/hosts.toml/credentials.toml"),
                context=context,
                parse_mode=ParseMode.HTML,
                reply_markup=hub_inline_kb(),
            )
            return
        await send_ui_card(
            bot,
            cid,
            "✅ <b>Бэкап конфигов</b>\n[2/2] Готово.\n"
            f"<code>{html.escape(str(backup_path))}</code>\n"
            f"Включено: {html.escape(', '.join(included))}",
            context=context,
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )
    except Exception:
        logger.exception("Backup configs failed")
        await send_ui_card(
            bot,
            cid,
            error_card("Не удалось создать бэкап.", "проверь права на /opt/trusttunnel/backup и повтори"),
            context=context,
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )


async def run_backup_confirm(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    await send_ui_card(
        bot,
        cid,
        "<b>💾 Бэкап конфигов</b>\nСоздать свежий архив <code>latest-configs.tar.gz</code>?",
        context=context,
        parse_mode=ParseMode.HTML,
        reply_markup=confirm_kb("bak:yes", "bak:no", no_label="❌ Нет"),
    )


async def run_restore_pick(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    files = await asyncio.to_thread(list_files_in_latest_backup)
    if not files:
        await send_ui_card(
            bot,
            cid,
            error_card("Бэкап не найден или пуст.", "сначала сделай «💾 Бэкап»"),
            context=context,
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )
        return
    rows = [[InlineKeyboardButton("🧩 Восстановить всё", callback_data="resask:__all__")]]
    rows.extend([[InlineKeyboardButton(f"📄 {name}", callback_data=f"resask:{name}")] for name in files])
    rows.append(card_footer_row("server"))
    await send_ui_card(
        bot,
        cid,
        "<b>Восстановление из latest-configs.tar.gz</b>\nВыбери режим восстановления:",
        context=context,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )


def _run_apt_update_sync() -> tuple[int, str, str]:
    return run_shell("apt-get update", timeout=1800, capture_limit=16000)


def _run_apt_upgrade_sync() -> tuple[int, str, str]:
    cmd = "DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::='--force-confold' upgrade"
    return run_shell(cmd, timeout=7200, capture_limit=24000)


def _schedule_background_task(context: ContextTypes.DEFAULT_TYPE | None, coro) -> None:
    app = getattr(context, "application", None) if context is not None else None
    if app is not None and hasattr(app, "create_task"):
        app.create_task(coro)
        return
    task = asyncio.create_task(coro)
    BACKGROUND_TASKS.add(task)

    def _forget(done: asyncio.Task[Any]) -> None:
        BACKGROUND_TASKS.discard(done)
        try:
            done.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background task failed")

    task.add_done_callback(_forget)


@contextlib.asynccontextmanager
async def _typing_while(bot, cid: int, *, interval: float = 4.0):
    """Держит "печатает…" в чате на время долгой операции (OS/TT upgrade,
    cert renew) между обновлениями карточки прогресса."""
    async def _pulse():
        while True:
            try:
                await bot.send_chat_action(chat_id=cid, action=ChatAction.TYPING)
            except Exception as e:
                logger.debug("Не удалось отправить typing: %s", e)
            await asyncio.sleep(interval)

    task = asyncio.create_task(_pulse())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def _edit_task_card(bot, cid: int, msg_id: int, text: str, *, kb=None) -> None:
    try:
        await bot.edit_message_text(
            chat_id=cid,
            message_id=msg_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
    except BadRequest as e:
        if not is_message_not_modified(e):
            logger.debug("Не удалось отредактировать карточку операции: %s", e)
    except TelegramError as e:
        logger.debug("Не удалось отредактировать карточку операции: %s", e)
    except Exception:
        logger.exception("Неожиданная ошибка при обновлении карточки операции")


async def run_os_upgrade(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    # Занятость уже проверена вызывающим (os_upgrade_callback, через _reject_if_busy).
    busy_set("обновление ОС")
    started_text = (
        "⏳ <b>Обновление ОС</b> запущено.\n"
        "<i>Операция идёт в фоне, меню работает.</i>"
    )
    try:
        if context is not None and isinstance(_ud(context).get(UI_MESSAGE_ID_KEY), int):
            await upsert_ui_message(context, cid, started_text, parse_mode=ParseMode.HTML)
            msg_id = _ud(context)[UI_MESSAGE_ID_KEY]
        else:
            msg = await send_inline_message(bot, cid, started_text, parse_mode=ParseMode.HTML)
            msg_id = msg.message_id
    except Exception:
        busy_clear()
        logger.exception("Не удалось запустить обновление ОС")
        raise
    _schedule_background_task(context, _os_upgrade_task(bot, cid, msg_id))


async def _os_upgrade_task(bot, cid: int, msg_id: int) -> None:
    try:
        async with _typing_while(bot, cid):
            await _edit_task_card(bot, cid, msg_id, "⏳ <b>Обновление ОС</b>\n[1/3] apt-get update…")
            code, _, err = await asyncio.to_thread(_run_apt_update_sync)
            if code != 0:
                logger.error("OS update failed at apt-get update: %s", err)
                await _edit_task_card(
                    bot,
                    cid,
                    msg_id,
                    "❌ <b>Обновление ОС</b>\napt-get update завершился с ошибкой.\n"
                    f"<code>{html.escape((err or 'unknown')[:500])}</code>\n"
                    "<i>Что делать: проверь сеть/репозитории и повтори.</i>",
                    kb=hub_inline_kb(),
                )
                return
            await _edit_task_card(bot, cid, msg_id, "⏳ <b>Обновление ОС</b>\n[2/3] apt-get upgrade…")
            code, _, err = await asyncio.to_thread(_run_apt_upgrade_sync)
            if code == 0:
                text = "✅ <b>Обновление ОС</b>\n[3/3] Готово."
                if Path("/var/run/reboot-required").exists():
                    text += "\n⚠️ Требуется перезагрузка сервера (обновилось ядро/системные библиотеки)."
                await _edit_task_card(bot, cid, msg_id, text, kb=hub_inline_kb())
            else:
                logger.error("OS update failed: %s", err)
                await _edit_task_card(
                    bot,
                    cid,
                    msg_id,
                    "❌ <b>Обновление ОС</b>\n"
                    f"<code>{html.escape((err or 'unknown')[:700])}</code>\n"
                    "<i>Что делать: посмотри логи apt и повтори.</i>",
                    kb=hub_inline_kb(),
                )
    except Exception:
        logger.exception("OS update task failed")
        await _edit_task_card(
            bot,
            cid,
            msg_id,
            "❌ <b>Обновление ОС</b>\nНе удалось выполнить. Повтори позже или проверь apt.\n"
            "<i>Детали: journalctl -u tt-bot</i>",
            kb=hub_inline_kb(),
        )
    finally:
        busy_clear()


def _fetch_tt_versions() -> tuple[str, str]:
    return get_current_tt_version(), get_latest_tt_version()


async def run_tt_upgrade_flow(bot, cid: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_ui_card(bot, cid, step_card("Обновление TrustTunnel", 1, 4, "Проверяю версии на GitHub…"), context=context, parse_mode=ParseMode.HTML)
    try:
        current, latest = await asyncio.to_thread(_fetch_tt_versions)

        if not is_newer(latest, current):
            await send_ui_card(
                bot,
                cid,
                "✅ <b>TrustTunnel</b>\n"
                f"Текущая: <code>{html.escape(current)}</code>\n"
                f"Последняя: <code>{html.escape(latest)}</code>\n"
                "Обновление не требуется",
                context=context,
                parse_mode=ParseMode.HTML,
                reply_markup=hub_inline_kb(),
            )
            return

        _ud(context)["pending_tt_update"] = {"current": current, "latest": latest}
        await send_ui_card(
            bot,
            cid,
            "<b>Доступно обновление TrustTunnel</b>\n"
            f"Текущая: <code>{html.escape(current)}</code>\n"
            f"Новая: <code>{html.escape(latest)}</code>\n\n"
            "Подтвердить установку?",
            context=context,
            reply_markup=confirm_kb("ttupd_yes", "ttupd_no"),
            parse_mode=ParseMode.HTML,
        )
    except urllib.error.URLError:
        await send_ui_card(
            bot,
            cid,
            error_card("Не удалось проверить версию на GitHub.", "проверь сеть/API и повтори"),
            context=context,
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )
    except Exception:
        logger.exception("TT update check failed")
        await send_ui_card(
            bot,
            cid,
            error_card("Не удалось проверить версию TrustTunnel.", "проверь логи tt-bot и повтори"),
            context=context,
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )


async def run_os_upgrade_confirm(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    await send_ui_card(
        bot,
        cid,
        "<b>🆙 Обновление ОС</b>\nМожет обновить ядро/системные библиотеки. Продолжить?",
        context=context,
        reply_markup=confirm_kb("osupd_yes", "osupd_no", danger=True),
        parse_mode=ParseMode.HTML,
    )


async def run_reboot_confirm(bot, cid: int, *, context: ContextTypes.DEFAULT_TYPE | None = None) -> None:
    await send_ui_card(
        bot,
        cid,
        "<b>🔁 Перезагрузка сервера</b>\nПродолжить?",
        context=context,
        reply_markup=confirm_kb("rbdo", "rbcancel", danger=True),
        parse_mode=ParseMode.HTML,
    )


# Главный экран
async def send_home_screen(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = UI_WELCOME + "\n\n" + UI_HOME
    try:
        await upsert_ui_message(
            context,
            message.chat_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
            force_new=True,
        )
        await _delete_message_quiet(message)
    except Exception:
        logger.exception("send_home_screen failed")
        await message.reply_text(
            text + "\n\n❌ Ошибка. Перезапусти tt-bot и проверь journalctl -u tt-bot",
            parse_mode=ParseMode.HTML,
        )


async def _navigate_inline(
    q: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, text: str, kb: InlineKeyboardMarkup
) -> None:
    media_attrs = (
        "photo",
        "document",
        "video",
        "animation",
        "audio",
        "voice",
        "video_note",
        "sticker",
    )
    msg = _accessible(q.message)
    if msg and any(getattr(msg, attr, None) for attr in media_attrs):
        await _clear_inline_keyboard_quiet(context.bot, msg.chat_id, msg.message_id)
        sent = await send_inline_message(
            context.bot,
            msg.chat_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        _ud(context)[UI_MESSAGE_ID_KEY] = sent.message_id
        return
    _remember_ui_message(context, msg)
    await safe_edit_message_text(q, text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ----- Navigation handlers -----
async def ui_back_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reset_nav_state(context)
    text = UI_WELCOME + "\n\n" + UI_HOME
    kb = hub_inline_kb()
    if update.callback_query:
        q = update.callback_query
        # Ответ на callback уже отправлен в nav_callback.
        await _navigate_inline(q, context, text, kb)
    elif update.message:
        await send_home_screen(update.message, context)


async def ui_open_vpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_rotate_wait(context)
    await cancel_add_flow(context)
    kb = vpn_hub_kb()
    if update.callback_query:
        q = update.callback_query
        # Ответ на callback уже отправлен в nav_callback.
        await _navigate_inline(q, context, UI_OPEN_VPN, kb)
    elif update.message:
        await upsert_ui_message(
            context,
            _chat_id(update),
            UI_OPEN_VPN,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            force_new=True,
        )
        await _delete_message_quiet(update.message)


async def ui_open_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_rotate_wait(context)
    await cancel_add_flow(context)
    kb = server_hub_kb()
    if update.callback_query:
        q = update.callback_query
        # Ответ на callback уже отправлен в nav_callback.
        await _navigate_inline(q, context, UI_OPEN_SERVER, kb)
    elif update.message:
        await upsert_ui_message(
            context,
            _chat_id(update),
            UI_OPEN_SERVER,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
            force_new=True,
        )
        await _delete_message_quiet(update.message)


async def users_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("ul:"):
        return
    await cb_answer(q)
    try:
        page = int((q.data or "ul:0")[3:])
    except ValueError:
        page = 0
    try:
        filter_mode = _users_filter_from_context(context)
        html_text, total_pages, users = await asyncio.to_thread(
            build_users_list_html, page, filter_mode=filter_mode
        )
        per = USERS_PER_PAGE
        page = max(0, min(page, total_pages - 1))
        slice_ = users[page * per : (page + 1) * per]
        kb = users_list_inline_kb(page, total_pages, slice_, filter_mode=filter_mode)
        await safe_edit_message_text(
            q,
            clip_text(html_text),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        _remember_ui_message(context, _accessible(q.message))
    except Exception:
        logger.exception("Users page failed")


async def users_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("uf:"):
        return
    await cb_answer(q)
    filter_mode = _normalize_users_filter((q.data or "uf:all").split(":", 1)[1])
    _ud(context)[USER_LIST_FILTER_KEY] = filter_mode
    try:
        html_text, total_pages, users = await asyncio.to_thread(
            build_users_list_html, 0, filter_mode=filter_mode
        )
        per = USERS_PER_PAGE
        slice_ = users[:per]
        await safe_edit_message_text(
            q,
            clip_text(html_text),
            parse_mode=ParseMode.HTML,
            reply_markup=users_list_inline_kb(0, total_pages, slice_, filter_mode=filter_mode),
        )
        _remember_ui_message(context, _accessible(q.message))
    except Exception:
        logger.exception("Users filter failed")


def _render_user_detail_text(username: str) -> str:
    prefix, proto = _export_context_for_username(username)
    prof = _get_user_profile(username)
    prefix_line = (
        f"префикс: <code>{html.escape(prefix)}</code>"
        if prefix
        else ("префикс: ⚠️ в профиле, но нет в map" if prof.get("random_prefix") else "префикс: нет")
    )
    return (
        f"<b>👤 {html.escape(username)}</b>\n"
        f"<blockquote>{prefix_line}\n"
        f"протокол: <code>{html.escape(_protocol_label(proto))}</code></blockquote>"
    )


async def user_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("udev:"):
        return
    await cb_answer(q)
    clear_rotate_wait(context)
    # Промпт ротации сейчас переиспользуется (edit) под карточку пользователя —
    # он не сгорает, просто перестаёт быть «висящим» сообщением ротации.
    _untrack_scaffold(context, ROTATE_SCAFFOLD_KEY, _accessible(q.message))
    username = data.split(":", 1)[1]
    try:
        if username not in await asyncio.to_thread(list_usernames):
            await safe_edit_message_text(
                q,
                f"Пользователь <code>{html.escape(username)}</code> не найден.",
                parse_mode=ParseMode.HTML,
                reply_markup=merge_inline_kb(card_footer_row("user")),
            )
            return
        text = await asyncio.to_thread(_render_user_detail_text, username)
        await safe_edit_message_text(
            q,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=user_detail_inline_kb(username),
        )
    except Exception:
        logger.exception("User detail failed")
        await safe_edit_message_text(
            q,
            error_card("Не удалось показать карточку пользователя.", "проверь credentials.toml"),
            parse_mode=ParseMode.HTML,
            reply_markup=merge_inline_kb(card_footer_row("user")),
        )


async def _send_user_qr(q: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, username: str, action_label: str) -> None:
    prefix, proto = await asyncio.to_thread(_export_context_for_username, username)
    async with CRED_LOCK:
        deeplink, png = await asyncio.to_thread(_export_bundle_sync, username)
    msg = _accessible(q.message)
    if not msg:
        return
    mode = _protocol_label(proto)
    if prefix:
        mode += f" · prefix {_format_client_prefix(prefix)}"
    await reply_deeplink_with_qr(
        msg,
        username=username,
        deeplink=deeplink,
        action_label=action_label,
        mode_label=mode,
        png=png,
        delete_source=True,
    )


async def user_action_qr_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith(("uqr:", "ure:")):
        return
    await cb_answer(q, "QR…")
    username = data.split(":", 1)[1]
    try:
        known = await asyncio.to_thread(list_usernames)
    except ValueError:
        await cb_answer(q, "credentials.toml повреждён", alert=True)
        return
    if username not in known:
        await cb_answer(q, "Пользователь не найден", alert=True)
        return
    label = "повтор QR" if data.startswith("ure:") else "экспорт из списка"
    try:
        await _send_user_qr(q, context, username, label)
    except Exception:
        logger.exception("User quick QR failed")
        await send_inline_message(context.bot, _chat_id(update), "Ошибка. Не удалось выдать QR.")


async def user_action_toml_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("utc:"):
        return
    await cb_answer(q, "TOML…")
    username = data.split(":", 1)[1]
    try:
        known = await asyncio.to_thread(list_usernames)
    except ValueError:
        await cb_answer(q, "credentials.toml повреждён", alert=True)
        return
    if username not in known:
        await cb_answer(q, "Пользователь не найден", alert=True)
        return
    protocol, random_prefix = await _load_export_profile(username)
    try:
        async with CRED_LOCK:
            filename, payload = await asyncio.to_thread(
                _export_toml_bundle_sync, username, protocol, random_prefix
            )
        await context.bot.send_document(
            chat_id=_chat_id(update),
            document=InputFile(io.BytesIO(payload), filename=filename),
            caption=f"<b>TOML</b> · <code>{html.escape(username)}</code>\n{_protocol_label(protocol)}",
            parse_mode=ParseMode.HTML,
            reply_markup=toml_share_kb(username),
            disable_notification=True,
        )
        await _delete_callback_source_quiet(q)
    except Exception:
        logger.exception("Quick TOML failed")
        await send_inline_message(context.bot, _chat_id(update), "Ошибка. Не удалось отправить TOML.")


async def user_action_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("ulink:"):
        return
    await cb_answer(q, "Ссылка…")
    username = data.split(":", 1)[1]
    try:
        known = await asyncio.to_thread(list_usernames)
    except ValueError:
        await cb_answer(q, "credentials.toml повреждён", alert=True)
        return
    if username not in known:
        await cb_answer(q, "Пользователь не найден", alert=True)
        return
    try:
        deeplink, _ = await asyncio.to_thread(_export_bundle_sync, username)
        await send_inline_message(
            context.bot,
            chat_id=_chat_id(update),
            text=f"<b>🔗 Ссылка</b> · <code>{html.escape(username)}</code>\n{deeplink_spoiler_html(deeplink)}",
            parse_mode=ParseMode.HTML,
            reply_markup=merge_inline_kb(
                [
                    InlineKeyboardButton("📤 QR", callback_data=f"uqr:{username}"),
                    InlineKeyboardButton("📄 TOML", callback_data=f"utc:{username}"),
                ],
                [InlineKeyboardButton("🏠 Главная", callback_data="nav:home")],
            ),
        )
        await _delete_callback_source_quiet(q)
    except Exception:
        logger.exception("Quick link failed")
        await send_inline_message(context.bot, _chat_id(update), "Ошибка. Не удалось отправить ссылку.")


async def user_action_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("uall:"):
        return
    await cb_answer(q, "Готовлю…")
    username = data.split(":", 1)[1]
    try:
        known = await asyncio.to_thread(list_usernames)
    except ValueError:
        await cb_answer(q, "credentials.toml повреждён", alert=True)
        return
    if username not in known:
        await cb_answer(q, "Пользователь не найден", alert=True)
        return
    protocol, random_prefix = await _load_export_profile(username)
    try:
        async with CRED_LOCK:
            deeplink, png = await asyncio.to_thread(_export_bundle_sync, username)
            filename, payload = await asyncio.to_thread(
                _export_toml_bundle_sync, username, protocol, random_prefix
            )
        msg = _accessible(q.message)
        if msg:
            await reply_deeplink_with_qr(
                msg,
                username=username,
                deeplink=deeplink,
                action_label="экспорт",
                mode_label=_protocol_label(protocol),
                include_service=False,
                png=png,
            )
        await context.bot.send_document(
            chat_id=_chat_id(update),
            document=InputFile(io.BytesIO(payload), filename=filename),
            caption=f"<b>TOML</b> · <code>{html.escape(username)}</code>\n{_protocol_label(protocol)}",
            parse_mode=ParseMode.HTML,
            reply_markup=toml_share_kb(username),
            disable_notification=True,
        )
        await send_inline_message(
            context.bot,
            chat_id=_chat_id(update),
            text=f"<b>🔗 Ссылка</b> · <code>{html.escape(username)}</code>\n{deeplink_spoiler_html(deeplink)}",
            parse_mode=ParseMode.HTML,
            reply_markup=merge_inline_kb(
                [InlineKeyboardButton("🏠 Главная", callback_data="nav:home")],
            ),
        )
        await _delete_callback_source_quiet(q)
    except Exception:
        logger.exception("Quick all export failed")
        await send_inline_message(context.bot, _chat_id(update), "Ошибка. Не удалось отправить комплект.")


async def user_action_rotate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("urot:"):
        return
    await cb_answer(q)
    username = data.split(":", 1)[1]
    begin_rotate_password_wait(context, username)
    # Только один промпт ротации живёт за раз — начало новой ротации сжигает
    # предыдущий, а не оставляет его висеть в чате.
    await _cleanup_rotate_scaffold(context.bot, context)
    prompt = await send_inline_message(
        context.bot,
        _chat_id(update),
        rotate_password_prompt_text(username),
        parse_mode=ParseMode.HTML,
        reply_markup=rotate_password_back_kb(f"udev:{username}"),
    )
    _ud(context).setdefault(ROTATE_SCAFFOLD_KEY, []).append((prompt.chat_id, prompt.message_id))
    await _delete_callback_source_quiet(q)


async def user_action_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("udel:"):
        return
    await cb_answer(q)
    username = data.split(":", 1)[1]
    await safe_edit_message_text(
        q,
        delete_user_confirm_text(username),
        reply_markup=delete_user_confirm_kb(username),
        parse_mode=ParseMode.HTML,
    )


def rules_sync_inline_kb() -> InlineKeyboardMarkup:
    return merge_inline_kb(
        [
            InlineKeyboardButton("🧹 Удалить лишнее", callback_data="rulesync:clean"),
            InlineKeyboardButton("➕ Починить rules", callback_data="rulesync:repair"),
        ],
        [InlineKeyboardButton("🔄 Обновить", callback_data="rulesync:view")],
        card_footer_row("rules"),
    )


async def rules_sync_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("rulesync:"):
        return
    mode = data.split(":", 1)[1]
    if mode == "repair":
        await cb_answer(q, "Чиню rules…")
        try:
            async with CRED_LOCK:
                fixed, errors = await asyncio.to_thread(repair_missing_rules_sync)
            summary = (
                f"Добавлено allow-правил: <code>{len(fixed)}</code>\n"
                f"Ошибки: <code>{len(errors)}</code>"
            )
            if fixed:
                summary += "\nСервис: <code>restart</code>"
            if errors:
                summary += "\n" + html_pre_block("\n".join(errors[:8]))
            text = await asyncio.to_thread(build_rules_sync_report) + "\n\n" + summary
        except Exception:
            logger.exception("Rules repair failed")
            text = "Ошибка при восстановлении rules.toml."
    elif mode == "clean":
        await cb_answer(q, "Очистка…")
        try:
            async with CRED_LOCK:
                removed_rules, removed_map = await asyncio.to_thread(cleanup_orphan_rules_sync)
            summary = (
                f"Удалено allow-правил: <code>{len(removed_rules)}</code>\n"
                f"Удалено записей map: <code>{len(removed_map)}</code>"
            )
            if removed_rules or removed_map:
                try:
                    await asyncio.to_thread(apply_tt_config_change)
                    summary += "\nСервис: <code>restart</code>"
                except CommandError as e:
                    summary += f"\n❌ {html.escape(str(e))}"
            text = await asyncio.to_thread(build_rules_sync_report) + "\n\n" + summary
        except Exception:
            logger.exception("Rules sync clean failed")
            text = "Ошибка при очистке rules.toml."
    else:
        await cb_answer(q)
        text = await asyncio.to_thread(build_rules_sync_report)
    kb = rules_sync_inline_kb()
    if q.message:
        await safe_edit_message_text(
            q,
            clip_text(text),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        _remember_ui_message(context, _accessible(q.message))
    else:
        sent = await send_inline_message(
            context.bot,
            _chat_id(update),
            clip_text(text),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        _remember_ui_message(context, sent)


async def nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("nav:"):
        return
    cid = _chat_id(update)
    msg = _accessible(q.message)
    await reset_nav_state(context)
    _remember_ui_message(context, msg)

    route_handlers: dict[str, Any] = {
        "nav:home": ui_back_home,
        "nav:vpn": ui_open_vpn,
        "nav:server": ui_open_server,
    }
    handler = route_handlers.get(data)
    if handler is not None:
        # Один answerCallbackQuery на весь переход.
        await cb_answer(q, "Меню" if data == "nav:home" else None)
        await handler(update, context)
        return

    if data == "nav:close":
        await cb_answer(q, "Закрыто")
        if msg is not None:
            try:
                await msg.delete()
            except Exception as e:
                logger.debug("Не удалось удалить сообщение при nav:close: %s", e)
        return

    if data == "nav:servercard":
        await cb_answer(q)
        await run_server_card(context.bot, cid, edit_message=msg)
        return

    if data == "nav:info":
        await cb_answer(q)
        await run_info_card(context.bot, cid, edit_message=msg)
        return

    if data == "nav:clients":
        await cb_answer(q)
        try:
            html_text, total_pages, _, _ = await asyncio.to_thread(clients_card_html, 0)
            kb = clients_inline_kb(0, total_pages)
            await safe_edit_message_text(
                q, clip_text(html_text), parse_mode=ParseMode.HTML, reply_markup=kb
            )
        except Exception:
            logger.exception("nav clients failed")
        return

    if data.startswith("nav:users:"):
        await cb_answer(q)
        try:
            page = int(data.split(":", 2)[2])
        except ValueError:
            page = 0
        try:
            filter_mode = _users_filter_from_context(context)
            html_text, total_pages, users = await asyncio.to_thread(
                build_users_list_html, page, filter_mode=filter_mode
            )
            per = USERS_PER_PAGE
            page = max(0, min(page, total_pages - 1))
            slice_ = users[page * per : (page + 1) * per]
            await safe_edit_message_text(
                q,
                clip_text(html_text),
                parse_mode=ParseMode.HTML,
                reply_markup=users_list_inline_kb(page, total_pages, slice_, filter_mode=filter_mode),
            )
        except Exception:
            logger.exception("nav users failed")
            await safe_edit_message_text(
                q,
                error_card("Не удалось показать список пользователей.", "проверь credentials.toml и попробуй ещё раз"),
                parse_mode=ParseMode.HTML,
                reply_markup=vpn_hub_kb(),
            )
        return

    if data == "nav:logs":
        await cb_answer(q)
        text, chunk, total_chunks = await asyncio.to_thread(build_logs_view, "all", 50, 0)
        await safe_edit_message_text(
            q,
            clip_text(text),
            reply_markup=logs_inline_kb("all", 50, chunk, total_chunks),
        )
        return

    if data == "nav:cert":
        await cb_answer(q)
        text, _ = await asyncio.to_thread(
            cached_compute, "cert_card", MONITOR_CACHE_TTL_SEC, get_cert_card_data
        )
        await safe_edit_message_text(
            q,
            clip_text(text),
            parse_mode=ParseMode.HTML,
            reply_markup=cert_card_inline_kb(),
        )
        return

    # Неизвестный nav:* (например, кнопка из старой версии карточки) — иначе
    # спиннер крутится до таймаута, не получив answerCallbackQuery.
    await cb_answer(q)


async def srv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("srv:"):
        return
    action = data.split(":", 1)[1]
    cid = _chat_id(update)
    await cb_answer(q)
    if action == "restart":
        await restart_tt_prompt_callback(update, context)
    elif action == "backup":
        await run_backup_confirm(context.bot, cid, context=context)
    elif action == "restore":
        await run_restore_pick(context.bot, cid, context=context)
    elif action == "ttupd":
        await run_tt_upgrade_flow(context.bot, cid, context)
    elif action == "osupd":
        await run_os_upgrade_confirm(context.bot, cid, context=context)
    elif action == "reboot":
        await run_reboot_confirm(context.bot, cid, context=context)


async def vpn_hub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("vpn:"):
        return
    action = data.split(":", 1)[1]
    # vpn:add обрабатывает диалог добавления пользователя.
    cid = _chat_id(update)
    if action == "find":
        await cb_answer(q)
        clear_all_pending_text_waits(context)
        await _cleanup_user_search_scaffold(context.bot, context)
        _ud(context)["pending_user_search"] = True
        prompt = await send_inline_message(
            context.bot,
            cid,
            "🔍 Введи <b>username</b> для поиска:",
            parse_mode=ParseMode.HTML,
            reply_markup=user_search_cancel_kb(),
        )
        _track_user_search_message(context, prompt)
        return
    await cb_answer(q)
    clear_all_pending_text_waits(context)
    if action == "rotate":
        await run_rotate_pick(context.bot, cid, context)
    elif action == "export":
        await run_export_pick(context.bot, cid, context=context)
    elif action == "del":
        await run_user_delete_list(context.bot, cid, context=context)


async def copyhost_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data != "copyhost:msg":
        return
    await cb_answer(q)
    await send_inline_message(
        context.bot,
        _chat_id(update),
        f"Домен endpoint:\n<code>{html.escape(_client_endpoint_address(ADDRESS))}</code>",
        parse_mode=ParseMode.HTML,
    )


async def user_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _ud(context).pop("pending_user_search", False):
        return
    message = update.message
    assert message is not None
    username = (message.text or "").strip()
    if not username:
        await message.reply_text("Пустой username.")
        return
    try:
        known = await asyncio.to_thread(list_usernames)
    except ValueError:
        await message.reply_text("credentials.toml повреждён — проверь файл вручную.")
        return
    if username not in known:
        await message.reply_text(
            f"Пользователь <code>{html.escape(username)}</code> не найден.",
            parse_mode=ParseMode.HTML,
        )
        return
    text = await asyncio.to_thread(_render_user_detail_text, username)
    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=user_detail_inline_kb(username),
    )


async def user_search_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data != "searchcancel":
        return
    await cb_answer(q, "Отменено")
    _ud(context).pop("pending_user_search", None)
    await _cleanup_user_search_scaffold(context.bot, context, current_message=_accessible(q.message))


async def restart_tt_prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "<b>♻️ Перезапуск trusttunnel</b>\nПодтвердить перезапуск сервиса?"
    kb = confirm_kb("ttrst_yes", "ttrst_no", danger=True)
    await send_ui_card(context.bot, _chat_id(update), text, context=context, reply_markup=kb, parse_mode=ParseMode.HTML)


def kb_menu_only() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["🏠 Меню"]], resize_keyboard=True)


async def _go_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reset_nav_state(context)
    message = update.message
    assert message is not None
    await send_home_screen(message, context)


# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Один носитель ReplyKeyboardMarkup на чат, не дублировать на каждом /start.
    # Чистые эмодзи нельзя — Telegram рисует их стикером.
    await context.bot.send_message(
        _chat_id(update),
        "⌨️ Кнопка 🏠 Меню внизу — вернуться на главную",
        reply_markup=kb_menu_only(),
    )
    await _go_home(update, context)


async def menu_button_tap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _go_home(update, context)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    assert message is not None and user is not None
    await message.reply_text(f"Твой Telegram ID: {user.id}")


def _services_status_line() -> str:
    tt = run_cmd(["systemctl", "is-active", SERVICE_NAME]) or "unknown"
    bot = run_cmd(["systemctl", "is-active", "tt-bot.service"]) or "unknown"
    return f"trusttunnel: {tt} · tt-bot: {bot}"


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    assert message is not None
    try:
        services = await asyncio.to_thread(_services_status_line)
    except Exception:
        services = "n/a"
    busy = busy_label()
    await message.reply_text(
        f"🟢 tt-bot жив\n"
        f"Операций в работе: {busy or 'нет'}\n"
        f"{services}"
    )


async def diff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    assert message is not None
    text = await asyncio.to_thread(_diff_against_latest_backup)
    await message.reply_text(
        f"<blockquote expandable><pre>{html.escape(clip_text(text, CLIP_TEXT_LIMIT_IN_BLOCKQUOTE))}</pre></blockquote>",
        parse_mode=ParseMode.HTML,
    )


# Scaffold cleanup (общий механизм для «сгорающих» служебных сообщений:
# поиск пользователя, сценарий добавления, промпт ротации пароля).
async def _burn_scaffold(
    bot,
    context: ContextTypes.DEFAULT_TYPE,
    key: str,
    *,
    extra: Message | None = None,
    keep: Message | None = None,
) -> None:
    """Удалить все (chat_id, message_id), затреканные под `key`, плюс `extra`
    (если задан), пропустив `keep` — используется, когда затреканное
    сообщение сейчас не сгорает, а переиспользуется (edit) под другую карточку."""
    refs = list(_ud(context).pop(key, None) or [])
    if extra is not None:
        refs.append((extra.chat_id, extra.message_id))
    keep_ref = (keep.chat_id, keep.message_id) if keep is not None else None
    seen: set[tuple[int, int]] = set()
    for chat_id, message_id in refs:
        ref = (chat_id, message_id)
        if ref == keep_ref or ref in seen:
            continue
        seen.add(ref)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as e:
            logger.debug("Не удалось удалить служебное сообщение (%s): %s", key, e)


def _untrack_scaffold(context: ContextTypes.DEFAULT_TYPE, key: str, message: Message | None) -> None:
    """Убрать сообщение из трекинга `key` БЕЗ удаления — когда оно сейчас
    переиспользуется (edit) под другую карточку, а не сгорает."""
    if message is None:
        return
    ref = (message.chat_id, message.message_id)
    refs = _ud(context).get(key)
    if not refs:
        return
    remaining = [r for r in refs if r != ref]
    if remaining:
        _ud(context)[key] = remaining
    else:
        _ud(context).pop(key, None)


# Поиск пользователя
def _track_user_search_message(context: ContextTypes.DEFAULT_TYPE, message: Message) -> None:
    _ud(context).setdefault(USER_SEARCH_SCAFFOLD_KEY, []).append((message.chat_id, message.message_id))


def user_search_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="searchcancel")]])


async def _cleanup_user_search_scaffold(
    bot,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    current_message: Message | None = None,
) -> None:
    await _burn_scaffold(bot, context, USER_SEARCH_SCAFFOLD_KEY, extra=current_message)


# Добавление пользователя
def _track_add_flow_message(context: ContextTypes.DEFAULT_TYPE, message: Message) -> None:
    _ud(context).setdefault(ADD_FLOW_SCAFFOLD_KEY, []).append((message.chat_id, message.message_id))


def add_username_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="addcancel")]])


async def _cleanup_add_flow_scaffold(
    bot,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    keep_message: Message | None = None,
) -> None:
    await _burn_scaffold(bot, context, ADD_FLOW_SCAFFOLD_KEY, keep=keep_message)


# Промпт смены пароля
async def _cleanup_rotate_scaffold(bot, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _burn_scaffold(bot, context, ROTATE_SCAFFOLD_KEY)


async def add_entry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return ConversationHandler.END
    data = q.data or ""
    if data != "vpn:add":
        return ConversationHandler.END
    await cb_answer(q)
    clear_all_pending_text_waits(context)
    _ud(context)["add_flow_active"] = True
    await safe_edit_message_text(
        q,
        "👤 Введи <b>username</b> нового пользователя:",
        parse_mode=ParseMode.HTML,
        reply_markup=add_username_cancel_kb(),
    )
    msg = _accessible(q.message)
    if msg:
        _track_add_flow_message(context, msg)
    return ASK_ADD_USERNAME


async def add_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return ASK_ADD_USERNAME
    data = q.data or ""
    if data != "addcancel":
        return ASK_ADD_USERNAME
    await cb_answer(q, "Отменено")
    _ud(context).pop("add_flow_active", None)
    _ud(context).pop("pending_add_username", None)
    _ud(context).pop("pending_add_password", None)
    _ud(context).pop("pending_add_random_prefix", None)
    await _cleanup_add_flow_scaffold(context.bot, context, keep_message=_accessible(q.message))
    await safe_edit_message_text(
        q,
        UI_WELCOME + "\n\n" + UI_HOME,
        parse_mode=ParseMode.HTML,
        reply_markup=hub_inline_kb(),
    )
    return ConversationHandler.END


async def add_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    assert message is not None
    if not _ud(context).get("add_flow_active"):
        return ConversationHandler.END
    # Трекаем сразу, независимо от валидности — некорректный ввод тоже должен
    # сгореть при отмене/выходе, а не оставаться висеть в чате.
    _track_add_flow_message(context, message)
    username = (message.text or "").strip()
    if not USERNAME_RE.fullmatch(username):
        await message.reply_text("Некорректный username. Разрешены: A-Z a-z 0-9 . _ -")
        return ASK_ADD_USERNAME
    if len(username) > MAX_USERNAME_LEN:
        await message.reply_text(
            f"Слишком длинный username (максимум {MAX_USERNAME_LEN} символов — лимит Telegram для кнопок)."
        )
        return ASK_ADD_USERNAME

    _ud(context)["pending_add_username"] = username
    ask_password = await message.reply_text("🔑 Теперь пришли <b>password</b>:", parse_mode=ParseMode.HTML)
    _track_add_flow_message(context, ask_password)
    return ASK_ADD_PASSWORD


async def add_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    assert message is not None
    _track_add_flow_message(context, message)
    password = (message.text or "").strip()
    username = _ud(context).get("pending_add_username", "")

    if not username:
        await message.reply_text("Сессия сброшена. Ещё раз: <b>➕ Новый пользователь</b> в блоке VPN.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    if not password:
        await message.reply_text("Пустой password. Введи пароль ещё раз.")
        return ASK_ADD_PASSWORD

    if any(ch in password for ch in ("\n", "\r", "\t")):
        await message.reply_text("Некорректный password. Убери служебные символы и отправь снова.")
        return ASK_ADD_PASSWORD

    _ud(context)["pending_add_password"] = password
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ С префиксом", callback_data="addpref:on")],
            [InlineKeyboardButton("➖ Без префикса", callback_data="addpref:off")],
            [InlineKeyboardButton("❌ Отмена", callback_data="addpref:cancel")],
        ]
    )
    await message.reply_text(
        "<b>Параметры клиента</b>\nВыбери режим создания:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    return ASK_ADD_PREFIX


async def add_prefix_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return ConversationHandler.END
    await cb_answer(q)

    data = q.data or ""
    if data not in ("addpref:on", "addpref:off", "addpref:cancel"):
        return ASK_ADD_PREFIX

    if data == "addpref:cancel":
        _ud(context).pop("pending_add_username", None)
        _ud(context).pop("pending_add_password", None)
        await _cleanup_add_flow_scaffold(context.bot, context)
        await safe_edit_message_text(q, "Создание пользователя отменено.")
        return ConversationHandler.END

    username = _ud(context).get("pending_add_username", "")
    password = _ud(context).get("pending_add_password", "")
    if not username or not password:
        await safe_edit_message_text(
            q,
            "Сессия сброшена. Ещё раз: <b>➕ Новый пользователь</b> в блоке VPN.",
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    random_prefix = data.endswith(":on")
    _ud(context)["pending_add_random_prefix"] = random_prefix
    kb = InlineKeyboardMarkup(
        _protocol_kb_rows(lambda p: f"addproto:{p}")
        + [[InlineKeyboardButton("❌ Отмена", callback_data="addproto:cancel")]]
    )
    await safe_edit_message_text(
        q,
        "<b>Параметры клиента</b>\nВыбери протокол подключения:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    return ASK_ADD_PROTOCOL


async def add_protocol_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return ConversationHandler.END
    await cb_answer(q)

    data = q.data or ""
    if data not in ("addproto:h2", "addproto:quic", "addproto:cancel"):
        return ASK_ADD_PROTOCOL

    if data == "addproto:cancel":
        _ud(context).pop("pending_add_username", None)
        _ud(context).pop("pending_add_password", None)
        _ud(context).pop("pending_add_random_prefix", None)
        await _cleanup_add_flow_scaffold(context.bot, context)
        await safe_edit_message_text(q, "Создание пользователя отменено.")
        return ConversationHandler.END

    protocol = "quic" if data.endswith(":quic") else "h2"
    username = _ud(context).get("pending_add_username", "")
    password = _ud(context).get("pending_add_password", "")
    random_prefix = bool(_ud(context).get("pending_add_random_prefix", False))
    if not username or not password:
        await safe_edit_message_text(
            q,
            "Сессия сброшена. Ещё раз: <b>➕ Новый пользователь</b> в блоке VPN.",
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )
        return ConversationHandler.END

    mode_label = "prefix on" if random_prefix else "prefix off"
    protocol_label = _protocol_label(protocol)
    try:
        async with CRED_LOCK:
            deeplink, png = await asyncio.to_thread(_add_user_bundle_sync, username, password, random_prefix)
            await asyncio.to_thread(
                _set_user_profile,
                username,
                protocol=protocol,
                random_prefix=random_prefix,
            )
        msg = _accessible(q.message)
        if msg:
            await reply_deeplink_with_qr(
                msg,
                username=username,
                deeplink=deeplink,
                action_label="создание пользователя",
                mode_label=f"{mode_label} · {protocol_label}",
                png=png,
                delete_source=True,
            )
    except ValueError as e:
        await safe_edit_message_text(q, f"Ошибка: {e}", reply_markup=hub_inline_kb())
    except CommandError as e:
        await safe_edit_message_text(
            q, f"❌ {html.escape(str(e))}", parse_mode=ParseMode.HTML, reply_markup=hub_inline_kb()
        )
    except Exception:
        logger.exception("Add user failed")
        await safe_edit_message_text(
            q, "Ошибка. Не удалось добавить пользователя.", reply_markup=hub_inline_kb()
        )
    finally:
        _ud(context).pop("pending_add_username", None)
        _ud(context).pop("pending_add_password", None)
        _ud(context).pop("pending_add_random_prefix", None)
        await _cleanup_add_flow_scaffold(context.bot, context)

    return ConversationHandler.END


# Смена пароля
async def rotate_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if not q:
        return
    await cb_answer(q)

    data = q.data or ""
    if not data.startswith("rotpick:"):
        return

    username = data.split(":", 1)[1]
    begin_rotate_password_wait(context, username)
    # Сжигает промпт, оставшийся от urot: (см. user_action_rotate_callback).
    await _cleanup_rotate_scaffold(context.bot, context)
    await safe_edit_message_text(q,
        rotate_password_prompt_text(username),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([card_footer_row("vpn")]),
    )
    msg = _accessible(q.message)
    if msg:
        _ud(context).setdefault(ROTATE_SCAFFOLD_KEY, []).append((msg.chat_id, msg.message_id))


async def rotate_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = _ud(context).get("pending_rotate_username")
    if not username:
        return

    message = update.message
    assert message is not None
    password = (message.text or "").strip()
    try:
        async with CRED_LOCK:
            old_password = await asyncio.to_thread(_get_user_password, username)
            err, bundle = await asyncio.to_thread(_apply_rotate_password_sync, username, password)
        if err:
            await message.reply_text(err, reply_markup=hub_inline_kb())
        elif bundle:
            uname, deeplink, png = bundle
            extra_rows = None
            if old_password is not None:
                _set_pending_undo(context, "rotate_password", {"username": uname, "old_password": old_password})
                extra_rows = [[InlineKeyboardButton("↩️ Отменить", callback_data="undo:go")]]
            await reply_deeplink_with_qr(
                message,
                username=uname,
                deeplink=deeplink,
                action_label="смена пароля",
                png=png,
                extra_rows=extra_rows,
            )
    except CommandError as e:
        await message.reply_text(
            f"❌ {html.escape(str(e))}", parse_mode=ParseMode.HTML, reply_markup=hub_inline_kb()
        )
    except Exception:
        logger.exception("Rotate password failed")
        await message.reply_text(
            "Ошибка. Не удалось выполнить ротацию пароля.", reply_markup=hub_inline_kb()
        )
    finally:
        _ud(context).pop("pending_rotate_username", None)
        # Введённый пароль должен сгореть независимо от исхода — успех, ошибка
        # валидации или неожиданное исключение.
        await _delete_message_quiet(message)


# Экспорт пользователя
async def export_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if not q:
        return
    await cb_answer(q)

    data = q.data or ""
    if not data.startswith("exppick:"):
        return

    username = data.split(":", 1)[1]
    kb = InlineKeyboardMarkup(_protocol_kb_rows(lambda p: f"expproto:{p}:{username}"))
    await safe_edit_message_text(q,
        "<b>📤 QR</b>\n"
        f"Пользователь: <code>{html.escape(username)}</code>\n"
        "Выбери протокол:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def export_protocol_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await cb_answer(q)
    data = q.data or ""
    if not data.startswith("expproto:"):
        return
    try:
        _, protocol, username = data.split(":", 2)
    except ValueError:
        return
    protocol = _normalize_protocol(protocol)
    try:
        deeplink, png = await asyncio.to_thread(_export_bundle_sync, username)
        msg = _accessible(q.message)
        if msg:
            await reply_deeplink_with_qr(
                msg,
                username=username,
                deeplink=deeplink,
                action_label=None,
                mode_label=_protocol_label(protocol),
                include_service=False,
                png=png,
                delete_source=True,
            )
    except CommandError as e:
        await best_effort_edit(q, f"❌ {html.escape(str(e))}", parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Export user failed")
        await best_effort_edit(q, "Ошибка. Не удалось экспортировать пользователя.")


def _protocol_dns_label() -> str:
    # Подпись = реальные апстримы из _protocol_dns_values, одинаковые для обоих протоколов.
    return "DoH + DoQ: AdGuard"


async def toml_export_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await cb_answer(q)

    data = q.data or ""
    if not data.startswith(("tc:", "tp:")):
        return

    if data.startswith("tc:"):
        username = data.split(":", 1)[1]
        profile = await asyncio.to_thread(_get_user_profile, username)
        preferred = _normalize_protocol(str(profile.get("protocol", "h2")))
        kb = InlineKeyboardMarkup(_protocol_kb_rows(lambda p: f"tp:{p}:{username}"))
        await send_inline_message(
            context.bot,
            chat_id=_chat_id(update),
            text=(
                "<b>Экспорт TOML</b>\n"
                f"Пользователь: <code>{html.escape(username)}</code>\n"
                f"Рекомендация: <code>{html.escape(_protocol_label(preferred))}</code>\n"
                "Выбери протокол."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    # tp:<protocol>:<username> — генерация TOML.
    try:
        _, protocol, username = data.split(":", 2)
    except ValueError:
        return
    protocol = _normalize_protocol(protocol)
    prof = await asyncio.to_thread(_get_user_profile, username)
    random_prefix = bool(prof.get("random_prefix", False))
    await safe_edit_message_text(q, "⏳ Готовлю TOML-файл…")
    try:
        async with CRED_LOCK:
            filename, payload = await asyncio.to_thread(_export_toml_bundle_sync, username, protocol, random_prefix)
        await context.bot.send_document(
            chat_id=_chat_id(update),
            document=InputFile(io.BytesIO(payload), filename=filename),
            caption=(
                "<b>TOML экспорт</b>\n"
                f"Пользователь: <code>{html.escape(username)}</code>\n"
                f"Протокол: <code>{html.escape(_protocol_label(protocol))}</code>\n"
                f"DNS: <code>{html.escape(_protocol_dns_label())}</code>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=toml_share_kb(username),
            disable_notification=True,
        )
        await safe_edit_message_text(q, "TOML-файл отправлен.")
    except Exception as e:
        logger.exception("TOML export failed")
        await best_effort_edit(q, f"❌ Не удалось сформировать TOML.\n<code>{html.escape(str(e)[:300])}</code>", parse_mode=ParseMode.HTML)


# Колбэки мониторинга


async def info_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or q.data != "infor":
        return
    await cb_answer(q, "Обновлено")
    try:
        text = await asyncio.to_thread(get_info_card_html_cached)
        await safe_edit_message_text(q,
            clip_text(text),
            parse_mode=ParseMode.HTML,
            reply_markup=info_card_inline_kb(),
        )
    except Exception:
        logger.exception("info refresh failed")


def get_certbot_log_tail(lines: int = 20) -> str:
    if not LE_LOG_FILE.exists():
        return f"Файл лога не найден: {html.escape(str(LE_LOG_FILE))}"
    try:
        p = run_process(["tail", "-n", str(max(20, lines * 4)), str(LE_LOG_FILE)], timeout=15, check=False)
        code, out, err = p.returncode, p.stdout.strip(), p.stderr.strip()
    except CommandError as e:
        code, out, err = 124, "", str(e)
    if code != 0:
        return f"Не удалось прочитать лог certbot.\n{html.escape(err or out)}"
    rows = (out or "").splitlines()
    snippet = "\n".join(rows[-lines:]) if rows else "Пусто."
    snippet = snippet[:CLIP_TEXT_LIMIT_IN_BLOCKQUOTE]
    return (
        f"🧾 Лог certbot · последние {lines}\n\n"
        f"<blockquote expandable>{html.escape(snippet)}</blockquote>"
    )


async def cert_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("certlog:"):
        return
    await cb_answer(q)
    try:
        lines = int((q.data or "certlog:20").split(":", 1)[1])
    except ValueError:
        lines = 20
    # Строгий whitelist: посторонние значения игнорируются.
    lines = 50 if lines == 50 else 20
    try:
        text = await asyncio.to_thread(get_certbot_log_tail, lines)
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("20", callback_data="certlog:20"),
                    InlineKeyboardButton("50", callback_data="certlog:50"),
                ],
                [InlineKeyboardButton("⬅️ Назад", callback_data="nav:cert", style="success")],
            ]
        )
        await safe_edit_message_text(q, clip_text(text), parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        logger.exception("cert log callback failed")


async def clients_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("ss:"):
        return
    await cb_answer(q)
    try:
        page = int(data[3:])
    except ValueError:
        return
    try:
        html_text, total_pages, _, _ = await asyncio.to_thread(clients_card_html, page)
        kb = clients_inline_kb(page, total_pages)
        await safe_edit_message_text(
            q,
            clip_text(html_text),
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        _remember_ui_message(context, _accessible(q.message))
    except Exception:
        logger.exception("clients page failed")


async def logs_filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if not data.startswith("logf:"):
        return
    if data == "logf:noop:50:0":
        await cb_answer(q)
        return
    await cb_answer(q, "Фильтр…")

    try:
        _, level, lines_s, chunk_s = data.split(":", 3)
    except ValueError:
        level, lines_s, chunk_s = "all", "50", "0"
    if level not in ("all", "err", "warn", "5m"):
        level = "all"
    lines = 200 if lines_s == "200" else 50
    try:
        chunk = int(chunk_s)
    except ValueError:
        chunk = 0

    try:
        text, chunk, total_chunks = await asyncio.to_thread(build_logs_view, level, lines, chunk)
        await safe_edit_message_text(q,
            clip_text(text),
            reply_markup=logs_inline_kb(level, lines, chunk, total_chunks),
        )
        _remember_ui_message(context, _accessible(q.message))
    except Exception:
        logger.exception("logs filter failed")


async def backup_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data not in ("bak:yes", "bak:no"):
        return
    if data == "bak:no":
        await cb_answer(q, "Отменено")
        await safe_edit_message_text(q,
            text=UI_OPEN_SERVER,
            parse_mode=ParseMode.HTML,
            reply_markup=server_hub_kb(),
        )
        return
    if await _reject_if_busy(update):
        return
    await cb_answer(q, "Создаю…", alert=True)
    _remember_ui_message(context, _accessible(q.message))
    await run_backup(context.bot, _chat_id(update), context=context)


async def restart_tt_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data not in ("ttrst_yes", "ttrst_no"):
        return
    if data == "ttrst_no":
        await cb_answer(q, "Отменено")
        await safe_edit_message_text(q,
            "Перезапуск <b>trusttunnel</b> отменён.",
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )
        return
    await cb_answer(q, "Перезапуск…", alert=True)
    await safe_edit_message_text(q, "⏳ Перезапускаю <b>trusttunnel</b>…", parse_mode=ParseMode.HTML)
    try:
        await asyncio.to_thread(apply_tt_config_change)
        await safe_edit_message_text(q,
            "Действие: <code>перезапуск</code>\n"
            "Сервис: <code>trusttunnel active</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )
    except Exception:
        logger.exception("Restart failed")
        await best_effort_edit(q,
            "❌ Не удалось перезапустить сервис.",
            parse_mode=ParseMode.HTML,
            reply_markup=hub_inline_kb(),
        )


def _undo_rotate_password_sync(username: str, old_password: str) -> bool:
    """Откатывает ротацию на уровне файла+сервиса. Возвращает False, если
    юзер не найден. При падении apply_tt_config_change возвращает
    credentials.toml к состоянию до этого вызова и пробрасывает исключение —
    тот же паттерн, что в _apply_rotate_password_sync."""
    _, old_text = _load_credentials_doc()
    changed = rotate_user_password(username, old_password)
    if not changed:
        return False
    try:
        apply_tt_config_change()
    except Exception:
        _atomic_write_credentials(old_text, old_text)
        raise
    return True


async def _undo_rotate_password(q, payload: dict[str, Any]) -> None:
    username = payload["username"]
    async with CRED_LOCK:
        changed = await asyncio.to_thread(_undo_rotate_password_sync, username, payload["old_password"])
    if not changed:
        await cb_answer(q, f"Пользователь {username} не найден", alert=True)
        return
    await cb_answer(q, "Пароль возвращён", alert=True)
    await q.edit_message_caption(
        caption=f"↩️ Пароль <code>{html.escape(username)}</code> возвращён к предыдущему.",
        parse_mode=ParseMode.HTML,
        reply_markup=hub_inline_kb(),
    )


async def _undo_delete_user(q, payload: dict[str, Any]) -> None:
    username = payload["username"]
    random_prefix = payload.get("random_prefix", False)
    protocol = _normalize_protocol(str(payload.get("protocol", "h2")))
    try:
        async with CRED_LOCK:
            deeplink, png = await asyncio.to_thread(
                _add_user_bundle_sync, username, payload["password"], random_prefix
            )
            await asyncio.to_thread(_set_user_profile, username, protocol=protocol, random_prefix=random_prefix)
    except ValueError as e:
        await cb_answer(q, str(e), alert=True)
        return
    await cb_answer(q, "Пользователь восстановлен", alert=True)
    msg = _accessible(q.message)
    if msg is None:
        return
    # Удаление сняло старый prefix — если он был случайным, новый deeplink
    # неизбежно другой, старая ссылка у клиента больше не рабочая.
    mode_label = "prefix on" if random_prefix else "prefix off"
    await reply_deeplink_with_qr(
        msg,
        username=username,
        deeplink=deeplink,
        action_label="восстановление после удаления",
        mode_label=f"{mode_label} · {_protocol_label(protocol)}",
        png=png,
    )


async def _undo_restore_file(q, payload: dict[str, Any]) -> None:
    filename = payload["filename"]
    async with CRED_LOCK:
        await asyncio.to_thread(_atomic_write_bytes, TT_DIR / filename, payload["data"], mode=payload.get("mode"))
    await asyncio.to_thread(apply_tt_config_change)
    await cb_answer(q, "Восстановлено обратно", alert=True)
    await safe_edit_message_text(q,
        f"↩️ <code>{html.escape(filename)}</code> возвращён к состоянию до восстановления.",
        parse_mode=ParseMode.HTML,
        reply_markup=hub_inline_kb(),
    )


_UNDO_HANDLERS = {
    "rotate_password": _undo_rotate_password,
    "delete_user": _undo_delete_user,
    "restore_file": _undo_restore_file,
}


async def undo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data != "undo:go":
        return
    info = _pop_pending_undo(context)
    if not info:
        await cb_answer(q, "Отменять уже нечего", alert=True)
        return
    handler = _UNDO_HANDLERS.get(info["kind"])
    if handler is None:
        await cb_answer(q, "Неизвестное действие", alert=True)
        return
    try:
        await handler(q, info["payload"])
    except Exception:
        logger.exception("Undo failed: kind=%s", info["kind"])
        await cb_answer(q, "Не удалось отменить", alert=True)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await reset_nav_state(context)
    message = update.message
    assert message is not None
    await message.reply_text("❌ <b>Ввод отменён</b>", parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# Пользователи и подтверждение удаления
async def delete_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    assert q is not None
    data = q.data or ""

    if data.startswith("delask:"):
        await cb_answer(q)
        username = data.split(":", 1)[1]
        await safe_edit_message_text(q,
            delete_user_confirm_text(username),
            reply_markup=delete_user_confirm_kb(username),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("del2:"):
        await cb_answer(q)
        username = data.split(":", 1)[1]
        await safe_edit_message_text(q,
            "<b>Удаление</b> · шаг 2/2\n"
            f"Удалить <code>{html.escape(username)}</code> и перезапустить сервис?",
            reply_markup=confirm_kb(f"deldo:{username}", f"delcancel:{username}", danger=True),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("delcancel:"):
        await cb_answer(q, "Отменено")
        username = data.split(":", 1)[1]
        await safe_edit_message_text(q, f"Удаление <code>{html.escape(username)}</code> отменено.", parse_mode=ParseMode.HTML)
        return

    if data.startswith("deldo:"):
        username = data.split(":", 1)[1]
        await cb_answer(q, "Удаляю…", alert=True)
        await safe_edit_message_text(q,
            f"Удаляю <code>{html.escape(username)}</code> и перезапускаю сервис… ⏳",
            parse_mode=ParseMode.HTML,
        )
        try:
            async with CRED_LOCK:
                old_password = await asyncio.to_thread(_get_user_password, username)
                prof = await asyncio.to_thread(_get_user_profile, username)
                ok, rules_removed = await asyncio.to_thread(_delete_user_and_restart_sync, username)
            if not ok:
                await safe_edit_message_text(q,
                    f"Пользователь <code>{html.escape(username)}</code> не найден.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=hub_inline_kb(),
                )
                return
            prefix_note = (
                f"\nПравил prefix в rules.toml снято: <code>{rules_removed}</code>"
                if rules_removed
                else "\nПравило prefix в rules.toml не найдено (проверьте «Синхр. rules»)"
            )
            kb = hub_inline_kb()
            if old_password is not None:
                _set_pending_undo(
                    context,
                    "delete_user",
                    {
                        "username": username,
                        "password": old_password,
                        "random_prefix": bool(prof.get("random_prefix")),
                        "protocol": prof.get("protocol", "h2"),
                    },
                )
                kb = _with_undo_row(kb)
            await safe_edit_message_text(q,
                f"Действие: <code>удаление</code>\n"
                f"Пользователь: <code>{html.escape(username)}</code>"
                f"{prefix_note}\n"
                "Сервис: <code>trusttunnel active</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except ValueError as e:
            await best_effort_edit(q,
                f"⚠️ {html.escape(str(e))}", parse_mode=ParseMode.HTML, reply_markup=hub_inline_kb()
            )
        except CommandError as e:
            await best_effort_edit(q,
                f"❌ {html.escape(str(e))}", parse_mode=ParseMode.HTML, reply_markup=hub_inline_kb()
            )
        except Exception:
            logger.exception("Delete user failed")
            await best_effort_edit(q,
                "Ошибка. Не удалось удалить пользователя.", reply_markup=hub_inline_kb()
            )


async def restore_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await cb_answer(q)

    data = q.data or ""
    if data.startswith("resask:"):
        filename = data.split(":", 1)[1]
        if filename == "__all__":
            label = "все файлы из бэкапа"
            cb = "resdo:__all__"
        else:
            label = filename
            cb = f"resdo:{filename}"
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Восстановить", callback_data=cb)],
                [InlineKeyboardButton("❌ Отмена", callback_data="rescancel:menu")],
            ]
        )
        await safe_edit_message_text(q,
            "<b>Подтверждение восстановления</b>\n"
            f"Выбор: <code>{html.escape(label)}</code>\n"
            "Будет взят из latest-configs.tar.gz,\n"
            "текущая версия сохранится в backup/restore-prev,\n"
            "после этого сервис будет перезапущен.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    if data.startswith("resdo:"):
        filename = data.split(":", 1)[1]
        prev_data: bytes | None = None
        prev_mode: int | None = None
        if filename == "__all__":
            await safe_edit_message_text(q, "⏳ Восстанавливаю <code>все файлы</code>…", parse_mode=ParseMode.HTML)
            files = await asyncio.to_thread(list_files_in_latest_backup)
            async with CRED_LOCK:
                ok, info = await asyncio.to_thread(restore_multiple_from_latest_backup, files)
        else:
            await safe_edit_message_text(q, f"⏳ Восстанавливаю <code>{html.escape(filename)}</code>…", parse_mode=ParseMode.HTML)
            prev_data, prev_mode = await asyncio.to_thread(_read_file_snapshot, TT_DIR / filename)
            async with CRED_LOCK:
                ok, info = await asyncio.to_thread(restore_file_from_latest_backup, filename)
        if not ok:
            await safe_edit_message_text(q,
                f"❌ {html.escape(info)}", parse_mode=ParseMode.HTML, reply_markup=hub_inline_kb()
            )
            return
        # to_thread: синхронный systemctl заморозил бы event loop на весь timeout.
        svc = (
            await asyncio.to_thread(run_cmd, ["systemctl", "is-active", SERVICE_NAME])
            or "unknown"
        )
        restored_label = "все файлы" if filename == "__all__" else filename
        kb = hub_inline_kb()
        if prev_data is not None:
            _set_pending_undo(context, "restore_file", {"filename": filename, "data": prev_data, "mode": prev_mode})
            kb = _with_undo_row(kb)
        await safe_edit_message_text(q,
            "Действие: <code>восстановление из бэкапа</code>\n"
            f"Файл: <code>{html.escape(restored_label)}</code>\n"
            f"Сервис: <code>{html.escape(svc)}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    if data.startswith("rescancel:"):
        await safe_edit_message_text(q, "Восстановление отменено.", reply_markup=hub_inline_kb())


# Колбэки обновления TrustTunnel


async def _tt_upgrade_task(bot, cid: int, msg_id: int, pending: dict[str, str]) -> None:
    try:
        async with _typing_while(bot, cid):
            await _edit_task_card(bot, cid, msg_id, "⏳ <b>Обновление TrustTunnel</b>\n[1/4] Останавливаю сервис…")
            await asyncio.to_thread(_tt_stop_sync)
            await asyncio.to_thread(_backup_tt_binary)
            await _edit_task_card(bot, cid, msg_id, "⏳ <b>Обновление TrustTunnel</b>\n[2/4] Устанавливаю новую версию…")
            code, out, err = await asyncio.to_thread(_tt_install_sync, pending["latest"])
            if code != 0:
                await asyncio.to_thread(_restore_tt_binary_backup)
                await asyncio.to_thread(_tt_start_best_effort)
                await _edit_task_card(
                    bot,
                    cid,
                    msg_id,
                    "❌ <b>Установка не удалась</b>\n"
                    f"<code>{html.escape((err or out or 'unknown')[:700])}</code>\n"
                    "<i>Старый бинарник восстановлен, сервис поднят.</i>",
                    kb=hub_inline_kb(),
                )
                return
            await _edit_task_card(bot, cid, msg_id, "⏳ <b>Обновление TrustTunnel</b>\n[3/4] Поднимаю сервис…")
            try:
                await asyncio.to_thread(_tt_start_sync)
            except CommandError:
                restored = await asyncio.to_thread(_restore_tt_binary_backup)
                if restored:
                    await asyncio.to_thread(_tt_start_best_effort)
                await _edit_task_card(
                    bot,
                    cid,
                    msg_id,
                    "❌ <b>Новая версия не поднялась</b>\n"
                    + ("Старый бинарник восстановлен." if restored else "Бэкапа не нашлось — проверь сервис вручную."),
                    kb=hub_inline_kb(),
                )
                return
            new_ver = await asyncio.to_thread(get_current_tt_version)
            await _edit_task_card(
                bot,
                cid,
                msg_id,
                f"✅ <b>TrustTunnel обновлён</b>\n[4/4] Готово.\nНовая версия: <code>{html.escape(new_ver)}</code>",
                kb=hub_inline_kb(),
            )
    except CommandError as e:
        await asyncio.to_thread(_tt_start_best_effort)
        await _edit_task_card(bot, cid, msg_id, f"❌ {html.escape(str(e))}", kb=hub_inline_kb())
    except Exception:
        logger.exception("tt update task failed")
        await asyncio.to_thread(_tt_start_best_effort)
        await _edit_task_card(
            bot,
            cid,
            msg_id,
            "❌ Обновление не удалось. Проверь логи сервера.",
            kb=hub_inline_kb(),
        )
    finally:
        busy_clear()


async def update_tt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    assert q is not None
    data = q.data or ""

    if data == "ttupd_no":
        _ud(context).pop("pending_tt_update", None)
        await cb_answer(q)
        await safe_edit_message_text(q, "Обновление TrustTunnel отменено.", reply_markup=hub_inline_kb())
        return

    if data != "ttupd_yes":
        return

    pending = _ud(context).get("pending_tt_update")
    if not pending:
        await cb_answer(q, "Нет запроса", alert=True)
        await safe_edit_message_text(q,
            "Нет активного запроса на обновление. Нажми кнопку еще раз.",
            reply_markup=hub_inline_kb(),
        )
        return

    if await _reject_if_busy(update):
        return
    msg = q.message
    if not msg:
        return
    _ud(context).pop("pending_tt_update", None)
    busy_set("обновление TrustTunnel")
    try:
        await cb_answer(q, "Обновление запущено…", alert=True)
        await safe_edit_message_text(q,
            "⏳ <b>Обновление TrustTunnel</b> запущено.\n"
            "<i>Операция идёт в фоне, меню работает.</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        busy_clear()
        logger.exception("Не удалось запустить обновление TrustTunnel")
        return
    _schedule_background_task(
        context,
        _tt_upgrade_task(context.bot, _chat_id(update), msg.message_id, pending),
    )


def _request_system_reboot_sync() -> None:
    run_process(["systemctl", "reboot"], timeout=15, retries=0, check=True)


async def reboot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return

    data = q.data or ""

    if data == "rbcancel":
        await cb_answer(q, "Отменено")
        await safe_edit_message_text(q, "Перезагрузка отменена.", reply_markup=hub_inline_kb())
        return

    if data == "rbdo":
        if await _reject_if_busy(update):
            return
        await cb_answer(q, "Перезагрузка…", alert=True)
        await safe_edit_message_text(q, "Перезагрузка сервера… ⏳")
        try:
            cid = _chat_id(update)
            await send_inline_message(context.bot, chat_id=cid, text="После включения сервера снова нажми /start.")
            await asyncio.to_thread(_request_system_reboot_sync)
        except Exception:
            logger.exception("Reboot failed")
            await safe_edit_message_text(q,
                "Ошибка. Не удалось выполнить reboot.", reply_markup=hub_inline_kb()
            )


async def os_upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    data = q.data or ""
    if data not in ("osupd_yes", "osupd_no"):
        return
    if data == "osupd_no":
        await cb_answer(q, "Отменено")
        await safe_edit_message_text(q,
            text=UI_OPEN_SERVER,
            parse_mode=ParseMode.HTML,
            reply_markup=server_hub_kb(),
        )
        return
    if await _reject_if_busy(update):
        return
    await cb_answer(q)
    await run_os_upgrade(context.bot, _chat_id(update), context=context)


CallbackHandlerFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]


@dataclass(frozen=True)
class CallbackRoute:
    name: str
    pattern: str
    handler: CallbackHandlerFn
    busy: bool = True


CALLBACK_ROUTES: tuple[CallbackRoute, ...] = (
    CallbackRoute("nav_callback", r"^nav:", nav_callback, busy=False),
    CallbackRoute("srv_callback", r"^srv:", srv_callback, busy=False),
    CallbackRoute("vpn_hub_callback", r"^vpn:", vpn_hub_callback),
    CallbackRoute("copyhost_callback", r"^copyhost:", copyhost_callback),
    CallbackRoute("rotate_pick_callback", r"^rotpick:", rotate_pick_callback),
    CallbackRoute("export_pick_callback", r"^exppick:", export_pick_callback),
    CallbackRoute("export_protocol_callback", r"^expproto:", export_protocol_callback),
    CallbackRoute("toml_export_callback", r"^(tc:|tp:)", toml_export_callback),
    CallbackRoute("delete_user_callback", r"^(delask:|del2:|deldo:|delcancel:)", delete_user_callback),
    CallbackRoute("restore_backup_callback", r"^(resask:|resdo:|rescancel:)", restore_backup_callback),
    CallbackRoute("update_tt_callback", r"^ttupd_(yes|no)$", update_tt_callback, busy=False),
    CallbackRoute("reboot_callback", r"^(rbdo|rbcancel)$", reboot_callback, busy=False),
    CallbackRoute("os_upgrade_callback", r"^osupd_(yes|no)$", os_upgrade_callback, busy=False),
    CallbackRoute("info_refresh_callback", r"^infor$", info_refresh_callback, busy=False),
    CallbackRoute("cert_log_callback", r"^certlog:", cert_log_callback, busy=False),
    CallbackRoute("user_search_cancel_callback", r"^searchcancel$", user_search_cancel_callback, busy=False),
    CallbackRoute("backup_confirm_callback", r"^bak:(yes|no)$", backup_confirm_callback, busy=False),
    CallbackRoute("clients_page_callback", r"^ss:", clients_page_callback),
    CallbackRoute("users_page_callback", r"^ul:", users_page_callback),
    CallbackRoute("users_filter_callback", r"^uf:", users_filter_callback),
    CallbackRoute("user_detail_callback", r"^udev:", user_detail_callback),
    CallbackRoute("user_action_qr_callback", r"^(uqr:|ure:)", user_action_qr_callback),
    CallbackRoute("user_action_toml_callback", r"^utc:", user_action_toml_callback),
    CallbackRoute("user_action_link_callback", r"^ulink:", user_action_link_callback),
    CallbackRoute("user_action_all_callback", r"^uall:", user_action_all_callback),
    CallbackRoute("user_action_rotate_callback", r"^urot:", user_action_rotate_callback),
    CallbackRoute("user_action_del_callback", r"^udel:", user_action_del_callback),
    CallbackRoute("rules_sync_callback", r"^rulesync:", rules_sync_callback),
    CallbackRoute("logs_filter_callback", r"^logf:", logs_filter_callback),
    CallbackRoute("restart_tt_confirm_callback", r"^ttrst_(yes|no)$", restart_tt_confirm_callback),
    CallbackRoute("undo_callback", r"^undo:go$", undo_callback),
)


def cancel_stray_add_flow(handler):
    """Любой маршрут из CALLBACK_ROUTES не относится к сценарию добавления
    пользователя (он живёт в своём ConversationHandler) — если юзер ушёл
    в другой раздел посреди добавления, сценарий надо считать брошенным,
    иначе следующий текст улетит в него как забытый пароль/username."""
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if _ud(context).get("add_flow_active"):
            await cancel_add_flow(context)
        return await handler(update, context)

    return wrapper


def build_callback_query_handler(route: CallbackRoute) -> CallbackQueryHandler:
    handler = busy_guard(route.handler) if route.busy else route.handler
    handler = allow_guard(handler)
    handler = cancel_stray_add_flow(handler)
    return CallbackQueryHandler(traced_callback(route.name, handler), pattern=route.pattern)


def main():
    runtime_lock = acquire_runtime_lock()
    stale_busy = _consume_stale_busy_marker()
    if stale_busy:
        logger.warning(
            "Обнаружен маркер занятости с прошлого запуска (%s) — "
            "предыдущая операция могла не завершиться штатно, проверь вручную",
            stale_busy,
        )
    # Дефолты PTB (5s read/connect/write, 1s pool) слишком жёсткие для сети с
    # заминками — единичный сетевой тормоз превращается в исключение прямо
    # в хендлере. Даём больше времени и больше соединений в пуле, чтобы не
    # биться в один короткий таймаут.
    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=10.0,
        read_timeout=20.0,
        write_timeout=10.0,
        pool_timeout=5.0,
    )
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .defaults(Defaults(disable_notification=True))
        .build()
    )
    app.add_error_handler(log_unhandled_error)

    app.add_handler(MessageHandler(filters.Text(["🏠 Меню"]), allow_guard(menu_button_tap)), group=-1)

    app.add_handler(CommandHandler("start", allow_guard(start)))
    app.add_handler(CommandHandler("status", allow_guard(status)))
    app.add_handler(CommandHandler("myid", allow_guard(myid)))
    app.add_handler(CommandHandler("diff", allow_guard(diff_command)))
    app.add_handler(CommandHandler("cancel", allow_guard(cancel, conv_end=True)))

    app.add_handler(build_add_conversation())

    for route in CALLBACK_ROUTES:
        app.add_handler(build_callback_query_handler(route))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, allow_guard(user_search_text)), group=5)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, allow_guard(rotate_password_input)), group=10)

    try:
        app.run_polling(
            drop_pending_updates=True,  # обновления за время ребута теряются; это осознанно: для них есть /status.
        )
    finally:
        runtime_lock.close()


if __name__ == "__main__":
    main()
