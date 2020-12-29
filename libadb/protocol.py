# -*-coding:utf-8-*-
import struct, traceback, time
from .exceptions import *
from queue import Queue, Empty, Full
from threading import Thread

# 版本信息，认证时需要
VERSION = 0x01000000
MAX_ADB_DATA = 4096

# adb 协议中定义的命令
SYNC = 0x434e5953
CNXN = 0x4e584e43
AUTH = 0x48545541
OPEN = 0x4e45504f
OKAY = 0x59414b4f
CLSE = 0x45534c43
WRTE = 0x45545257
STLS = 0x534C5453

# 认证参数
AUTH_TOKEN = 1
AUTH_SIGNATURE = 2
AUTH_RSAPUBLICKEY = 3


def name(num):
    return struct.pack(b'<I', num)


class ADBProtocol(object):

    def __init__(self, handle):
        self._handle = handle
        self._cache_list = []
        self.receive_queue = {"default": Queue(10000)}
        self.send_queue = Queue(10000)

        self.send_task = Thread(target=self.send_loop, daemon=True)
        self.receive_task = Thread(target=self.receive_loop, daemon=True)

        self.send_task.start()
        self.receive_task.start()

    def receive(self, local_id=None, remote_id=None, cmd=(), timeout=0):
        while True:
            if AUTH in cmd or CNXN in cmd:
                response = self.receive_queue.get("default").get(block=True)
            else:
                response = self.receive_queue.get(local_id).get(block=True)
            if self._is_expected(response, local_id, remote_id, cmd):
                return response

    def send_loop(self):
        while True:
            data = self.send_queue.get(block=True)
            self._handle.write(data)

    def receive_loop(self):
        while True:
            response = self._atom_receive()
            if not response:
                continue
            if response[0] in [AUTH, CNXN]:
                self.receive_queue["default"].put(response, block=True)
            elif response[2] in self.receive_queue:
                self.receive_queue[response[2]].put(response, block=True)
            else:
                print("delete", response)

    def send(self, cmd, arg0, arg1, data=b""):
        # todo 这里要不要做长度判断
        if cmd in [WRTE, OPEN] and arg0 not in self.receive_queue:
            self.receive_queue[arg0] = Queue(10000)

        msg = struct.pack(b'<6I', cmd, arg0, arg1, len(data), self.calculate_checksum(data), cmd ^ 0xFFFFFFFF)
        self.send_queue.put(msg)
        if cmd in [WRTE, OPEN, CNXN, AUTH]:
            self.send_queue.put(data)

    def _is_expected(self, data, local_id=None, remote_id=None, cmd=()):
        if local_id and data[2] != local_id:
            print("local_id is not expect: {}".format(local_id))
            return False
        if remote_id and data[1] != remote_id:
            print("remote_id is not expect: {}".format(remote_id))
            return False
        if cmd and data[0] not in cmd:
            print("cmd is not expect")
            return False
        return True

    def _atom_receive(self, ms=0):
        """
        adb协议中不允许穿插其他内容的读取操作，比如：WRTE 命令后会紧跟 数据
        """
        msg = self._handle.read(24, timeout=ms)
        if len(msg) != 24:
            return ()
        cmd, arg0, arg1, length, checksum, unused_magic = struct.unpack(b'<6I', msg)
        if cmd == WRTE:
            data = self._read_specified_length(length, checksum, ms)
            self.send(OKAY, arg1, arg0)
            return cmd, arg0, arg1, data  # 命令,remote_id,local_id,数据
        elif cmd in [AUTH, CNXN]:
            data = self._read_specified_length(length, checksum, ms)
            return cmd, arg0, arg1, data  # CNXN, version, maxdata, 设备信息 or AUTH, type, 0, 数据
        else:
            return cmd, arg0, arg1, b""

    def _read_specified_length(self, _len, checksum, ms):
        data = bytearray()
        while _len > 0:
            temp = bytearray(self._handle.read(_len, ms))
            data += temp
            _len -= len(temp)
        if checksum == self.calculate_checksum(data):
            return bytes(data)
        else:
            raise Exception("Checksum Error")

    def _clear_cache(self, local_id):
        """清除local_id的response，因为已经过期"""
        for response in self._cache_list[:]:
            if response[2] == local_id:
                self._cache_list.remove(response)

    @staticmethod
    def calculate_checksum(data):
        # The checksum is just a sum of all the bytes. I swear.
        if isinstance(data, bytearray):
            total = sum(data)
        elif isinstance(data, bytes):
            if data and isinstance(data[0], bytes):
                # Python 2 bytes (str) index as single-character strings.
                total = sum(map(ord, data))
            else:
                # Python 3 bytes index as numbers (and PY2 empty strings sum() to 0)
                total = sum(data)
        else:
            # Unicode strings (should never see?)
            total = sum(map(ord, data))
        return total & 0xFFFFFFFF

