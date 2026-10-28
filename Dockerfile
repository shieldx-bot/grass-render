FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Thu vien he thong cho Chrome for Testing (khop _LIB2PKG cua notebook goc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget curl unzip fonts-liberation \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libgtk-3-0 libdbus-1-3 libexpat1 \
    libx11-6 libxcb1 libxext6 libgl1 libegl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY download_chrome.py .
# Tai Chrome for Testing 131 luc BUILD de runtime khoi dong nhanh
RUN python download_chrome.py

COPY app.py .

# Thu muc du lieu (cookie/profile/extension) - ephemeral tren Render free
RUN mkdir -p /app/data

EXPOSE 10000
CMD ["python", "app.py"]
