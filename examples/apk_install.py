# coding: utf-8
#
# Install problems
#
# OPPO need password

import time
import uiautomator2 as u2


def oppo_verify(u):
    password = "your-password"
    if u(packageName="com.coloros.safecenter", textContains="请验证身份后安装").exists:
        print("Auto click install")
        u.set_fastinput_ime()
        u(className='android.widget.EditText').set_text(password)
        u(className='android.widget.Button', text='安装').click()
        time.sleep(5)
        u(className='android.widget.Button', text='安装').click()
        u(className='android.widget.Button', text='完成').click()
        return True

    if u(packageName="com.android.packageinstaller", text="重新安装").click_exists():
        print("Reinstall")
        u(className='android.widget.Button', text='安装').click()
        u(className='android.widget.Button', text='完成').click()
        return True


def main():
    u = u2.connect()
    u.open_identify()
    u.app_install('https://some-gameapp.apk', installing_callback=oppo_verify)





if __name__ == '__main__':
    main()