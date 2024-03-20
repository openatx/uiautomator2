#!/usr/bin/env python
# -*- coding: utf-8 -*-

import threading
import time

import cv2
import numpy as np
import requests
import websocket

__version__ = "0.0.1"


class CVHandler(object):
    template_threshold = 0.95  # 模板匹配的阈值

    def show(self, img):
        ''' 显示一个图片 '''
        cv2.imshow('image', img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def imread(self, filename):
        '''
        Like cv2.imread
        This function will make sure filename exists
        '''
        im = cv2.imread(filename)
        if im is None:
            raise RuntimeError("file: '%s' not exists" % filename)
        return im

    def imdecode(self, img_data):
        '''
        Like cv2.imdecode
        This function will make sure filename exists
        直接读取从网络下载的图片数据
        '''
        im = np.asarray(bytearray(img_data), dtype="uint8")
        im = cv2.imdecode(im, cv2.IMREAD_COLOR)
        if im is None:
            raise RuntimeError("img_data is can not decode")
        return im

    def find_template(self, im_source, im_search, threshold=template_threshold, rgb=False, bgremove=False):
        '''
        @return find location
        if not found; return None
        '''
        result = self.find_all_template(im_source, im_search, threshold, 1, rgb, bgremove)
        return result[0] if result else None

    def find_all_template(self, im_source, im_search, threshold=template_threshold, maxcnt=0, rgb=False,
                          bgremove=False):
        '''
        Locate image position with cv2.templateFind

        Use pixel match to find pictures.

        Args:
            im_source(string): 图像、素材
            im_search(string): 需要查找的图片
            threshold: 阈值，当相识度小于该阈值的时候，就忽略掉

        Returns:
            A tuple of found [(point, score), ...]

        Raises:
            IOError: when file read error
        '''
        # method = cv2.TM_CCORR_NORMED
        # method = cv2.TM_SQDIFF_NORMED
        method = cv2.TM_CCOEFF_NORMED

        if rgb:
            s_bgr = cv2.split(im_search)  # Blue Green Red
            i_bgr = cv2.split(im_source)
            weight = (0.3, 0.3, 0.4)
            resbgr = [0, 0, 0]
            for i in range(3):  # bgr
                resbgr[i] = cv2.matchTemplate(i_bgr[i], s_bgr[i], method)
            res = resbgr[0] * weight[0] + resbgr[1] * weight[1] + resbgr[2] * weight[2]
        else:
            s_gray = cv2.cvtColor(im_search, cv2.COLOR_BGR2GRAY)
            i_gray = cv2.cvtColor(im_source, cv2.COLOR_BGR2GRAY)
            # 边界提取(来实现背景去除的功能)
            if bgremove:
                s_gray = cv2.Canny(s_gray, 100, 200)
                i_gray = cv2.Canny(i_gray, 100, 200)

            res = cv2.matchTemplate(i_gray, s_gray, method)
        w, h = im_search.shape[1], im_search.shape[0]

        result = []
        while True:
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            if method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            if max_val < threshold:
                break
            # calculator middle point
            middle_point = (top_left[0] + w / 2, top_left[1] + h / 2)
            result.append(dict(
                result=middle_point,
                rectangle=(top_left, (top_left[0], top_left[1] + h), (top_left[0] + w, top_left[1]),
                           (top_left[0] + w, top_left[1] + h)),
                confidence=max_val
            ))
            if maxcnt and len(result) >= maxcnt:
                break
            # floodfill the already found area
            cv2.floodFill(res, None, max_loc, (-1000,), max_val - threshold + 0.1, 1, flags=cv2.FLOODFILL_FIXED_RANGE)
        return result

    def _sift_instance(self, edge_threshold=100):
        if hasattr(cv2, 'SIFT'):
            return cv2.SIFT(edgeThreshold=edge_threshold)
        return cv2.xfeatures2d.SIFT_create(edgeThreshold=edge_threshold)

    def sift_count(self, img):
        sift = self._sift_instance()
        kp, des = sift.detectAndCompute(img, None)
        return len(kp)

    def find_sift(self, im_source, im_search, min_match_count=4):
        '''
        SIFT特征点匹配
        '''
        res = self.find_all_sift(im_source, im_search, min_match_count, maxcnt=1)
        if not res:
            return None
        return res[0]

    def find_all_sift(self, im_source, im_search, min_match_count=4, maxcnt=0):
        '''
        使用sift算法进行多个相同元素的查找
        Args:
            im_source(string): 图像、素材
            im_search(string): 需要查找的图片
            threshold: 阈值，当相识度小于该阈值的时候，就忽略掉
            maxcnt: 限制匹配的数量

        Returns:
            A tuple of found [(point, rectangle), ...]
            A tuple of found [{"point": point, "rectangle": rectangle, "confidence": 0.76}, ...]
            rectangle is a 4 points list
        '''
        sift = self._sift_instance()
        flann = cv2.FlannBasedMatcher({'algorithm': self.FLANN_INDEX_KDTREE, 'trees': 5}, dict(checks=50))

        kp_sch, des_sch = sift.detectAndCompute(im_search, None)
        if len(kp_sch) < min_match_count:
            return None

        kp_src, des_src = sift.detectAndCompute(im_source, None)
        if len(kp_src) < min_match_count:
            return None

        h, w = im_search.shape[1:]

        result = []
        while True:
            # 匹配两个图片中的特征点，k=2表示每个特征点取2个最匹配的点
            matches = flann.knnMatch(des_sch, des_src, k=2)
            good = []
            for m, n in matches:
                # 剔除掉跟第二匹配太接近的特征点
                if m.distance < 0.9 * n.distance:
                    good.append(m)

            if len(good) < min_match_count:
                break

            sch_pts = np.float32([kp_sch[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            img_pts = np.float32([kp_src[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            # M是转化矩阵
            M, mask = cv2.findHomography(sch_pts, img_pts, cv2.RANSAC, 5.0)
            matches_mask = mask.ravel().tolist()

            # 计算四个角矩阵变换后的坐标，也就是在大图中的坐标
            h, w = im_search.shape[:2]
            pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, M)

            # trans numpy arrary to python list
            # [(a, b), (a1, b1), ...]
            pypts = []
            for npt in dst.astype(int).tolist():
                pypts.append(tuple(npt[0]))

            lt, br = pypts[0], pypts[2]
            middle_point = (lt[0] + br[0]) / 2, (lt[1] + br[1]) / 2

            result.append(dict(
                result=middle_point,
                rectangle=pypts,
                confidence=(matches_mask.count(1), len(good))  # min(1.0 * matches_mask.count(1) / 10, 1.0)
            ))

            if maxcnt and len(result) >= maxcnt:
                break

            # 从特征点中删掉那些已经匹配过的, 用于寻找多个目标
            qindexes, tindexes = [], []
            for m in good:
                qindexes.append(m.queryIdx)  # need to remove from kp_sch
                tindexes.append(m.trainIdx)  # need to remove from kp_img

            def filter_index(indexes, arr):
                r = np.ndarray(0, np.float32)
                for i, item in enumerate(arr):
                    if i not in qindexes:
                        r = np.append(r, item)
                return r

            kp_src = filter_index(tindexes, kp_src)
            des_src = filter_index(tindexes, des_src)

        return result

    def find_all(self, im_source, im_search, maxcnt=0):
        '''
        优先Template，之后Sift
        @ return [(x,y), ...]
        '''
        result = self.find_all_template(im_source, im_search, maxcnt=maxcnt)
        if not result:
            result = self.find_all_sift(im_source, im_search, maxcnt=maxcnt)
        if not result:
            return []
        return [match["result"] for match in result]

    def find(self, im_source, im_search):
        '''
        Only find maximum one object
        '''
        r = self.find_all(im_source, im_search, maxcnt=1)
        return r[0] if r else None

    def brightness(self, im):
        '''
        Return the brightness of an image
        Args:
            im(numpy): image

        Returns:
            float, average brightness of an image
        '''
        im_hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(im_hsv)
        height, weight = v.shape[:2]
        total_bright = 0
        for i in v:
            total_bright = total_bright + sum(i)
        return float(total_bright) / (height * weight)


class Aircv(object):
    timeout = 30
    wait_before_operation = 1  # 操作前等待时间 秒
    rcv_interval = 2  # 接收图片的间隔时间 秒
    # temporary_directory = "./"  # 临时保存截图的目录路径
    support_network = False  # 是否启用网络下载图片
    url = ""
    host = "127.0.0.1:8000"
    path = "/image_service/download/"

    def __init__(self, d):
        self.__rcv_interva_time_cache = 0

        self.d = d
        self.cvHandler = CVHandler()
        self.FLANN_INDEX_KDTREE = 0
        # self.aircv_cache_image_name = Aircv.temporary_directory + self.d._host + "_aircv_cache_image.jpg"
        self.debug = True
        self.aircv_cache_image = None
        self.ws_screen = None
        self.zoom_out = None
        # 下面三个函数放在最后，而且顺序不能变
        self.detection_screen()
        self.start_get_screen()
        self.get_scaling_ratio()

    def detection_screen(self):
        """检测设备屏幕比例，必须为 16:9"""
        display_height = self.d.info['displayHeight']
        display_width = self.d.info['displayWidth']
        if display_height / display_width != 16 / 9 and display_width / display_height != 16 / 9:
            raise RuntimeError("Does not support current mobile phones, The screen ratio is not 16:9")

    def get_scaling_ratio(self):
        """计算缩放比"""
        while True:
            if self.aircv_cache_image is not None:
                self.zoom_out = 1.0 * self.d.info['displayHeight'] / self.aircv_cache_image.shape[0]
                break

    def start_get_screen(self):

        def on_message(ws, message):
            this = self
            if isinstance(message, bytes):

                if int(time.time()) - this.__rcv_interva_time_cache >= Aircv.rcv_interval:
                    # with open(this.aircv_cache_image_name, 'wb') as f:
                    #     f.write(message)
                    # this.aircv_cache_image = this.cvHandler.imread(self.aircv_cache_image_name)
                    this.aircv_cache_image = this.cvHandler.imdecode(message)
                    this.__rcv_interva_time_cache = int(time.time())

        def on_error(ws, error):
            raise RuntimeError(error)

        def on_close(ws):
            print("### ws_screen closed ###")

        def on_open(ws):
            print("### ws_screen on_open ###")

        if not self.ws_screen or not self.ws_screen.keep_running:
            self.ws_screen = websocket.WebSocketApp("ws://" + self.d._host + ":" + str(self.d._port) + "/minicap",
                                                    on_open=on_open,
                                                    on_message=on_message,
                                                    on_error=on_error,
                                                    on_close=on_close)
            ws_thread = threading.Thread(target=self.ws_screen.run_forever)
            ws_thread.daemon = True
            ws_thread.start()

    def stop_get_scren(self):
        if self.ws_screen and self.ws_screen.keep_running:
            self.ws_screen.close()

    # operating
    def find_template_by_crop(self, img, area=None):
        if Aircv.support_network:
            img_url = "".join(["http://", Aircv.host, Aircv.path, img])
            data = requests.get(img_url)
            img_serch = self.cvHandler.imdecode(data.content)
        else:
            img_serch = self.cvHandler.imread(img)
        if area:
            crop_img = self.aircv_cache_image[area[1]:area[3], area[0]:area[2]]
            result = self.cvHandler.find_template(crop_img, img_serch)
            point = result['result'] if result else None
            if point:
                point = (point[0] + area[0], point[1] + area[1])
        else:
            crop_img = self.aircv_cache_image
            result = self.cvHandler.find_template(crop_img, img_serch)
            point = result['result'] if result else None

        return (int(point[0] * self.zoom_out), int(point[1] * self.zoom_out)) if point else None

    def exists(self, img, timeout=timeout, area=None):
        point = None
        is_exists = False
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                point = self.find_template_by_crop(img, area)
            if point:
                is_exists = True
                break
            else:
                timeout -= 1
                time.sleep(1)
        return is_exists

    def click(self, img, timeout=timeout, area=None):
        point = None
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                point = self.find_template_by_crop(img, area)
            if point:
                time.sleep(Aircv.wait_before_operation)
                self.d.click(point[0], point[1])
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')

    def click_index(self, img, index=1, maxcnt=20, timeout=timeout):
        point = None
        img_serch = self.cvHandler.imread(img)
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                result_list = self.cvHandler.find_all_template(self.aircv_cache_image, img_serch, maxcnt=maxcnt)
                point = result_list[index - 1]['result'] if result_list else None
            if point:
                time.sleep(Aircv.wait_before_operation)
                self.d.click(point[0], point[1])
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')

    def long_click(self, img, duration=None, timeout=timeout, area=None):
        point = None
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                point = self.find_template_by_crop(img, area)
            if point:
                time.sleep(Aircv.wait_before_operation)
                self.d.long_click(point[0], point[1], duration)
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')

    def swipe(self, img_from, img_to, duration=0.1, steps=None, timeout=timeout, area=None):
        point_from = None
        point_to = None
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                point_from = self.find_template_by_crop(img_from, area)
                point_to = self.find_template_by_crop(img_to, area)
            if point_from and point_to:
                time.sleep(Aircv.wait_before_operation)
                self.d.swipe(point_from[0], point_from[1], point_to[0], point_to[1], duration, steps)
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')

    def swipe_points(self, img_list, duration=0.5, timeout=timeout, area=None):
        point_list = []
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                for img in img_list:
                    point = self.find_template_by_crop(img, area)
                    if not point:
                        break
                    point_list.append(point)
            if len(point_list) == len(img_list):
                time.sleep(Aircv.wait_before_operation)
                self.d.swipe_points(point_list, duration)
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')

    def drag(self, img_from, img_to, duration=0.1, steps=None, timeout=timeout, area=None):
        point_from = None
        point_to = None
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                point_from = self.find_template_by_crop(img_from, area)
                point_to = self.find_template_by_crop(img_to, area)
            if point_from and point_to:
                time.sleep(Aircv.wait_before_operation)
                self.d.drag(point_from[0], point_from[1], point_to[0], point_to[1], duration, steps)
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')

    def get_point(self, img, timeout=timeout, area=None):
        point = None
        while timeout:
            if self.debug:
                print(timeout)
            if self.aircv_cache_image is not None:
                point = self.find_template_by_crop(img, area)
            if point:
                break
            else:
                timeout -= 1
                time.sleep(1)
            if not timeout:
                raise RuntimeError('No image found')
        return point



