import os
import asyncio
import nest_asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

nest_asyncio.apply()

# ----------------- CONFIGURATION -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")

# -------------------------------------------------

async def scrape_lamix(query: str):
    """Playwright দিয়ে Lamix-এর Form Submit ও reCAPTCHA বাইপাস করে CLI ডাটা স্ক্র্যাপ করে"""
    async with async_playwright() as p:
        # Railway-র কম মেমোরির জন্য অপটিমাইজড ব্রাউজার অপশন
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--single-process'
            ]
        )
        page = await browser.new_page()
        
        try:
            # ১. Lamix tools পেজে যাওয়া
            await page.goto("https://www.lamix.org/tools", wait_until="domcontentloaded", timeout=30000)
            
            # ২. ইনপুট ফিল্ডে সার্চ মান বসানো
            await page.fill('input[type="text"]', query)
            
            # ৩. সার্চ বাটনে ক্লিক করা
            await page.click('#search-btn')
            
            # ৪. রেজাল্ট লোড হওয়া পর্যন্ত ওয়েট করা (৩ সেকেন্ড)
            await page.wait_for_timeout(3000)
            
            content = await page.content()
            await browser.close()
            
            # BeautifulSoup দিয়ে ডাটা পার্স করা
            soup = BeautifulSoup(content, 'html.parser')
            
            # পেজের পুরো টেক্সট নিয়ে সার্চ রেজাল্ট চেকিং
            text_data = soup.get_text()
            return text_data
            
        except Exception as e:
            await browser.close()
            return f"Error occurred: {str(e)}"

# টেলিগ্রাম কমান্ড হ্যান্ডলার: /search <service_name>
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("ব্যবহার নিয়ম: `/search ebay`", parse_mode="Markdown")
        return

    service_query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🔍 `{service_query}` এর জন্য Lamix-এ খোঁজ করা হচ্ছে...", parse_mode="Markdown")

    # স্ক্র্যাপার রান করা
    scraped_result = await scrape_lamix(service_query)

    # রেজাল্ট ফিল্টার বা মেসেজ রেডি করা
    if "Error" in scraped_result:
        await status_msg.edit_text(f"❌ সমস্যা হয়েছে: {scraped_result}")
    else:
        # রেজাল্ট টেক্সট ছোট করে টেলিগ্রামে পাঠানো
        output_preview = scraped_result[:1500] if len(scraped_result) > 1500 else scraped_result
        await status_msg.edit_text(f"✅ **Lamix Result:**\n\n```\n{output_preview}\n```", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("search", search_command))
    
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
