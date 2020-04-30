## 本地开发指南

```
git clone https://github.com/openatx/uiautomator2
pip3 install -e uiautomator2
```

`-e`这个选项可以将该目录以软连接的形式添加到Python `site-packages`

## 生成CHANGELOG
See changelog from git history

```
git log --graph --date-order -C -M --pretty=format:"<%h> %ad [%an] %Cgreen%d%Creset %s" --all --date=short
```

## 使用Sphinx生成文档
```bash
pip3 install -e .
cd docs
make publish
```

## ViewConfiguration
一些默认的配置，从 `/android/view/ViewConfiguration.java`中可以查到

> 单位: 毫秒

- TAP_TIMEOUT: 100
- LONG_PRESS_TIMEOUT: 500
- DOUBLE_TAP_TIMEOUT: 300
