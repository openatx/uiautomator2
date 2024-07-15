# QUICK REFENRECE GUIDE

```python
import uiautomator2 as u2

d = u2.connect("--serial-here--") # 只有一个设备也可以省略参数
d = u2.connect() # 一个设备时, read env-var ANDROID_SERIAL

# 信息获取
print(d.info)
print(d.device_info)
width, height = d.window_size()
print(d.wlan_ip)
print(d.serial)

## 截图
d.screenshot() # Pillow.Image.Image格式
d.screenshot().save("current_screen.jpg")

# 获取hierarchy
d.dump_hierarchy() # str

# 设置查找元素等待时间，单位秒
d.implicitly_wait(10)

d.app_current() # 获取前台应用 packageName, activity
d.app_start("io.appium.android.apis") # 启动应用
d.app_start("io.appium.android.apis", stop=True) # 启动应用前停止应用
d.app_stop("io.appium.android.apis") # 停止应用

app = d.session("io.appium.android.apis") # 启动应用并获取session

# session的用途是操作的同时监控应用是否闪退，当闪退时操作，会抛出SessionBrokenError
app.click(10, 20) # 坐标点击

# 无session状态下操作
d.click(10, 20) # 坐标点击
d.long_click(10, 10)
d.double_click(10, 20)

d.swipe(10, 20, 80, 90) # 从(10, 20)滑动到(80, 90)
d.swipe_ext("right") # 整个屏幕右滑动
d.swipe_ext("right", scale=0.9) # 屏幕右滑，滑动距离为屏幕宽度的90%
d.drag(10, 10, 80, 80)

d.press("back") # 模拟点击返回键
d.press("home") # 模拟Home键
d.long_press("volume_up")

d.send_keys("hello world") # 模拟输入，需要光标已经在输入框中才可以
d.clear_text() # 清空输入框

d.screen_on() # wakeUp
d.screen_off() # sleep screen

print(d.orientation) # left|right|natural|upsidedown
d.orientation = 'natural'
d.freeze_rotation(True)

print(d.last_toast) # 获取显示的toast文本
d.clear_toast() # 重置一下

d.open_notification()
d.open_quick_settings()

d.open_url("https://www.baidu.com")
d.keyevent("HOME") # same as: input keyevent HOME

# 执行shell命令
output, exit_code = d.shell("ps -A", timeout=60) # 执行shell命令，获取输出和exitCode
output = d.shell("pwd").output # 这样也可以
exit_code = d.shell("pwd").exit_code # 这样也可以

# Selector操作
sel = d(text="Gmail")
sel.wait()
sel.click()

```

```python
# XPath操作
# 元素操作
d.xpath("立即开户").wait() # 等待元素，最长等10s（默认）
d.xpath("立即开户").wait(timeout=10) # 修改默认等待时间

# 常用配置
d.settings['wait_timeout'] = 20 # 控件查找默认等待时间(默认20s)

d.xpath("立即开户").click() # 包含查找等待+点击操作，匹配text或者description等于立即开户的按钮
d.xpath("//*[@text='私人FM']/../android.widget.ImageView").click()

d.xpath('//*[@text="私人FM"]').get().info # 获取控件信息

for el in d.xpath('//android.widget.EditText').all():
    print("rect:", el.rect) # output tuple: (left_x, top_y, width, height)
    print("bounds:", el.bounds) # output tuple: （left, top, right, bottom)
    print("center:", el.center())
    el.click() # click operation
    print(el.elem) # 输出lxml解析出来的Node

# 监控弹窗(在线程中监控)
d.watcher.when("跳过").click()
d.watcher.start()
```

**欢迎多提意见。更欢迎Pull Request**