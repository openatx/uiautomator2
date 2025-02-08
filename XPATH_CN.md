# uiautomator2 xpath extension

[📖 Read the English version](XPATH.md)

用这个插件前，要先了解一些XPath知识。
好在网上这方便的资料很多。下面列举一些

- [W3CSchool XPath教程](http://www.w3school.com.cn/xpath/index.asp)
- [XPath tutorial](http://www.zvon.org/xxl/XPathTutorial/)
- [阮一峰的XPath学习笔记](http://www.ruanyifeng.com/blog/2009/07/xpath_path_expressions.html)
- [测试XPath的网站](https://www.freeformatter.com/xpath-tester.html)
- [XPath tester](https://extendsclass.com/xpath-tester.html)

代码并没有完全测试完，可能还有bug，欢迎跟我反馈。

## 工作原理
1. 通过uiautomator2库的`dump_hierarchy`接口，获取到当前的UI界面（一个很丰富的XML）。
2. 然后使用`lxml`库解析，寻找匹配的xpath，然后使用click指令完后操作

>目前发现lxml只支持XPath1.0, 有了解的可以告诉我下怎么支持XPath2.0

**弹窗监控原理**

通过hierarchy可以知道界面上的所有元素信息（包括弹窗和要点击的按钮）。
假设有 `跳过`, `知道了` 这两个弹窗按钮。需要点击的按钮名是 `播放`

1. 获取到当前界面的XML（通过dump_hierarchy函数）
2. 检查有没有`跳过`, `知道了` 这两个按钮，如果有就点击，然后回到第一步
3. 检查有没有`播放`按钮, 有就点击，结束。没有找到在回到第一步，一直执行到查找次数超标。

## 安装方法
```
pip3 install -U uiautomator2
```

## 使用方法

### 简单用法

看下面的这个简单的例子了解下如何使用

```python
import uiautomator2 as u2

def main():
    d = u2.connect()
    d.app_start("com.netease.cloudmusic", stop=True)

    d.xpath('//*[@text="私人FM"]').click()
    
    #
    # 高级用法(元素定位)
    #

    # @开头
    d.xpath('@personal-fm') # 等价于 d.xpath('//*[@resource-id="personal-fm"]')
    # 多个条件定位, 类似于AND
    d.xpath('//android.widget.Button').xpath('//*[@text="私人FM"]')
    
    d.xpath('//*[@text="私人FM"]').parent() # 定位到父元素
    d.xpath('//*[@text="私人FM"]').parent("@android:list") # 定位到符合条件的父元素

	# 包含child的时候，不建议在使用多条件的xpath，因为容易搞混
	d.xpath('@android:id/list').child('/android.widget.TextView').click()
	# 等价于下面这个
	# d.xpath('//*[@resource-id="android:id/list"]/android.widget.TextView').click()
```

>下面的代码为了方便就不写`import`和`main`了，默认存在`d`这个变量

### `XPathSelector`的操作

```python
sl = d.xpath("@com.example:id/home_searchedit") # sl为XPathSelector对象

# 点击
sl.click()
sl.click(timeout=10) # 指定超时时间, 找不到抛出异常 XPathElementNotFoundError
sl.click_exists() # 存在即点击，返回是否点击成功
sl.click_exists(timeout=10) # 等待最多10s钟

sl.match() # 不匹配返回None, 否则返回XMLElement

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

# 修改默认的等待时间为15s
d.xpath.global_set("timeout", 15)
d.xpath.implicitly_wait(15) # 与上一行代码等价 (TODO: Removed)

print(sl.exists) # 返回是否存在 (bool)
sl.get_last_match() # 获取上次匹配的XMLElement

sl.get_text() # 获取组件名
sl.set_text("") # 清空输入框
sl.set_text("hello world") # 输入框输入 hello world

# 遍历所有匹配的元素
for el in d.xpath('//android.widget.EditText').all():
    print("rect:", el.rect) # output tuple: (x, y, width, height)
    print("center:", el.center())
    el.click() # click operation
    print(el.elem) # 输出lxml解析出来的Node
    print(el.text)

# child操作
d.xpath('@android:id/list').child('/android.widget.TextView').click()
等价于 d.xpath('//*[@resource-id="android:id/list"]/android.widget.TextView').all()
```

高级查找语法

> Added in version 3.1

```python
# 查找 text=NFC AND id=android:id/item
(d.xpath("NFC") & d.xpath("@android:id/item")).get()

# 查找 text=NFC OR id=android:id/item
(d.xpath("NFC") | d.xpath("App") | d.xpath("Content")).get()

# 复杂一点也支持
((d.xpath("NFC") | d.xpath("@android:id/item")) & d.xpath("//android.widget.TextView")).get()

### `XMLElement`的操作

```python
# 通过XPathSelector.get() 返回的对象叫做 XMLElement
el = d.xpath("@com.example:id/home_searchedit").get()

lx, ly, width, height = el.rect # 获取左上角坐标和宽高
lx, ly, rx, ry = el.bounds # 左上角与右下角的坐标
x, y = el.center() # get element center position
x, y = el.offset(0.5, 0.5) # same as center()

# send click
el.click()

# 打印文本内容
print(el.text) 

# 获取组内的属性, dict类型
print(el.attrib)

# 控件截图 （原理为先整张截图，然后再crop）
el.screenshot()

# 控件滑动
el.swipe("right") # left, right, up, down
el.swipe("right", scale=0.9) # scale默认0.9, 意思是滑动距离为控件宽度的90%, 上滑则为高度的90%

print(el.info)
# output example
{'index': '0',
 'text': '',
 'resourceId': 'com.example:id/home_searchedit',
 'checkable': 'true',
 'checked': 'true',
 'clickable': 'true',
 'enabled': 'true',
 'focusable': 'false',
 'focused': 'false',
 'scrollable': 'false',
 'longClickable': 'false',
 'password': 'false',
 'selected': 'false',
 'visibleToUser': 'true',
 'childCount': 0,
 'className': 'android.widget.Switch',
 'bounds': {'left': 882, 'top': 279, 'right': 1026, 'bottom': 423},
 'packageName': 'com.android.settings',
 'contentDescription': '',
 'resourceName': 'android:id/switch_widget'}
```

### 滑动到指定位置
> `scroll_to` 这个功能属于新增加的，可能不这么完善（比如不能检测是否滑动到底部了）

先看例子

```python
from uiautomator2 import connect_usb, Direction

d = connect_usb()

d.scroll_to("下单")
d.scroll_to("下单", Direction.FORWARD) # 默认就是向下滑动，除此之外还可以BACKWARD, HORIZ_FORWARD(水平), HORIZ_BACKWARD(水平反向)
d.scroll_to("下单", Direction.HORIZ_FORWARD, max_swipes=5)

# 除此之外还可以在指定在某个元素内滑动
d.xpath('@com.taobao.taobao:id/dx_root').scroll(Direction.HORIZ_FORWARD)
d.xpath('@com.taobao.taobao:id/dx_root').scroll_to("下单", Direction.HORIZ_FORWARD)
```

**比较完整的例子**

```python
import uiautomator2 as u2
from uiautomator2 import Direction

def main():
    d = u2.connect()
    d.app_start("com.netease.cloudmusic", stop=True)

    # steps
    d.xpath("//*[@text='私人FM']/../android.widget.ImageView").click()
    d.xpath("下一首").click()

    # 监控弹窗2s钟，时间可能大于2s
    d.xpath.sleep_watch(2)
    d.xpath("转到上一层级").click()
    
    d.xpath("转到上一层级").click(watch=False) # click without trigger watch
    d.xpath("转到上一层级").click(timeout=5.0) # wait timeout 5s

    d.xpath.watch_background() # 开启后台监控模式，默认每4s检查一次
    d.xpath.watch_background(interval=2.0) # 每2s检查一次
    d.xpath.watch_stop() # 停止监控

    for el in d.xpath('//android.widget.EditText').all():
        print("rect:", el.rect) # output tuple: (left_x, top_y, width, height)
        print("bounds:", el.bounds) # output tuple: （left, top, right, bottom)
        print("center:", el.center())
        el.click() # click operation
        print(el.elem) # 输出lxml解析出来的Node
    
    # 滑动
    el = d.xpath('@com.taobao.taobao:id/fl_banner_container').get()

    # 从右滑到左
    el.swipe(Direction.HORIZ_FORWARD) 
    el.swipe(Direction.LEFT) # 从右滑到左

    # 从下滑到上
    el.swipe(Direction.FORWARD)
    el.swipe(Direction.UP)

    el.swipe("right", scale=0.9) # scale 默认0.9, 滑动距离为控件宽度的80%, 滑动的中心点与控件中心点一致
    el.swipe("up", scale=0.5) # 滑动距离为控件高度的50%

    # scroll同swipe不一样，scroll返回bool值，表示是否还有新元素出现
    el.scroll(Direction.FORWARD) # 向下滑动
    el.scroll(Direction.BACKWARD) # 向上滑动
    el.scroll(Direction.HORIZ_FORWARD) # 水平向前
    el.scroll(Direction.HORIZ_BACKWARD) # 水平向后

    if el.scroll("forward"):
        print("还可以继续滚动")
```

### `PageSource`对象
> Added in version 3.1

这个属于高级用法，但是这个对象也最初级，几乎所有的函数都依赖它。

什么是PageSource？

PageSource是从d.dump_hierarchy()的返回值初始化来的。主要用于通过XPATH完成元素的查找工作。

用法？

```python
source = d.xpath.get_page_source()

# find_elements 是核心方法
elements = source.find_elements('//android.widget.TextView') # List[XMLElement]
for el in elements:
    print(el.text)

# 获取坐标后点击
x, y = elements[0].center()
d.click(x, y)

# 多种条件的查询写法
es1 = source.find_elements('//android.widget.TextView')
es2 = source.find_elements(XPath('@android:id/content').joinpath("//*"))

# 寻找是TextView但不属于id=android:id/content下的节点
els = set(es1) - set(es2)

# 寻找是TextView同事属于id=android:id/content下的节点
els = set(es1) & set(es2)
```

## XPath规则
为了写起脚本来更快，我们自定义了一些简化的xpath规则

**规则1**

`//` 开头代表原生xpath

**规则2**

`@` 开头代表resourceId定位

`@smartisanos:id/right_container` 相当于 
`//*[@resource-id="smartisanos:id/right_container"]`

**规则3**

`^`开头代表正则表达式

`^.*道了` 相当于 `//*[re:match(text(), '^.*道了')]`

**规则4**

> 灵感来自SQL like

`知道%` 匹配`知道`开始的文本， 相当于 `//*[starts-with(text(), '知道')]`

`%知道` 匹配`知道`结束的文本，相当于 `//*[ends-with(text(), '知道')]`

`%知道%` 匹配包含`知道`的文本，相当于 `//*[contains(text(), '知道')]`

**规则 Last**

会匹配text 和 description字段

如 `搜索` 相当于 XPath `//*[@text="搜索" or @content-desc="搜索" or @resource-id="搜索"]`

## 特殊说明
- 有时className中包含有`$@#&`字符，这个字符在XML中是不合法的，所以全部替换成了`.`

## XPath的一些高级用法
```
# 所有元素
//*

# resource-id包含login字符
//*[contains(@resource-id, 'login')]

# 按钮包含账号或帐号
//android.widget.Button[contains(@text, '账号') or contains(@text, '帐号')]

# 所有ImageView中的第二个
(//android.widget.ImageView)[2]

# 所有ImageView中的最后一个
(//android.widget.ImageView)[last()]

# className包含ImageView
//*[contains(name(), "ImageView")]
```

## 一些有用的网站
- [XPath playground](https://scrapinghub.github.io/xpath-playground/)
- [XPath的一些高级用法-简书](https://www.jianshu.com/p/4fef4142b33f)
- [XPath Quicksheet](https://devhints.io/xpath)

如有其他资料，欢迎提[Issues](https://github.com/openatx/uiautomator2/issues/new)补充
