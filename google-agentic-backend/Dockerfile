FROM python:3.11-slim-bullseye

WORKDIR /google-agentic-backend

COPY . /google-agentic-backend

RUN apt update

RUN apt-get install curl -y

RUN pip install -r requirements.txt

CMD ["bash", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 80 --reload"]
