.PHONY: init init-python init-frontend up down logs

init: init-python init-frontend

init-python:
	python -m venv .venv
	. .venv/Scripts/activate && pip install -U pip

init-frontend:
	cd frontend && npm install

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f
