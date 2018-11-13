# uiautomator2 xpath extension

## 使用方法
```python
import uiautomator2 as u2
import uiautomator2.ext.xpath as xpath

xpath.init()

def main():
    d = u2.connect()
    d.ext_xpath.when("//*[popup]").click()

    d.ext_xpath.click("//*[@content-desc='下一步']")
```

## XPath规则
- `//` 开头代表原生xpath
- `@` 开头代表resourceId定位
- 其他的是text或者description

例子

`@smartisanos:id/right_container` 相当于 
`//*[@resource-id="smartisanos:id/right_container"]`

`开始` 相当于 
`//*[@text="开始" or @content-desc="开始"]`