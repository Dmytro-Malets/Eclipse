FROM python:3.12.4-slim

WORKDIR /app
COPY . /app/

RUN pip install --no-cache-dir -r requirements/prod.txt
RUN mkdir -p /var/log/bot && chown -R root:root /var/log/bot && chmod 755 /var/log/bot

CMD ["sh", "-c", "alembic upgrade head && python3 main.py"]