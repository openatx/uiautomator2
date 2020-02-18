# 使用百度OCR选取文字元素

## 前提条件

1.需要有百度云账号，百度云注册账号: https://cloud.baidu.com/?from=console

2.创建一个文字识别的应用: https://console.bce.baidu.com/ai/#/ai/ocr/overview/index 

  记住三个值 AppID 、API_Key、Secret_Key

3.需要安装百度OCR Python SDK：`pip install baidu-aip`

百度OCR具体应用见百度文档：https://cloud.baidu.com/doc/OCR/s/ejwvxzls6

## 示例

```python
import uiautomator2 as u2
import uiautomator2.ext.ocr.baiduOCR as ocr

APP_ID = '创建应用的APP_ID'
API_KEY = '创建应用的API_KEY'
SECRECT_KEY = '创建应用的SECRECT_KEY'
# options = {"templateSign": ''}  # iOCR财会票据识别模板id

u2.plugin_add("ocr", ocr.OCR, APP_ID, API_KEY, SECRECT_KEY)
# u2.plugin_add("ocrCustom", ocr.OCRCustom, APP_ID, API_KEY, SECRECT_KEY, options)

d = u2.connect()
d.ext_ocr("对战模式").click()
# d.ext_ocrCustom("对战模式").click()
```