from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.request import HTTPXRequest
import os, sqlite3, uuid, asyncio

# ================= CONFIG =================

TOKEN = os.getenv("8105577463:AAH9FmxO23xX39MsQmSfueq38CEdCB7F9qk")
BOT_USERNAME = "hcjvkvkguf_bot"

ALLOWED_UPLOADERS = [8295342154, 7025490921]

# 🔐 FORCE JOIN CHANNEL
FORCE_CHANNEL = "test1234521221412"
FORCE_CHANNEL_URL = "https://t.me/test1234521221412"

# 📢 PRIVATE STORAGE CHANNEL (REPLACE THIS)
STORAGE_CHANNEL_ID = -1003323683630

AUTO_DELETE_SECONDS = 20 * 60

# =========================================

request = HTTPXRequest(connect_timeout=20, read_timeout=20)

# ================= DATABASE =================

db = sqlite3.connect("files.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS batches (
    batch_id TEXT,
    channel_msg_id INTEGER,
    caption TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS stats (
    batch_id TEXT PRIMARY KEY,
    downloads INTEGER DEFAULT 0
)
""")

db.commit()

active_batches = {}   # user_id -> list of channel_msg_id
active_caption = {}   # user_id -> caption

# ================= HELPERS =================

def join_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔗 Join Channel", url=FORCE_CHANNEL_URL),
            InlineKeyboardButton("✅ I already joined", callback_data="check_join")
        ]
    ])

def batch_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add more files", callback_data="add_more")],
        [InlineKeyboardButton("✅ Done (get link)", callback_data="done")]
    ])

async def is_member(bot, user_id):
    try:
        m = await bot.get_chat_member(f"@{FORCE_CHANNEL}", user_id)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

async def auto_delete(context, chat_id, msg_ids):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    for mid in msg_ids:
        try:
            await context.bot.delete_message(chat_id, mid)
        except:
            pass

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("📤 Upload files and add caption.")
        return

    batch_id = context.args[0]

    if not await is_member(context.bot, update.effective_user.id):
        await update.message.reply_text(
            "🔒 Join the channel to access files.",
            reply_markup=join_keyboard()
        )
        context.user_data["pending"] = batch_id
        return

    await send_batch(update, context, batch_id)

# ================= SEND FILES =================

async def send_batch(update, context, batch_id):
    cur.execute(
        "SELECT channel_msg_id, caption FROM batches WHERE batch_id=?",
        (batch_id,)
    )
    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("❌ Files not found.")
        return

    cur.execute("INSERT OR IGNORE INTO stats VALUES (?,0)", (batch_id,))
    cur.execute("UPDATE stats SET downloads=downloads+1 WHERE batch_id=?", (batch_id,))
    db.commit()

    warn = await update.message.reply_text(
        "⚠️ Save or forward files.\n⏳ Auto-delete after 20 minutes."
    )
    msg_ids = [warn.message_id]

    for msg_id, caption in rows:
        m = await context.bot.copy_message(
            chat_id=update.effective_chat.id,
            from_chat_id=STORAGE_CHANNEL_ID,
            message_id=msg_id,
            caption=caption
        )
        msg_ids.append(m.message_id)

    context.application.create_task(
        auto_delete(context, update.effective_chat.id, msg_ids)
    )

# ================= CALLBACKS =================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "check_join":
        batch_id = context.user_data.get("pending")
        if await is_member(context.bot, uid):
            await send_batch(q, context, batch_id)
            context.user_data.pop("pending", None)
        else:
            await q.message.reply_text(
                "❌ You haven't joined yet.",
                reply_markup=join_keyboard()
            )
        return

    if uid not in ALLOWED_UPLOADERS:
        return

    if q.data == "add_more":
        await q.message.reply_text("➕ Send more files.")
        return

    if q.data == "done":
        files = active_batches.get(uid)
        if not files:
            await q.message.reply_text("❌ No files.")
            return

        batch_id = uuid.uuid4().hex[:10]
        caption = active_caption.get(uid, "")

        for msg_id in files:
            cur.execute(
                "INSERT INTO batches VALUES (?,?,?)",
                (batch_id, msg_id, caption)
            )

        cur.execute("INSERT OR IGNORE INTO stats VALUES (?,0)", (batch_id,))
        db.commit()

        active_batches[uid].clear()
        active_caption.pop(uid, None)

        link = f"https://t.me/{BOT_USERNAME}?start={batch_id}"
        await q.message.reply_text(f"✅ Lifetime link:\n{link}")

# ================= FILE UPLOAD =================

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ALLOWED_UPLOADERS:
        return

    msg = update.message
    if msg.caption:
        active_caption[uid] = msg.caption

    sent = await context.bot.copy_message(
        chat_id=STORAGE_CHANNEL_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id
    )

    active_batches.setdefault(uid, []).append(sent.message_id)

    await msg.reply_text(
        f"📎 Stored\n📦 Total: {len(active_batches[uid])}",
        reply_markup=batch_keyboard()
    )

# ================= RUN =================

app = ApplicationBuilder().token(TOKEN).request(request).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(callbacks))
app.add_handler(MessageHandler(filters.ALL, handle_file))

print("Bot running...")
app.run_polling()

