# uiautomator2
Android Uiautomator2 Python Wrapper

暂时先中文，以后再英文

# Installation
git clone this repo and run `pip install -e .`

# Usage 使用指南
```python
import uiautomator2 as ut2

d = ut2.connect('http://10.0.0.1')
with d.session('com.example.hello_world') as s:
    s(text='Clock').tap()
    assert s(resourceId='Time').value == '00:00'
```

是不是觉得这个例子太简单了，没错，那是因为那个项目还没做完呢

## Uiautomator与Uiautomator2的区别
1. api不同但也差不多
2. Uiautomator2是安卓项目，而Uiautomator是java项目
3. Uiautomator2可以输入中文，而Uiautomator的java工程需借助utf7输入法才能输入中文
4. Uiautomator2必须明确EditText框才能向里面输入文字，Uiautomator直接指定父类也可以在子类中输入文字
5. Uiautomator2获取控件速度快写，而Uiautomator获取速度慢一些;

# LICENSE
Under [MIT](LICENSE)