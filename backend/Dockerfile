FROM python:3.11-slim

WORKDIR /app

# 🔥 INSTALL SSL + CA CERTIFICATES (THIS FIXES EVERYTHING)
RUN apt-get update && apt-get install -y \
    ca-certificates \
    openssl \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    libmariadb-dev-compat \
    libmariadb-dev \
    && update-ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app/

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
