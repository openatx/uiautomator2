#!/bin/bash
#

set -e

APK_VERSION=$(cat ../version.py| grep apk_version | awk '{print $NF}')
APK_VERSION=${APK_VERSION//[\"\']}
JAR_VERSION="0.1.0"

cd "$(dirname $0)"


function download() {
	local URL=$1
	local OUTPUT=$2
	echo ">> download $URL -> $OUTPUT"
	curl -L "$URL" --output "$OUTPUT"
}

function download_apk(){
	local VERSION=$1
	local NAME=$2
	local URL="https://github.com/openatx/android-uiautomator-server/releases/download/$VERSION/$NAME"
	download "$URL" "$NAME"
	unzip -tq "$NAME"
}

function download_jar() {
	local URL="https://public.uiauto.devsleep.com/u2jar/$JAR_VERSION/u2.jar"
	https_proxy= download "$URL" "u2.jar"
}

echo "APK_VERSION: $APK_VERSION"

download_jar
download_apk "$APK_VERSION" "app-uiautomator.apk"
cat > version.json <<EOF
{
  "com.github.uiautomator": "$APK_VERSION"
}
EOF
