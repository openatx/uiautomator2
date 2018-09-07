# coding: utf-8
#

from __future__ import absolute_import, print_function

import threading
import re
import time
import datetime
import csv
import atexit
from collections import namedtuple

_MEM_PATTERN = re.compile(r'TOTAL[:\s]+(\d+)')
# acct_tag_hex is a socket tag
# cnt_set==0 are for background data
# cnt_set==1 are for foreground data
_NetStats = namedtuple(
    "NetStats",
    """idx iface acct_tag_hex uid_tag_int cnt_set rx_bytes rx_packets
    tx_bytes tx_packets rx_tcp_bytes rx_tcp_packets rx_udp_bytes rx_udp_packets rx_other_bytes rx_other_packets
    tx_tcp_bytes tx_tcp_packets tx_udp_bytes tx_udp_packets tx_other_bytes tx_other_packets"""
    .split())


class Perf(object):
    def __init__(self, d, package_name=None):
        self.d = d
        self.package_name = package_name
        self.csv_output = "perf.csv"
        self.debug = False
        self.interval = 1.0
        self._th = None
        self._event = threading.Event()
        self._condition = threading.Condition()
        self._data = {}

    def memory(self):
        """ PSS(KB) """
        output = self.d.shell(['dumpsys', 'meminfo', self.package_name]).output
        m = _MEM_PATTERN.search(output)
        if m:
            return int(m.group(1))
        return 0

    def _cpu_rawdata_collect(self, pid):
        first_line = d.shell(['cat', '/proc/stat']).output.splitlines()[0]
        assert first_line.startswith('cpu ')
        # ds: user, nice, system, idle, iowait, irq, softirq, stealstolen, guest, guest_nice
        ds = list(map(int, first_line.split()[1:]))
        total_cpu = sum(ds)
        idle = ds[3]

        proc_stat = d.shell(
            ['cat', '/proc/%d/stat' % pid]).output.split(') ')[1].split()
        utime = int(proc_stat[11])
        stime = int(proc_stat[12])
        return (total_cpu, idle, utime + stime)

    def cpu(self, pid):
        """ CPU

        Refs:
        - http://man7.org/linux/man-pages/man5/proc.5.html
        - [安卓性能测试之cpu占用率统计方法总结](https://www.jianshu.com/p/6bf564f7cdf0)
        """
        store_key = 'cpu-%d' % pid
        # first time jiffies
        if store_key in self._data:
            tjiff1, idle1, pjiff1 = self._data[store_key]
        else:
            tjiff1, idle1, pjiff1 = self._cpu_rawdata_collect(pid)
            time.sleep(.3)

        # second time jiffies
        self._data[
            store_key] = tjiff2, idle2, pjiff2 = self._cpu_rawdata_collect(pid)

        # calculate
        pcpu = 100.0 * (pjiff2 - pjiff1) / (tjiff2 - tjiff1)  # process cpu
        scpu = 100.0 * ((tjiff2 - idle2) -
                        (tjiff1 - idle1)) / (tjiff2 - tjiff1)  # system cpu
        return round(pcpu, 1), round(scpu, 1)

        # Retrive cpu from top
        # for line in d.shell(["top", "-n", "1"]).output.splitlines():
        #     vs = line.split()
        #     if len(vs) > 5 and vs[-1] == self.package_name:
        #         if vs[4].endswith('%'):
        #             print("Miss:", float(vs[4][:-1]) - pcpu)
        #             return float(vs[4][:-1]), 0.0
        # return (0.0, 0.0)

    def netstat(self, pid):
        """
        Returns:
            (rx_bytes, tx_bytes)
        """
        m = re.search(r'^Uid:\s+(\d+)',
                      self.d.shell(['cat', '/proc/%d/status' % pid]).output,
                      re.M)
        if not m:
            return (0, 0)
        uid = m.group(1)
        lines = self.d.shell(
            ['cat', '/proc/net/xt_qtaguid/stats']).output.splitlines()

        rx, tx = 0, 0
        for line in lines:
            vs = line.split()
            if len(vs) != 21:
                continue
            v = _NetStats(*vs)
            if v.uid_tag_int != uid:
                continue
            if v.iface != 'wlan0':
                continue
            # FIXME(ssx): tcp and udp data will support when some one needed
            rx += int(v.rx_bytes)
            tx += int(v.tx_bytes)

        store_key = 'netstat-%s' % uid
        drx, dtx = 0, 0
        if store_key in self._data:
            last_rx, last_tx = self._data[store_key]
            drx, dtx = rx - last_rx, tx - last_tx
        self._data[store_key] = (rx, tx)
        return drx, dtx

    def collect(self):
        pid = self.d._pidof_app(self.package_name)
        if pid is None:
            return
        pss = self.memory()
        cpu, scpu = self.cpu(pid)
        rx_bytes, tx_bytes = self.netstat(pid)
        timestr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return {
            'time': timestr,
            'pss': round(pss / 1024.0, 2),
            'cpu': cpu,
            'systemCpu': scpu,
            'rxBytes': rx_bytes,
            'txBytes': tx_bytes,
        }

    def continue_collect(self, f):
        try:
            headers = ['time', 'pss', 'cpu', 'systemCpu', 'rxBytes', 'txBytes']
            fcsv = csv.writer(f)
            fcsv.writerow(headers)
            update_time = time.time()
            while not self._event.isSet():
                perfdata = self.collect()
                if self.debug:
                    print("DEBUG:", perfdata)
                if not perfdata:
                    print("perf package is not alive:", self.package_name)
                    time.sleep(1)
                    continue
                fcsv.writerow([perfdata[k] for k in headers])
                wait_seconds = max(0,
                                   self.interval - (time.time() - update_time))
                time.sleep(wait_seconds)
                update_time = time.time()
            f.close()
        finally:
            self._condition.acquire()
            self._th = None
            self._condition.notify()
            self._condition.release()

    def start(self):
        f = open("perf.csv", "w", newline='\n')

        def defer_close():
            if not f.closed:
                f.close()

        atexit.register(defer_close)

        if self._th:
            raise RuntimeError("perf is already running")
        if not self.package_name:
            raise EnvironmentError("package_name need to be set")
        self._data.clear()
        self._event = threading.Event()
        self._condition = threading.Condition()
        self._th = threading.Thread(target=self.continue_collect, args=(f, ))
        self._th.daemon = True
        self._th.start()

    def stop(self):
        self._event.set()
        self._condition.acquire()
        self._condition.wait(timeout=2)
        self._condition.release()


if __name__ == '__main__':
    import uiautomator2 as u2
    pkgname = "com.tencent.tmgp.sgame"
    pkgname = "com.netease.cloudmusic"
    u2.plugin_register('perf', Perf, pkgname)

    d = u2.connect("10.242.62.224")
    print(d.current_app())
    # print(d.ext_perf.netstat(5350))
    # d.app_start(pkgname)
    d.ext_perf.start()
    d.ext_perf.debug = True
    try:
        time.sleep(500)
    except KeyboardInterrupt:
        d.ext_perf.stop()
        print("threading stopped")