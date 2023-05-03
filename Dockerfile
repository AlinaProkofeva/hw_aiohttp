FROM python:3.11-slim

WORKDIR /app

ADD . .

RUN pip install -r requirements.txt

EXPOSE 8080