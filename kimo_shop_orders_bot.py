import os
import json
import logging
from datetime import datetime
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# KIMO SHOP Stars Order Bot
# Configure these environment variables on your hosting provider:
# BOT_TOKEN, ADMIN_IDS, CARD_NUMBER, CARD_HOLDER
# Optional prices: PRICE_50, PRICE_100, PRICE_250, PRICE_500
# Prices are displayed exactly as entered; use your local currency wording.
# Example: PRICE_50="..." and so on.

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
CARD_NUMBER = os.getenv("CARD_NUMBER", "اطلاعات کارت هنوز تنظیم نشده").strip()
CARD_HOLDER = os.getenv("CARD_HOLDER", "نام صاحب کارت را تنظیم کنید").strip()

PACKAGES = {
    "50": ("۵۰ استارز", os.getenv("PRICE_50", "قیمت اعلام می‌شود")),
    "100": ("۱۰۰ استارز", os.getenv("PRICE_100", "قیمت اعلام می‌شود")),
    "250": ("۲۵۰ استارز", os.getenv("PRICE_250", "قیمت اعلام می‌شود")),
    "500": ("۵۰۰ استارز", os.getenv("PRICE_500", "قیمت اعلام می‌شود")),
}

DATA_FILE = Path("kimo_orders.json")
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("kimo_shop")


def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.exception("Could not read order database")
    return {"next_id": 1, "orders": {}}


def save_data(data):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def package_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ {label} — {price}", callback_data=f"pack:{key}")]
        for key, (label, price) in PACKAGES.items()
    ])


def admin_order_keyboard(order_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید پرداخت", callback_data=f"admin:paid:{order_id}"),
        InlineKeyboardButton("❌ رد پرداخت", callback_data=f"admin:reject:{order_id}")
    ]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_package", None)
    await update.message.reply_text(
        "سلام کیمویی! 💙 به فروشگاه KIMO SHOP خوش اومدی.\n\n"
        "برای ثبت سفارش تلگرام استارز، بسته موردنظرت رو انتخاب کن:",
        reply_markup=package_keyboard()
    )


async def myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    found = [
        o for o in data["orders"].values()
        if str(o.get("user_id")) == uid
    ]
    if not found:
        await update.message.reply_text("هنوز سفارشی ثبت نکردی. برای شروع /start رو بزن.")
        return
    lines = ["📦 سفارش‌های شما:"]
    for o in found[-10:]:
        lines.append(
            f"#{o['id']} — {o['package_label']} — وضعیت: {o['status']}"
        )
    await update.message.reply_text("\n".join(lines))


async def package_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split(":", 1)[1]
    if key not in PACKAGES:
        await query.edit_message_text("این بسته معتبر نیست. /start رو بزن.")
        return
    label, price = PACKAGES[key]
    context.user_data["pending_package"] = key
    await query.edit_message_text(
        f"🛍️ بسته انتخابی: {label}\n"
        f"💰 قیمت: {price}\n\n"
        "برای ادامه، نام کاربری تلگرام دریافت‌کننده استارز رو بفرست "
        "(مثلاً @username).\n\n"
        "برای لغو، /start رو بزن."
    )
    context.user_data["awaiting_username"] = True


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_username"):
        await update.message.reply_text("برای ثبت سفارش /start رو بزن.")
        return
    recipient = update.message.text.strip()
    if len(recipient) < 2 or len(recipient) > 64:
        await update.message.reply_text("نام کاربری معتبر نیست؛ دوباره بفرست.")
        return
    key = context.user_data.get("pending_package")
    if key not in PACKAGES:
        context.user_data.clear()
        await update.message.reply_text("سفارش منقضی شد. دوباره /start رو بزن.")
        return

    data = load_data()
    order_id = data["next_id"]
    data["next_id"] += 1
    label, price = PACKAGES[key]
    user = update.effective_user
    order = {
        "id": order_id,
        "user_id": user.id,
        "username": user.username or "",
        "recipient": recipient,
        "package_key": key,
        "package_label": label,
        "price": price,
        "status": "در انتظار رسید",
        "created_at": datetime.now().isoformat(timespec="seconds")
    }
    data["orders"][str(order_id)] = order
    save_data(data)

    context.user_data["awaiting_username"] = False
    context.user_data["current_order_id"] = order_id

    await update.message.reply_text(
        f"🧾 سفارش #{order_id} ثبت شد.\n"
        f"⭐ بسته: {label}\n"
        f"👤 دریافت‌کننده: {recipient}\n"
        f"💰 مبلغ: {price}\n\n"
        f"💳 کارت‌به‌کارت:\n"
        f"شماره کارت: {CARD_NUMBER}\n"
        f"به نام: {CARD_HOLDER}\n\n"
        "بعد از پرداخت، عکس رسید رو همین‌جا بفرست.\n"
        "⚠️ سفارش بعد از بررسی ادمین تأیید می‌شه."
    )


