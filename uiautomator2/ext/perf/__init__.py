# coding: utf-8
#

from __future__ import absolute_import, print_function

import threading
import re
import time
import csv

_MEM_PATTERN = re.compile(r'TOTAL[:\s]+(\d+)')


class Perf(object):
    def __init__(self, d, package_name=None):
        self.d = d
        self.package_name = package_name
        self._th = None
        self._event = threading.Event()
        self._condition = threading.Condition()

    def memory(self):
        """ PSS """
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
        # print("total cpu", total_cpu)

        proc_stat = d.shell(
            ['cat', '/proc/%d/stat' % pid]).output.split(') ')[1].split()
        utime = int(proc_stat[11])
        stime = int(proc_stat[12])
        return (total_cpu, idle, utime + stime)
        # print(proc_stat)
        # print(utime, stime)

    def cpu(self):
        """ CPU

        Refs:
        - http://man7.org/linux/man-pages/man5/proc.5.html
        - [安卓性能测试之cpu占用率统计方法总结](https://www.jianshu.com/p/6bf564f7cdf0)
        """
        pid = self.d._pidof_app(self.package_name)
        if pid is None:
            return 0.0
        print("Pid:", pid)
        tjiff1, idle1, pjiff1 = self._cpu_rawdata_collect(pid)
        time.sleep(.3)
        tjiff2, idle2, pjiff2 = self._cpu_rawdata_collect(pid)
        pcpu = 100.0 * (pjiff2 - pjiff1) / (tjiff2 - tjiff1)  # process cpu
        scpu = 100.0 * ((tjiff2 - idle2) -
                        (tjiff1 - idle1)) / (tjiff2 - tjiff1)  # system cpu
        # print("CPU:", pcpu, scpu)
        return round(pcpu, 1), round(scpu, 1)
        # print("cal cpu:", round(pcpu, 1), round(scpu, 1))

        # first_line = d.shell(['cat', '/proc/stat']).output.splitlines()[0]
        # assert first_line.startswith('cpu ')
        # total_cpu = sum(map(int, first_line.split()[1:]))
        # print("total cpu", total_cpu)

        # proc_stat = d.shell(
        #     ['cat', '/proc/%d/stat' % pid]).output.split(') ')[1].split()
        # utime = proc_stat[11]
        # stime = proc_stat[12]
        # print(proc_stat)
        # print(utime, stime)

        # time.sleep(.3)

        # for line in d.shell(["top", "-n", "1"]).output.splitlines():
        #     vs = line.split()
        #     if len(vs) > 5 and vs[-1] == self.package_name:
        #         if vs[4].endswith('%'):
        #             print("Miss:", float(vs[4][:-1]) - pcpu)
        #             return float(vs[4][:-1]), 0.0
        # return (0.0, 0.0)

    def collect(self):
        start = time.time()
        pss = self.memory()
        print("memofy time used =", time.time() - start)
        cpu, scpu = self.cpu()
        print("collect time used =", time.time() - start)
        return {
            'time': int(time.time() * 1000),
            'pss': pss,
            'cpu': cpu,
            'systemCpu': scpu,
        }

    def continue_collect(self):
        try:
            with open("perf.csv", "w", newline='\n') as f:
                fcsv = csv.writer(f)
                headers = ['time', 'pss', 'cpu', 'systemCpu']
                fcsv.writerow(headers)
                while not self._event.isSet():
                    perfdata = self.collect()
                    fcsv.writerow([perfdata[k] for k in headers])
                    print(time.time(), perfdata)
                    time.sleep(.5)
        finally:
            print("collect finish")
            self._condition.acquire()
            self._th = None
            print("notify condi")
            self._condition.notify()
            self._condition.release()

    def start(self):
        if self._th:
            raise RuntimeError("perf is already running")
        if not self.package_name:
            raise EnvironmentError("package_name need to be set")
        self._event = threading.Event()
        self._condition = threading.Condition()
        self._th = threading.Thread(target=self.continue_collect)
        self._th.daemon = True
        self._th.start()

    def stop(self):
        print("stop() wait collect stopped")
        self._event.set()
        self._condition.acquire()
        print("wait done")
        self._condition.wait(timeout=2)
        self._condition.release()
        print("stoped")


if __name__ == '__main__':
    import uiautomator2 as u2
    pkgname = "com.tencent.tmgp.sgame"
    u2.plugin_register('perf', Perf, pkgname)

    d = u2.connect("10.242.62.224")
    print(d.current_app())
    # d.app_start(pkgname)
    d.ext_perf.start()
    try:
        time.sleep(500)
    except KeyboardInterrupt:
        d.ext_perf.stop()
        print("threading stopped")
    # time.sleep(2)