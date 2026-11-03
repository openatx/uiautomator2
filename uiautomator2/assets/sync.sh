#!/bin/bash
#

set -e

U2_VERSION=$(cat ../version.py| grep __u2_version__ | awk '{print $NF}')
U2_VERSION=${U2_VERSION//[\"\']}

cd "$(dirname $0)"


function download() {
	local URL=$1
	local OUTPUT=$2
	echo ">> download $URL -> $OUTPUT"
	curl -L "$URL" --output "$OUTPUT"
}

function download_apk() {
	local URL="https://github.com/openatx/android-uiautomator-server-jar/releases/download/$U2_VERSION/u2.apk"
	download "$URL" "u2.apk"
	unzip -tq "u2.apk"
}

echo "U2_VERSION: $U2_VERSION"

download_apk
cat > version.json <<EOF
{
  "u2.apk": "$U2_VERSION"
}
EOF
