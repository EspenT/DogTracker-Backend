FROM python:3.11-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir fastapi uvicorn websockets python-dotenv paho-mqtt PyJWT passlib[bcrypt] python-multipart pydantic[email]


EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

