# -*-coding:utf-8-*-

class EstablishConnectionError(Exception):
    pass


class RunCommandError(Exception):
    pass


class TcpTimeoutException(Exception):
    pass


class FileNotFoundException(Exception):
    pass


class DeviceNotFound(Exception):

    def __init__(self, sno):
        super(DeviceNotFound, self).__init__("device({}) is not found".format(sno))


class MultiDeviceError(Exception):

    def __init__(self):
        super(MultiDeviceError, self).__init__("There are multiple devices")

class NoDeviceFound(Exception):

    def __init__(self):
        super(NoDeviceFound, self).__init__("No Device Found")