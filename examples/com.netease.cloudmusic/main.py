# coding: utf-8

import uiautomator2 as u2


def main():
    u = u2.connect_usb()
    u.app_start('com.netease.cloudmusic')
    u(text='私人FM').click()
    u(description='转到上一层级').click()
    u(text='每日推荐').click()
    u(description='转到上一层级').click()
    u(text='歌单').click()
    u(description='转到上一层级').click()
    u(text='排行榜').click()
    u(description='转到上一层级').click()

if __name__ == '__main__':
    main()