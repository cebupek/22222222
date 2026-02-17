# ============================================================
# ИМПОРТЫ
# ============================================================
import asyncio
import logging
import aiohttp
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    Application,
)

# ============================================================
# НАСТРОЙКИ И КОНСТАНТЫ
# ============================================================
BOT_TOKEN = "8566474882:AAHfufmlEeW0XmkX_y4IDL6Tcwj52D6Eaa8"
MOD_IDS = [7628577301, 222222, 333333]
APP_URL = ""
SITE_URL = "https://music.be-sunshainy.ru/"

POLL_INTERVAL = 15    # секунд между проверками очередей
PING_INTERVAL = 10    # секунд между self-ping запросами

API_SONGS  = f"{SITE_URL.rstrip('/')}/api/bot/pending/songs"
API_NAMES  = f"{SITE_URL.rstrip('/')}/api/bot/pending/names"
API_COVERS = f"{SITE_URL.rstrip('/')}/api/bot/pending/covers"

API_DEL_SONG  = f"{SITE_URL.rstrip('/')}/api/bot/delete/song"
API_DEL_NAME  = f"{SITE_URL.rstrip('/')}/api/bot/delete/name"
API_DEL_COVER = f"{SITE_URL.rstrip('/')}/api/bot/delete/cover"

RULES_TEXT = (
    "📋 <b>Правила модерации треков</b>\n\n"
    "<b>✅ Принимаем:</b>\n"
    "• Оригинальный трек (студийная запись)\n"
    "• Существующая песня с правильным названием и исполнителем\n"
    "• Длина: от 1 до 10 минут (обычно 1–6 минут)\n\n"
    "<b>❌ Отклоняем:</b>\n"
    "• Голосовые сообщения, вырезки из стримов, случайные звуки\n"
    "• Треки длиннее 10–15 минут\n"
    "• Политический подтекст — особенно Россия/Украина\n"
    "• Стёбная и провокационная тематика\n"
    "• Неприемлемый контент\n\n"
    "<b>💡 Совет:</b>\n"
    "Если трек без подписи — проверь его в интернете, затем заполни "
    "исполнителя и название через кнопку ✍️"
)

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MusicBot")

# ============================================================
# ОЧЕРЕДИ И ТРЕКИ
# ============================================================
seen_songs: set = set()
seen_names: set = set()
seen_covers: set = set()

