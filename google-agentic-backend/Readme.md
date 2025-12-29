# Google Agentic Assignment Backend

## Features

- FastAPI for building APIs
- Docker for containerization
- Qdrant
- Docker Compose for easy setup
- Secrets management with `secrets.json`

## Requirements

- Docker
- Docker Compose

# installation and run locally:

- Create venv and activate
- pip install -r "requirements.txt"
- in terminal "uvicorn main:app --port 8000 --reload"
- make sure to match the port in frontend as well before calling api

--------OR-----------

- just docker compose up, make sure secrets.json is present at the root of the backend.
