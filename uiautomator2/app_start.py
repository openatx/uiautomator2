# coding:utf-8
# datetime: 2020/5/15 7:27 PM
# software: PyCharm
# File: app_start

LICENSE = 'Copyright 2019.'

import time
import subprocess

class Phone:

    def __init__(self, d=None, u2url=None,brand=None, logger=None):

        self.exlude_app = ["com.tencent.mm",'com.github.uiautomator', 'com.github.uiautomator.test']
        self.d = d
        if not brand:
            self.brand = self.d.device_info['brand']
        else:
            self.brand = brand

        self.logger = logger

        self.attention = {
                        "com.android.packageinstaller": [u"确定", u"安装", u"下一步", u"好", u"允许", u"我知道"],
                        "com.miui.securitycenter": [u"继续安装"],  # xiaomi
                        "com.lbe.security.miui": [u"允许"],  # xiaomi
                        "android": [u"好", u"安装"],  # vivo
                        "com.huawei.systemmanager": [u"立即删除"],  # huawei
                        "com.android.systemui": [u"同意"],  # 锤子
                    }

        self.attention_install = {
                "letv" : {
                    'adb_install_allow' :{'times': 5,
                                        'when': [ "//*[@resource-id='android:id/le_bottomsheet_btn_confirm_5']", "不再提示" ],
                                        'call': (('text','不再提示'), ('text','允许') )}
                        },
                "xiaomi": {
                    'adb_install_allow': {'times': 5,
                                          'when': [],
                                          'call': None }
                },
                "vivo": {
                    'adb_IMEI_allow': {'times': 5,
                                          'when': ["//*[@resource-id='android:id/alertTitle']", "知道了"],
                                          'call': ( ('text', '知道了'), ('text', '好') )},
                    'adb_nomarket_allow': {'times': 5,
                                          'when': ["安全警告","好"],
                                          'call': (('text', '好'))},
                    'adb_install_allow': {'times': 5,
                                           'when': ["//*[@resource-id='vivo:id/vivo_adb_install_ok_button']","安装"],
                                           'call': (('text', '安装'), ('resourceId', 'vivo:id/vivo_adb_install_ok_button'))}
                },
                "meizu": {
                    'adb_install_allow': {'times': 5,
                                          'when': [],
                                          'call': None }
                },
                "oppo": {
                    'adb_nomarket_allow': {'times': 5,
                                          'when': ["安装风险", "允许"],
                                          'call': ( ('text', '允许'), ('resourceId', 'android:id/button2') )},
                    'adb_install_allow': {'times': 5,
                                          'when': ["//*[@resource-id='com.android.packageinstaller:id/permission_list']",
                                                   "安装"],
                                          'call': ( ('text', '安装'), ('resourceId', 'com.android.packageinstaller:id/bottom_button_two') )}
                },
            }
        self.attention_install['LeEco'.lower()] = self.attention_install['letv']

        self.attention_start = {
                "letv": {
                    'allow_out_app': {'times': 5,
                                          'when': ["//*[@resource-id='android:id/le_bottomsheet_btn_confirm_5']", "允许"],
                                          'call': (('text', '允许'))},
                    'allow_in_app': {'times': 3,
                                          'when': ["//*[@resource-id='android:id/le_bottomsheet_btn_confirm_5']", "允许"],
                                          'call': ( ('text', '不再提示'), ('text', '允许') )}
                },
                "xiaomi": {
                    'allow_in_app': {'times': 5,
                                          'when': [ "//*[@resource-id='com.lbe.security.miui:id/perm_desc_root']", "允许" ],
                                          'call': ( ('text', '不再提示'), ('text', '允许') )}
                },
                "vivo": {
                    'allow_in_app': {'times': 5,
                                       'when': ["权限请求", "允许"],
                                       'call': ( ('text', '允许'), ('resourceId', 'android:id/button1') )},
                },
                "meizu": {
                    'allow_in_app': {'times': 5,
                                          'when': ["//*[@resource-id='android:id/title_template']", "允许" ],
                                          'call': ( ('text', '允许'), ('resourceId', 'android:id/button1') )}
                },
                "oppo": {
                    'allow_in_app': {'times': 5,
                                           'when': ["//*[@resource-id='android:id/title_template']", "允许"],
                                           'call': ( ('text', '允许'), ('resourceId', 'android:id/button1') )},
                },
            }
        self.attention_start[ 'LeEco'.lower() ] = self.attention_start['letv']


    def permission_call_func(self, *args, **kwargs ):
        for item in args:
            if self.d(**{item[0]:item[1]}).exists:
                self.d(**{item[0]:item[1]}).click()
        return True

    def register_watcher(self, attention=None):
        if not attention:
            return False

        for key,value in attention.items():
            watcher = self.d.watcher(key, value['times'])
            if not value['when']:
                continue
            for wh in value['when']:
                watcher = watcher.when(wh)
            if not value['call']:
                continue
            watcher.call( self.permission_call_func, *value['call']  )
        return True

    def permission_install(self):
        device_brand = self.brand
        if device_brand.lower() in self.attention_install:
            attention =  self.attention_install[ device_brand.lower() ]
            self.register_watcher(attention = attention)
            return True

        for key,value in self.attention_install.items():
            self.register_watcher(attention=value)
        self.d.watcher.start()
        return True

    def permission_start(self):
        device_brand = self.brand
        if device_brand.lower() in self.attention_start:
            attention =  self.attention_start[ device_brand.lower() ]
            self.register_watcher(attention = attention)
            return True

        for key,value in self.attention_start.items():
            self.register_watcher(attention=value)
        self.d.watcher.start()
        return True

    def permission_message_install(self):
        # 乐视提示是否adb可安装
        # d(resourceId="android:id/le_bottomsheet_btn_chk_ctn")  不再提示框
        if self.brand == 'letv' or self.brand == 'leeco':
            self.d.watcher('adb_install_allow', 5).when(
                "//*[@resource-id='android:id/le_bottomsheet_btn_confirm_5']").when("不再提示").call(
                self.permission_call_func, ('text','不再提示'), ('text','允许'))

            # self.d.watcher('adb_install_allow', 5).when("不再提示").call(
            #     self.permission_call_func, ('text', '不再提示'), ('text', '允许'))

        elif self.brand == 'xiaomi':# 小米 没有提示
            pass
        elif self.brand == 'meizu': # meizu 没有安全提示警告
            pass

        elif self.brand == 'vivo':
            # vivo 提示安全警告
            self.d.watcher('adb_IMEI_allow', 5).when(
                "//*[@resource-id='android:id/alertTitle']").when("知道了").call(
                self.permission_call_func, ('text', '知道了'), ('text', '好')) #这个是防止vivo的IMEI MEID无效

            self.d.watcher('adb_nomarket_allow', 5).when("//android.widget.TextView[@text='安全警告']").call(
                self.permission_call_func, ('text', '好'))

            self.d.watcher('adb_install_allow', 5).when(
                "//*[@resource-id='vivo:id/vivo_adb_install_ok_button']").when("安装").call(
                self.permission_call_func, ('text', '安装'), ('resourceId', 'vivo:id/vivo_adb_install_ok_button'))

        elif self.brand == 'oppo':
            # oppo 非市场应用 # 下面是点击安装按钮
            self.d.watcher('adb_nomarket_allow', 5).when("安装风险").when("允许").call(
                self.permission_call_func, ('text', '允许'), ('resourceId', 'android:id/button2'))
            self.d.watcher('adb_install_allow', 5).when(
                "//*[@resource-id='com.android.packageinstaller:id/permission_list']").when("安装").call(
                self.permission_call_func, ('text', '安装'), ('resourceId', 'com.android.packageinstaller:id/bottom_button_two'))
        else:
            return False

        self.d.watcher.start()
        return True


    def permission_message_start(self):
        # 乐视在打开页面弹出确认
        # d(resourceId="android:id/le_bottomsheet_btn_chk_ctn")  不再提示框
        if self.brand == 'letv' or self.brand == 'leeco':
            self.d.watcher('allowout', 5).when(
                "//*[@resource-id='android:id/le_bottomsheet_btn_confirm_5']").when("允许").call(
                self.permission_call_func, ('text', '允许'))

            # 乐视在app内部弹出确认
            # self.d(resourceId="com.android.packageinstaller:id/permission_message").exists   text=要允许刷宝短视频使用此设备的位置信息吗？
            # self.d(resourceId="com.android.packageinstaller:id/permission_allow_button").click()  text=允许
            # self.d(resourceId="com.android.packageinstaller:id/permission_deny_button").click()  text=拒绝
            self.d.watcher('allowin', 3).when(
                "//*[@resource-id='com.android.packageinstaller:id/permission_message']").when("允许").call(
                self.permission_call_func, ('text', '不再提示'), ('text', '允许'))

        elif self.brand == 'xiaomi':
            # 小米手机弹出框 照片媒体文件 卫星网络定位 IMEI-IMSI-手机号码权限
            #d(resourceId="com.lbe.security.miui:id/desc_container")
            #d(resourceId="com.lbe.security.miui:id/perm_desc_root")
            #d(resourceId="com.lbe.security.miui:id/permission_list")
            self.d.watcher('allowin_lbe', 5).when(
                "//*[@resource-id='com.lbe.security.miui:id/perm_desc_root']").when("允许").call(
                self.permission_call_func, ('text', '不再提示'), ('text', '允许'))

            self.d.watcher('allowin_android', 5).when(
                "//*[@resource-id='android:id/button1']").when("允许").call(
                self.permission_call_func, ('text', '不再提示'), ('text', '允许'))

        elif self.brand == 'vivo':
            # vivo手机弹出框 手机状态 拍照 录音 位置 通讯录 sdka
            # d(resourceId="vivo:id/rememberCB") 不再提示
            # d(resourceId="vivo:id/confirm_msg")
            # d(resourceId="android:id/title_template")
            # d(resourceId="vivo:id/hint_msg")  d(resourceId="android:id/button1") 允许
            self.d.watcher('allowin', 5).when("权限请求").when("允许").call(
                self.permission_call_func, ('text', '允许'), ('resourceId', 'android:id/button1'))
            #这里还有个i管家 取消的按钮

        elif self.brand == 'meizu':
            # meizu
            # d(resourceId="android:id/title_template") d(resourceId="android:id/topPanel")
            # d(resourceId="android:id/button1") 允许  d(resourceId="android:id/buttonPanel")
            self.d.watcher('allowin', 5).when(
                "//*[@resource-id='android:id/title_template']").when("允许").call(
                     self.permission_call_func, ('text', '允许'), ('resourceId', 'android:id/button1'))

        elif self.brand == 'oppo':
            # oppo 权限
            self.d.watcher('allowin', 5).when(
                "//*[@resource-id='android:id/title_template']").when("允许").call(
                self.permission_call_func, ('text', '允许'), ('resourceId', 'android:id/button1'))

        else:
            return False

        self.d.watcher.start()
        return True

    # TODO  apk更新  apk安装  apk权限
    # 针对 oppo vivo 机型需要优化， 两个品牌在安装的时候，刚开始安装就出现安装完成，所有在后面要有等待过程
    def detect_start_app(self, app_info=None, app=None ,start=False, location=False): # 请求更新 以及 安装
        '''

        :param app_info: app_info = {
                                        "app_alias_name": "ju_news",
                                        "app_package_name": "com.xiangzi.jukandian",
                                    }


        :param app:{
                    'appalias': 'wechat',
                    'chinese': '微信',
                    'packagename': 'com.tencent.mm',
                    'host_url': 'http://dldir1.qq.com/weixin/android/weixin705android1440.apk',
                    'mi_url': 'https://b6.market.xiaomi.com/download/AppStore/087c84ba1fb4c3299bfc2b1cd9d5bf0315943dff0/com.tencent.mm.apk',
                    'tencent_url': 'https://d4975263df62a5727ed5f2e8637b3c74.dd.cdntips.com/imtt.dd.qq.com/16891/apk/B1E9D2F728BAD42741673019E6FC8986.apk',
                    'pan_url': None,
                    'version': '7.0.10'
                }
        :param start:
        :param location:
        :return:
        '''
        # step1 检查更新信息
        if not app_info:
            return False
        if not app:
            app = self.appinfo(appinfo=app_info)
        if not app:
            self.logger.error("appalias %s info is %s" % (app_info["app_alias_name"], app))
            return False

        self.logger.debug("appalias %s info is %s" % (app_info["app_alias_name"], app))

        if app:  #如果没有拿到请求就直接启动app看能否启动
            install =False
            try:
                info = self.d.app_info(app_info["app_package_name"])
                if info["versionName"] < app["version"]:
                    install = True
            except:
                install = True

            if install:
                # self.d.press('home')  # 回到主页面，否则可能会扰乱权限按钮的解析
                # TODO  watcher start
                urls = [app["tencent_url"], app["mi_url"],
                        app["host_url"], app["pan_url"]]
                watcher_status = self.permission_message_install()
                for url in urls:
                    try:
                        self.d.app_install(url)
                        break
                    except:
                        pass
                if watcher_status:
                    self.d.watcher.reset()

            self.logger.debug("appalias %s install completed." % (app_info["app_alias_name"]))

        if start:
            # step2 启动app， 这里非常要注意，oppo vivo
            watcher_status = self.permission_message_start()
            try:
                if self.d.app_current()["package"] == app_info["app_package_name"]:
                    self.exlude_app.append(app_info["app_package_name"])
                    self.stop_all_app()
                    self.d.app_start(app_info["app_package_name"])  # 为了防止跳到其他app上
                else:
                    self.d.press("home")
                    self.stop_all_app()
                    self.start_app(app_info,location=location)
            except:
                self.logger.error("正在运行%s, 启动失败..." % self.d.app_info(app_info["app_package_name"])['label'] )
            # time.sleep(5)  #为了防止打开app还没来得及点击权限确认按钮
            self.logger.info("正在运行%s, 启动成功..." % self.d.app_info(app_info["app_package_name"])['label'] )

            if watcher_status:
                self.d.watcher.reset()

        return app

    def subprocess(self,cmd=None):
        if not cmd:
            return None
        try:
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.wait()
            out = p.stdout.read()
            result = out.decode().strip()
            return result
        except:
            return None

    def pmlist_package(self,string=None):
        if not string:
            return []
        result = []
        for line in string.strip().split('\n'):
            if ':' not in line:
                continue
            nline = line.strip().split(':')
            result.append(nline[1].strip())
        return result


    def list_packages(self):
        try:
            result = self.subprocess(''' pm list packages -3 ''')
            result = self.pmlist_package(string=result)
            return result
        except:
            return []

    def stop_all_app(self):
        kill_pkgs = set(self.d.app_list_running()).difference(self.exlude_app)
        kill_pkgs = list(set(self.list_packages()).intersection(set(kill_pkgs)))

        if not kill_pkgs:
            return True

        for pkg in kill_pkgs:
            self.d.app_stop(pkg)
        return True

    def close_all_app(self):
        try:
            self.d.press('recent')
            if self.d(resourceId="com.android.systemui:id/clearAnimView").exists:  #小米
                self.d(resourceId="com.android.systemui:id/clearAnimView").click()
                return True
            if self.d(resourceId="com.android.systemui:id/leui_recent_clear_all_txtview").exists: #乐视
                self.d(resourceId="com.android.systemui:id/leui_recent_clear_all_txtview").click()
                return True
            if self.d(resourceId="com.android.systemui:id/clear_all_icon").exists: # meizu
                self.d(resourceId="com.android.systemui:id/clear_all_icon").click()
                return True
            if self.d(resourceId="com.coloros.recents:id/clear_button").exists:
                self.d(resourceId="com.coloros.recents:id/clear_button").click()
                return True
            if self.d(text="一键加速").exists: # vivo 机型
                self.d(text="一键加速").click()
                # time.sleep(1)
                # self.d.press('back')
                # Swipe(self.d).swipeUp_from_bottom()
                return True
            if self.d(resourceId="com.coloros.recents:id/progress_bar").exists:
                self.d(resourceId="com.coloros.recents:id/progress_bar").click()
                return True
            if self.d(resourceId="com.android.systemui:id/leui_recent_clear_all_btn").exists: #乐视 这个可能有bug，点不到
                self.d(resourceId="com.android.systemui:id/leui_recent_clear_all_btn").click()
                return True

            self.d.press('back')

            return False
        except:
            return False

    def start_app(self,app_info, location=False):

        if not self.d.device_info:
            self.logger.info("%s IP device is closed connect! reconnect again! ")
            return False

        self.close_all_app() # 点击关闭所有的app activity

        self.d.press('home')

        start_time = time.time()

        while True:
            try:
                self.d.app_start(app_info["app_package_name"])

                time.sleep(5)  # maybe is starting

                if self.d.app_current()["package"] == app_info["app_package_name"]:
                    break
            except:
                self.logger.error("Start %s error, maybe app is installing, otherwise atx is running."
                             % app_info["app_alias_name"])
                time.sleep(10)

            if time.time() - start_time >= 60:  #1分钟都没启动完就报错
                raise Exception("Start %s error, check atx is running or \
                 app is installing." % app_info["app_alias_name"])

        return True



# Example
# Phone(d, u2url='0.0.0.0:7912').detect_start_app(app_info=app_info, start=start)
