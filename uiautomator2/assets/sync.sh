#!/bin/bash
#

set -e

APK_VERSION=$(cat ../version.py| grep apk_version | awk '{print $NF}')
APK_VERSION=${APK_VERSION//[\"\']}

cd "$(dirname $0)"

# function download_atx_agent() {
# 	VERSION=$1
# 	NAME="tmp-atx-agent.tar.gz"
# 	URL="https://github.com/openatx/atx-agent/releases/download/$VERSION/atx-agent_${VERSION}_linux_armv6.tar.gz"
# 	echo "$URL"
# 	curl -L "$URL" --output "$NAME"
# 	tar -xzvf "$NAME" atx-agent
# 	rm -f "$NAME"
# }

function download_apk(){
	VERSION=$1
	NAME=$2
	URL="https://github.com/openatx/android-uiautomator-server/releases/download/$VERSION/$NAME"
	echo ">> download $URL -> $NAME"
	curl -L "$URL" --output "$NAME"
	unzip -tq "$NAME"
}

# download_atx_agent "$AGENT_VERSION"
# echo "atx_agent_version: $AGENT_VERSION" >> version.txt

echo "APK_VERSION: $APK_VERSION"

download_apk "$APK_VERSION" "app-uiautomator.apk"
download_apk "$APK_VERSION" "app-uiautomator-test.apk"
echo "apk_version: $APK_VERSION" > version.txt
