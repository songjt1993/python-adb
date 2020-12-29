# -*-coding:utf-8-*-
from .device_pool import DevicePool

DEVICEPOOL = DevicePool()


def devices():
    return DEVICEPOOL.devices()


def shell(cmd="", sno=None, block=True):
    device = DEVICEPOOL.get_device(sno)
    cn = device.shell(cmd)
    if block:
        cn.wait()
        return cn.output()
    else:
        return cn


def _shell(sno=None):
    device = DEVICEPOOL.get_device(sno)
    return device.shell()


def forward(tcp1, tcp2, sno=None):
    device = DEVICEPOOL.get_device(sno)
    device.forward(tcp1, tcp2)



def push():
    pass

