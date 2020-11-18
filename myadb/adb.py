# -*-coding:utf-8-*-
import usb1, os, struct, socket, traceback
from .device import ADBDevice
from .handle import TCPHandle, USBHandle
from .params import *


class PyADB(object):

    def __init__(self):
        self._usb_devices = {}
        self._remote_devices = {}

    def update_usb_devices(self):
        ctx = usb1.USBContext()
        for device in ctx.getDeviceList(skip_on_error=True):
            for setting in device.iterSettings():
                if (CLASS, SUBCLASS, PROTOCOL) == \
                        (setting.getClass(), setting.getSubClass(), setting.getProtocol()):
                    port_path = tuple([device.getBusNumber()] + device.getPortNumberList())
                    kwargs = {
                        "port_path": port_path,
                        "usb_device": device,
                        "config": setting,
                        "handle": device.open()
                    }
                    # 设置配置
                    # kwargs["handle"].setConfiguration(setting.getConfigurationValue())
                    # 声明接口
                    kwargs["handle"].claimInterface(setting.getNumber())
                    # 获取端点
                    for endpoint in setting.iterEndpoints():
                        address = endpoint.getAddress()
                        if address & usb1.libusb1.USB_ENDPOINT_DIR_MASK:
                            kwargs["read_endpoint"] = address
                            kwargs["max_read_packet_len"] = endpoint.getMaxPacketSize()
                        else:
                            kwargs["write_endpoint"] = address
                    self._usb_devices[port_path] = ADBDevice(USBHandle(**kwargs))

    def try_to_connect(self, ip_port):
        try:
            new_connection = socket.create_connection(ip_port.split(":"), 3)
            self._remote_devices[ip_port] = ADBDevice(TCPHandle(ip_port, new_connection, timeout_s=5))
            return self._remote_devices[ip_port]
        except socket.timeout:
            traceback.print_exc()
            return False
        except socket.error:
            traceback.print_exc()
            return False

    def get_first_device(self):
        if self._usb_devices:
            return list(self._usb_devices.values())[0]
        else:
            return None


