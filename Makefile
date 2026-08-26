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
	node --check app/static/pages.js
	node --check app/static/graph.js
	node --check app/static/workspace.js
	node --check app/static/quantizer.js
	node --check app/static/components.js

package:
	cd .. && zip -r app-viedit-py.zip app-viedit-py \
		-x 'app-viedit-py/.git/*' 'app-viedit-py/.venv/*' \
		'app-viedit-py/__pycache__/*' 'app-viedit-py/.pytest_cache/*'
