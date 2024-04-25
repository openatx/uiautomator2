# coding: utf-8
#


class BaseError(Exception):
    """ base error for uiautomator2 """

class HTTPError(BaseError):
    pass


class AdbShellError(BaseError):
    pass

class LaunchUiautomatorError(BaseError):
    pass

class ConnectError(BaseError):
    pass


RequestError = HTTPError

class XPathElementNotFoundError(HTTPError):
    pass


class UiAutomationError(BaseError):
    pass


class UiAutomationNotConnectedError(UiAutomationError):
    pass

class InjectPermissionError(UiAutomationError):
    """ 开发者选项中: 模拟点击没有打开 """


class JSONRpcInvalidResponseError(UiAutomationError):
    pass

class UnknownRPCError(UiAutomationError):
    pass


class APkSignatureError(UiAutomationError):
    pass


class HierarchyEmptyError(BaseError):
    """ retry when meet this error """

class SessionBrokenError(BaseError):
    """ only happens when app quit or crash """

class JSONRPCError(RequestError):
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


class UiObjectNotFoundError(JSONRPCError):
    """ 控件没找到 """