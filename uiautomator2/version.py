# coding: utf-8
#

import pkg_resources
try:
    __version__ = pkg_resources.get_distribution("uiautomator2").version
except pkg_resources.DistributionNotFound:
    __version__ = "unknown"

# See ChangeLog for details

__apk_version__ = '2.3.3'
# 2.3.3 make float windows smaller
# 2.3.2 merge pull requests # require atx-agent>=0.10.0
# 2.3.1 support minicapagent, rotationagent, minitouchagent
# 2.2.1 fix click bottom(infinitly display) not working bug
# 2.2.0 add MinitouchAgent instead of /data/local/tmp/minitouch
# 2.1.1 add show floatWindow support(pm grant, still have no idea), add TC_TREND analysis
# 2.0.5 add ToastActivity to show toast or just launch and quit
# 2.0.4 fix floatingWindow crash on Sumsung Android 9
# 2.0.3 use android.app.Service instead of android.app.intentService to simpfy logic
# 2.0.2 fix error: AndroidQ Service must be explicit
# 2.0.1 fix AndroidQ support
# 2.0.0 remove runWatchersOnWndowsChange, add setToastListener(bool), add floatWindow
# 1.1.7 fix dumpHierarchy XML charactor error
# 1.1.6 fix android P support
# 1.1.5 waitForExists use UiObject2 method first then fallback to UiObject.waitForExists
# 1.1.4 add ADB_EDITOR_CODE broadcast support, fix bug （toast捕获导致app闪退)
# 1.1.3 use thread to make watchers.watched faster, try to fix input method type multi
# 1.1.2 fix count error when have child && sync watched, to prevent watchers.remove error
# 1.1.1 support toast capture
# 1.1.0 update uiautomator-v18:2.1.2 -> uiautomator-v18:2.1.3 (This version fixed setWaitIdleTimeout not working bug)
# 1.0.14 catch NullException, add gps mock support
# 1.0.13 whatsinput suppoort, but not very well
# 1.0.12 add toast support
# 1.0.11 add auto install support
# 1.0.10 fix service not started bug
# 1.0.9 fix apk version code and version name
# ERR: 1.0.8 bad version number. show ip on notification
# ERR: 1.0.7 bad version number. new input method, some bug fix

__jar_version__ = 'v0.1.6'  # no useless for now.
# v0.1.6 first release version

__atx_agent_version__ = '0.10.0'
# 0.10.0 remove tunnel code, use androidx.test.runner
# 0.9.6 fix security reason for remote control device
# 0.9.5 log support rotate, prevent log too large
# 0.9.4 test travis push to qiniu-cdn
# 0.9.3 fix atx-agent version output too many output
# 0.9.2 fix when /sdcard/atx-agent.log can't create, atx-agent can't start error
# 0.9.1 update /minicap to use apkagent and minicap
# 0.9.0 add /minicap/broadcast api, add service("apkagent")
# 0.8.4 use minicap when sdk less than Android Q
# 0.8.3 use minitouchagent instead of /data/local/tmp/minitouch
# 0.8.2 change am instrument maxRetry from 3 to 1
# 0.8.1 fix --stop can not stop atx-agent error, fix --help format error
# 0.8.0 add /newCommandTimeout api, ref: appium-newCommandTimeout
# 0.7.4 add /finfo/{filepath:.*} api
# 0.7.3 add uiautomator-1.0 support
# 0.7.2 fix stop already stopped uiautomator return status 500 error
# 0.7.1 fix UIAutomation not connected error.
# 0.7.0 add webview support, kill uiautomator if no activity in 3 minutes
# 0.6.2 fix app_info fd leak error, update androidbinary to fix parse apk manifest err
# 0.6.1 make dump_hierarchy more robust, add cpu,mem collect
# 0.6.0 add /dump/hierarchy (works fine even if uiautomator is down)
# 0.5.5 add minitouch reset, /screenshot support download param, fix dns error
# 0.5.4 upgrade atx-agent to fix apk parse mainActivity of com.tmall.wireless
# 0.5.3 try to fix panic in heartbeat
# 0.5.2 fix /session/${pkgname} launch timeout too short error(before was 10s)
# 0.5.1 bad tag, deprecated
# 0.5.0 add /packages/${pkgname}/<info|icon> api
# 0.4.9 update for go1.11
# 0.4.8 add /wlan/ip and /packages REST API for package install
# 0.4.6 fix download dns resolve error (sometimes)
# 0.4.5 add http log, change atx-agent -d into atx-agent server -d
# 0.4.4 this version is gone
# 0.4.3 ignore sigint to prevent atx-agent quit
# 0.4.2 hot fix, close upgrade-self
# 0.4.1 fix app-download time.Timer panic error, use safe-time.Timer instead.
# 0.4.0 add go-daemon lib. use safe-time.Timer to prevent panic error. this will make it run longer
# 0.3.6 support upload zip and unzip, fix minicap rotation error when atx-agent is killed -9
# 0.3.5 hot fix for session
# 0.3.4 fix session() sometimes can not get mainActivity error
# 0.3.3 /shell support timeout
# 0.3.2 fix dns resolve error when network changes
# 0.3.0 use github.com/codeskyblue/heartbeat library instead of websocket, add /whatsinput
# 0.2.1 support occupy /minicap connection
# 0.2.0 add session support
# 0.1.8 fix screenshot always the same image. (BUG in 0.1.7), add /shell/stream add timeout for /shell
# 0.1.7 fix dns resolve error in /install
# 0.1.6 change download logic. auto fix orientation
# 0.1.5 add singlefight for minicap and minitouch, proxy dial-timeout change 30 to 10
# 0.1.4 phone remote control
# 0.1.2 /download support
# 0.1.1 minicap buildin
