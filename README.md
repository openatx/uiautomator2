# uiautomator2
Android Uiautomator2 Python Wrapper

暂时先中文，以后再英文

# Installation
git clone this repo and run `pip install -e .`

# Usage 使用指南
```python
import uiautomator2 as ut2

d = ut2.connect('http://10.0.0.1')
with d.session('com.example.hello_world') as s:
    s(text='Clock').tap()
    assert s(resourceId='Time').value == '00:00'
```

## 其他常见用法

查看系统信息
```python
>>> d.info
{
    "displayRotation": 1,
    "displaySizeDpY": 360,
    "displaySizeDpX": 640,
    "screenOn": true,
    "currentPackageName": "com.netease.index",
    "productName": "surabaya",
    "displayWidth": 1920,
    "sdkInt": 23,
    "displayHeight": 1080,
    "naturalOrientation": false
}
```

元素操作, 默认会等待10s，如果没有找到会抛出`UiObjectNotFoundError`
```python
>>> s(text="Game").tap()
# 选择相邻元素点击
>>> s(text="Game").sibling(className="android.widget.ImageView").click()
```

dump xml格式的hierarchy

```python
d.dump_hierarchy()
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

# LICENSE
Under [MIT](LICENSE)