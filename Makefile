.PHONY: build

format:
	poetry run isort . -m HANGING_INDENT -l 120

test:
	poetry run pytest -v tests

cov:
	poetry run pytest --cov=. --cov-report xml --cov-report term

build:
	rm -fr dist
	poetry build