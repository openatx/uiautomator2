#!/bin/bash
#

set -e

if [[ $# -eq 0 ]]
then
	URL="https://github.com/appium/java-client/raw/v7.3.0/src/test/java/io/appium/java_client/ApiDemos-debug.apk"
	python3 -m adbutils -i "$URL" #https://github.com/appium/java-client/raw/master/src/test/java/io/appium/java_client/ApiDemos-debug.apk
fi
py.test -v "$@"