# ============================================================
# API-ЗАПРОСЫ
# ============================================================
async def fetch_pending(session: aiohttp.ClientSession, url: str) -> list:
    """Получить список ожидающих элементов с сайта."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                logger.debug("Fetched from %s: %d items", url, len(data))
                return data if isinstance(data, list) else []
            else:
                logger.warning("Non-200 from %s: %s", url, resp.status)
                return []
    except Exception as exc:
        logger.error("Error fetching %s: %s", url, exc)
        return []


async def delete_item(session: aiohttp.ClientSession, url: str, item_id) -> bool:
    """Отправить DELETE-запрос на сайт."""
    try:
        async with session.delete(
            f"{url}/{item_id}", timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            ok = resp.status in (200, 204)
            logger.info("DELETE %s/%s -> %s", url, item_id, resp.status)
            return ok
    except Exception as exc:
        logger.error("Error deleting %s/%s: %s", url, item_id, exc)
        return False

# ============================================================
# УВЕДОМЛЕНИЯ МОДЕРАМ
# ============================================================
async def notify_mods(bot: Bot, text: str) -> None:
    """Отправить сообщение всем модераторам."""
    for mod_id in MOD_IDS:
        try:
            await bot.send_message(chat_id=mod_id, text=text, parse_mode="HTML")
            logger.info("Notified mod %s", mod_id)
        except Exception as exc:
            logger.error("Failed to notify mod %s: %s", mod_id, exc)

# ============================================================
# ФУНКЦИИ ОБРАБОТКИ НОВЫХ ЭЛЕМЕНТОВ
# ============================================================
async def process_songs(bot: Bot, session: aiohttp.ClientSession) -> None:
    """Проверить новые песни и уведомить модераторов."""
    items = await fetch_pending(session, API_SONGS)
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen_songs:
            continue
        seen_songs.add(item_id)
        title  = item.get("title", "—")
        artist = item.get("artist", "—")
        msg = (
            "🎵 <b>Новая песня на модерации</b>\n\n"
            f"🆔 ID: <code>{item_id}</code>\n"
            f"🎤 Исполнитель: {artist}\n"
            f"📀 Название: {title}\n\n"
            f"✅ Одобрить на сайте или\n"
            f"❌ Удалить: /delete_song {item_id}\n\n"
            + RULES_TEXT
        )
        await notify_mods(bot, msg)
        logger.info("New song queued: id=%s title=%s", item_id, title)


async def process_names(bot: Bot, session: aiohttp.ClientSession) -> None:
    """Проверить новые названия плейлистов и уведомить модераторов."""
    items = await fetch_pending(session, API_NAMES)
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen_names:
            continue
        seen_names.add(item_id)
        name = item.get("name", "—")
        msg = (
            "📋 <b>Новое название плейлиста на модерации</b>\n\n"
            f"🆔 ID: <code>{item_id}</code>\n"
            f"📝 Название: {name}\n\n"
            f"✅ Одобрить на сайте или\n"
            f"❌ Удалить: /delete_name {item_id}"
        )
        await notify_mods(bot, msg)
        logger.info("New playlist name queued: id=%s name=%s", item_id, name)


async def process_covers(bot: Bot, session: aiohttp.ClientSession) -> None:
    """Проверить новые обложки и уведомить модераторов."""
    items = await fetch_pending(session, API_COVERS)
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen_covers:
            continue
        seen_covers.add(item_id)
        title   = item.get("title", "—")
        img_url = item.get("cover_url") or item.get("image_url") or ""
        cover_line = f'🔗 <a href="{img_url}">Посмотреть обложку</a>\n' if img_url else ""
        msg = (
            "🖼 <b>Новая обложка на модерации</b>\n\n"
            f"🆔 ID: <code>{item_id}</code>\n"
            f"📀 Плейлист: {title}\n"
            f"{cover_line}\n"
            f"✅ Одобрить на сайте или\n"
            f"❌ Удалить: /delete_cover {item_id}"
        )
        await notify_mods(bot, msg)
        logger.info("New cover queued: id=%s title=%s", item_id, title)

# ============================================================
# PING К САМОМУ СЕБЕ (anti-sleep для Render)
# ============================================================
async def self_ping_loop() -> None:
    """Раз в PING_INTERVAL секунд пингуем APP_URL, чтобы Render не засыпал."""
    if not APP_URL:
        logger.info("APP_URL is empty — self-ping disabled.")
        return

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(
                    APP_URL, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    logger.info("Self-ping %s -> %s", APP_URL, resp.status)
            except Exception as exc:
                logger.warning("Self-ping failed: %s", exc)
            await asyncio.sleep(PING_INTERVAL)

# ============================================================
# ПРОВЕРКА ОЧЕРЕДЕЙ (основной цикл)
# ============================================================
async def queue_check_loop(bot: Bot) -> None:
    """Каждые POLL_INTERVAL секунд проверяем все три очереди."""
    logger.info("Queue check loop started (interval=%ds)", POLL_INTERVAL)
    async with aiohttp.ClientSession() as session:
        while True:
            logger.debug("Checking queues...")
            await asyncio.gather(
                process_songs(bot, session),
                process_names(bot, session),
                process_covers(bot, session),
            )
            await asyncio.sleep(POLL_INTERVAL)

# ============================================================
# TELEGRAM КОМАНДЫ
# ============================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 <b>Music Moderation Bot</b>\n\n"
        "Я слежу за очередями модерации на сайте и уведомляю модераторов.\n\n"
        "<b>Доступные команды:</b>\n"
        "/ping — проверить работу бота\n"
        "/rules — правила модерации треков\n"
        "/delete_song &lt;id&gt; — удалить песню\n"
        "/delete_name &lt;id&gt; — удалить название плейлиста\n"
        "/delete_cover &lt;id&gt; — удалить обложку",
        parse_mode="HTML",
    )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🏓 Pong! Бот работает корректно.")
    logger.info("/ping from user %s", update.effective_user.id)


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать правила модерации."""
    await update.message.reply_text(RULES_TEXT, parse_mode="HTML")
    logger.info("/rules from user %s", update.effective_user.id)

