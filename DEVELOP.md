## 本地开发指南

```
git clone https://github.com/openatx/uiautomator2
pip install -e uiautomator2
```

`-e`这个选项可以将该目录以软连接的形式添加到Python `site-packages`

## 生成CHANGELOG
See changelog from git history

```
git log --graph --date-order -C -M --pretty=format:"<%h> %ad [%an] %Cgreen%d%Creset %s" --all --date=short
```
