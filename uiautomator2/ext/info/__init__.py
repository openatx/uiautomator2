import json
import os
import datetime
import sys


class Info(object):
    def __init__(self, driver):
        self._driver = driver
        self.log = self.read_file('log.txt').splitlines()
        self.record = json.loads(self.read_file('record.json'))
        self.test_info = {}

    @staticmethod
    def read_file(filename):
        try:
            with open(filename, 'r') as f:
                return f.read()
        except IOError as e:
            print(os.strerror(e.errno))

    def get_basic_info(self):
        device_info = self._driver.device_info
        app = self._driver.current_app()['package']
        self.test_info['basic_info'] = {
            'device_info': device_info,
            'app': app
        }

    def get_record_info(self):
        steps = len(self.record['steps'])
        start_time = datetime.datetime.strptime(self.record['steps'][0]['time'], '%H:%M:%S')
        end_time = datetime.datetime.strptime(self.record['steps'][steps - 1]['time'], '%H:%M:%S')
        total_time = end_time - start_time
        self.test_info['record_info'] = {
            'steps': steps,
            'start_time': self.record['steps'][0]['time'],
            'total_time': str(total_time)
        }

    def get_result_info(self):
        trace_list = []
        for i in range(len(self.log)):
            if 'Traceback' in self.log[i]:
                new_trace = self.log[i]
                i += 1
                while 'File' in self.log[i]:
                    new_trace += '\n' + self.log[i]
                    i += 1
                new_trace += '\n' + self.log[i]
                trace_list.append(new_trace)
        self.test_info['trace_info'] = {
            'trace_count': len(trace_list),
            'trace_list': trace_list
        }

    def write_info(self):
        self.get_basic_info()
        self.get_record_info()
        self.get_result_info()
        with open('info.json', 'wb') as f:
            f.write(json.dumps(self.test_info))
