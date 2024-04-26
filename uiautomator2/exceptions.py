# coding: utf-8
#

class BaseException(Exception):
    """ base error for uiautomator2 """

## DeviceError
class DeviceError(BaseException):
    pass

class AdbShellError(DeviceError):...
class ConnectError(DeviceError):...
class HTTPError(DeviceError):...

class UiAutomationError(DeviceError):
    pass


class UiAutomationNotConnectedError(UiAutomationError):...    
class InjectPermissionError(UiAutomationError):... #开发者选项中: 模拟点击没有打开
class APkSignatureError(UiAutomationError):...
class LaunchUiAutomationError(UiAutomationError):...
class AccessibilityServiceAlreadyRegisteredError(UiAutomationError):...


## RPCError
class RPCError(BaseException):
    pass

class RPCUnknownError(RPCError):...
class RPCInvalidError(RPCError):...
class HierarchyEmptyError(RPCError):...


class NormalError(RPCError):
    pass

class XPathElementNotFoundError(NormalError):...
class SessionBrokenError(NormalError):... #only happens when app quit or crash
class UiObjectNotFoundError(NormalError):...