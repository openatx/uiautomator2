## 项目背景

大约在2017年的时候，我在做Android自动化相关的工作，当时的脚本是用的Python写的，所以去网上找了下相关的开源项目。

刚好找到了 https://github.com/xiaocong/uiautomator
原理是在手机上运行了一个http rpc服务，将uiautomator中的功能开放出来，然后再将这些http接口封装成Python库。这个库写的实在是太好了，爱不释手。
但是这个项目很久也没更新了，也联系不上作者，于是我就fork了一个版本
为了方便做区分我们就在后面加了个2，从uiautomator变成了uiautomator2

- [openatx/uiautomator2](https://github.com/openatx/uiautomator2)
- [openatx/android-uiautomator-server](https://github.com/openatx/android-uiautomator-server)

增加了各种各样的代码，对其中的bug做了修复。

期间也衍生出来的很多其他项目

- 自动化工具 https://github.com/NeteaseGame/ATX 废弃
- 设备管理平台(也支持iOS) [atxserver2](https://github.com/openatx/atxserver2) 废弃
- 纯Python的ADB客户端 https://github.com/openatx/adbutils 这个还健康的存活着
- https://github.com/openatx/weditor 不维护了，不过有开发了一个新的。 https://uiauto.dev
- [uiauto.dev](https://uiauto.dev) 用于查看UI层级结构，类似于uiautomatorviewer(用于替代之前写的weditor），用于查看UI层级结构 

