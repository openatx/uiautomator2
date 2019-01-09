# uiautomator2 xpath extension

用这个插件前，要先了解一些XPath知识。
好在网上这方便的资料很多。下面列举一些

- [W3CSchool XPath教程](http://www.w3school.com.cn/xpath/index.asp)
- [XPath tutorial](http://www.zvon.org/xxl/XPathTutorial/)
- [阮一峰的XPath学习笔记](http://www.ruanyifeng.com/blog/2009/07/xpath_path_expressions.html)
- [测试XPath的网站](https://www.freeformatter.com/xpath-tester.html)

## 工作原理
1. 通过uiautomator2库的`dump_hierarchy`接口，获取到当前的UI界面（一个很丰富的XML）。
2. 然后使用`lxml`库解析，寻找匹配的xpath，然后使用click指令完后操作

**弹窗监控原理**

通过hierarchy可以知道界面上的所有元素信息（包括弹窗和要点击的按钮）。
假设有 `跳过`, `知道了` 这两个弹窗按钮。需要点击的按钮名是 `播放`

1. 获取到当前界面的XML（通过dump_hierarchy函数）
2. 检查有没有`跳过`, `知道了` 这两个按钮，如果有就点击，然后回到第一步
3. 检查有没有`播放`按钮, 有就点击，结束。没有找到在回到第一步，一直执行到查找次数超标。

## 安装方法
```
pip install -U --pre uiautomator2
```

## 使用方法
目前该插件已经内置到uiautomator2中了，所以不需要plugin注册了。

```python
import uiautomator2 as u2


def main():
    d = u2.connect()
    d.app_start("com.netease.cloudmusic", stop=True)

    # watchers 监控弹窗
    d.xpath.when("跳过").click()
    d.xpath.when("知道了").click()

    # steps
    d.xpath("//*[@text='私人FM']/../android.widget.ImageView").click()
    d.xpath("下一首").click()

    # 监控弹窗2s钟，时间可能大于2s
    d.xpath.sleep_watch(2)
    d.xpath("转到上一层级").click()

    # 一直在后台监控（目前每隔4s检查一次），暂时还没提供暂停的方法
    d.xpath.watch_background()
```

别名定义，感觉这种写法有点类似selenium中的[PageObjects](https://selenium-python.readthedocs.io/page-objects.html)

>下面的代码为了方便就不写`import`了

```python
# 这里是Python3的写法，python2的string定义需要改成 u"菜单" 注意前的这个u
d.xpath.global_set("alias", {
    "菜单": "@com.netease.cloudmusic:id/qh", # TODO(ssx): maybe we can support P("@com.netease.cloudmusic:id/qh", wait_timeout=2) someday
    "设置": "//android.widget.TextView[@text='设置']",
})


# 这里需要 $ 开头
d.xpath("$菜单").click() # 等价于 d.xpath()
d.xpath("$设置").click()


# alias_strict 设置项
d.xpath("$返回").click() # 等价于 d.xpath("返回").click()，因为返回没有预先在alias中定义

d.xpath.global_set("alias_strict", True) # 默认 False
d.xpath("$返回").click() # 在这里会直接跑出XPathError异常
```

## XPath规则
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

**规则5**

> 另外来自Selenium PageObjects

`$知道` 匹配 通过`d.xpath.global_set("alias", dict)` dict字典中的内容， 如果不存在将使用`知道`来匹配

**规则 Last**

会匹配text 和 description字段

如 `搜索` 相当于 XPath `//*[@text="搜索" or @content-desc="搜索"]`

## 特殊说明
- 有时className中包含有`$`字符，这个字符在XML中是不合法的，所以全部替换成了`-`
