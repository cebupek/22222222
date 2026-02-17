import asyncio
import logging
import aiohttp
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Application

BOT_TOKEN = "8566474882:AAHfufmlEeW0XmkX_y4IDL6Tcwj52D6Eaa8"
MOD_IDS = [7628577301, 222222, 333333]
APP_URL = ""
SITE_URL = "https://music.be-sunshainy.ru/"
POLL_INTERVAL = 15
PING_INTERVAL = 10

API_SONGS  = SITE_URL + "api/bot/pending/songs"
API_NAMES  = SITE_URL + "api/bot/pending/names"
API_COVERS = SITE_URL + "api/bot/pending/covers"
API_DEL_SONG  = SITE_URL + "api/bot/delete/song"
API_DEL_NAME  = SITE_URL + "api/bot/delete/name"
API_DEL_COVER = SITE_URL + "api/bot/delete/cover"

RULES_TEXT = (
    "\n\n<b>Pravila moderacii:</b>\n"
    "Prinimaem: originalnyj trek, pravilnoe nazvanie, dlina 1-10 min\n"
    "Otklonaem: golosovye, stremy, politika, provokacii, nepriemlemyj kontent"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MusicBot")

seen_songs = set()
seen_names = set()
seen_covers = set()


async def fetch_pending(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data if isinstance(data, list) else []
            logger.warning("Non-200 from %s: %s", url, resp.status)
            return []
    except Exception as exc:
        logger.error("Error fetching %s: %s", url, exc)
        return []


async def delete_item(session, url, item_id):
    try:
        async with session.delete(url + "/" + str(item_id), timeout=aiohttp.ClientTimeout(total=10)) as resp:
            ok = resp.status in (200, 204)
            logger.info("DELETE %s/%s -> %s", url, item_id, resp.status)
            return ok
    except Exception as exc:
        logger.error("Error deleting %s/%s: %s", url, item_id, exc)
        return False


async def notify_mods(bot, text):
    for mod_id in MOD_IDS:
        try:
            await bot.send_message(chat_id=mod_id, text=text, parse_mode="HTML")
            logger.info("Notified mod %s", mod_id)
        except Exception as exc:
            logger.error("Failed to notify mod %s: %s", mod_id, exc)


async def process_songs(bot, session):
    items = await fetch_pending(session, API_SONGS)
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen_songs:
            continue
        seen_songs.add(item_id)
        title = item.get("title", "-")
        artist = item.get("artist", "-")
        msg = (
            "<b>Novaya pesnya na moderacii</b>\n"
            "ID: <code>" + str(item_id) + "</code>\n"
            "Ispolnitel: " + artist + "\n"
            "Nazvanie: " + title + "\n\n"
            "Udalit: /delete_song " + str(item_id) +
            RULES_TEXT
        )
        await notify_mods(bot, msg)
        logger.info("New song: id=%s title=%s", item_id, title)


async def process_names(bot, session):
    items = await fetch_pending(session, API_NAMES)
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen_names:
            continue
        seen_names.add(item_id)
        name = item.get("name", "-")
        msg = (
            "<b>Novoe nazvanie plejlista na moderacii</b>\n"
            "ID: <code>" + str(item_id) + "</code>\n"
            "Nazvanie: " + name + "\n\n"
            "Udalit: /delete_name " + str(item_id)
        )
        await notify_mods(bot, msg)
        logger.info("New name: id=%s name=%s", item_id, name)


async def process_covers(bot, session):
    items = await fetch_pending(session, API_COVERS)
    for item in items:
        item_id = item.get("id")
        if item_id is None or item_id in seen_covers:
            continue
        seen_covers.add(item_id)
        title = item.get("title", "-")
        img_url = item.get("cover_url") or item.get("image_url") or ""
        cover_line = ""
        if img_url:
            cover_line = "\nOblozhka: " + img_url
        msg = (
            "<b>Novaya oblozhka na moderacii</b>\n"
            "ID: <code>" + str(item_id) + "</code>\n"
            "Plejlist: " + title +
            cover_line + "\n\n"
            "Udalit: /delete_cover " + str(item_id)
        )
        await notify_mods(bot, msg)
        logger.info("New cover: id=%s title=%s", item_id, title)


async def self_ping_loop():
    if not APP_URL:
        logger.info("APP_URL empty, self-ping disabled.")
        return
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(APP_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    logger.info("Self-ping -> %s", resp.status)
            except Exception as exc:
                logger.warning("Self-ping failed: %s", exc)
            await asyncio.sleep(PING_INTERVAL)


async def queue_check_loop(bot):
    logger.info("Queue loop started, interval=%ds", POLL_INTERVAL)
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.gather(
                process_songs(bot, session),
                process_names(bot, session),
                process_covers(bot, session),
            )
            await asyncio.sleep(POLL_INTERVAL)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Music Moderation Bot</b>\n\n"
        "Komandy:\n"
        "/ping - proverit bota\n"
        "/rules - pravila moderacii\n"
        "/delete_song id\n"
        "/delete_name id\n"
        "/delete_cover id",
        parse_mode="HTML",
    )


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot rabotaet.")
    logger.info("/ping from %s", update.effective_user.id)


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b>Pravila moderacii trekov</b>\n\n"
        "Prinimaem:\n"
        "- Originalnyj trek (studijnaya zapis)\n"
        "- Pravilnoe nazvanie i ispolnitel\n"
        "- Dlina: 1-10 minut\n\n"
        "Otklonaem:\n"
        "- Golosovye, vyreski iz strimov\n"
        "- Treki dlinnee 15 minut\n"
        "- Politika (Rossiya/Ukraina)\n"
        "- Provokacii i nepriemlemyj kontent"
    )
    await update.message.reply_text(text, parse_mode="HTML")


def is_mod(user_id):
    return user_id in MOD_IDS


async def cmd_delete_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_mod(update.effective_user.id):
        await update.message.reply_text("Net prav.")
        return
    if not context.args:
        await update.message.reply_text("Ukazhi ID: /delete_song <id>")
        return
    item_id = context.args[0]
    async with aiohttp.ClientSession() as session:
        ok = await delete_item(session, API_DEL_SONG, item_id)
    if ok:
        await update.message.reply_text("Pesnya " + item_id + " udalena.")
        seen_songs.discard(item_id)
    else:
        await update.message.reply_text("Oshibka udaleniya " + item_id)


async def cmd_delete_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_mod(update.effective_user.id):
        await update.message.reply_text("Net prav.")
        return
    if not context.args:
        await update.message.reply_text("Ukazhi ID: /delete_name <id>")
        return
    item_id = context.args[0]
    async with aiohttp.ClientSession() as session:
        ok = await delete_item(session, API_DEL_NAME, item_id)
    if ok:
        await update.message.reply_text("Nazvanie " + item_id + " udaleno.")
        seen_names.discard(item_id)
    else:
        await update.message.reply_text("Oshibka udaleniya " + item_id)


async def cmd_delete_cover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_mod(update.effective_user.id):
        await update.message.reply_text("Net prav.")
        return
    if not context.args:
        await update.message.reply_text("Ukazhi ID: /delete_cover <id>")
        return
    item_id = context.args[0]
    async with aiohttp.ClientSession() as session:
        ok = await delete_item(session, API_DEL_COVER, item_id)
    if ok:
        await update.message.reply_text("Oblozhka " + item_id + " udalena.")
        seen_covers.discard(item_id)
    else:
        await update.message.reply_text("Oshibka udaleniya " + item_id)


async def main():
    logger.info("Starting bot...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("delete_song", cmd_delete_song))
    app.add_handler(CommandHandler("delete_name", cmd_delete_name))
    app.add_handler(CommandHandler("delete_cover", cmd_delete_cover))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot polling. Starting background tasks...")
    await asyncio.gather(
        queue_check_loop(app.bot),
        self_ping_loop(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
