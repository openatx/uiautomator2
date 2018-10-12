#!/bin/bash -
#

set -e

# Verisons modify here
ATX_AGENT_VERSION=0.3.0
UIAUTOMATOR_APK_VERSION=1.0.13

# Download resources
mkdir -p vendor

download_apk(){
        APK_BASE_URL="https://github.com/openatx/android-uiautomator-server/releases/download/${UIAUTOMATOR_APK_VERSION}"
        wget -O vendor/app-uiautomator.apk "$APK_BASE_URL/app-uiautomator.apk"
        wget -O vendor/app-uiautomator-test.apk "$APK_BASE_URL/app-uiautomator-test.apk"
}

download_stf(){
        ## minicap+minitouch
        wget -O vendor/stf-binaries.zip "https://github.com/codeskyblue/stf-binaries/archive/master.zip"
        unzip -o -d vendor/ vendor/stf-binaries.zip
}

download_atx(){
        ## atx-agent
        wget -O vendor/atx-agent-$ATX_AGENT_VERSION.tar.gz "https://github.com/openatx/atx-agent/releases/download/$ATX_AGENT_VERSION/atx-agent_${ATX_AGENT_VERSION}_linux_armv6.tar.gz"
        tar -C vendor/ -xzvf vendor/atx-agent-$ATX_AGENT_VERSION.tar.gz atx-agent
}

download_atx
download_apk
download_stf

echo "Everything is downloaded. ^_^"