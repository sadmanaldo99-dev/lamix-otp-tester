import asyncio
import os
import re
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Environment Variables (Railway Variables থেকে আসবে)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PUBLIC_CHANNEL_ID = os.environ.get("CHAT_ID")
LAMIX_API_URL = os.environ.get("LAMIX_API_URL")
LAMIX_TOKEN = os.environ.get("LAMIX_TOKEN")

# Global State Management
waiting_for_added_event = asyncio.Event()


# ১. টেক্সট থেকে ওয়েবসাইটের নাম ফিল্টার করার ফাংশন
def extract_services_from_text(raw_text):
    # সাধারণ কম্যান্ড বাদ দেওয়া
    if raw_text.startswith("/"):
        raw_text = raw_text.split(" ", 1)[-1] if " " in raw_text else ""

    lines = raw_text.split("\n")
    cleaned_services = []

    # ইমোজি ও বিশেষ চিহ্ন বাদ দেওয়ার Regex
    clean_pattern = re.compile(r"[^\w\s-]")

    for line in lines:
        line_str = line.strip()

        # CONTENT বা অন্যান্য টেক্সটের পার্ট আসলে পড়া বন্ধ করে দেবে
        if any(
            header in line_str.upper()
            for header in ["CONTENT", "SMS", "TOP SIDS", "ALGERIA", "http"]
        ):
            if "CONTENT" in line_str.upper():
                break
            continue

        # ইমোজি ও স্পেশাল ক্যারেক্টার ক্লিন করা
        cleaned = clean_pattern.sub("", line_str).strip()

        # শুধু নম্বর/ফোন নম্বর বা ছোট টেক্সট বাদ দেওয়া
        if cleaned and not cleaned.isdigit() and len(cleaned) > 1:
            cleaned_services.append(cleaned.lower())

    return cleaned_services


# ২. CLI সার্চ করে Range বের করার ফাংশন
def get_service_range(service_name):
    params = {
        "action": "getCli",
        "token": LAMIX_TOKEN,
        "service": service_name,
    }
    try:
        res = requests.get(LAMIX_API_URL, params=params, timeout=10).json()
        if res.get("status") == "success":
            return res.get("range")
    except Exception as e:
        print(f"CLI Error: {e}")
    return None


# ৩. নির্দিষ্ট Range-এর নম্বর নেওয়ার ফাংশন
def get_number_by_range(service_name, target_range):
    params = {
        "action": "getNumber",
        "token": LAMIX_TOKEN,
        "service": service_name,
        "range": target_range,
    }
    try:
        res = requests.get(LAMIX_API_URL, params=params, timeout=10).json()
        if res.get("status") == "success":
            return res.get("id"), res.get("number")
    except Exception as e:
        print(f"Get Number Error: {e}")
    return None, None


# ৪. OTP চেক করার ফাংশন
def check_otp(order_id):
    params = {"action": "getStatus", "token": LAMIX_TOKEN, "id": order_id}
    try:
        res = requests.get(LAMIX_API_URL, params=params, timeout=10).json()
        if res.get("status") == "STATUS_OK":
            return res.get("sms")
    except Exception as e:
        print(f"Check OTP Error: {e}")
    return None


# ৫. Order Cancel করার ফাংশন
def cancel_order(order_id):
    params = {
        "action": "setStatus",
        "token": LAMIX_TOKEN,
        "id": order_id,
        "status": "8",
    }
    try:
        requests.get(LAMIX_API_URL, params=params, timeout=10)
    except Exception as e:
        print(f"Cancel Error: {e}")


# ৬. মূল অটো-টেস্টিং লুপ
async def test_websites_loop(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, services: list
):
    global waiting_for_added_event

    for service in services:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔍 *Searching CLI for:* `{service.upper()}`",
            parse_mode="Markdown",
        )

        target_range = get_service_range(service)
        if not target_range:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ No CLI range found for `{service}`. Skipping...",
                parse_mode="Markdown",
            )
            continue

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📌 `{service.upper()}` Range Detected: `{target_range}`",
            parse_mode="Markdown",
        )

        failed_attempts = 0
        for attempt in range(1, 4):
            order_id, number = None, None

            # স্টক চেক ও 'added' ইনপুটের ওয়েট লুপ
            while True:
                order_id, number = get_number_by_range(service, target_range)
                if order_id and number:
                    break

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ *No numbers found in range `{target_range}` for `{service}`!*\n\n"
                    f"👉 Please add numbers to panel and reply with `added`.",
                    parse_mode="Markdown",
                )

                waiting_for_added_event.clear()
                await waiting_for_added_event.wait()

                await context.bot.send_message(
                    chat_id=chat_id, text="🔄 Re-checking panel stock..."
                )

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧪 *Attempt {attempt}/3* for `{service}`\n📱 Number: `{number}`\nWaiting for OTP...",
                parse_mode="Markdown",
            )

            # ৬০ সেকেন্ড OTP এর জন্য অপেক্ষা
            otp_received = None
            for _ in range(12):
                await asyncio.sleep(5)
                otp = check_otp(order_id)
                if otp:
                    otp_received = otp
                    break

            if otp_received:
                alert_msg = (
                    f"🚨 *OTP RECEIVED & METHOD LIVE!* 🚨\n\n"
                    f"🌐 *Website:* `{service.upper()}`\n"
                    f"🎯 *Range:* `{target_range}`\n"
                    f"📱 *Number:* `{number}`\n"
                    f"💬 *OTP Code:* `{otp_received}`\n\n"
                    f"🔥 *সবাই কাজ শুরু করে দিতে পারো!*"
                )
                await context.bot.send_message(
                    chat_id=PUBLIC_CHANNEL_ID,
                    text=alert_msg,
                    parse_mode="Markdown",
                )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ OTP Received for `{service}`! Public alert sent.",
                    parse_mode="Markdown",
                )
                break
            else:
                cancel_order(order_id)
                failed_attempts += 1
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Attempt {attempt} failed for `{service}`. Canceled.",
                )

        if failed_attempts == 3:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏭️ 3 attempts failed for `{service}`. Skipping to next...",
                parse_mode="Markdown",
            )


# ৭. যে কোনো টেক্সট বা ফরওয়ার্ড মেসেজ রিসিভার
async def handle_all_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    global waiting_for_added_event
    text = update.message.text.strip()

    # যদি ইউজার 'added' মেসেজ দেয়
    if text.lower() == "added":
        if not waiting_for_added_event.is_set():
            waiting_for_added_event.set()
            await update.message.reply_text("👍 Resuming number search...")
        return

    # ফরওয়ার্ড করা পোস্ট থেকে ওয়েবসাইটের নাম এক্সট্র্যাক্ট করা
    services = extract_services_from_text(text)

    if not services:
        await update.message.reply_text(
            "⚠️ No valid service names found in the message."
        )
        return

    await update.message.reply_text(
        f"🚀 Detected {len(services)} service(s): `{', '.join(services)}`\nStarting tracking...",
        parse_mode="Markdown",
    )

    asyncio.create_task(
        test_websites_loop(context, update.message.chat_id, services)
    )


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # যে কোনো টেক্সট বা ফরওয়ার্ড মেসেজ প্রসেস করবে
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages)
    )
    app.add_handler(CommandHandler("test", handle_all_messages))

    print("Smart Auto-Tester Bot is Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
