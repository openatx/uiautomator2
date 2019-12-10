# QUICK REFENRECE GUIDE

```python
import uiautomator2 as u2

d = u2.connect("--serial-here--") # 只有一个设备也可以省略参数
d = u2.connect() # 一个设备时
d = u2.connect("10.1.2.3") # 通过设备的IP连接(需要在同一局域网且设备上的atx-agent已经安装并启动)

d.app_current() # 获取前台应用 packageName, activity
d.app_start("com.example.app") # 启动应用
d.app_start("com.example.app", stop=True) # 启动应用前停止应用
d.app_stop("com.example.app") # 停止应用

app = d.session("com.example.app") # 启动应用并获取session

# session的用途是操作的同时监控应用是否闪退，当闪退时操作，会抛出SessionBrokenError
app.click(10, 20) # 坐标点击

# 无session状态下操作
d.click(10, 20) # 坐标点击
d.swipe(10, 20, 80, 90) # 从(10, 20)滑动到(80, 90)
d.swipe_ext("right") # 整个屏幕右滑动
d.swipe_ext("right", scale=0.9) # 屏幕右滑，滑动距离为屏幕宽度的90%

d.press("back") # 模拟点击返回键
d.press("home") # 模拟Home键

d.send_keys("hello world") # 模拟输入，需要光标已经在输入框中才可以
d.clear_text() # 清空输入框

# 执行shell命令
output, exit_code = d.shell("ps -A", timeout=60) # 执行shell命令，获取输出和exitCode
output = d.shell("pwd").output # 这样也可以
exit_code = d.shell("pwd").exit_code # 这样也可以

# 元素操作
d.xpath("立即开户").wait() # 等待元素，最长等10s（默认）
d.xpath("立即开户").wait(timeout=10) # 修改默认等待时间

# 常用配置
d.settings['wait_timeout'] = 20 # 控件查找默认等待时间(默认20s)

# xpath操作
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