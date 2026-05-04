FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Base SQLite persistante si tu montes un volume sur /data (voir PLAYERS_DB_PATH)
ENV PLAYERS_DB_PATH=/data/players.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py database.py seed_list.py .

RUN mkdir -p /data

CMD ["python", "bot.py"]
