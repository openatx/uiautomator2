# coding: utf-8
#
#  DEPRECATED
#
#  This file is deprecated and will be removed in the future.
import logging
import re
import time
from collections import defaultdict, namedtuple
from functools import partial
from pprint import pprint
from typing import Union

import requests
from lxml import etree

import uiautomator2 as u2
from uiautomator2.image import compare_ssim, draw_point, imread

logger = logging.getLogger(__name__)


def xml2nodes(xml_content: Union[str, bytes]):
    if isinstance(xml_content, str):
        xml_content = xml_content.encode("utf-8")

    root = etree.fromstring(xml_content)
    nodes = []
    for _, n in etree.iterwalk(root):
        attrib = dict(n.attrib)
        if "bounds" in attrib:
            bounds = re.findall(r"(\d+)", attrib.pop("bounds"))
            if len(bounds) != 4:
                continue
            lx, ly, rx, ry = map(int, bounds)
            attrib['size'] = (rx - lx, ry - ly)
        attrib.pop("index", None)

        ok = False
        for attrname in ("text", "resource-id", "content-desc"):
            if attrname in attrib:
                ok = True
                break
        if ok:
            items = []
            for k, v in sorted(attrib.items()):
                items.append(k + ":" + str(v))
            nodes.append('|'.join(items))
    return nodes


def hierarchy_sim(xml1: str, xml2: str):
    ns1 = xml2nodes(xml1)
    ns2 = xml2nodes(xml2)

    from collections import Counter
    c1 = Counter(ns1)
    c2 = Counter(ns2)

    same_count = sum(
        [min(c1[k], c2[k]) for k in set(c1.keys()).intersection(c2.keys())])
    logger.debug("Same count: %d ns1: %d ns2: %d", same_count, len(ns1), len(ns2))
    return same_count / (len(ns1) + len(ns2)) * 2


def read_file_content(filename: str) -> bytes:
    with open(filename, "rb") as f:
        return f.read()


def safe_xmlstr(s):
    return s.replace("$", "-")


def frozendict(d: dict):
    items = []
    for k, v in sorted(d.items()):
        items.append(k + ":" + str(v))
    return '|'.join(items)


CompareResult = namedtuple("CompareResult", ["score", "detail"])
Point = namedtuple("Point", ['x', 'y'])


