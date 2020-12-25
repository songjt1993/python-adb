# -*-coding:utf-8-*-
import usb1, os, struct, socket, traceback
from .handle import TCPHandle, USBHandle
from .device import AndroidDevice
from .exceptions import *

CLASS = 0xFF
SUBCLASS = 0x42
PROTOCOL = 0x03


class DevicePool(object):

    def __init__(self):
        self._usb_devices = {}
        self._tcp_devices = {}
        self.refresh_devices()

    def refresh_devices(self):
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
                    self._usb_devices[port_path] = AndroidDevice(USBHandle(**kwargs))

    def get_device(self, sno=None):
        if len(self._usb_devices) == 0:
            raise NoDeviceFound()
        if len(self._usb_devices) == 1:
            return list(self._usb_devices.values())[0]
        elif sno is not None:
            for _, device in self._usb_devices.items():
                if device.sno == sno:
                    return device
            raise DeviceNotFound(sno)
        else:
            raise MultiDeviceError()

    def devices(self):
        tmp = []
        for _, device in self._usb_devices.items():
            tmp.append({
                "serialno": device.shell("getprop ro.serialno"),
                "status": device.device_state
            })

