.PHONY: build

format:
	poetry run isort . -m HANGING_INDENT -l 120

test:
	poetry run pytest -v mobile_tests/

covtest:
	poetry run coverage run -m pytest -v demo_tests tests
	poetry run coverage html --include 'uiautomator2/**'


cov:
	poetry run pytest -v tests/ \
			--cov-config=.coveragerc \
			--cov uiautomator2 \
			--cov-report xml \
			--cov-report term

sync:
	cd uiautomator2/assets; ./sync.sh; cd -

build:
	poetry self add "poetry-dynamic-versioning[plugin]"
	cd uiautomator2/assets; ./sync.sh; cd -
	rm -fr dist
	poetry build -vvv

init:
	if [ ! -f "ApiDemos-debug.apk" ]; then \
		wget https://github.com/appium/appium/raw/master/packages/appium/sample-code/apps/ApiDemos-debug.apk; \
	fi
	poetry run python -m adbutils -i ./ApiDemos-debug.apk

