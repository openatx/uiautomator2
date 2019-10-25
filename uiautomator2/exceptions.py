# coding: utf-8
#

# class ATXError(Exception):
#     pass

import json


class BaseError(Exception):
    pass


class RetryError(BaseError):
    """ retry when meet this error """


class UiaError(BaseError):
    pass


class UiautomatorQuitError(UiaError):
    pass


class ConnectError(UiaError):
    pass


class XPathElementNotFoundError(UiaError):
    pass


class GatewayError(UiaError):
    def __init__(self, response, description):
        self.response = response
        self.description = description

    def __str__(self):
        return "uiautomator2.GatewayError(" + self.description + ")"


class JsonRpcError(UiaError):
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

    def __init__(self, error={}, method=None):
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


class SessionBrokenError(UiaError):
    """ only happens when app quit or crash """


class UiObjectNotFoundError(JsonRpcError):
    pass


class UiAutomationNotConnectedError(JsonRpcError):
    pass


class NullObjectExceptionError(JsonRpcError):
    pass


class NullPointerExceptionError(JsonRpcError):
    pass


class StaleObjectExceptionError(JsonRpcError):
    pass
