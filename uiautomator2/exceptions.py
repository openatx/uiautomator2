# coding: utf-8
#

# class ATXError(Exception):
#     pass

import json


class BaseError(Exception):
    pass


class RetryError(BaseError):
    """ retry when meet this error """


class SessionBrokenError(BaseError):
    """ only happens when app quit or crash """


class UiautomatorQuitError(BaseError):
    pass


class ConnectError(BaseError):
    pass


class XPathElementNotFoundError(BaseError):
    pass


class GatewayError(BaseError):
    def __init__(self, response, description):
        self.response = response
        self.description = description

    def __str__(self):
        return "uiautomator2.GatewayError(" + self.description + ")"


class JsonRpcError(BaseError):
    @staticmethod
    def format_errcode(errcode):
        m = {
            -32700: 'Parse error',
            -32600: 'Invalid Request',
            -32601: 'Method not found',
            -32602: 'Invalid params',
            -32603: 'Internal error',
            -32001: 'Jsonrpc error',
            -32002: 'Client error',
        }
        if errcode in m:
            return m[errcode]
        if errcode >= -32099 and errcode <= -32000:
            return 'Server error'
        return 'Unknown error'

    def __init__(self, error: dict = {}, method=None):
        self.code = error.get('code')
        self.message = error.get('message', '')
        self.data = error.get('data', '')
        self.method = method
        if isinstance(self.data, dict):
            self.exception_name = self.data.get("exceptionTypeName")
        else:
            self.exception_name = None

    def __str__(self):
        return '%d %s: <%s> data: %s, method: %s' % (
            self.code, self.format_errcode(
                self.code), self.message, self.data, self.method)

    def __repr__(self):
        return repr(str(self))


class UiObjectNotFoundError(JsonRpcError):
    """ 控件没找到 """


class UiAutomationNotConnectedError(JsonRpcError):
    """ 与手机上运行的UiAutomator服务连接断开 """


class NullObjectExceptionError(JsonRpcError):
    """ 空对象错误 """


class NullPointerExceptionError(JsonRpcError):
    """ 空指针错误 """


class StaleObjectExceptionError(JsonRpcError):
    """ 一种，打算要操作的对象突然消失的错误 """


class InjectPermissionError(JsonRpcError):
    """ 开发者选项中: 模拟点击没有打开 """


# 保证兼容性
UiaError = BaseError

