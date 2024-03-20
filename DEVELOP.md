## 本地开发指南

```
git clone https://github.com/openatx/uiautomator2
cd uiautomator2

pip install poetry
poetry install
```

项目使用poetry做包管理还打包发布功能

## 生成CHANGELOG
See changelog from git history

```
git log --graph --date-order -C -M --pretty=format:"<%h> %ad [%an] %Cgreen%d%Creset %s" --all --date=short
```


## ViewConfiguration
一些默认的配置，从 `/android/view/ViewConfiguration.java`中可以查到

> 单位: 毫秒

- TAP_TIMEOUT: 100
- LONG_PRESS_TIMEOUT: 500
- DOUBLE_TAP_TIMEOUT: 300
