# uiautomator2 XPath Extension

[📖 阅读中文版](XPATH_CN.md)

Before using this plugin, you need to understand some XPath knowledge. Fortunately, there are many convenient resources available online. Below are some examples:

- [W3CSchool XPath Tutorial](http://www.w3school.com.cn/xpath/index.asp)
- [XPath Tutorial](http://www.zvon.org/xxl/XPathTutorial/)
- [Ruan Yifeng’s XPath Learning Notes](http://www.ruanyifeng.com/blog/2009/07/xpath_path_expressions.html)
- [Website for Testing XPath](https://www.freeformatter.com/xpath-tester.html)
- [XPath Tester](https://extendsclass.com/xpath-tester.html)

The code has not been fully tested and may still have bugs. Feedback is welcome.

## How It Works

1. Use the `dump_hierarchy` interface from the `uiautomator2` library to obtain the current UI screen (a comprehensive XML).
2. Then use the `lxml` library to parse and search for matching XPath expressions, and perform click operations using the `click` command.

> Currently, `lxml` only supports XPath 1.0. If anyone knows how to support XPath 2.0, please let me know.

**Popup Monitoring Principle**

The hierarchy provides information about all elements on the screen (including popups and buttons to be clicked). Suppose there are two popup buttons: `Skip` and `Got It`. The button to be clicked is `Play`.

1. Obtain the current screen’s XML (using the `dump_hierarchy` function).
2. Check if the `Skip` or `Got It` buttons are present. If they are, click them and return to step 1.
3. Check if the `Play` button is present. If it is, click it and finish. If not found, return to step 1 and keep executing until the search attempts exceed the limit.

## Installation

```bash
pip3 install -U uiautomator2
```

## Usage

### Simple Usage

Check out the following simple example to understand how to use it:

```python
import uiautomator2 as u2

def main():
    d = u2.connect()
    d.app_start("com.netease.cloudmusic", stop=True)

    d.xpath('//*[@text="Private FM"]').click()
    
    #
    # Advanced Usage (Element Positioning)
    #

    # Starting with @
    d.xpath('@personal-fm') # Equivalent to d.xpath('//*[@resource-id="personal-fm"]')
    
    # Multiple condition positioning, similar to AND
    d.xpath('//android.widget.Button').xpath('//*[@text="Private FM"]')
    
    d.xpath('//*[@text="Private FM"]').parent() # Position to the parent element
    d.xpath('//*[@text="Private FM"]').parent("@android:list") # Position to the parent element that meets the condition

    # When using child, it is not recommended to use multiple condition XPath because it can be confusing
    d.xpath('@android:id/list').child('/android.widget.TextView').click()
    # Equivalent to the following
    # d.xpath('//*[@resource-id="android:id/list"]/android.widget.TextView').click()
```

> For convenience, the following code does not include `import` and `main`. It is assumed that the variable `d` exists.

### Operations of `XPathSelector`

```python
sl = d.xpath("@com.example:id/home_searchedit") # sl is an XPathSelector object

# Click
sl.click()
sl.click(timeout=10) # Specify a timeout, throws XPathElementNotFoundError if not found
sl.click_exists() # Click if exists, returns whether the click was successful
sl.click_exists(timeout=10) # Wait up to 10 seconds

sl.match() # Returns None if not matched, otherwise returns an XMLElement

# Wait for the corresponding element to appear, returns XMLElement
# The default waiting time is 10 seconds
el = sl.wait()
el = sl.wait(timeout=15) # Wait for 15 seconds, returns None if not found

# Wait for the element to disappear
sl.wait_gone()
sl.wait_gone(timeout=15) 

# Similar to wait, but throws XPathElementNotFoundError if not found
el = sl.get() 
el = sl.get(timeout=15)

# Change the default waiting time to 15 seconds
d.xpath.global_set("timeout", 15)
d.xpath.implicitly_wait(15) # Equivalent to the previous line (TODO: Removed)

print(sl.exists) # Returns whether it exists (bool)
sl.get_last_match() # Get the last matched XMLElement

sl.get_text() # Get the component name
sl.set_text("") # Clear the input box
sl.set_text("hello world") # Input "hello world" into the input box

# Iterate through all matched elements
for el in d.xpath('//android.widget.EditText').all():
    print("rect:", el.rect) # Output tuple: (x, y, width, height)
    print("center:", el.center())
    el.click() # Click operation
    print(el.elem) # Output the Node parsed by lxml
    print(el.text)

# Child operation
d.xpath('@android:id/list').child('/android.widget.TextView').click()
# Equivalent to d.xpath('//*[@resource-id="android:id/list"]/android.widget.TextView').all()
```

### Advanced Search Syntax

> Added in version 3.1

```python
# Find text=NFC AND id=android:id/item
(d.xpath("NFC") & d.xpath("@android:id/item")).get()

# Find text=NFC OR id=android:id/item
(d.xpath("NFC") | d.xpath("App") | d.xpath("Content")).get()

# Supports more complex queries
((d.xpath("NFC") | d.xpath("@android:id/item")) & d.xpath("//android.widget.TextView")).get()
```

### Operations of `XMLElement`

```python
# The object returned by XPathSelector.get() is called XMLElement
el = d.xpath("@com.example:id/home_searchedit").get()

lx, ly, width, height = el.rect # Get the top-left coordinates and size
lx, ly, rx, ry = el.bounds # Top-left and bottom-right coordinates
x, y = el.center() # Get the element’s center position
x, y = el.offset(0.5, 0.5) # Same as center()

# Send click
el.click()

# Print text content
print(el.text) 

# Get the attributes within the group, as a dict
print(el.attrib)

# Take a screenshot of the control (the principle is to take a full screenshot first, then crop)
el.screenshot()

# Swipe the control
el.swipe("right") # left, right, up, down
el.swipe("right", scale=0.9) # scale defaults to 0.9, meaning the swipe distance is 90% of the control's width. Swiping up uses 90% of the height.

print(el.info)
# Output example
{
 'index': '0',
 'text': '',
 'resourceId': 'com.example:id/home_searchedit',
 'checkable': 'true',
 'checked': 'true',
 'clickable': 'true',
 'enabled': 'true',
 'focusable': 'false',
 'focused': 'false',
 'scrollable': 'false',
 'longClickable': 'false',
 'password': 'false',
 'selected': 'false',
 'visibleToUser': 'true',
 'childCount': 0,
 'className': 'android.widget.Switch',
 'bounds': {'left': 882, 'top': 279, 'right': 1026, 'bottom': 423},
 'packageName': 'com.android.settings',
 'contentDescription': '',
 'resourceName': 'android:id/switch_widget'
}
```

### Swipe to a Specified Position

> The `scroll_to` feature is newly added and may not be fully polished (for example, it cannot detect if it has scrolled to the bottom).

First, see the example:

```python
from uiautomator2 import connect_usb, Direction

d = connect_usb()

d.scroll_to("Place Order")
d.scroll_to("Place Order", Direction.FORWARD) # Defaults to scrolling down. Other options include BACKWARD, HORIZ_FORWARD (horizontal), HORIZ_BACKWARD (horizontal reverse)
d.scroll_to("Place Order", Direction.HORIZ_FORWARD, max_swipes=5)

# Additionally, you can scroll within a specified element
d.xpath('@com.taobao.taobao:id/dx_root').scroll(Direction.HORIZ_FORWARD)
d.xpath('@com.taobao.taobao:id/dx_root').scroll_to("Place Order", Direction.HORIZ_FORWARD)
```

**A More Complete Example**

```python
import uiautomator2 as u2
from uiautomator2 import Direction

def main():
    d = u2.connect()
    d.app_start("com.netease.cloudmusic", stop=True)

    # Steps
    d.xpath("//*[@text='Private FM']/../android.widget.ImageView").click()
    d.xpath("Next Song").click()

    # Monitor popups for 2 seconds, the time may exceed 2 seconds
    d.xpath.sleep_watch(2)
    d.xpath("Go to Previous Level").click()
    
    d.xpath("Go to Previous Level").click(watch=False) # Click without triggering watch
    d.xpath("Go to Previous Level").click(timeout=5.0) # Wait timeout 5 seconds

    d.xpath.watch_background() # Enable background monitoring mode, checks every 4 seconds by default
    d.xpath.watch_background(interval=2.0) # Check every 2 seconds
    d.xpath.watch_stop() # Stop monitoring

    for el in d.xpath('//android.widget.EditText').all():
        print("rect:", el.rect) # Output tuple: (left_x, top_y, width, height)
        print("bounds:", el.bounds) # Output tuple: (left, top, right, bottom)
        print("center:", el.center())
        el.click() # Click operation
        print(el.elem) # Output the Node parsed by lxml

    # Swiping
    el = d.xpath('@com.taobao.taobao:id/fl_banner_container').get()

    # Swipe from right to left
    el.swipe(Direction.HORIZ_FORWARD) 
    el.swipe(Direction.LEFT) # Swipe from right to left

    # Swipe from bottom to top
    el.swipe(Direction.FORWARD)
    el.swipe(Direction.UP)

    el.swipe("right", scale=0.9) # scale defaults to 0.9, swipe distance is 80% of the control's width, the swipe center aligns with the control's center
    el.swipe("up", scale=0.5) # Swipe distance is 50% of the control's height

    # scroll is different from swipe; scroll returns a bool indicating whether new elements appeared
    el.scroll(Direction.FORWARD) # Swipe down
    el.scroll(Direction.BACKWARD) # Swipe up
    el.scroll(Direction.HORIZ_FORWARD) # Swipe horizontally forward
    el.scroll(Direction.HORIZ_BACKWARD) # Swipe horizontally backward

    if el.scroll("forward"):
        print("Can continue scrolling")
```

### `PageSource` Object

> Added in version 3.1

This is an advanced usage, but this object is also the most fundamental, as almost all functions depend on it.

**What is PageSource?**

PageSource is initialized from the return value of `d.dump_hierarchy()`. It is mainly used to find elements through XPath.

**Usage:**

```python
source = d.xpath.get_page_source()

# find_elements is the core method
elements = source.find_elements('//android.widget.TextView') # List[XMLElement]
for el in elements:
    print(el.text)

# Get coordinates and click
x, y = elements[0].center()
d.click(x, y)

# Multiple condition query syntax
es1 = source.find_elements('//android.widget.TextView')
es2 = source.find_elements(XPath('@android:id/content').joinpath("//*"))

# Find TextViews that do not belong to nodes under id=android:id/content
els = set(es1) - set(es2)

# Find TextViews that belong to nodes under id=android:id/content
els = set(es1) & set(es2)
```

## XPath Rules

To write scripts faster, we have customized some simplified XPath rules.

**Rule 1**

Starting with `//` represents native XPath.

**Rule 2**

Starting with `@` represents resourceId positioning.

`@smartisanos:id/right_container` is equivalent to `//*[@resource-id="smartisanos:id/right_container"]`

**Rule 3**

Starting with `^` represents a regular expression.

`^.*done` is equivalent to `//*[re:match(text(), '^.*done')]`

**Rule 4**

> Inspired by SQL LIKE

`Know%` matches text starting with `Know`, equivalent to `//*[starts-with(text(), 'Know')]`

`%Know` matches text ending with `Know`, equivalent to `//*[ends-with(text(), 'Know')]`

`%Know%` matches text containing `Know`, equivalent to `//*[contains(text(), 'Know')]`

**Last Rule**

Matches both `text` and `description` fields.

For example, `Search` is equivalent to XPath `//*[@text="Search" or @content-desc="Search" or @resource-id="Search"]`

## Special Notes

- Sometimes, `className` contains characters like `$@#&`, which are invalid in XML. Therefore, they are all replaced with `.`.

## Some Advanced Uses of XPath

```
# All elements
//*

# Elements where resource-id contains 'login'
//*[contains(@resource-id, 'login')]

# Buttons containing 'Account' or 'Account Number'
/android.widget.Button[contains(@text, 'Account') or contains(@text, 'Account Number')]

# The second element among all ImageViews
(//android.widget.ImageView)[2]

# The last element among all ImageViews
(//android.widget.ImageView)[last()]

# Elements where className contains 'ImageView'
//*[contains(name(), "ImageView")]
```

## Some Useful Websites

- [XPath Playground](https://scrapinghub.github.io/xpath-playground/)
- [Some Advanced Uses of XPath - JianShu](https://www.jianshu.com/p/4fef4142b33f)
- [XPath Quicksheet](https://devhints.io/xpath)

If you have other resources, feel free to submit [Issues](https://github.com/openatx/uiautomator2/issues/new) to contribute.