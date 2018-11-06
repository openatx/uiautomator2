import json
import os
import datetime
import atexit


class Info(object):
    def __init__(self, driver, package_name=None):
        self._driver = driver
        self.output_dir = 'report/'
        self.pkg_name = package_name
        self.test_info = {}
        atexit.register(self.write_info)

    def read_file(self, filename):
        try:
            with open(self.output_dir + filename, 'r') as f:
                return f.read()
        except IOError as e:
            print(os.strerror(e.errno))

    def get_basic_info(self):
        device_info = self._driver.device_info
        app = self.pkg_name
        self.test_info['basic_info'] = {'device_info': device_info, 'app': app}

    def get_record_info(self):
        record = json.loads(self.read_file('record.json'))
        steps = len(record['steps'])
        start_time = datetime.datetime.strptime(record['steps'][0]['time'],
                                                '%H:%M:%S')
        end_time = datetime.datetime.strptime(
            record['steps'][steps - 1]['time'], '%H:%M:%S')
        total_time = end_time - start_time
        self.test_info['record_info'] = {
            'steps': steps,
            'start_time': record['steps'][0]['time'],
            'total_time': str(total_time)
        }

    def get_result_info(self):
        log = self.read_file('log.txt')
        trace_list = []
        if log:
            log = log.splitlines()
            for i in range(len(log)):
                if 'Traceback' in log[i]:
                    new_trace = log[i]
                    i += 1
                    while 'File' in log[i]:
                        new_trace += '\n' + log[i]
                        i += 1
                    new_trace += '\n' + log[i]
                    trace_list.append(new_trace)
        self.test_info['trace_info'] = {
            'trace_count': len(trace_list),
            'trace_list': trace_list
        }

    def start(self):
        self.get_basic_info()

    def write_info(self):
        # self.get_basic_info()
        self.get_record_info()
        self.get_result_info()
        with open(self.output_dir + 'info.json', 'wb') as f:
            f.write(json.dumps(self.test_info))
