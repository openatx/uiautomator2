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
