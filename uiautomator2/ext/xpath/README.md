# uiautomator2 xpath extension

## 工作原理
1. 通过uiautomator2库的`dump_hierarchy`接口，获取到当前的UI图层。
2. 然后使用`lxml`库解析，寻找匹配的xpath，然后执行相应的操作

这个插件最非常多的地方都用的XPath，所以要先了解一些XPath知识。
好在网上这方便的资料很多。下面列举一些

- [W3CSchool XPath教程](http://www.w3school.com.cn/xpath/index.asp)
- [XPath tutorial](http://www.zvon.org/xxl/XPathTutorial/)
- [阮一峰的XPath学习笔记](http://www.ruanyifeng.com/blog/2009/07/xpath_path_expressions.html)
- [测试XPath的网站](https://www.freeformatter.com/xpath-tester.html)

## 使用方法
```python
import uiautomator2 as u2
import uiautomator2.ext.xpath as xpath

xpath.init()

def main():
    d = u2.connect()
    d.app_start("com.netease.cloudmusic", stop=True)

    # watchers
    d.ext_xpath.when("跳过").click()
    d.ext_xpath.when("知道了").click()

    # steps
    d.ext_xpath("//*[@text='私人FM']/../android.widget.ImageView").click()
    d.ext_xpath("下一首").click()
    d.ext_xpath.sleep_watch(2)
    d.ext_xpath("转到上一层级").click()
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

**规则 Last**

会匹配text 和 description字段

如 `搜索` 相当于 XPath `//*[@text="搜索" or @content-desc="搜索"]`

## 特殊说明
- 有时className中包含有`$`字符，这个字符在XML中是不合法的，所以全部替换成了`-`