class Widget(object):
    __domains = {
        "lo": "http://localhost:17310",
    }

    def __init__(self, d: "u2.Device"):
        self._d = d
        self._widgets = {}
        self._compare_results = {}

        self.popups = []

    @property
    def wait_timeout(self):
        return self._d.settings['wait_timeout']

    def _get_widget(self, id: str):
        if id in self._widgets:
            return self._widgets[id]
        widget_url = self._id2url(id)
        r = requests.get(widget_url, timeout=3)
        data = r.json()
        self._widgets[id] = data
        return data

    def _id2url(self, id: str):
        fields = re.sub("#.*", "", id).split(
            "/")  # remove chars after # and split host and id
        assert len(fields) <= 2
        if len(fields) == 1:
            return f"http://localhost:17310/api/v1/widgets/{id}"

        host = self.__domains.get(fields[0])
        id = fields[1]  # ignore the third part
        if not re.match("^https?://", host):
            host = "http://" + host
        return f"{host}/api/v1/widgets/{id}"

    def _eq(self, precision: float, a, b):
        return abs(a - b) < precision

    def _percent_equal(self, precision: float, a, b, asize, bsize):
        return abs(a / min(asize) - b / min(bsize)) < precision

    def _bounds2rect(self, bounds: str):
        """
        Returns:
            tuple: (lx, ly, width, height)
        """
        if not bounds:
            return 0, 0, 0, 0
        lx, ly, rx, ry = map(int, re.findall(r"\d+", bounds))
        return (lx, ly, rx - lx, ry - ly)

    def _compare_node(self, node_a, node_b, size_a, size_b) -> float:
        """
        Args:
            node_a, node_b: etree.Element
            size_a, size_b: tuple size
        
        Returns:
            CompareResult
        """
        result_key = (node_a, node_b)
        if result_key in self._compare_results:
            return self._compare_results[result_key]

        scores = defaultdict(dict)

        # max 1
        if node_a.tag == node_b.tag:
            scores['class'] = 1

        # max 3
        for key in ('text', 'resource-id', 'content-desc'):
            if node_a.attrib.get(key) == node_b.attrib.get(key):
                scores[key] = 1 if node_a.attrib.get(key) else 0.1

        # bounds = node_a.attrib.get("bounds")
        # pprint(list(map(int, re.findall(r"\d+", bounds))))
        ax, ay, aw, ah = self._bounds2rect(node_a.attrib.get("bounds"))
        bx, by, bw, bh = self._bounds2rect(node_b.attrib.get("bounds"))

        # max 2
        peq = partial(self._percent_equal, 1 / 20, asize=size_a, bsize=size_b)
        if peq(ax, bx) and peq(ay, by):
            scores['left_top'] = 1
        if peq(aw, bw) and peq(ah, bh):
            scores['size'] = 1

        score = round(sum(scores.values()), 1)
        result = self._compare_results[result_key] = CompareResult(
            score, scores)
        return result

    def node2string(self, node: etree.Element):
        return node.tag + ":" + '|'.join([
            node.attrib.get(key, "")
            for key in ["text", "resource-id", "content-desc"]
        ])

    def hybird_compare_node(self, node_a, node_b, size_a, size_b):
        """
        Returns:
            (scores, results)
        
        Return example:
            【3.0, 3.2], [CompareResult(score=3.0), CompareResult(score=3.2)]
        """
        cmp_node = partial(self._compare_node, size_a=size_a, size_b=size_b)

        results = []

        results.append(cmp_node(node_a, node_b))
        results.append(cmp_node(node_a.getparent(), node_b.getparent()))

        a_children = node_a.getparent().getchildren()
        b_children = node_b.getparent().getchildren()
        if len(a_children) != len(b_children):
            return results

        children_result = []
        a_children.remove(node_a)
        b_children.remove(node_b)
        for i in range(len(a_children)):
            children_result.append(cmp_node(a_children[i], b_children[i]))
        results.append(children_result)
        return results

    def _hybird_result_to_score(self, obj: Union[list, CompareResult]):
        """
        Convert hybird_compare_node returns to score
        """
        if isinstance(obj, CompareResult):
            return obj.score
        ret = []
        for item in obj:
            ret.append(self._hybird_result_to_score(item))
        return ret

    def replace_etree_node_to_class(self, root: etree.ElementTree):
        for node in root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class", "") or "node")
        return root

    def compare_hierarchy(self, node, root, node_wsize, root_wsize):
        results = {}
        for node2 in root.xpath("/hierarchy//*"):
            result = self.hybird_compare_node(node, node2, node_wsize, root_wsize)
            results[node2] = result  #score
        return results

    def etree_fromstring(self, s: str):
        root = etree.fromstring(s.encode('utf-8'))
        return self.replace_etree_node_to_class(root)

    def node_center_point(self, node) -> Point:
        lx, ly, rx, ry = map(int, re.findall(r"\d+",
                                             node.attrib.get("bounds")))
        return Point((lx + rx) // 2, (ly + ry) // 2)

    def match(self, widget: dict, hierarchy=None, window_size: tuple = None):
        """
        Args:
            widget: widget id
            hierarchy (optional): current page hierarchy
            window_size (tuple): width and height

        Returns:
            None or MatchResult(point, score, detail, xpath, node, next_result)
        """
        window_size = window_size or self._d.window_size()
        hierarchy = hierarchy or self._d.dump_hierarchy()
        w = widget.copy()

        widget_root = self.etree_fromstring(w['hierarchy'])
        widget_node = widget_root.xpath(w['xpath'])[0]

        # 节点打分
        target_root = self.etree_fromstring(hierarchy)
        results = self.compare_hierarchy(widget_node, target_root, w['window_size'], window_size) # yapf: disable

        # score结构调整
        scores = {}
        for node, result in results.items():
            scores[node] = self._hybird_result_to_score(result) # score eg: [3.2, 2.2, [1.0, 1.2]]

        # 打分排序
        nodes = list(scores.keys())
        nodes.sort(key=lambda n: scores[n], reverse=True)
        possible_nodes = nodes[:10]
        
        # compare image
        # screenshot = self._d.screenshot()
        # for node in possible_nodes:
        #     bounds = node.attrib.get("bounds")
        #     lx, ly, rx, ry = bounds = list(map(int, re.findall(r"\d+", bounds)))
        #     w, h = rx - lx, ry - ly
        #     crop_image = screenshot.crop(bounds)
        #     template = imread(w['target_image']['url'])
        #     try:
        #         score = compare_ssim(template, crop_image)
        #         scores[node][0] += score
        #     except ValueError:
        #         pass
        # nodes.sort(key=lambda n: scores[n], reverse=True)

        first, second = nodes[:2]

        MatchResult = namedtuple(
            "MatchResult",
            ["point", "score", "detail", "xpath", "node", "next_result"])

        def get_result(node, next_result=None):
            point = self.node_center_point(node)
            xpath = node.getroottree().getpath(node)
            return MatchResult(point, scores[node], results[node], xpath,
                               node, next_result)

        return get_result(first, get_result(second))

    def exists(self, id: str) -> bool:
        pass

    def update_widget(self, id, hierarchy, xpath):
        url = self._id2url(id)
        r = requests.put(url, json={"hierarchy": hierarchy, "xpath": xpath})
        print(r.json())

    def wait(self, id: str, timeout=None):
        """
        Args:
            timeout (float): seconds to wait

        Returns:
            None or Result
        """
        timeout = timeout or self.wait_timeout
        widget = self._get_widget(id) # 获取节点信息

        begin_time = time.time()
        deadline = time.time() + timeout

        while time.time() < deadline:
            hierarchy = self._d.dump_hierarchy()
            hsim = hierarchy_sim(hierarchy, widget['hierarchy'])

            app = self._d.app_current()
            is_same_activity = widget['activity'] == app['activity']
            if not is_same_activity:
                print("activity different:", "got", app['activity'], 'expect', widget['activity'])
            print("hierarchy: %.1f%%" % hsim)
            print("----------------------")

            window_size = self._d.window_size()

            page_ok = False
            if is_same_activity:
                if hsim > 0.7:
                    page_ok = True
                if time.time() - begin_time > 10.0 and hsim > 0.6:
                    page_ok = True

            if page_ok:
                result = self.match(widget, hierarchy, window_size)
                if result.score[0] < 2:
                    time.sleep(0.5)
                    continue

                if hsim < 0.8:
                    self.update_widget(id, hierarchy, result.xpath)
                return result
            time.sleep(1.0)

    def click(self, id: str, debug: bool = False, timeout=10):
        print("Click", id)

        result = self.wait(id, timeout=timeout)
        if result is None:
            raise RuntimeError("target not found")

        x, y = result.point
        if debug:
            show_click_position(self._d, Point(x, y))
        self._d.click(x, y)
        # return

        # while True:
        #     hierarchy = self._d.dump_hierarchy()
        #     hsim = hierarchy_sim(hierarchy, widget['hierarchy'])

        #     app = self._d.app_current()
        #     is_same_activity = widget['activity'] == app['activity']

        #     print("activity same:", is_same_activity)
        #     print("hierarchy:", hsim)

        #     window_size = self._d.window_size()

        #     if is_same_activity and hsim > 0.8:
        #         result = self.match(widget, hierarchy, window_size)
        #         pprint(result.score)
        #         pprint(result.second.score)
        #         x, y = result.point
        #         self._d.click(x, y)
        #         return
        #     time.sleep(0.1)
        # return


def show_click_position(d: u2.Device, point: Point):
    # # pprint(result.widget)
    # # pprint(dict(result.node.attrib))
    im = draw_point(d.screenshot(), point.x, point.y)
    im.show()


def main():
    d = u2.connect("30.10.93.26")

    # d.widget.click("00013#推荐歌单第一首")

    d.widget.exists("lo/00019#播放全部")
    return

    d.widget.click("00019#播放全部")
    # d.widget.click("00018#播放暂停")
    d.widget.click("00018#播放暂停")
    d.widget.click("00021#转到上一层级")
    return

    d.widget.click("每日推荐")
    widget_id = "00009#上新"
    widget_id = "00011#每日推荐"
    widget_id = "00014#立减20"
    result = d.widget.match(widget_id)
    # e = Widget(d)
    # result = e.match("00003")
    # print(result)
    # # e.match("00002")
    # # result = e.match("00007")

    wsize = d.window_size()
    from lxml import etree

    result = d.widget.match(widget_id)
    pprint(result.node.attrib)
    pprint(result.score)
    pprint(result.detail)

    show_click_position(d, result.point)
    return

    root = etree.parse(
        '/Users/shengxiang/Projects/weditor/widgets/00010/hierarchy.xml')
    nodes = root.xpath('/hierarchy/node/node/node/node')
    a, b = nodes[0], nodes[1]
    result = d.widget.hybird_compare_node(a, b, wsize, wsize)
    pprint(result)
    score = d.widget._hybird_result_to_score(result)
    pprint(score)
    return

    score = d.widget._compare_node(a, b, wsize, wsize)
    print(score)

    a, b = nodes[0].getparent(), nodes[1].getparent()
    score = d.widget._compare_node(a, b, wsize, wsize)
    pprint(score)

    return

    print("score:", result.score)
    x, y = result.point
    # # pprint(result.widget)
    # # pprint(dict(result.node.attrib))
    pprint(result.detail)
    im = draw_point(d.screenshot(), x, y)
    im.show()


if __name__ == "__main__":
    main()
