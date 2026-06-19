# Railway single-service image: builds the React frontend, then runs FastAPI
# serving both the API and the static frontend, with the worker in-process.
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY --from=fe /fe/dist ./app/static
ENV RUN_WORKER_IN_APP=true
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
