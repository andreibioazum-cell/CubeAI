# Один контейнер на всё: собранный фронтенд раздаёт тот же процесс,
# который считает эволюцию.

FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app

# Без torch: он нужен только сети-проектировщику и вкусовому критику,
# а весит 4 ГБ. В обычном режиме показа не загружается вовсе.
RUN pip install --no-cache-dir \
    "numpy>=2.0" "fastapi>=0.115" "uvicorn[standard]>=0.30" "pillow>=10.0"

COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist

ENV CAINE_SOURCE=auto \
    CAINE_DUEL=1 \
    CAINE_EVOLVE=1 \
    CAINE_EVOLVE_DUTY=0.2 \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
