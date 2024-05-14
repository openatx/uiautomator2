## Local development

```
git clone https://github.com/openatx/uiautomator2
cd uiautomator2

pip install poetry
poetry install

# download apk to assets/
make sync

# run python shell after device or emulator connected
poetry run uiautomator2 console
```


## ViewConfiguration
Default configuration can retrived from [/android/view/ViewConfiguration.java](https://android.googlesource.com/platform/frameworks/base/+/master/core/java/android/view/ViewConfiguration.java)

> Unit: ms

- TAP_TIMEOUT: 100
- LONG_PRESS_TIMEOUT: 500
- DOUBLE_TAP_TIMEOUT: 300
