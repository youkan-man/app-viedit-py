.PHONY: up down logs test lint package

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test:
	pytest -q

lint:
	ruff check .
	python -m compileall -q app main.py
	node --check app/static/app.js
	node --check app/static/workspace.js

package:
	cd .. && zip -r pylabview-vi-xml-web.zip pylabview-vi-xml-web \
		-x 'pylabview-vi-xml-web/.git/*' 'pylabview-vi-xml-web/.venv/*' \
		'pylabview-vi-xml-web/__pycache__/*' 'pylabview-vi-xml-web/.pytest_cache/*'
