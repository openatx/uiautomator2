# uiautomator2
[![Build Status](https://travis-ci.org/openatx/uiautomator2.svg?branch=master)](https://travis-ci.org/openatx/uiautomator2)
[![PyPI](https://img.shields.io/pypi/v/uiautomator2.svg)]()
[![PyPI](https://img.shields.io/pypi/pyversions/uiautomator2.svg)]()

Android Uiautomator2 Python Wrapper
这是一个可以完成Android的UI自动化的python库。**该项目还在火热的开发中**

google提供的uiautomator库功能做起安卓自动化来非常强大，唯独有两个缺点：1. 只能在手机上运行 2. 只能使用java语言。
所以为了能更简单快捷的使用uiautomator，这个项目通过在手机上运行了一个http服务的方法，将uiautomator中的函数开放了出来。然后再将这些http接口，封装成了python库。这里要非常感谢 Xiaocong He ([@xiaocong][])，他将这个想法实现了出来，uiautomator2这个项目则是对原有xiaocong的项目[uiautomator](https://github.com/xiaocong/uiautomator)进行了bug的修改，功能进行了加强。具体有以下

* 修复uiautomator经常性退出的问题
* 代码进行了重构和精简，方便维护
* 增加了脱离数据线运行测试的功能
* 通过[minicap](https://github.com/openstf/minicap)加快截图速度

虽然我说的很简单，但是实现起来用到了很多的技术和技巧，功能非常强，唯独文档有点少。哈哈

# Installation
1. Install python library

    ```bash
    # Since uiautomator2 is still developing, you have to add --pre to install development version
    pip install --pre uiautomator2

    # Or you can install from source
    git clone https://github.com/openatx/uiautomator2
    pip install -e uiautomator2
    ```

    Optional, used in screenshot()
    
    ```bash
    pip install pillow
    ```

2. 安装依赖(apk, atx-agent, minicap)到手机

    电脑连接上一个手机或多个手机, 确保adb已经添加到环境变量中，执行下面的命令会自动安装[uiautomator-apk](https://github.com/openatx/android-uiautomator-server/releases) 以及 [atx-agent](https://github.com/openatx/atx-agent)

    ```bash
    python -m uiautomator2 init
    ```

3. 最后的测试

    Test if install successfully

    ```bash
    $ adb forward tcp:7912 tcp:7912 # 转发手机的7912端口到PC上
    $ adb shell 'echo $(curl -s localhost:7912/version)'
    # expect: 0.0.?
    ```

# Usage 使用指南
下文中我们用`device_ip`这个变量来定义手机的IP，通常来说安装完`atx-agent`的时候会自动提示你手机的IP是多少。

如果手机的WIFI跟电脑不是一个网段的，需要先通过数据线将手机连接到电脑上，使用命令`adb forward tcp:7912 tcp:7912` 将手机上的服务端口7912转发到PC上。这个时候连接地址使用`127.0.0.1`即可。

## 命令行使用
- init: 初始化设备的atx-agent等

    Installation部分已经介绍过，这里就不写了

- install: 通过URL安装应用

    ```bash
    $ python -m uiautomator2 install $device_ip https://example.org/some.apk
    MainThread: 15:37:55,731 downloading 80.4 kB / 770.6 kB
    MainThread: 15:37:56,763 installing 770.6 kB / 770.6 kB
    MainThread: 15:37:58,780 success installed 770.6 kB / 770.6 kB
    ```

- clear-cache: 清空缓存

    ```bash
    $ python -m uiautomator2 clear-cache
    ```

- `app-stop-all`: 停止所有应用

    ```bash
    $ python -m uiautomator2 app-stop-all $device_ip
    ```
## QUICK START
Open python, input with the following code

```python
>>> import uiautomator2 as ut2
>>> d = ut2.connect(device_ip)
>>> print(d.info)
{'currentPackageName': 'com.android.systemui', 'displayHeight': 1920, 'displayRotation': 0, 'displaySizeDpX': 360, 'displaySizeDpY': 640, 'displayWidth': 1080, 'productName': 'surabaya', 'screenOn': False, 'sdkInt': 23, 'naturalOrientation': True}
```

当`device_ip`为空时，会先检查环境变量`ANDROID_DEVICE_IP`,最后才设置成默认值`127.0.0.1`

## 一些常用但是不知道归到什么类里的函数
先中文写着了，国外大佬们先用Google Translate顶着

### 检查并维持uiautomator处于运行状态
```
d.healthcheck()
```

### 连接本地的设备
需要设备曾经使用`python -muiautomator2 init`初始化过

```
d = u2.connect_usb("{Your-Device-Serial}")
```

### 一定时间内，出现则点击
10s内如果出现Skip则点击

```python
clicked = d(text='Skip').click_exists(timeout=10.0)
```

**Notes:** In below examples, we use `d` represent the uiautomator2 connect object

# Table of Contents
**[Basic API Usage](#basic-api-usages)**
  - **[Retrive the device info](#retrive-the-device-info)**
  - **[Key Event Actions of the device](#key-event-actions-of-the-device)**
  - **[Gesture interaction of the device](#gesture-interaction-of-the-device)**
  - **[Screen Actions of the device](#screen-actions-of-the-device)**
  - **[Push file into device](#push-file-into-device)**

**[App management](#app-management)**
  - **[App install](#app-install)**

**[Watcher introduction](#watcher)**

**[Selector](#selector)**
  - **[Click settings](#click-settings)**
  - **[Child and sibling UI object](#child-and-sibling-ui-object)**
  - **[Get the selected ui object status and its information](#get-the-selected-ui-object-status-and-its-information)**
  - **[Perform the click action on the seleted ui object](#perform-the-click-action-on-the-seleted-ui-object)**

**[Contributors](#contributors)**

**[LICENSE](#license)**

**TODO**

## Basic API Usages
This part show the normal actions of the device through some simple examples

### Retrive the device info

```python
d.info
```

Below is a possible result:

```
{ 
    u'displayRotation': 0,
    u'displaySizeDpY': 640,
    u'displaySizeDpX': 360,
    u'currentPackageName': u'com.android.launcher',
    u'productName': u'takju',
    u'displayWidth': 720,
    u'sdkInt': 18,
    u'displayHeight': 1184,
    u'naturalOrientation': True
}
```

### Key Event Actions of the device

* Tun on/off screen

    ```python
    d.screen_on() # turn on screen
    d.screen_off() # turn off screen
    ```

* Get screen on/off status

    ```python
    d.info.get('screenOn') # require android >= 4.4
    ```

* Press hard/soft key

    ```python
    d.press("home") # press home key
    d.press("back") # the normal way to press back key
    d.press(0x07, 0x02) # press keycode 0x07('0') with META ALT(0x02)
    ```

* Next keys are currently supported:

    - home
    - back
    - left
    - right
    - up
    - down
    - center
    - menu
    - search
    - enter
    - delete ( or del)
    - recent (recent apps)
    - volume_up
    - volume_down
    - volume_mute
    - camera
    - power

You can find all key code definitions at [Android KeyEvnet](https://developer.android.com/reference/android/view/KeyEvent.html)

* Unlock screen

    ```python
    d.unlock()
    # 1. launch activity: com.github.uiautomator.ACTION_IDENTIFY
    # 2. press "home"
    ```

### Gesture interaction of the device
* Click the screen

    ```python
    d.click(x, y)
    ```

* Long click the screen

    ```python
    d.long_click(x, y)
    d.long_click(x, y, 0.5) # long click 0.5s (default)
    ```

* Swipe

    ```python
    d.swipe(sx, sy, ex, ey)
    d.swipe(sx, sy, ex, ey, 0.5) # swipe for 0.5s(default)
    ```

* Drag

    ```python
    d.drag(sx, sy, ex, ey)
    d.drag(sx, sy, ex, ey, 0.5) # swipe for 0.5s(default)

Note: click, swipe, drag support percent position. Example:

`d.long_click(0.5, 0.5)` means long click center of screen

### Screen Actions of the device
* Retrieve/Set Orientation

    The possible orientation is:

    -   `natural` or `n`
    -   `left` or `l`
    -   `right` or `r`
    -   `upsidedown` or `u` (can not be set)

    ```python
    # retrieve orientation, it may be "natural" or "left" or "right" or "upsidedown"
    orientation = d.orientation

    # WARNING: not pass testing in my TT-M1
    # set orientation and freeze rotation.
    # notes: "upsidedown" can not be set until Android 4.3.
    d.set_orientation('l') # or "left"
    d.set_orientation("l") # or "left"
    d.set_orientation("r") # or "right"
    d.set_orientation("n") # or "natural"
    ```

* Freeze/Un-Freeze rotation

    ```python
    # freeze rotation
    d.freeze_rotation()
    # un-freeze rotation
    d.freeze_rotation(False)
    ```

* Take screenshot

    ```python
    # take screenshot and save to local file "home.png", can not work until Android 4.2.
    d.screenshot("home.png")
    # get png as raw data
    png_raw = d.screenshot()
    with open('home.png', 'wb') as f:
        f.write(png_raw)
    ```

* Dump Window Hierarchy

    ```python
    # or get the dumped content(unicode) from return.
    xml = d.dump_hierarchy()
    ```

* Open notification or quick settings

    ```python
    d.open_notification()
    d.open_quick_settings()
    ```

### Push file into device
```python
# push into a folder
d.push("foo.txt", "/sdcard/")
# push and rename
d.push("foo.txt", "/sdcard/bar.txt")
# push fileobj
with open("foo.txt", 'rb') as f:
    d.push(f, "/sdcard/")
# push and change file mode
d.push("foo.sh", "/data/local/tmp/", mode=0o755)
```

### App management
Include app install, launch and stop

#### App install
Only support install from url for now.

```python
d.app_install('http://some-domain.com/some.apk')
```

#### App launch
```python
d.app_start("com.example.hello_world") # start with package name
```

#### App stop
```python
# perform am force-stop
d.app_stop("com.example.hello_world") 
# perform pm clear
d.app_clear('com.example.hello_world')
```

#### App stop all the runnings
```python
# stop all
d.app_stop_all()
# stop all app except com.examples.demo
d.app_stop_all(excludes=['com.examples.demo'])
```

### Selector

Selector is to identify specific ui object in current window.

```python
# To seleted the object ,text is 'Clock' and its className is 'android.widget.TextView'
d(text='Clock', className='android.widget.TextView')
```

#### Click settings
```python
# set delay 1.5s after each UI click and click
d.set_click_post_delay(1.5)
```

#### Child and sibling UI object
* child

    ```python
    # get the child or grandchild
    d(className="android.widget.ListView").child(text="Bluetooth")
    ```

* sibling

    ```python
    # get sibling or child of sibling
    d(text="Google").sibling(className="android.widget.ImageView")
    ```

Selector supports below parameters. Refer to [UiSelector java doc](http://developer.android.com/tools/help/uiautomator/UiSelector.html) for detailed information.

*  `text`, `textContains`, `textMatches`, `textStartsWith`
*  `className`, `classNameMatches`
*  `description`, `descriptionContains`, `descriptionMatches`, `descriptionStartsWith`
*  `checkable`, `checked`, `clickable`, `longClickable`
*  `scrollable`, `enabled`,`focusable`, `focused`, `selected`
*  `packageName`, `packageNameMatches`
*  `resourceId`, `resourceIdMatches`
*  `index`, `instance`

#### Get the selected ui object status and its information
* Check if the specific ui object exists

    ```python
    d(text="Settings").exists # True if exists, else False
    d.exists(text="Settings") # alias of above property.
    ```

* Retrieve the info of the specific ui object

    ```python
    d(text="Settings").info
    ```

    Below is a possible result:

    ```
    { u'contentDescription': u'',
    u'checked': False,
    u'scrollable': False,
    u'text': u'Settings',
    u'packageName': u'com.android.launcher',
    u'selected': False,
    u'enabled': True,
    u'bounds': {u'top': 385,
                u'right': 360,
                u'bottom': 585,
                u'left': 200},
    u'className': u'android.widget.TextView',
    u'focused': False,
    u'focusable': True,
    u'clickable': True,
    u'chileCount': 0,
    u'longClickable': True,
    u'visibleBounds': {u'top': 385,
                        u'right': 360,
                        u'bottom': 585,
                        u'left': 200},
    u'checkable': False
    }
    ```
* Set/Clear text of editable field

    ```python
    d(text="Settings").clear_text()  # clear the text
    d(text="Settings").set_text("My text...")  # set the text
    ```

#### Perform the click action on the seleted ui object
* Perform click on the specific ui object

    ```python
    # click on the center of the specific ui object
    d(text="Settings").click()
    # wait element show for 10 seconds(Default)
    d(text="Settings").click(timeout=10)
    # alias of click
    # short name for quick type with keyboard
    d(text="Settings").tap()
    # wait element show for 0 seconds
    d(text="Settings").tap_nowait()
    ```

* Perform long click on the specific ui object

    ```python
    # long click on the center of the specific ui object
    d(text="Settings").long_click()
    ```

#### Gesture action for the specific ui object
* Drag the ui object to another point or ui object 

    ```python
    # notes : drag can not be set until Android 4.3.
    # drag the ui object to point (x, y)
    d(text="Settings").drag_to(x, y, duration=0.5)
    # drag the ui object to another ui object(center)
    d(text="Settings").drag_to(text="Clock", duration=0.25)
    ```

* Wait until the specific ui appears or gone
    
    ```python
    # wait until the ui object appears
    d(text="Settings").wait(timeout=3.0) # return bool
    # wait until the ui object gone
    d(text="Settings").wait_gone(timeout=1.0)
    ```

    Default timeout is 10s

### Watcher

You can register [watcher](http://developer.android.com/tools/help/uiautomator/UiWatcher.html) to perform some actions when a selector can not find a match.


* Register Watcher

  When a selector can not find a match, uiautomator will run all registered watchers.

  - Click target when conditions match

  ```python
  d.watcher("AUTO_FC_WHEN_ANR").when(text="ANR").when(text="Wait") \
                               .click(text="Force Close")
  # d.watcher(name) ## creates a new named watcher.
  #  .when(condition)  ## the UiSelector condition of the watcher.
  #  .click(target)  ## perform click action on the target UiSelector.
  ```

  - Press key when conditions match

  ```python
  d.watcher("AUTO_FC_WHEN_ANR").when(text="ANR").when(text="Wait") \
                               .press("back", "home")
  # d.watcher(name) ## creates a new named watcher.
  #  .when(condition)  ## the UiSelector condition of the watcher.
  #  .press(<keyname>, ..., <keyname>.()  ## press keys one by one in sequence.
  ```

* Check if the named watcher triggered

  A watcher is triggered, which means the watcher was run and all its conditions matched.

  ```python
  d.watcher("watcher_name").triggered
  # true in case of the specified watcher triggered, else false
  ```

* Remove named watcher

  ```python
  # remove the watcher
  d.watcher("watcher_name").remove()
  ```

* List all watchers

  ```python
  d.watchers
  # a list of all registered wachers' names
  ```

* Check if there is any watcher triggered

  ```python
  d.watchers.triggered
  #  true in case of any watcher triggered
  ```

* Reset all triggered watchers

  ```python
  # reset all triggered watchers, after that, d.watchers.triggered will be false.
  d.watchers.reset()
  ```

* Remvoe watchers

  ```python
  # remove all registered watchers
  d.watchers.remove()
  # remove the named watcher, same as d.watcher("watcher_name").remove()
  d.watchers.remove("watcher_name")
  ```

* Force to run all watchers

  ```python
  # force to run all registered watchers
  d.watchers.run()
  ```

另外文档还是有很多没有写，推荐直接去看源码[__init__.py](uiautomato2/__init__.py)

## 测试方法
```bash
$ adb forward tcp:9008 tcp:9008
$ curl -d '{"jsonrpc":"2.0","method":"deviceInfo","id":1}' localhost:9008/jsonrpc/0
# expect JSON output
```

## Uiautomator与Uiautomator2的区别
1. api不同但也差不多
2. Uiautomator2是安卓项目，而Uiautomator是java项目
3. Uiautomator2可以输入中文，而Uiautomator的java工程需借助utf7输入法才能输入中文
4. Uiautomator2必须明确EditText框才能向里面输入文字，Uiautomator直接指定父类也可以在子类中输入文字
5. Uiautomator2获取控件速度快写，而Uiautomator获取速度慢一些;

# ABOUT
项目重构自 <https://github.com/openatx/atx-uiautomator>

# 依赖项目
- uiautomator守护程序 <https://github.com/openatx/atx-agent>
- uiautomator jsonrpc server<https://github.com/openatx/android-uiautomator-server/>

# Contributors
- codeskyblue ([@codeskyblue][])
- Xiaocong He ([@xiaocong][])
- Yuanyuan Zou ([@yuanyuan][])
- Qian Jin ([@QianJin2013][])
- Xu Jingjie ([@xiscoxu][])
- Xia Mingyuan ([@mingyuan-xia][])
- Artem Iglikov, Google Inc. ([@artikz][])

[@codeskyblue]: https://github.com/codeskyblue
[@xiaocong]: https://github.com/xiaocong
[@yuanyuan]: https://github.com/yuanyuanzou
[@QianJin2013]: https://github.com/QianJin2013
[@xiscoxu]: https://github.com/xiscoxu
[@mingyuan-xia]: https://github.com/mingyuan-xia
[@artikz]: https://github.com/artikz

# LICENSE
Under [MIT](LICENSE)