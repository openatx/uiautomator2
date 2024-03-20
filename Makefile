.PHONY: build

format:
	poetry run isort . -m HANGING_INDENT -l 120

test:
	poetry run pytest -v tests

cov:
	poetry run pytest -v tests/unittests --cov=. --cov-report xml --cov-report term

build:
	rm -fr dist
	poetry build

init:
	if [ ! -f "ApiDemos-debug.apk" ]; then \
		wget https://github.com/appium/appium/raw/master/packages/appium/sample-code/apps/ApiDemos-debug.apk; \
	fi
	poetry run python -m adbutils -i ./ApiDemos-debug.apk
