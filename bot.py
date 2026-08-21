import os
import re
import asyncio
import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from langchain_groq import ChatGroq
from browser_use import Agent

# Direct Credentials (HARDCODED)
TELEGRAM_BOT_TOKEN = "8976398054"  # আপনার দেওয়া বট টোকেন
PUBLIC_CHANNEL_ID = "-1003795293328"  # আপনার দেওয়া চ্যাট আইডি

# Environment Variables for APIs
LAMIX_API_URL = (os.environ.get("LAMIX_API_URL") or "").strip()
LAMIX_TOKEN = (os.environ.get("LAMIX_TOKEN") or "").strip()
GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()

waiting_events = {}

def log(text):
    print(text, flush=True)

# ১. ইনপুট ফরম্যাট থেকে service:range বের করার লজিক (যেমন: ebay:972)
def parse_service_and_range(raw_text):
    lines = raw_text.strip().split("\n")
    tasks = []
    for line in lines:
        line_str = line.strip()
        if ":" in line_str:
            parts = line_str.split(":", 1)
            service = parts[0].strip().lower()
            country_range = parts[1].strip()
            if service and country_range:
                tasks.append((service, country_range))
    return tasks

# ২. Temp Mail জেনারেটর
async def generate_temp_mail():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get("https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1")
            if res.status_code == 200:
                emails = res.json()
                if emails:
                    return emails[0]
    except Exception as e:
        log(f"Temp Mail Error: {e}")
    return "testuser_temp@1secmail.com"

# ৩. প্যানেল থেকে নম্বর অর্ডার
async def buy_number_from_panel(service, country_range):
    params = {
        "action": "getNumber",
        "token": LAMIX_TOKEN,
        "service": service,
        "range": country_range
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(LAMIX_API_URL, params=params)
            if res.status_code == 200:
                try:
                    data = res.json()
                    if data.get("status") == "success":
                        return data.get("id"), data.get("number")
                except Exception:
                    if "ACCESS_NUMBER" in res.text:
                        parts = res.text.split(":")
                        return parts[1], parts[2]
    except Exception as e:
        log(f"Buy Number Error: {e}")
    return None, None

# ৪. AI Browser Agent (স্বয়ংক্রিয় ব্রাউজার নেভিগেশন)
async def run_ai_browser_agent(service, country_range, phone_number, email):
    if not GROQ_API_KEY:
        log("Groq API Key missing in environment! Skipping AI Agent.")
        return False

    try:
        llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            groq_api_key=GROQ_API_KEY
        )

        prompt = (
            f"Go to the sign up or account creation page of {service}. "
            f"Fill the email field with {email} if required. "
            f"Find the phone number input field, select country code or range {country_range}, "
            f"and enter the number {phone_number}. Then click the submit or Send OTP button."
        )

        agent = Agent(task=prompt, llm=llm)
        await agent.run()
        return True
    except Exception as e:
        log(f"AI Agent Error: {e}")
        return False

# ৫. OTP চেক করা
async def check_otp_status(order_id):
    params = {"action": "getStatus", "token": LAMIX_TOKEN, "id": order_id}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(LAMIX_API_URL, params=params)
            if res.status_code == 200:
                try:
                    data = res.json()
                    if data.get("status") == "STATUS_OK":
                        return data.get("sms")
                except Exception:
                    if "STATUS_OK" in res.text:
                        return res.text.split("STATUS_OK:")[1]
    except Exception as e:
        log(f"Check OTP Error: {e}")
    return None

# ৬. নম্বর বাতিল করা
async def cancel_number_order(order_id):
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
        log(f"Cancel Order Error: {e}")

# ৭. অটোমেশন লুপ
async def run_automation_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int, tasks: list):
    global waiting_events

    for service, country_range in tasks:
        temp_email = await generate_temp_mail()
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🎯 *New Task Started!*\n"
                 f"🌐 Service: `{service.upper()}`\n"
                 f"📍 Country Range: `{country_range}`\n"
                 f"📧 Temp Email: `{temp_email}`",
            parse_mode="Markdown",
        )

        failed_attempts = 0
        for attempt in range(1, 4):
            order_id, number = None, None

            while True:
                order_id, number = await buy_number_from_panel(service, country_range)
                if order_id and number:
                    break

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ *Stock Out!* No `{country_range}` numbers found for `{service}`.\n\n"
                         f"👉 Add numbers to panel and reply with `added`.",
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
                text=f"🧪 *Attempt {attempt}/3*\n"
                     f"📱 Copied Number: `{number}`\n"
                     f"🤖 *AI Agent navigating to `{service}` to submit number...*",
                parse_mode="Markdown",
            )

            asyncio.create_task(run_ai_browser_agent(service, country_range, number, temp_email))

            await context.bot.send_message(
                chat_id=chat_id,
                text="⏳ Waiting for OTP code from panel...",
                parse_mode="Markdown",
            )

            otp_received = None
            for _ in range(12):
                await asyncio.sleep(5)
                otp = await check_otp_status(order_id)
                if otp:
                    otp_received = otp
                    break

            if otp_received:
                alert_msg = (
                    f"🚨 *WORK METHOD IS LIVE!* 🚨\n\n"
                    f"🌐 *Service:* `{service.upper()}`\n"
                    f"🎯 *Country Range:* `{country_range}`\n"
                    f"📱 *Tested Number:* `{number}`\n"
                    f"💬 *Received OTP:* `{otp_received}`\n\n"
                    f"🔥 *এই রেঞ্জে কাজ চলতেছে, সবাই কাজ শুরু করতে পারো!*"
                )
                
                try:
                    await context.bot.send_message(
                        chat_id=int(PUBLIC_CHANNEL_ID),
                        text=alert_msg,
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    log(f"Public Channel Alert Error: {e}")

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ *Success!* OTP received for `{service}`. Public alert sent!",
                    parse_mode="Markdown",
                )
                break
            else:
                await cancel_number_order(order_id)
                failed_attempts += 1
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Attempt {attempt} failed (No OTP). Order Canceled.",
                )

        if failed_attempts == 3:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏭️ 3 attempts failed for `{service}:{country_range}`. Moving to next...",
                parse_mode="Markdown",
            )

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global waiting_events
    chat_id = update.message.chat_id
    text = update.message.text.strip()

    if text.lower() == "added":
        if chat_id in waiting_events:
            waiting_events[chat_id].set()
            await update.message.reply_text("👍 Resuming task search...")
        return

    tasks = parse_service_and_range(text)

    if not tasks:
        await update.message.reply_text(
            "⚠️ Invalid format! Please send in this format:\n`ebay:972`\n`amazon:1`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text(
        f"🚀 Received {len(tasks)} task(s). Starting automation loop...",
        parse_mode="Markdown",
    )

    asyncio.create_task(
        run_automation_loop(context, chat_id, tasks)
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages)
    )
    log("Bot started successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()
