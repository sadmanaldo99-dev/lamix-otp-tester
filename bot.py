import asyncio
import os
import re
import requests
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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PUBLIC_CHANNEL_ID = os.environ.get("CHAT_ID")
LAMIX_API_URL = os.environ.get("LAMIX_API_URL")
LAMIX_TOKEN = os.environ.get("LAMIX_TOKEN")

# Global State Management
waiting_for_added_event = asyncio.Event()


# ১. টেক্সট থেকে সার্ভিস ফিল্টার
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
            for header in ["CONTENT", "SMS", "TOP SIDS", "ALGERIA", "http"]
        ):
            if "CONTENT" in line_str.upper():
                break
            continue

        cleaned = clean_pattern.sub("", line_str).strip()

        if cleaned and not cleaned.isdigit() and len(cleaned) > 1:
            cleaned_services.append(cleaned.lower())

    return cleaned_services


# ২. Playwright দিয়ে আসল ব্রাউজারের মতো টাইপ করে Range বের করা
async def get_service_range(service_name):
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, args=["--no-sandbox"]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            # lamix tools পেজে যাওয়া
            await page.goto(
                "https://www.lamix.org/tools",
                wait_until="networkidle",
                timeout=30000,
            )

            # ইনপুট বক্সে নাম লেখা
            input_box = page.locator("input").first
            await input_box.fill(service_name)

            # সার্চ বাটনে ক্লিক করা
            search_button = page.locator(
                "button:has-text('SEARCH'), input[type='submit']"
            ).first
            if await search_button.count() > 0:
                await search_button.click()
            else:
                await input_box.press("Enter")

            # ডাটা লোড হওয়ার জন্য ২ সেকেন্ড অপেক্ষা
            await page.wait_for_timeout(2000)

            # ফলাফল থেকে Range ফিল্টার করা
            content = await page.content()

            # পেজের টেক্সট থেকে ডিজিট/রেঞ্জ ফিল্টার
            body_text = await page.locator("body").inner_text()
            lines = body_text.split("\n")

            for line in lines:
                if service_name.lower() in line.lower():
                    numbers = re.findall(r"\+?\d{4,15}", line)
                    if numbers:
                        await browser.close()
                        return numbers[0]

            # টেবিলের ক্ষেত্রে td খোঁজা
            cells = await page.locator("td, div, p, span").all_inner_texts()
            for i, text in enumerate(cells):
                if service_name.lower() in text.lower():
                    for next_text in cells[i : i + 3]:
                        numbers = re.findall(r"\+?\d{4,15}", next_text)
                        if numbers:
                            await browser.close()
                            return numbers[0]

            await browser.close()
    except Exception as e:
        print(f"Playwright Scraping Error: {e}")

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


# ৭. মেসেজ হ্যান্ডলার
async def handle_all_messages(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
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

    print("Playwright Smart Auto-Tester Bot is Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
