import os
import re
import asyncio
import httpx
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
PUBLIC_CHANNEL_ID = os.environ.get("CHAT_ID")
LAMIX_API_URL = os.environ.get("LAMIX_API_URL")
LAMIX_TOKEN = os.environ.get("LAMIX_TOKEN")

# Chat specific waiting state
waiting_events = {}

def log(text):
    print(text, flush=True)

def extract_services_from_text(raw_text):
    if raw_text.startswith("/"):
        raw_text = raw_text.split(" ", 1)[-1] if " " in raw_text else ""

    lines = raw_text.split("\n")
    cleaned_services = []
    clean_pattern = re.compile(r"[^\w\s-]")

    for line in lines:
        line_str = line.strip()

        if any(
            header in line_str.upper()
            for header in ["CONTENT", "SMS", "TOP SIDS", "ALGERIA", "HTTP"]
        ):
            if "CONTENT" in line_str.upper():
                break
            continue

        cleaned = clean_pattern.sub("", line_str).strip()

        if cleaned and not cleaned.isdigit() and len(cleaned) > 1:
            cleaned_services.append(cleaned.lower())

    return cleaned_services

# Advanced Async Range Search
async def get_service_range(service_name):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    clean_service = service_name.strip().lower()
    
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # পদ্ধতি ১: ডিরেক্ট ওয়েব স্ক্র্যাপিং
        try:
            url = f"https://www.lamix.org/tools?search={clean_service}"
            res = await client.get(url, headers=headers)
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                
                for element in soup.find_all(["tr", "div", "p", "td", "li", "span"]):
                    elem_text = element.get_text().strip()
                    if clean_service in elem_text.lower():
                        found_nums = re.findall(r"\+?\d[\d\s-]{3,14}\d", elem_text)
                        if found_nums:
                            clean_range = found_nums[0].replace(" ", "").replace("-", "")
                            log(f"✅ Found range via Direct Web for {service_name}: {clean_range}")
                            return clean_range
            else:
                log(f"Web Search Blocked/Failed with status: {res.status_code}")
                        
        except Exception as e:
            log(f"Direct fetch failed: {e}")

        # পদ্ধতি ২: ব্যাকআপ API রেঞ্জ খোঁজা
        if LAMIX_API_URL and LAMIX_TOKEN:
            try:
                params = {
                    "action": "getServices",
                    "token": LAMIX_TOKEN
                }
                res = await client.get(LAMIX_API_URL, params=params)
                data = res.json()
                
                data_str = str(data)
                if clean_service in data_str.lower():
                    nums = re.findall(r"\+?\d{4,15}", data_str)
                    if nums:
                        log(f"✅ Found range via API for {service_name}: {nums[0]}")
                        return nums[0]
            except Exception as e:
                log(f"API Range Search Error: {e}")

    return None

async def get_number_by_range(service_name, target_range):
    params = {
        "action": "getNumber",
        "token": LAMIX_TOKEN,
        "service": service_name,
        "range": target_range,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(LAMIX_API_URL, params=params)
            data = res.json()
            if data.get("status") == "success":
                return data.get("id"), data.get("number")
    except Exception as e:
        log(f"Get Number Error: {e}")
    return None, None

async def check_otp(order_id):
    params = {"action": "getStatus", "token": LAMIX_TOKEN, "id": order_id}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(LAMIX_API_URL, params=params)
            data = res.json()
            if data.get("status") == "STATUS_OK":
                return data.get("sms")
    except Exception as e:
        log(f"Check OTP Error: {e}")
    return None

async def cancel_order(order_id):
    params = {
        "action": "setStatus",
        "token": LAMIX_TOKEN,
        "id": order_id,
        "status": "8",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(LAMIX_API_URL, params=params)
    except Exception as e:
        log(f"Cancel Error: {e}")

async def test_websites_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, services: list):
    global waiting_events

    for service in services:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔍 *Searching Tools Web for:* `{service.upper()}`",
            parse_mode="Markdown",
        )

        target_range = await get_service_range(service)
        if not target_range:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ No CLI range found for `{service}` on Lamix Tools. Skipping...",
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

            while True:
                order_id, number = await get_number_by_range(service, target_range)
                if order_id and number:
                    break

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ *No numbers found in range `{target_range}` for `{service}`!*\n\n"
                         f"👉 Please add numbers to panel and reply with `added`.",
                    parse_mode="Markdown",
                )

                event = asyncio.Event()
                waiting_events[chat_id] = event
                await event.wait()
                waiting_events.pop(chat_id, None)

                await context.bot.send_message(
                    chat_id=chat_id, text="🔄 Re-checking panel stock..."
                )

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🧪 *Attempt {attempt}/3* for `{service}`\n📱 Number: `{number}`\nWaiting for OTP...",
                parse_mode="Markdown",
            )

            otp_received = None
            for _ in range(12):
                await asyncio.sleep(5)
                otp = await check_otp(order_id)
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
                if PUBLIC_CHANNEL_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=PUBLIC_CHANNEL_ID,
                            text=alert_msg,
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        log(f"Public channel send error: {e}")

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ OTP Received for `{service}`! Public alert sent.",
                    parse_mode="Markdown",
                )
                break
            else:
                await cancel_order(order_id)
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

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_events
    chat_id = update.message.chat_id
    text = update.message.text.strip()

    if text.lower() == "added":
        if chat_id in waiting_events:
            waiting_events[chat_id].set()
            await update.message.reply_text("👍 Resuming number search...")
        return

    services = extract_services_from_text(text)

    if not services:
        await update.message.reply_text(
            "⚠️ No valid service names found in the message."
        )
        return

    await update.message.reply_text(
        f"🚀 Detected {len(services)} service(s): `{', '.join(services)}`\nSearching CLI ranges...",
        parse_mode="Markdown",
    )

    asyncio.create_task(
        test_websites_loop(context, chat_id, services)
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages)
    )
    app.add_handler(CommandHandler("test", handle_all_messages))
    log("Fast Ultra-Light Tester Bot is Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
