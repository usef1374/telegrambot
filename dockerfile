FROM ubuntu:20.04

# تنظیم نصب غیرتعاملی و منطقه زمانی
ENV DEBIAN_FRONTEND=noninteractive
RUN ln -fs /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone

# نصب پایتون و libssl1.1 با آپدیت کامل
RUN apt-get update && apt-get install -y \
    python3.9 \
    python3-pip \
    libssl1.1 \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# نصب بسته‌ها در یک محیط مجازی (اختیاری اما توصیه‌شده)
WORKDIR /app
COPY . /app
RUN python3.9 -m pip install --upgrade pip \
    && python3.9 -m pip install -r requirements.txt

CMD ["python3.9", "main.py"]