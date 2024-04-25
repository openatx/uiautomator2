# 前言

这是一个 uiautimator2 的一个插件，使得 uiautimator2 可以支持通过图像识别来对手机进行操作  
代码集成了开源库: [aircv](https://github.com/NetEaseGame/aircv)


# 注意

1. 只能支持常宽比为 16:9 的手机
2. 截图是以 atx-agent 传过来的图像为基准，图片大小为 800*450  
    因为分辨率小了，会有失真，所以匹配阈值可适当减小（下面有说明）
3. 因为基准图为 800*450 分辨率，area 区域范围不能大于该分辨率（下面有说明）
4. 有时候确实有但是查找不到，或者查找错误，可适当截图截的大一点


# 环境
opencv3.x
1. 安装opencv3 支持py2和py3（测试环境 python2.7.15 和 python3.7.0）
    ```bash
    pip install opencv_python
    ```
2. 安装 websocket
    ```bash
    pip install websocket
    ```
3. 安装 numpy
    ```bash
    pip install numpy
    ```


# 设置

```python
# 启用支持网络下载图片选项
Aircv.support_network = True  # 默认 False，不启用
# 设置 host，支持 http
Aircv.host = "127.0.0.1:8000"
# 请求路径，固定
Aircv.path = "/image_service/download/"
# 示例，图片请求地址
img_url = "http://127.0.0.1:8000/image_service/download/@img1"


# 全局设置操作的超时时间，大于该值时间没有找到图像，会报异常
# timeout 可以在每个函数调用时单独设置
Aircv.timeout = 30

# 全局设置操作的等待时间，该值为在查找到图像后，等待多久再操作（等待UI元素渲染完成）
# 例如点击操作，查找到图像后，等待 1秒，然后才点击
Aircv.wait_before_operation = 1

# 全局设置读取图像的频率，间隔几秒读取一张图像，默认为 2秒
# 手机端的服务会 atx-agent 会以较高频率不断发送 800*450 的图像过来，设置该值限制频率
Aircv.rcv_interval = 2

# 图像查找采用模板匹配的方式
# 该设置定义阈值，大于该阈值，则认为图像相同，即找到图像
# 一般来说大于0.999认为图像一样，阈值默认值为0.95
CVHandler.template_threshold = 0.95

```


# 图像传输

> 一般来说，图像传输会在连接上设备开始传输，程序结束会自动关闭传输
> 如果需要主动关闭，开启图像传输的话，可参考如下
```python
import uiautomator2 as u2
from aircv import Aircv

u2.plugin_register('aircv', Aircv)
d = u2.connect()

# 关闭图像传输
d.ext_aircv.stop_get_scren()

# 开启图像传输
d.ext_aircv.start_get_screen()

```


# 示例

```python
import uiautomator2 as u2
from aircv import Aircv

u2.plugin_register('aircv', Aircv)
d = u2.connect()


# 判断是否存在
d.ext_aircv.exists('tmp.jpg')
d.ext_aircv.exists('tmp.jpg', timeout=60)  # 设置超时时间


# 点击
d.ext_aircv.click('tmp.jpg')
d.ext_aircv.click('tmp.jpg', timeout=60)  # 设置超时时间


# 原图像中指定查找范围，安卓以左上角为原点即（0,0）
# 参数传入左上角坐标和右下角坐标(x1, y1, x2, y2)
d.ext_aircv.click('tmp.jpg', area=(100, 100, 300, 200))


# 长按
d.ext_aircv.long_click('tmp.jpg')
d.ext_aircv.long_click('tmp.jpg', duration=5)  # 设置长按时间
d.ext_aircv.long_click('tmp.jpg', timeout=60)  # 设置超时时间
d.ext_aircv.long_click('tmp.jpg', area=(100, 100, 300, 200))  # 设置查找范围


# 滑动
d.ext_aircv.swipe('tmp1.jpg', 'tmp2.jpg')

#设置持续时间，0.1 表示持续 1秒， 默认 1秒
d.ext_aircv.swipe('tmp1.jpg', 'tmp2.jpg', duration=0.1)
d.ext_aircv.swipe('tmp1.jpg', 'tmp2.jpg', timeout=60)  # 设置超时时间
d.ext_aircv.swipe('tmp1.jpg', 'tmp2.jpg', area=(100, 100, 300, 200))  # 设置查找范围


# 多点滑动
# duration 的值， 0.1 表示持续 1秒， 默认 1秒
img_list = ['tmp1.jpg', 'tmp2.jpg', 'tmp3.jpg']
d.ext_aircv.swipe_points(img_list, duration=0.5, timeout=60)


# 拖动（按住一会再滑动）
d.ext_aircv.drag('tmp1.jpg', 'tmp2.jpg', duration=0.1, timeout=60)
d.ext_aircv.drag('tmp1.jpg', 'tmp2.jpg', area=(100, 100, 300, 200))  # 设置查找范围


# 获取坐标(x, y)（返回查找到图像的中心坐标）
d.ext_aircv.get_point('tmp1.jpg', timeout=60, area=(100, 100, 300, 200)) 

```
