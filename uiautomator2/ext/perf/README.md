# Performance 性能采集
自动记录测试过程中的CPU，PSS, NET

使用方法
```python
import uiautomator2 as u2
import uiautomator2.ext.perf as perf

package_name = "com.netease.cloudmusic"
u2.plugin_register('perf', perf.Perf)


def main():
    d = u2.connect()
    d.ext_perf.package_name = package_name
    d.ext_perf.csv_output = "perf.csv" # 保存数据到perf.csv
    # d.debug = True # 采集到数据就输出，默认关闭
    # d.interval = 1.0 # 数据采集间隔，默认1.0s，尽量不要小于0.5s，因为采集内存比较费时间
    d.ext_perf.start()

    # run ... tests code here ...
    d.ext_perf.stop() # 最好结束的时候调用下，虽然不调用也没多大关系


if __name__ == '__main__':
    main()
```

保存的csv文件内容格式为

```csv
time,pss,cpu,systemCpu,rxBytes,txBytes
2018-09-07 16:09:16.725,161.41,1.9,6.2,0,0
2018-09-07 16:09:17.812,161.42,3.6,9.1,31650,2943
2018-09-07 16:09:19.043,167.1,17.3,52.5,3379507,133231
2018-09-07 16:09:19.800,168.92,12.8,33.6,801161,30242
2018-09-07 16:09:20.871,168.78,12.3,26.0,0,0
2018-09-07 16:09:21.842,168.76,12.1,26.9,0,0
2018-09-07 16:09:22.910,169.39,12.5,26.3,187,64
```

数据项说明

- PSS直接通过`dumpsys meminfo <package-name>`获取
- CPU应该是会超过100%的，直接读取的`/proc/`下的文件计算出来的
- rxBytes, txBytes 目前只有wlan的流量，tcp和udp的流量总和

## 参考资料
- [Python CSV读写方法](https://python3-cookbook.readthedocs.io/zh_CN/latest/c06/p01_read_write_csv_data.html)
- [android屏幕刷新显示机制](https://blog.csdn.net/litefish/article/details/53939882)
- [Android FPS计算方法](https://www.jianshu.com/p/1fe9783d266b)
- [Github项目@leekinwa-androidTestTools_performance_FPS](https://github.com/leekinwa/androidTestTools_Performance_FPS)
- [官方proc文件格式资料](http://man7.org/linux/man-pages/man5/proc.5.html)
- [Chromium有关FPS的计算方法](https://github.com/ChromiumWebApps/chromium/blob/master/build/android/pylib/perf/surface_stats_collector.py)
- [FPS 计算方法的比较 by fenfenzhong](https://testerhome.com/topics/4643)
- [安卓性能测试之cpu占用率统计方法总结](https://www.jianshu.com/p/6bf564f7cdf0)
- [Android 性能测试实践 (四) 流量](https://testerhome.com/topics/2643)