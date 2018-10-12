# coding: utf-8
#

try:
    from lxml import etree
    LXML = True
except:
    import xml.etree.ElementTree as ET
    LXML = False


def safe_xmlstr(s):
    return s.replace("$", "-")


def xpath_findall(xpath, xml_content):
    """
    Search xml by xpath

    Returns:
        List of Element [Element...]
    """
    if LXML:
        # print(xml_content)
        root = etree.fromstring(xml_content.encode('utf-8'))
        for node in root.xpath("//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class"))
        return root.xpath(
            xpath, namespaces={"re": "http://exslt.org/regular-expressions"})
    else:
        root = ET.fromstring(xml_content)
        for node in root.findall(".//node"):
            node.tag = safe_xmlstr(node.attrib.pop("class"))
        return root.findall(xpath if xpath.startswith(".") else "." + xpath)
