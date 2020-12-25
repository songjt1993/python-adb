# -*-coding:utf-8-*-
from .device_pool import DevicePool

DEVICEPOOL = DevicePool()


def devices():
    return DEVICEPOOL.devices()


def shell(cmd="", sno=None):
    device = DEVICEPOOL.get_device(sno)
    cn = device.shell(cmd)
    cn.wait()
    return cn.output()

def forward(sno, remote_port, local_port):
    pass


def push():
    pass

