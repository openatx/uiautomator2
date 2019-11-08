# coding: utf-8
#
import re
from collections import defaultdict, namedtuple
from pprint import pprint
from typing import Union

import requests
from lxml import etree

import uiautomator2 as u2


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
                print(bounds)
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
    print("Same count:", same_count, len(ns1), len(ns2))
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


class Easy(object):
    def __init__(self, d: u2.Device):
        self._d = d
        self._widgets = {}

    def _get_widget(self, id: str):
        if id in self._widgets:
            return self._widgets[id]
        r = requests.get(f"http://localhost:17310/api/v1/widgets/{id}")
        data = r.json()
        self._widgets[id] = data
        return data

    def match(self, id: str):
        w = self._get_widget(id)
        print(w['activity'])
        same_activity = w['activity'] == self._d.app_current()['activity']
        hierarchy = self._d.dump_hierarchy()
        hsim = hierarchy_sim(hierarchy, w['hierarchy'])
        print("hierarchy:", hsim)

        node_scores = defaultdict(int)
        scores = defaultdict(dict)
        nodes = []

        root = etree.fromstring(hierarchy.encode('utf-8'))

        for node in root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class"))
            nodes.append(node)

            if same_activity:
                scores[node]['activity'] = 1
                node_scores[node] += 1

            for node_key, widget_key in [('text', 'text'),
                                         ('resource-id', 'resource_id'),
                                         ('content-desc', "description")]:
                if node.attrib.get(node_key) == w.get(widget_key):
                    v = 1 if w[widget_key] else 0.5
                    scores[node][node_key] = v
                    node_scores[node] += v

            lx, ly, rx, ry = map(
                int, re.findall(r"(\d+)", node.attrib.get("bounds")))

            window_width, window_height = map(int, w['window_size'])
            target_width, target_height = w['target_size']
            pwidth, pheight = target_width / window_width, target_height / window_height

            if w['target_size'] == [rx - lx, ry - ly]:
                scores[node]['size'] = 1
                node_scores[node] += 1

            cx, cy = w['center_point']
            if lx < cx < rx and ly < cy < ry:
                scores[node]['point'] = 0.5
                node_scores[node] += 0.5

        xpath_matches = root.xpath(
            w['xpath'],
            namespaces={"re": "http://exslt.org/regular-expressions"})
        for node in xpath_matches:
            scores[node]['xpath'] = 1
            node_scores[node] += 1

        top, second = sorted(node_scores.items(), key=lambda v: -v[1])[:2]
        print(top, second)
        node, score = top[0], top[1]
        # score /= 6
        lx, ly, rx, ry = map(int,
                             re.findall(r"(\d+)", node.attrib.get("bounds")))
        x, y = (lx + rx) // 2, (ly + ry) // 2

        print((x, y), score)
        print("xpath:", etree.ElementTree(root).getpath(node))
        print("------------------")
        widget = w.copy()
        widget.pop("hierarchy", None)
        return namedtuple("Result",
                          ['node', 'point', 'score', 'detail', 'widget'])(
                              node, (x, y), score, scores[node], widget)
        # if score < 5:
        #     return None
        # return (x, y)

    def click(self, id: str):
        result = self.match(id)
        print("result", result)
        # self._d.click(x, y)


if __name__ == "__main__":
    d = u2.connect()
    e = Easy(d)
    e.match("00001")
    e.match("00002")
    result = e.match("00007")
    from uiautomator2.image import draw_point
    x, y = result.point
    pprint(result.widget)
    pprint(dict(result.node.attrib))
    pprint(result.detail)
    im = draw_point(d.screenshot(), x, y)
    im.save("s.jpg")
    if result.score > 5:
        d.click(x, y)

