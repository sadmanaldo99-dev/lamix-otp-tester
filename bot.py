import os
import re
import asyncio
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
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

# Global State & Browser Management
waiting_for_added_event = asyncio.Event()
playwright_instance = None
browser_instance = None

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

async def get_browser():
    global playwright_instance, browser_instance
    if not browser_instance or not browser_instance.is_connected():
        log("🚀 Starting Playwright Browser...")
        playwright_instance = await async_playwright().start()
        browser_instance = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--single-process'
            ]
        )
    return browser_instance

async async def get_service_range(service_name):
    try:
        browser = await get_browser()
        page = await browser.new_page()
        log(f"🔎 Scraping Lamix for: {service_name}")
        
        # ১. পেজ লোড হওয়া পর্যন্ত ওয়েট
        await page.goto("https://www.lamix.org/tools", wait_until="networkidle", timeout=30000)
        
        # ২. ইনপুট ফিল্ড ও সার্চ
        input_element = await page.wait_for_selector('input[type="text"]', timeout=10000)
        await input_element.fill(service_name)
        await page.keyboard.press("Enter")
        
        # ৩. ডাটা টেবিল বা রেজাল্ট লোড হওয়ার সময় দেওয়া (৪ সেকেন্ড)
        await page.wait_for_timeout(4000)
        
        content = await page.content()
        await page.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # টেবিলের ভেতর ডাটা খোঁজা (Lamix-এ সাধারণত td বা tr-এ থাকে)
        for row in soup.find_all(["tr", "div", "li"]):
            text = row.get_text().strip()
            if service_name.lower() in text.lower():
                numbers = re.findall(r"\+?\d{4,15}", text)
                if numbers:
                    log(f"✅ Range Found for {service_name}: {numbers[0]}")
                    return numbers[0]

        # ব্যাকআপ: পুরো পেজে নম্বর খোঁজা
        all_numbers = re.findall(r"\+?\d{4,15}", soup.get_text())
        if all_numbers:
            log(f"✅ Range Found (Fallback) for {service_name}: {all_numbers[0]}")
            return all_numbers[0]

    except Exception as e:
        log(f"❌ Scraping Error for {service_name}: {e}")

    return None
   ef gst_fef get_number_by_range(service_name, target_range):
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
        log(f"Get Number Error: {e}")
    return None, None

def check_otp(order_id):
    params = {"action": "getStatus", "token": LAMIX_TOKEN, "id": order_id}
    try:
        res = requests.get(LAMIX_API_URL, params=params, timeout=10).json()
        if res.get("status") == "STATUS_OK":
            return res.get("sms")
    except Exception as e:
        log(f"Check OTP Error: {e}")
    return None

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
        log(f"Cancel Error: {e}")

async def test_websites_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, services: list):
    global waiting_for_added_event

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
                if PUBLIC_CHANNEL_ID:
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

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_for_added_event
    text = update.message.text.strip()

    if text.lower() == "added":
        if not waiting_for_added_event.is_set():
            waiting_for_added_event.set()
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
        test_websites_loop(context, update.message.chat_id, services)
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
