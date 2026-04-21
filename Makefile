.PHONY: init init-python init-frontend up up-prod down down-prod logs logs-prod

init: init-python init-frontend

init-python:
	python -m venv .venv
	. .venv/Scripts/activate && pip install -U pip

init-frontend:
	cd frontend && npm install

up:
	docker compose up --build

up-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build

down:
	docker compose down

down-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

logs:
	docker compose logs -f

logs-prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f
