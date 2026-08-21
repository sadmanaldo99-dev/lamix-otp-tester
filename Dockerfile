# ১. Playwright-এর অফিশিয়াল পাইথন ইমেজ ব্যবহার
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# ২. ওয়ার্কিং ডিরেক্টরি সেটআপ
WORKDIR /app

# ৩. প্রজেক্টের ফাইল কপি করা
COPY . /app

# ৪. ডিপেনডেন্সি ইনস্টল করা
RUN pip install --no-cache-dir -r requirements.txt

# ৫. বট রান করার কমান্ড
CMD ["python", "bot.py"]