async def receipt_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("current_order_id")
    if not order_id:
        await update.message.reply_text("اول از /start یک سفارش ثبت کن.")
        return

    data = load_data()
    order = data["orders"].get(str(order_id))
    if not order or order["status"] not in ("در انتظار رسید", "در انتظار بررسی"):
        await update.message.reply_text("سفارش فعالی برای دریافت رسید پیدا نشد.")
        return

    order["status"] = "در انتظار بررسی"
    order["receipt_file_id"] = update.message.photo[-1].file_id
    save_data(data)

    user = update.effective_user
    admin_text = (
        f"🛎️ سفارش جدید KIMO SHOP — #{order_id}\n"
        f"⭐ بسته: {order['package_label']}\n"
        f"💰 مبلغ: {order['price']}\n"
        f"👤 دریافت‌کننده: {order['recipient']}\n"
        f"🧑 مشتری: {user.full_name}\n"
        f"🔗 نام کاربری: @{user.username}" if user.username else
        f"🛎️ سفارش جدید KIMO SHOP — #{order_id}\n"
        f"⭐ بسته: {order['package_label']}\n"
        f"💰 مبلغ: {order['price']}\n"
        f"👤 دریافت‌کننده: {order['recipient']}\n"
        f"🧑 مشتری: {user.full_name}\n"
        f"🆔 آیدی مشتری: {user.id}"
    )
    delivered = False
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=update.message.photo[-1].file_id,
                caption=admin_text,
                reply_markup=admin_order_keyboard(order_id)
            )
            delivered = True
        except Exception:
            logger.exception("Failed to send order to admin %s", admin_id)

    if delivered:
        await update.message.reply_text(
            f"✅ رسید سفارش #{order_id} برای بررسی ارسال شد.\n"
            "بعد از بررسی، نتیجه بهت اطلاع داده می‌شه."
        )
    else:
        await update.message.reply_text(
            "رسید دریافت شد، اما ارسال آن به ادمین انجام نشد. "
            "ادمین باید ADMIN_IDS را در تنظیمات هاست بررسی کند."
        )


async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("این دکمه فقط برای ادمین است.", show_alert=True)
        return

    _, action, order_id = query.data.split(":")
    data = load_data()
    order = data["orders"].get(str(order_id))
    if not order:
        await query.edit_message_caption(caption="سفارش پیدا نشد.")
        return

    if action == "paid":
        order["status"] = "پرداخت تأیید شد"
        user_message = (
            f"✅ پرداخت سفارش #{order_id} تأیید شد!\n"
            "برای هماهنگی تحویل، منتظر پیام بعدی فروشگاه باش."
        )
        admin_status = "✅ پرداخت تأیید شد"
    else:
        order["status"] = "پرداخت رد شد"
        user_message = (
            f"❌ رسید سفارش #{order_id} تأیید نشد.\n"
            "لطفاً رسید و مبلغ پرداختی رو بررسی کن و برای راهنمایی با فروشگاه تماس بگیر."
        )
        admin_status = "❌ پرداخت رد شد"

    save_data(data)
    try:
        await context.bot.send_message(chat_id=order["user_id"], text=user_message)
    except Exception:
        logger.exception("Could not notify customer for order %s", order_id)

    await query.edit_message_caption(
        caption=(query.message.caption or "") + f"\n\n{admin_status}",
        reply_markup=None
    )


async def orders_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("این دستور فقط برای ادمین است.")
        return
    data = load_data()
    orders = list(data["orders"].values())[-15:]
    if not orders:
        await update.message.reply_text("هنوز سفارشی ثبت نشده.")
        return
    lines = ["📋 آخرین سفارش‌ها:"]
    for o in reversed(orders):
        lines.append(
            f"#{o['id']} | {o['package_label']} | {o['price']} | {o['status']}"
        )
    await update.message.reply_text("\n".join(lines))


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled bot error", exc_info=context.error)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN تنظیم نشده است.")
    if not ADMIN_IDS:
        raise SystemExit("ADMIN_IDS تنظیم نشده است. آیدی عددی ادمین را وارد کنید.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myorders", myorders))
    app.add_handler(CommandHandler("orders", orders_admin))
    app.add_handler(CallbackQueryHandler(package_selected, pattern=r"^pack:"))
    app.add_handler(CallbackQueryHandler(admin_decision, pattern=r"^admin:(paid|reject):"))
    app.add_handler(MessageHandler(filters.PHOTO, receipt_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    app.add_error_handler(error_handler)

    logger.info("KIMO SHOP order bot is running")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
