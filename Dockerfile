FROM python:3.12.4-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r requirements/prod.txt
RUN mkdir -p /var/log/bot && chown -R root:root /var/log/bot && chmod 755 /var/log/bot

COPY . /app/

CMD ["sh", "-c", "alembic upgrade head && python3 main.py"]