if __name__ == "__main__ff":
    element = {
        "ocr_text": "雨伞",
        "resource_id": "",
        "text": "雨伞",
        "description": "",
        "target_size": [150, 96],
        "device_size": [1080, 1920],
        "center_point": (0.106, 0.227),
        "xpath_no_index":
        "//android.view.ViewGroup/android.widget.FrameLayout/android.widget.TextView",
        "package": "com.taobao.taobao",
        "activity": "com.taobao.search.searchdoor.SearchDoorActivity",
        "hierarchy":
        "http://tmallwireless-ycombinator.cn-hangzhou.oss-cdn.aliyun-inc.com/b0cf0228/page.xml",
        "rotation": 0,
        "target_image": {
            "device_size": [1080, 1920],
            "url":
            "http://tmallwireless-ycombinator.cn-hangzhou.oss-cdn.aliyun-inc.com/0e8afe6c/umbrella.jpg",
        },
        # "target_image": "http://tmallwireless-ycombinator.cn-hangzhou.oss-cdn.aliyun-inc.com/0e8afe6c/umbrella.jpg",
        "device_image": {
            "device_size": [1080, 1920],
            "url":
            "http://tmallwireless-ycombinator.cn-hangzhou.oss-cdn.aliyun-inc.com/4ba6a631/screenshot.jpg",
        }
    }

    # 确认是否当前页面
    current_xml = d.dump_hierarchy().encode('utf-8')
    target_xml = requests.get(element['hierarchy']).content

    xml_sim = hierarchy_sim(current_xml, target_xml)
    print("hierarchy_sim:", xml_sim)

    # 确认组件
    root = etree.fromstring(current_xml)

    nodes = []
    text_matches = []
    desc_matches = []
    id_matches = []

    node_scores = defaultdict(int)

    for node in root.xpath("//node"):
        node.tag = safe_xmlstr(node.attrib.pop("class"))
        nodes.append(node)

        # print(node.attrib)
        if node.attrib.get("text") == element['text']:
            print("Text matches")
            node_scores[node] += 1

        if node.attrib.get("resource-id") == element['resource_id']:
            # print("resource id matches")
            node_scores[node] += 1

        if node.attrib.get("content-desc") == element['description']:
            node_scores[node] += 1

    xpath_matches = root.xpath(
        element['xpath_no_index'],
        namespaces={"re": "http://exslt.org/regular-expressions"})
    for node in xpath_matches:
        node_scores[node] += 1

    for n in sorted(node_scores.items(), key=lambda v: -v[1])[:10]:
        print(n)

    # elements = []
    # for _, node in etree.iterwalk(root):
    #     if "class" not in node.attrib:
    #         continue
    #     node.tag = safe_xmlstr(node.attrib.pop("class"))
    #     elements.append(node)

    # _xml_elements = d.xpath(element['xpath_no_index'], source=current_xml).all()
    # xpath_matched = {e.elem for e in _xml_elements}
    # xpath_elms = {e.elem for e in _xml_elements}

    # print(elements[0], list(xpath_elms)[0])
    # print(len(xpath_elms), len(xpath_elms.intersection(elements)))

    print(
        "text exists:",
        d.xpath('//*[@text="{}"]'.format(element['text']),
                source=current_xml).exists)
    app_current = d.app_current()
    print("activity:", app_current['activity'] == element['activity'])
    print(
        "text exists:",
        d.xpath('//*[@content-desc="{}"]'.format(element['description']),
                source=current_xml).exists)

# resource_id = ""
# class_name = "android.widget.ImageView"
# xpath_no_index = "//android.widget.FrameLayout/android.widget.LinearLayout//android.widget.FrameLayout/android.widget.ImageView"
# rect = [329, 600, 186, 186]
# image = "shoes.jpg"
# point = [0.4, 0.336]
# # epx, epy = 329 + 93, 693

# while True:
#     h2_content = d.dump_hierarchy().encode('utf-8')
#     p = percent_same_xml(read_file_content("hierarchy.xml"), h2_content)

#     print("Percent:", p)
