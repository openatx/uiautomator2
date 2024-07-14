# coding: utf-8
#
# BaseException
#   +- RPCError
#   |   +- RPCUnknownError
#   |   +- RPCInvalidError
#   |   +- HierarchyEmptyError
#   |   +- RPCStackOverflowError
#   |   +- NormalError
#   |     +- XPathElementNotFoundError
#   |     +- UiObjectNotFoundError
#   |     +- AppNotFoundError
#   |     +- SessionBrokenError  
#   +- DeviceError
#      +- InputIMEError
#      +- HTTPError
#      +- ConnectError
#      +- AdbShellError
#      +- AdbBroadcastError
#      +- APKSignatureError
#      +- UiAutomationError
#         +- UiAutomationNotConnectedError
#         +- InjectPermissionError
#         +- LaunchUiAutomationError
#         +- AccessibilityServiceAlreadyRegisteredError


class BaseException(Exception):
    """ base error for uiautomator2 """

## DeviceError
class DeviceError(BaseException): ...
class AdbShellError(DeviceError):...
class ConnectError(DeviceError):...
class HTTPError(DeviceError):...
class AdbBroadcastError(DeviceError):...

class UiAutomationError(DeviceError):...
class InputIMEError(DeviceError):...

class UiAutomationNotConnectedError(UiAutomationError):...    
class InjectPermissionError(UiAutomationError):... #开发者选项中: 模拟点击没有打开
class APKSignatureError(UiAutomationError):...
class LaunchUiAutomationError(UiAutomationError):...
class AccessibilityServiceAlreadyRegisteredError(UiAutomationError):...


## RPCError
class RPCError(BaseException):
    pass

class RPCUnknownError(RPCError):...
class RPCInvalidError(RPCError):...
class HierarchyEmptyError(RPCError):...
class RPCStackOverflowError(RPCError):...


class NormalError(RPCError):
    pass

class XPathElementNotFoundError(NormalError):...
class SessionBrokenError(NormalError):... #only happens when app quit or crash
class UiObjectNotFoundError(NormalError):...
class AppNotFoundError(NormalError):...