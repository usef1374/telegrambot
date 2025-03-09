FROM ubuntu:20.04

# تنظیم نصب غیرتعاملی و منطقه زمانی
ENV DEBIAN_FRONTEND=noninteractive
RUN ln -fs /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone

# نصب پایتون و وابستگی‌ها
RUN apt-get update && apt-get install -y \
    python3.9 \
    python3-pip \
    libssl1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN pip3 install -r requirements.txt
CMD ["python3", "main.py"]