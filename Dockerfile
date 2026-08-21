FROM python:3.11-slim

WORKDIR /app

# সিস্টেম নির্ভর প্যাকেজ ও ব্রাউজার ইনস্টল
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps

COPY . .

CMD ["python", "bot.py"]
