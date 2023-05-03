FROM python:3.11-slim

WORKDIR /app

ADD . .

RUN pip install -r requirements.txt

#CMD [ "gunicorn", "-c", "gunicorn.conf", "main:get_app" ]