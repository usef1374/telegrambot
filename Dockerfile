# استفاده از اوبونتو 20.04 که libssl1.1 را دارد
FROM ubuntu:20.04

# نصب پایتون و وابستگی‌ها
RUN apt-get update && apt-get install -y \
    python3.9 \
    python3-pip \
    libssl1.1 \
    && rm -rf /var/lib/apt/lists/*

# تنظیم دایرکتوری کاری
WORKDIR /app

# کپی فایل‌ها
COPY . /app

# نصب بسته‌های پایتون
RUN pip3 install -r requirements.txt

# اجرای برنامه
CMD ["python3", "main.py"]