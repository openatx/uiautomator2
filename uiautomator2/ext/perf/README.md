# Performance 性能采集
自动记录测试过程中的CPU，PSS

使用方法
```python
import uiautomator2 as u2
import uiautomator2.ext.perf as perf

package_name = "com.netease.cloudmusic"
u2.plugin_register('perf', perf.Perf)


def main():
    d = u2.connect()
    d.ext_perf.package_name = package_name
    d.ext_perf.start()

    # run ... tests
    d.ext_perf.stop() # call at last


if __name__ == '__main__':
    main()
```