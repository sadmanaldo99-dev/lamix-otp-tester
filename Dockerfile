FROM python:3.11-slim

WORKDIR /app

# ব্রাউজার ও সিস্টেম ডিপেন্ডেন্সি ইনস্টল
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Chromium ব্রাউজার এবং সমস্ত সিস্টেমে ব্যবহৃত নির্ভরতা ইনস্টল
RUN playwright install chromium --with-deps

COPY . .

CMD ["python", "bot.py"]
