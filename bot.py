import os
import telebot

# Get bot token from environment variables (set in Railway)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

bot = telebot.TeleBot(BOT_TOKEN)

# Command: /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = "👋 আসসালামু আলাইকুম! আপনার টেলিগ্রাম বটটি সফলভাবে চালু হয়েছে।"
    bot.reply_to(message, welcome_text)

# Command: /help
@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = "🤖 সাহায্য প্রয়োজন?\n\nআপনার যেকোনো মেসেজ লিখলে বটটি রিপ্লাই দেবে।"
    bot.reply_to(message, help_text)

# Echo all messages
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"আপনি পাঠিয়েছেন: {message.text}")

if __name__ == "__main__":
    print("Bot is starting...")
    bot.infinity_polling()
```eof

```text:requirements.txt
pyTelegramBotAPI==4.14.0
```eof

```markdown:setup_guide.md
# GitHub এবং Railway-তে বট সেটআপ করার সম্পূর্ণ গাইড

---

## Step 1: GitHub-এ ফাইল আপলোড করা

1. **GitHub ওয়েবসাইট খুলুন:** [github.com](https://github.com/)-এ যান এবং আপনার নতুন Gmail দিয়ে একাউন্ট তৈরি করুন/লগইন করুন।
2. **নতুন Repository তৈরি করুন:**
   - উপরে ডানপাশের **`+`** আইকনে ক্লিক করে **New repository** সিলেক্ট করুন।
   - **Repository name** দিন (যেমন: `my-telegram-bot`)।
   - Public বা Private যেকোনো একটি বেছে নিন।
   - **Create repository** বাটনে ক্লিক করুন।
3. **ফাইল ৩টি তৈরি করুন:**
   - **`bot.py`**:
     - `creating a new file`-এ ক্লিক করুন।
     - ফাইল নাম দিন `bot.py` এবং ওপরের `bot.py` কোডটি কপি-পেস্ট করুন।
     - নিচে এসে **Commit changes**-এ ক্লিক করুন।
   - **`requirements.txt`**:
     - আবার `Add file` -> `Create new file`-এ ক্লিক করুন।
     - ফাইল নাম দিন `requirements.txt` এবং ভেতর লিখুন:
       
```text
       pyTelegramBotAPI==4.14.0
