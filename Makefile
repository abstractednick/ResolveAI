.PHONY: install api frontend seed test compose

install:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

api:
	. .venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

seed:
	. .venv/bin/activate && python scripts/seed.py

test:
	. .venv/bin/activate && pytest -q

compose:
	docker compose up --build