# ============================================================
# УДАЛЕНИЕ ПЕСЕН / ОБЛОЖЕК / НАЗВАНИЙ
# ============================================================
def _is_mod(user_id: int) -> bool:
    return user_id in MOD_IDS


async def cmd_delete_song(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_mod(user_id):
        await update.message.reply_text("⛔ У вас недостаточно прав.")
        logger.warning("Unauthorized /delete_song by user %s", user_id)
        return
    if not context.args:
        await update.message.reply_text("❗ Укажите ID: /delete_song <id>")
        return
    item_id = context.args[0]
    async with aiohttp.ClientSession() as session:
        ok = await delete_item(session, API_DEL_SONG, item_id)
    if ok:
        await update.message.reply_text(
            f"✅ Песня <code>{item_id}</code> успешно удалена.", parse_mode="HTML"
        )
        seen_songs.discard(item_id)
        try:
            seen_songs.discard(int(item_id))
        except ValueError:
            pass
    else:
        await update.message.reply_text(
            f"❌ Не удалось удалить песню <code>{item_id}</code>. Проверьте ID.",
            parse_mode="HTML"
        )


async def cmd_delete_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_mod(user_id):
        await update.message.reply_text("⛔ У вас недостаточно прав.")
        logger.warning("Unauthorized /delete_name by user %s", user_id)
        return
    if not context.args:
        await update.message.reply_text("❗ Укажите ID: /delete_name <id>")
        return
    item_id = context.args[0]
    async with aiohttp.ClientSession() as session:
        ok = await delete_item(session, API_DEL_NAME, item_id)
    if ok:
        await update.message.reply_text(
            f"✅ Название <code>{item_id}</code> успешно удалено.", parse_mode="HTML"
        )
        seen_names.discard(item_id)
        try:
            seen_names.discard(int(item_id))
        except ValueError:
            pass
    else:
        await update.message.reply_text(
            f"❌ Не удалось удалить название <code>{item_id}</code>. Проверьте ID.",
            parse_mode="HTML"
        )


async def cmd_delete_cover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_mod(user_id):
        await update.message.reply_text("⛔ У вас недостаточно прав.")
        logger.warning("Unauthorized /delete_cover by user %s", user_id)
        return
    if not context.args:
        await update.message.reply_text("❗ Укажите ID: /delete_cover <id>")
        return
    item_id = context.args[0]
    async with aiohttp.ClientSession() as session:
        ok = await delete_item(session, API_DEL_COVER, item_id)
    if ok:
        await update.message.reply_text(
            f"✅ Обложка <code>{item_id}</code> успешно удалена.", parse_mode="HTML"
        )
        seen_covers.discard(item_id)
        try:
            seen_covers.discard(int(item_id))
        except ValueError:
            pass
    else:
        await update.message.reply_text(
            f"❌ Не удалось удалить обложку <code>{item_id}</code>. Проверьте ID.",
            parse_mode="HTML"
        )

# ============================================================
# ГЛАВНАЯ ASYNC ФУНКЦИЯ
# ============================================================
async def main() -> None:
    logger.info("Starting Music Moderation Bot...")

    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем команды
    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("ping",         cmd_ping))
    app.add_handler(CommandHandler("rules",        cmd_rules))
    app.add_handler(CommandHandler("delete_song",  cmd_delete_song))
    app.add_handler(CommandHandler("delete_name",  cmd_delete_name))
    app.add_handler(CommandHandler("delete_cover", cmd_delete_cover))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    logger.info("Bot is polling. Launching background tasks...")

    # Запускаем фоновые задачи параллельно
    await asyncio.gather(
        queue_check_loop(app.bot),
        self_ping_loop(),
    )

# ============================================================
# ЗАПУСК БОТА
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
```

