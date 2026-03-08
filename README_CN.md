# uiautomator2

[![PyPI](https://img.shields.io/pypi/v/uiautomator2.svg)](https://pypi.python.org/pypi/uiautomator2)
![PyPI](https://img.shields.io/pypi/pyversions/uiautomator2.svg)
[![codecov](https://codecov.io/gh/openatx/uiautomator2/graph/badge.svg?token=d0ZLkqorBu)](https://codecov.io/gh/openatx/uiautomator2)

[📖 Read the English version](README.md)

一个简单、好用、稳定的Android自动化的库

## 工作原理
本框架主要包含两个部分:

1. 手机端: 运行一个基于UiAutomator的HTTP服务，提供Android自动化的各种接口
2. Python客户端: 通过HTTP协议与手机端通信，调用UiAutomator的各种功能

简单来说就是把Android自动化的能力通过HTTP接口的方式暴露给Python使用。这种设计使得Python端的代码编写更加简单直观。

> 还在用2.x.x版本的用户，可以先看一下[2to3](docs/2to3.md) 再决定是否要升级3.x.x （强烈建议升级）

## 交流群

- QQ交流群: 1群:815453846 2群:943964182
- Discord: <https://discord.gg/PbJhnZJKDd>

# 依赖
- Android版本 4.4+
- Python 3.8+

# 安装

```sh
pip install uiautomator2

# 检查是否安装成功，正常情况下会输出库的版本好
uiautomator2 version
# or: python -m uiautomator2 version
```

安装元素查看工具（可选，但是强烈推荐）

> 更详细的使用说明参考: https://github.com/codeskyblue/uiautodev QQ:536481989


```sh
pip install uiautodev

# 命令行启动后会自动打开浏览器
uiautodev
# or: python -m uiautodev
```

代替品: uiautomatorviewer, Appium Inspector

# 快速入门

准备一台开启了`开发者选项`的安卓手机，连接上电脑，确保执行`adb devices`可以看到连接上的设备。

打开python交互窗口。然后将下面的命令输入到窗口中。

```python
import uiautomator2 as u2

d = u2.connect() # 连接多台设备需要指定设备序列号
print(d.info)
# 期望输出
# {'currentPackageName': 'net.oneplus.launcher', 'displayHeight': 1920, 'displayRotation': 0, 'displaySizeDpX': 411, 'displaySizeDpY': 731, 'displayWidth': 1080, 'productName': 'OnePlus5', 'screenOn': True, 'sdkInt': 27, 'naturalOrientation': True}
```

脚本例子

```python
import uiautomator2 as u2

d = u2.connect('Q5S5T19611004599')
d.app_start('tv.danmaku.bili', stop=True) # 启动Bilibili
d.wait_activity('.MainActivityV2')
d.sleep(5) # 等待开屏广告消失
d.xpath('//*[@text="我的"]').click()
# 获取粉丝数量
fans_count = d.xpath('//*[@resource-id="tv.danmaku.bili:id/fans_count"]').text
print(f"粉丝数量: {fans_count}")
```

# 使用文档

## 连接设备

方法1: 使用设备序列号链接设备 例如序列号. `Q5S5T19611004599` (seen from `adb devices`)

```python
import uiautomator2 as u2

d = u2.connect('Q5S5T19611004599') # alias for u2.connect_usb('123456f')
print(d.info)
```

方法2: 序列号可以通过环境变量传递 `ANDROID_SERIAL`


```python
# export ANDROID_SERIAL=Q5S5T19611004599
d = u2.connect()
```

方法3: 通过transport_id指定设备

```sh
$ adb devices -l
Q5S5T19611004599       device 0-1.2.2 product:ELE-AL00 model:ELE_AL00 device:HWELE transport_id:6
```

这里可以看到transport_id:6

> 也可以通过 adbutils.adb.list(extended=True)获取所有连接的transport_id
> 参考 https://github.com/openatx/adbutils

```python
import adbutils # 需要版本>=2.9.1
import uiautomator2 as u2
dev = adbutils.device(transport_id=6)
d = u2.connect(dev)
```

## 通过XPath操作元素

什么是XPath：

XPath 是一种在 XML 或 HTML 文档中定位内容的查询语言。它使用简单的语法规则建立从根节点到所需元素的路径。

基本语法：
- `/` - 从根节点开始选择
- `//` - 从当前节点开始选择任意位置
- `.` - 选择当前节点 
- `..` - 选择当前节点的父节点
- `@` - 选择属性
- `[]` - 谓语表达式，用于过滤条件

通过[UIAutoDev](https://uiauto.dev)可以快速的生成XPath

常用用法

```python
d.xpath('//*[@text="私人FM"]').click()

# 语法糖
d.xpath('@personal-fm') # 等价于 d.xpath('//*[@resource-id="personal-fm"]')

sl = d.xpath("@com.example:id/home_searchedit") # sl为XPathSelector对象
sl.click()
sl.click(timeout=10) # 指定超时时间, 找不到抛出异常 XPathElementNotFoundError
sl.click_exists() # 存在即点击，返回是否点击成功
sl.click_exists(timeout=10) # 等待最多10s钟

# 等到对应的元素出现，返回XMLElement
# 默认的等待时间是10s
el = sl.wait()
el = sl.wait(timeout=15) # 等待15s, 没有找到会返回None

# 等待元素消失
sl.wait_gone()
sl.wait_gone(timeout=15) 

# 跟wait用法类似，区别是如果没找到直接抛出 XPathElementNotFoundError 异常
el = sl.get() 
el = sl.get(timeout=15)

sl.get_text() # 获取组件名
sl.set_text("") # 清空输入框
sl.set_text("hello world") # 输入框输入 hello world
```

更多用法参考 [XPath接口文档](XPATH_CN.md)

## 插件

- webview: https://github.com/YuYoungG/uiautomator2-webview

为了保持项目的简洁与可扩展性，后续插件将以第三方库的形式接入。

## 通过UiAutomator接口操作元素

### 元素等待时长
设置元素查找等待时间（默认20s）

```python
d.implicitly_wait(10.0) # 也可以通过d.settings['wait_timeout'] = 10.0 修改
print("wait timeout", d.implicitly_wait()) # get default implicit wait

# 如果Settings 10s没有出现就抛出异常 UiObjectNotFoundError
d(text="Settings").click() 
```

等待时长影响如下函数 `click`, `long_click`, `drag_to`, `get_text`, `set_text`, `clear_text`
 

### 获取设备信息

通过UiAutomator获取到的信息

```python
d.info
# Output
{'currentPackageName': 'com.android.systemui',
 'displayHeight': 1560,
 'displayRotation': 0,
 'displaySizeDpX': 360,
 'displaySizeDpY': 780,
 'displayWidth': 720,
 'naturalOrientation': True,
 'productName': 'ELE-AL00',
 'screenOn': True,
 'sdkInt': 29}
```

获取设备信息（基于adb shell getprop命令）

```python
print(d.device_info)
# output
{'arch': 'arm64-v8a',
 'brand': 'google',
 'model': 'sdk_gphone64_arm64',
 'sdk': 34,
 'serial': 'EMULATOR34X1X19X0',
 'version': 14}
```

获取屏幕物理尺寸 （依赖adb shell wm size)

```python
print(d.window_size())
# device upright output example: (1080, 1920)
# device horizontal output example: (1920, 1080)
```

获取当前App (依赖adb shell)

```python
print(d.app_current())
# Output example 1: {'activity': '.Client', 'package': 'com.netease.example', 'pid': 23710}
# Output example 2: {'activity': '.Client', 'package': 'com.netease.example'}
# Output example 3: {'activity': None, 'package': None}
```

等待Activity （依赖adb shell）

```python
d.wait_activity(".ApiDemos", timeout=10) # default timeout 10.0 seconds
# Output: true of false
```

获取设备序列号

```python
print(d.serial)
# output example: 74aAEDR428Z9
```

获取设备WLAN IP (依赖adb shell)

```python
print(d.wlan_ip)
# output example: 10.0.0.1 or None
```

### 剪贴板
设置粘贴板内容或获取内容

* clipboard/set_clipboard

    ```python
    # 设置剪贴板
    d.clipboard = 'hello-world'
    # or
    d.set_clipboard('hello-world', 'label')

    # 获取剪贴板
    # 依赖输入法(com.github.uiautomator/.AdbKeyboard)
    d.set_input_ime()
    print(d.clipboard)
    ```

### Key Events

* Turn on/off screen

    ```python
    d.screen_on() # turn on the screen
    d.screen_off() # turn off the screen
    ```

* Get current screen status

    ```python
    d.info.get('screenOn')
    ```

* Press hard/soft key

    ```python
    d.press("home") # press the home key, with key name
    d.press("back") # press the back key, with key name
    d.press(0x07, 0x02) # press keycode 0x07('0') with META ALT(0x02)
    ```

* These key names are currently supported:

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
    # This is equivalent to
    # 1. press("power")
    # 2. swipe from left-bottom to right-top
    ```

### Gesture interaction with the device
* Click on the screen

    ```python
    d.click(x, y)
    ```

* Double click

    ```python
    d.double_click(x, y)
    d.double_click(x, y, 0.1) # default duration between two click is 0.1s
    ```

* Long click on the screen

    ```python
    d.long_click(x, y)
    d.long_click(x, y, 0.5) # long click 0.5s (default)
    ```

* Swipe

    ```python
    d.swipe(sx, sy, ex, ey)
    d.swipe(sx, sy, ex, ey, 0.5) # swipe for 0.5s(default)
    ```

* SwipeExt 扩展功能

    ```python
    d.swipe_ext("right") # 手指右滑，4选1 "left", "right", "up", "down"
    d.swipe_ext("right", scale=0.9) # 默认0.9, 滑动距离为屏幕宽度的90%
    d.swipe_ext("right", box=(0, 0, 100, 100)) # 在 (0,0) -> (100, 100) 这个区域做滑动

    # 实践发现上滑或下滑的时候，从中点开始滑动成功率会高一些
    d.swipe_ext("up", scale=0.8) # 代码会vkk

    # 还可以使用Direction作为参数
    from uiautomator2 import Direction
    
    d.swipe_ext(Direction.FORWARD) # 页面下翻, 等价于 d.swipe_ext("up"), 只是更好理解
    d.swipe_ext(Direction.BACKWARD) # 页面上翻
    d.swipe_ext(Direction.HORIZ_FORWARD) # 页面水平右翻
    d.swipe_ext(Direction.HORIZ_BACKWARD) # 页面水平左翻
    ```

* Drag

    ```python
    d.drag(sx, sy, ex, ey)
    d.drag(sx, sy, ex, ey, 0.5) # swipe for 0.5s(default)

* Swipe points

    ```python
    # swipe from point(x0, y0) to point(x1, y1) then to point(x2, y2)
    # time will speed 0.2s bwtween two points
    d.swipe_points([(x0, y0), (x1, y1), (x2, y2)], 0.2))
    ```

    多用于九宫格解锁，提前获取到每个点的相对坐标（这里支持百分比），
    更详细的使用参考这个帖子 [使用u2实现九宫图案解锁](https://testerhome.com/topics/11034)

* Touch and drap (Beta)

    这个接口属于比较底层的原始接口，感觉并不完善，不过凑合能用。注：这个地方并不支持百分比

    ```python
    d.touch.down(10, 10) # 模拟按下
    time.sleep(.01) # down 和 move 之间的延迟，自己控制
    d.touch.move(15, 15) # 模拟移动
    d.touch.up(10, 10) # 模拟抬起
    ```

Note: click, swipe, drag operations support percentage position values. Example:

`d.long_click(0.5, 0.5)` means long click center of screen

### 屏幕相关接口
* Retrieve/Set device orientation

    The possible orientations:

    -   `natural` or `n`
    -   `left` or `l`
    -   `right` or `r`
    -   `upsidedown` or `u` (can not be set)

    ```python
    # retrieve orientation. the output could be "natural" or "left" or "right" or "upsidedown"
    orientation = d.orientation

    # WARNING: not pass testing in my TT-M1
    # set orientation and freeze rotation.
    # notes: setting "upsidedown" requires Android>=4.3.
    d.set_orientation('l') # or "left"
    d.set_orientation("l") # or "left"
    d.set_orientation("r") # or "right"
    d.set_orientation("n") # or "natural"
    ```

* Freeze/Un-freeze rotation

    ```python
    # freeze rotation
    d.freeze_rotation()
    # un-freeze rotation
    d.freeze_rotation(False)
    ```

* Take screenshot

    ```python
    # take screenshot and save to a file on the computer, require Android>=4.2.
    d.screenshot("home.jpg")
    
    # get PIL.Image formatted images. Naturally, you need pillow installed first
    image = d.screenshot() # default format="pillow"
    image.save("home.jpg") # or home.png. Currently, only png and jpg are supported

    # get opencv formatted images. Naturally, you need numpy and cv2 installed first
    import cv2
    image = d.screenshot(format='opencv')
    cv2.imwrite('home.jpg', image)

    # get raw jpeg data
    imagebin = d.screenshot(format='raw')
    open("some.jpg", "wb").write(imagebin)
    ```

* Dump UI hierarchy

    ```python
    # get the UI hierarchy dump content
    xml = d.dump_hierarchy()

    # compressed=True: include not import nodes
    # pretty: format xml
    # max_depth: limit xml depth, default 50
    xml = d.dump_hierarchy(compressed=False, pretty=False, max_depth=50)
    ```

* Open notification or quick settings

    ```python
    d.open_notification()
    d.open_quick_settings()
    ```

### Selector

Selector is a handy mechanism to identify a specific UI object in the current window.

```python
# Select the object with text 'Clock' and its className is 'android.widget.TextView'
d(text='Clock', className='android.widget.TextView')
```

Selector supports below parameters. Refer to [UiSelector Java doc](http://developer.android.com/tools/help/uiautomator/UiSelector.html) for detailed information.

*  `text`, `textContains`, `textMatches`, `textStartsWith`
*  `className`, `classNameMatches`
*  `description`, `descriptionContains`, `descriptionMatches`, `descriptionStartsWith`
*  `checkable`, `checked`, `clickable`, `longClickable`
*  `scrollable`, `enabled`,`focusable`, `focused`, `selected`
*  `packageName`, `packageNameMatches`
*  `resourceId`, `resourceIdMatches`
*  `index`, `instance`

#### Children and siblings

* children

  ```python
  # get the children or grandchildren
  d(className="android.widget.ListView").child(text="Bluetooth")
  ```

* siblings

  ```python
  # get siblings
  d(text="Google").sibling(className="android.widget.ImageView")
  ```

* children by text or description or instance

  ```python
  # get the child matching the condition className="android.widget.LinearLayout"
  # and also its children or grandchildren with text "Bluetooth"
  d(className="android.widget.ListView", resourceId="android:id/list") \
   .child_by_text("Bluetooth", className="android.widget.LinearLayout")

  # get children by allowing scroll search
  d(className="android.widget.ListView", resourceId="android:id/list") \
   .child_by_text(
      "Bluetooth",
      allow_scroll_search=True,
      className="android.widget.LinearLayout"
    )
  ```

  - `child_by_description` is to find children whose grandchildren have
      the specified description, other parameters being similar to `child_by_text`.

  - `child_by_instance` is to find children with has a child UI element anywhere
      within its sub hierarchy that is at the instance specified. It is performed
      on visible views **without scrolling**.

  See below links for detailed information:

  -   [UiScrollable](http://developer.android.com/tools/help/uiautomator/UiScrollable.html), `getChildByDescription`, `getChildByText`, `getChildByInstance`
  -   [UiCollection](http://developer.android.com/tools/help/uiautomator/UiCollection.html), `getChildByDescription`, `getChildByText`, `getChildByInstance`

  Above methods support chained invoking, e.g. for below hierarchy

  ```xml
  <node index="0" text="" resource-id="android:id/list" class="android.widget.ListView" ...>
    <node index="0" text="WIRELESS & NETWORKS" resource-id="" class="android.widget.TextView" .../>
    <node index="1" text="" resource-id="" class="android.widget.LinearLayout" ...>
      <node index="1" text="" resource-id="" class="android.widget.RelativeLayout" ...>
        <node index="0" text="Wi‑Fi" resource-id="android:id/title" class="android.widget.TextView" .../>
      </node>
      <node index="2" text="ON" resource-id="com.android.settings:id/switchWidget" class="android.widget.Switch" .../>
    </node>
    ...
  </node>
  ```
  ![settings](https://raw.github.com/xiaocong/uiautomator/master/docs/img/settings.png)

  To click the switch widget right to the TextView 'Wi‑Fi', we need to select the switch widgets first. However, according to the UI hierarchy, more than one switch widgets exist and have almost the same properties. Selecting by className will not work. Alternatively, the below selecting strategy would help:

  ```python
  d(className="android.widget.ListView", resourceId="android:id/list") \
    .child_by_text("Wi‑Fi", className="android.widget.LinearLayout") \
    .child(className="android.widget.Switch") \
    .click()
  ```

* relative positioning

  Also we can use the relative positioning methods to get the view: `left`, `right`, `top`, `bottom`.

  -   `d(A).left(B)`, selects B on the left side of A.
  -   `d(A).right(B)`, selects B on the right side of A.
  -   `d(A).up(B)`, selects B above A.
  -   `d(A).down(B)`, selects B under A.

  So for above cases, we can alternatively select it with:

  ```python
  ## select "switch" on the right side of "Wi‑Fi"
  d(text="Wi‑Fi").right(className="android.widget.Switch").click()
  ```

* Multiple instances

  Sometimes the screen may contain multiple views with the same properties, e.g. text, then you will
  have to use the "instance" property in the selector to pick one of qualifying instances, like below:

  ```python
  d(text="Add new", instance=0)  # which means the first instance with text "Add new"
  ```

  In addition, uiautomator2 provides a list-like API (similar to jQuery):

  ```python
  # get the count of views with text "Add new" on current screen
  d(text="Add new").count

  # same as count property
  len(d(text="Add new"))

  # get the instance via index
  d(text="Add new")[0]
  d(text="Add new")[1]
  ...

  # iterator
  for view in d(text="Add new"):
      view.info  # ...
  ```

  **Notes**: when using selectors in a code block that walk through the result list, you must ensure that the UI elements on the screen
  keep unchanged. Otherwise, when Element-Not-Found error could occur when iterating through the list.

#### Get the selected ui object status and its information
* Check if the specific UI object exists

    ```python
    d(text="Settings").exists # True if exists, else False
    d.exists(text="Settings") # alias of above property.

    # advanced usage
    d(text="Settings").exists(timeout=3) # wait Settings appear in 3s, same as .wait(3)
    ```

* Retrieve the info of the specific UI object

    ```python
    d(text="Settings").info
    ```

    Below is a possible output:

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

* Get/Set/Clear text of an editable field (e.g., EditText widgets)

    ```python
    d(text="Settings").get_text()  # get widget text
    d(text="Settings").set_text("My text...")  # set the text
    d(text="Settings").clear_text()  # clear the text
    ```

* Get Widget center point

    ```python
    x, y = d(text="Settings").center()
    # x, y = d(text="Settings").center(offset=(0, 0)) # left-top x, y
    ```
    
* Take screenshot of widget

    ```python
    im = d(text="Settings").screenshot()
    im.save("settings.jpg")
    ```

#### Perform the click action on the selected UI object
* Perform click on the specific   object

    ```python
    # click on the center of the specific ui object
    d(text="Settings").click()
    
    # wait element to appear for at most 10 seconds and then click
    d(text="Settings").click(timeout=10)
    
    # click with offset(x_offset, y_offset)
    # click_x = x_offset * width + x_left_top
    # click_y = y_offset * height + y_left_top
    d(text="Settings").click(offset=(0.5, 0.5)) # Default center
    d(text="Settings").click(offset=(0, 0)) # click left-top
    d(text="Settings").click(offset=(1, 1)) # click right-bottom

    # click when exists in 10s, default timeout 0s
    clicked = d(text='Skip').click_exists(timeout=10.0)
    
    # click until element gone, return bool
    is_gone = d(text="Skip").click_gone(maxretry=10, interval=1.0) # maxretry default 10, interval default 1.0
    ```

* Perform long click on the specific UI object

    ```python
    # long click on the center of the specific UI object
    d(text="Settings").long_click()
    ```

#### Gesture actions for the specific UI object
* Drag the UI object towards another point or another UI object 

    ```python
    # notes : drag can not be used for Android<4.3.
    # drag the UI object to a screen point (x, y), in 0.5 second
    d(text="Settings").drag_to(x, y, duration=0.5)
    # drag the UI object to (the center position of) another UI object, in 0.25 second
    d(text="Settings").drag_to(text="Clock", duration=0.25)
    ```

* Swipe from the center of the UI object to its edge

    Swipe supports 4 directions:

    - left
    - right
    - top
    - bottom

    ```python
    d(text="Settings").swipe("right")
    d(text="Settings").swipe("left", steps=10)
    d(text="Settings").swipe("up", steps=20) # 1 steps is about 5ms, so 20 steps is about 0.1s
    d(text="Settings").swipe("down", steps=20)
    ```

* Two-point gesture from one point to another

  ```python
  d(text="Settings").gesture((sx1, sy1), (sx2, sy2), (ex1, ey1), (ex2, ey2))
  ```

* Two-point gesture on the specific UI object

  Supports two gestures:
  - `In`, from edge to center
  - `Out`, from center to edge

  ```python
  # notes : pinch can not be set until Android 4.3.
  # from edge to center. here is "In" not "in"
  d(text="Settings").pinch_in(percent=100, steps=10)
  # from center to edge
  d(text="Settings").pinch_out()
  ```

* Wait until the specific UI appears or disappears
    
    ```python
    # wait until the ui object appears
    d(text="Settings").wait(timeout=3.0) # return bool
    # wait until the ui object gone
    d(text="Settings").wait_gone(timeout=1.0)
    ```

    The default timeout is 20s. see **global settings** for more details

* Perform fling on the specific ui object(scrollable)

  Possible properties:
  - `horiz` or `vert`
  - `forward` or `backward` or `toBeginning` or `toEnd`

  ```python
  # fling forward(default) vertically(default) 
  d(scrollable=True).fling()
  # fling forward horizontally
  d(scrollable=True).fling.horiz.forward()
  # fling backward vertically
  d(scrollable=True).fling.vert.backward()
  # fling to beginning horizontally
  d(scrollable=True).fling.horiz.toBeginning(max_swipes=1000)
  # fling to end vertically
  d(scrollable=True).fling.toEnd()
  ```

* Perform scroll on the specific ui object(scrollable)

  Possible properties:
  - `horiz` or `vert`
  - `forward` or `backward` or `toBeginning` or `toEnd`, or `to`

  ```python
  # scroll forward(default) vertically(default)
  d(scrollable=True).scroll(steps=10)
  # scroll forward horizontally
  d(scrollable=True).scroll.horiz.forward(steps=100)
  # scroll backward vertically
  d(scrollable=True).scroll.vert.backward()
  # scroll to beginning horizontally
  d(scrollable=True).scroll.horiz.toBeginning(steps=100, max_swipes=1000)
  # scroll to end vertically
  d(scrollable=True).scroll.toEnd()
  # scroll forward vertically until specific ui object appears
  d(scrollable=True).scroll.to(text="Security")
  ```

### 输入法

> 输入法APK: https://github.com/openatx/android-uiautomator-server/releases

```python
d.send_keys("你好123abcEFG")
d.send_keys("你好123abcEFG", clear=True)

d.clear_text() # 清除输入框所有内容

d.send_action() # 根据输入框的需求，自动执行回车、搜索等指令, Added in version 3.1
# 也可以指定发送的输入法action, eg: d.send_action("search") 支持 go, search, send, next, done, previous

d.hide_keyboard() # 隐藏输入法
```

输入法send_keys的时候，优先使用剪贴板进行输入。如果剪贴板接口无法使用，会安装辅助输入法进行输入。


```python
print(d.current_ime()) # 获取当前输入法ID
```

> 更多参考: [IME_ACTION_CODE](https://developer.android.com/reference/android/view/inputmethod/EditorInfo)

### Toast
```python
print(d.last_toast) # get last toast, if not toast return None
d.clear_toast()
```

### WatchContext (废弃)
注: 这里不是很推荐用这个接口，最好点击元素前检查一下是否有弹窗

目前的这个watch_context是用threading启动的，每2s检查一次
目前还只有click这一种触发操作

```python
with d.watch_context() as ctx:
    # 当同时出现 （立即下载 或 立即更新）和 取消 按钮的时候，点击取消
    ctx.when("^立即(下载|更新)").when("取消").click() 
    ctx.when("同意").click()
    ctx.when("确定").click()
    # 上面三行代码是立即执行完的，不会有什么等待
    
    ctx.wait_stable() # 开启弹窗监控，并等待界面稳定（两个弹窗检查周期内没有弹窗代表稳定）

    # 使用call函数来触发函数回调
    # call 支持两个参数，d和el，不区分参数位置，可以不传参，如果传参变量名不能写错
    # eg: 当有元素匹配仲夏之夜，点击返回按钮
    ctx.when("仲夏之夜").call(lambda d: d.press("back"))
    ctx.when("确定").call(lambda el: el.click())

    # 其他操作

# 为了方便也可以使用代码中默认的弹窗监控逻辑
# 下面是目前内置的默认逻辑，可以加群at群主，增加新的逻辑，或者直接提pr
    # when("继续使用").click()
    # when("移入管控").when("取消").click()
    # when("^立即(下载|更新)").when("取消").click()
    # when("同意").click()
    # when("^(好的|确定)").click()
with d.watch_context(builtin=True) as ctx:
    # 在已有的基础上增加
    ctx.when("@tb:id/jview_view").when('//*[@content-desc="图片"]').click()

    # 其他脚本逻辑
```

另外一种写法

```python
ctx = d.watch_context()
ctx.when("设置").click()
ctx.wait_stable() # 等待界面不在有弹窗了

ctx.close()
```

### 全局设置

```python
u2.HTTP_TIMEOUT = 60 # 默认值60s, http默认请求超时时间
```

其他的配置，目前已大部分集中到 `d.settings` 中，根据后期的需求配置可能会有增减。

```python
print(d.settings)
{'operation_delay': (0, 0),
 'operation_delay_methods': ['click', 'swipe'],
 'wait_timeout': 20.0}

# 配置点击前延时0.5s，点击后延时1s
d.settings['operation_delay'] = (.5, 1)

# 修改延迟生效的方法
# 其中 double_click, long_click 都对应click
d.settings['operation_delay_methods'] = ['click', 'swipe', 'drag', 'press']
d.settings['wait_timeout'] = 20.0 # 默认控件等待时间（原生操作，xpath插件的等待时间）

d.settings['max_depth'] = 50 # 默认50，限制dump_hierarchy返回的元素层级
```

对于随着版本升级，设置过期的配置时，会提示Deprecated，但是不会抛异常。

```bash
>>> d.settings['click_before_delay'] = 1  
[W 200514 14:55:59 settings:72] d.settings[click_before_delay] deprecated: Use operation_delay instead
```

UiAutomator中的超时设置(隐藏方法)

```python
>> d.jsonrpc.getConfigurator() 
{'actionAcknowledgmentTimeout': 500,
 'keyInjectionDelay': 0,
 'scrollAcknowledgmentTimeout': 200,
 'waitForIdleTimeout': 0,
 'waitForSelectorTimeout': 0}

>> d.jsonrpc.setConfigurator({"waitForIdleTimeout": 100})
{'actionAcknowledgmentTimeout': 500,
 'keyInjectionDelay': 0,
 'scrollAcknowledgmentTimeout': 200,
 'waitForIdleTimeout': 100,
 'waitForSelectorTimeout': 0}
```

为了防止客户端程序响应超时，`waitForIdleTimeout`和`waitForSelectorTimeout`目前已改为`0`

Refs: [Google uiautomator Configurator](https://developer.android.com/reference/android/support/test/uiautomator/Configurator)

## 应用管理
This part showcases how to perform app management

### 安装应用
We only support installing an APK from a URL

```python
d.app_install('http://some-domain.com/some.apk')
```

### 启动应用
```python
# 默认的这种方法是先通过atx-agent解析apk包的mainActivity，然后调用am start -n $package/$activity启动
d.app_start("com.example.hello_world")

# 使用 monkey -p com.example.hello_world -c android.intent.category.LAUNCHER 1 启动
# 这种方法有个副作用，它自动会将手机的旋转锁定给关掉
d.app_start("com.example.hello_world", use_monkey=True) # start with package name

# 通过指定main activity的方式启动应用，等价于调用am start -n com.example.hello_world/.MainActivity
d.app_start("com.example.hello_world", ".MainActivity")
```

### 停止应用

```python
# equivalent to `am force-stop`, thus you could lose data
d.app_stop("com.example.hello_world") 
# equivalent to `pm clear`
d.app_clear('com.example.hello_world')
```

### 停止所有应用
```python
# stop all
d.app_stop_all()
# stop all app except for com.examples.demo
d.app_stop_all(excludes=['com.examples.demo'])
```

### 获取应用信息
```python
d.app_info("com.examples.demo")
# expect output
#{
#    "mainActivity": "com.github.uiautomator.MainActivity",
#    "label": "ATX",
#    "versionName": "1.1.7",
#    "versionCode": 1001007,
#    "size":1760809
#}

# save app icon
img = d.app_icon("com.examples.demo")
img.save("icon.png")
```

### 列出所有运行的应用
```python
d.app_list_running()
# expect output
# ["com.xxxx.xxxx", "com.github.uiautomator", "xxxx"]
```

### 等待应用运行
```python
pid = d.app_wait("com.example.android") # 等待应用运行, return pid(int)
if not pid:
    print("com.example.android is not running")
else:
    print("com.example.android pid is %d" % pid)

d.app_wait("com.example.android", front=True) # 等待应用前台运行
d.app_wait("com.example.android", timeout=20.0) # 最长等待时间20s（默认）
```

### 拉取和推送文件
* push a file to the device

    ```python
    # push to a folder
    d.push("foo.txt", "/sdcard/")
    # push and rename
    d.push("foo.txt", "/sdcard/bar.txt")
    # push fileobj
    with open("foo.txt", 'rb') as f:
        d.push(f, "/sdcard/")
    # push and change file access mode
    d.push("foo.sh", "/data/local/tmp/", mode=0o755)
    ```

* pull a file from the device

    ```python
    d.pull("/sdcard/tmp.txt", "tmp.txt")

    # FileNotFoundError will raise if the file is not found on the device
    d.pull("/sdcard/some-file-not-exists.txt", "tmp.txt")
    ```

### 其他应用操作

```python
# grant all the permissions
d.app_auto_grant_permissions("io.appium.android.apis")

# open scheme
d.open_url("appname://appnamehost")
# same as
# adb shell am start -a android.intent.action.VIEW -d "appname://appnamehost"
```

### Session (Beta)
Session represent an app lifecycle. Can be used to start app, detect app crash.

* Launch and close app

    ```python
    sess = d.session("com.netease.cloudmusic") # start 网易云音乐
    sess.close() # 停止网易云音乐
    sess.restart() # 冷启动网易云音乐
    ```

* Use python `with` to launch and close app

    ```python
    with d.session("com.netease.cloudmusic") as sess:
        sess(text="Play").click()
    ```

* Attach to the running app

    ```python
    # launch app if not running, skip launch if already running
    sess = d.session("com.netease.cloudmusic", attach=True)
    ```

* Detect app crash

    ```python
    # When app is still running
    sess(text="Music").click() # operation goes normal

    # If app crash or quit
    sess(text="Music").click() # raise SessionBrokenError
    # other function calls under session will raise SessionBrokenError too
    ```

    ```python
    # check if session is ok.
    # Warning: function name may change in the future
    sess.running() # True or False
    ```


## 其他接口

### 停止后台HTTP服务
通常情况下Python程序退出了，UiAutomation就退出了。
不过也可以通过接口的方法停止服务

```python
d.stop_uiautomator()
```

### 开启调试
打印出代码背后的HTTP请求信息

```python
>>> d.debug = True
>>> d.info
12:32:47.182 $ curl -X POST -d '{"jsonrpc": "2.0", "id": "b80d3a488580be1f3e9cb3e926175310", "method": "deviceInfo", "params": {}}' 'http://127.0.0.1:54179/jsonrpc/0'
12:32:47.225 Response >>>
{"jsonrpc":"2.0","id":"b80d3a488580be1f3e9cb3e926175310","result":{"currentPackageName":"com.android.mms","displayHeight":1920,"displayRotation":0,"displaySizeDpX":360,"displaySizeDpY":640,"displayWidth":1080,"productName"
:"odin","screenOn":true,"sdkInt":25,"naturalOrientation":true}}
<<< END
```

```python
from uiautomator2 import enable_pretty_logging
enable_pretty_logging()
```

Or

```
logger = logging.getLogger("uiautomator2")
# setup logger
```

## 命令行功能
其中的`$device_ip`代表设备的ip地址

如需指定设备需要传入`--serial` 如 `python3 -m uiautomator2 --serial bff1234 <SubCommand>`, SubCommand为子命令（screenshot, current 等）

> 1.0.3 Added: `python3 -m uiautomator2` equals to `uiautomator2`

- screenshot: 截图

    ```bash
    $ uiautomator2 screenshot screenshot.jpg
    ```

- current: 获取当前包名和activity

    ```bash
    $ uiautomator2 current
    {
        "package": "com.android.browser",
        "activity": "com.uc.browser.InnerUCMobile",
        "pid": 28478
    }
    ```
    
- uninstall： Uninstall app

    ```bash
    $ uiautomator2 uninstall <package-name> # 卸载一个包
    $ uiautomator2 uninstall <package-name-1> <package-name-2> # 卸载多个包
    $ uiautomator2 uninstall --all # 全部卸载
    ```

- stop: Stop app

    ```bash
    $ uiautomator2 stop com.example.app # 停止一个app
    $ uiautomator2 stop --all # 停止所有的app
    ```

- doctor:

    ```bash
    $ uiautomator2 doctor
    [I 2024-04-25 19:53:36,288 __main__:101 pid:15596] uiautomator2 is OK
    ```

## Google UiAutomator 2.0和1.x的区别
https://www.cnblogs.com/insist8089/p/6898181.html

- 新增接口：UiObject2、Until、By、BySelector
- 引入方式：2.0中，com.android.uiautomator.core.* 引入方式被废弃。改为android.support.test.uiautomator
- 构建系统：Maven 和/或 Ant（1.x）；Gradle（2.0）
- 产生的测试包的形式：从zip /jar（1.x） 到 apk（2.0）
- 在本地环境以adb命令运行UIAutomator测试，启动方式的差别：   
  adb shell uiautomator runtest UiTest.jar -c package.name.ClassName（1.x）
  adb shell am instrument -e class com.example.app.MyTest 
  com.example.app.test/android.support.test.runner.AndroidJUnitRunner（2.0）
- 能否使用Android服务及接口？ 1.x~不能；2.0~能。
- og输出？ 使用System.out.print输出流回显至执行端（1.x）； 输出至Logcat（2.0）
- 执行？测试用例无需继承于任何父类，方法名不限，使用注解 Annotation进行（2.0）;  需要继承UiAutomatorTestCase，测试方法需要以test开头(1.x) 


## 依赖项目
- [![PyPI](https://img.shields.io/pypi/v/adbutils.svg?label=adbutils)](https://github.com/openatx/adbutils)
- [![GitHub tag (latest SemVer)](https://img.shields.io/github/tag/openatx/android-uiautomator-server.svg?label=android-uiautomator-server)](https://github.com/openatx/android-uiautomator-server) 已迁移到私有仓库，需要合作开发进QQ群联系群主

# Contributors

[contributors](../../graphs/contributors)

# 其他优秀的项目

- https://github.com/ecnusse/Kea2: 面向安卓的自动化界面遍历与脚本协同测试框架
- https://github.com/atinfo/awesome-test-automation 所有优秀测试框架的集合，包罗万象
- [google/mobly](https://github.com/google/mobly) 谷歌内部的测试框架，虽然我不太懂，但是感觉很好用
- https://github.com/zhangzhao4444/Maxim 基于Uiautomator的monkey
- http://www.sikulix.com/ 基于图像识别的自动化测试框架，非常的老牌
- http://airtest.netease.com/ 本项目的前身，后来被网易广州团队接手并继续优化。实现有一个不错的IDE (archived)

排名有先后，欢迎补充

# LICENSE
[MIT](LICENSE)