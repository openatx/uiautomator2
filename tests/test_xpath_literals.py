import pytest
from lxml import etree

from uiautomator2.xpath import PageSource, XPath, string_quote

LITERAL_VALUES = [
    pytest.param("Settings", id="plain"),
    pytest.param("don't", id="single-quote"),
    pytest.param('say "yes"', id="double-quote"),
    pytest.param('He said "don\'t"', id="both-quotes"),
    pytest.param(r"C:\temp", id="backslash"),
    pytest.param("line1\nline2", id="newline"),
    pytest.param("设置", id="unicode"),
]


def make_source(attribute, values):
    root = etree.Element("hierarchy")
    for index, value in enumerate(values):
        node = etree.SubElement(root, "node", {
            "class": "android.widget.TextView",
            "index": str(index),
            "text": "",
            "content-desc": "",
            "resource-id": "",
        })
        node.set(attribute, value)
    source = PageSource(etree.tostring(root, encoding="unicode"))
    # XML attribute normalization must not change the test input.
    assert [node.get(attribute) for node in source.root] == values
    return source


@pytest.mark.parametrize("value", LITERAL_VALUES)
@pytest.mark.parametrize("attribute", ["text", "content-desc"])
@pytest.mark.parametrize("mode", ["exact", "contains", "prefix", "suffix"])
def test_xpath_text_shorthand_preserves_literals(value, attribute, mode):
    if mode == "exact":
        selector = value
        values = [value, value + "after", "before" + value]
    elif mode == "contains":
        selector = "%" + value + "%"
        values = ["before" + value + "after", "unrelated", value[:-1]]
    elif mode == "prefix":
        selector = value + "%"
        values = [value + "after", "before" + value, value[:-1]]
    else:
        selector = "%" + value
        values = ["before" + value, value + "after", value[:-1]]

    source = make_source(attribute, values)
    assert [element.attrib["index"] for element in XPath(selector).all(source)] == ["0"]


@pytest.mark.parametrize("value", LITERAL_VALUES)
def test_xpath_resource_id_shorthand_preserves_literals(value):
    source = make_source("resource-id", [value, value + "after", "before" + value])
    # A text match alone must not satisfy the resource-id shorthand.
    source.root[1].set("text", value)
    assert [element.attrib["index"] for element in XPath("@" + value).all(source)] == ["0"]


@pytest.mark.parametrize("attribute", ["text", "content-desc", "resource-id"])
@pytest.mark.parametrize("pattern, matching, nonmatching", [
    pytest.param(r"^A\d+$", "A123", "Aletters", id="digit-escape"),
    pytest.param(r"^C:\\temp$", r"C:\temp", "C:temp", id="literal-backslash"),
    pytest.param('^He said "don\'t"$', 'He said "don\'t"', "He said dont", id="both-quotes"),
    pytest.param("^line1\nline2$", "line1\nline2", r"line1\nline2", id="newline"),
    pytest.param("^Settings$", "Settings", "Other", id="plain"),
])
def test_xpath_regex_shorthand_preserves_pattern(pattern, matching, nonmatching, attribute):
    source = make_source(attribute, [matching, nonmatching])
    assert [element.attrib["index"] for element in XPath(pattern).all(source)] == ["0"]


@pytest.mark.parametrize("value", ["", "'", '"', "'\"'", "a''\"b", "\t\r\n"])
def test_string_quote_roundtrip(value):
    assert etree.Element("root").xpath(string_quote(value)) == value
