# -*-coding:utf-8-*-
import struct

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

    def receive(self, local_id=None, remote_id=None, cmd=(), ms=0):
        # 先检查cache中的结果
        for response in self._cache_list[:]:
            if self._is_expected(response, local_id, remote_id, cmd):
                self._cache_list.remove(response)
                return response

        # 再去读取usb缓冲区中的, todo 超时处理
        while True:
            response = self._atom_receive(ms)
            print("{} {} <<< {}".format(name(response[0]), response[2], response[1]))
            if self._is_expected(response, local_id, remote_id, cmd):
                return response
            else:
                self._cache_list.append(response)

    def send(self, cmd, arg0, arg1, data=b""):
        print("{} {} >>> {}".format(name(cmd), arg0, arg1))
        msg = struct.pack(b'<6I', cmd, arg0, arg1, len(data), self.calculate_checksum(data), cmd ^ 0xFFFFFFFF)
        self._handle.write(msg)
        if cmd in [WRTE, OPEN, CNXN, AUTH]:
            self._handle.write(data)

    def _is_expected(self, data, local_id=None, remote_id=None, cmd=()):
        if local_id and data[2] != local_id:
            return False
        if remote_id and data[1] != remote_id:
            return False
        if cmd and data[0] not in cmd:
            return False
        return True

    def _atom_receive(self, ms=0):
        """
        adb协议中不允许穿插其他内容的读取操作，比如：WRTE 命令后会紧跟 数据
        """
        msg = self._handle.read(24, timeout=ms)
        cmd, arg0, arg1, length, checksum, unused_magic = struct.unpack(b'<6I', msg)
        if cmd == WRTE:
            data = self._read_specified_length(length, checksum)
            self.send(OKAY, arg1, arg0)
            return cmd, arg0, arg1, data  # 命令,remote_id,local_id,数据
        elif cmd in [AUTH, CNXN]:
            data = self._read_specified_length(length, checksum)
            return cmd, arg0, arg1, data  # CNXN, version, maxdata, 设备信息 or AUTH, type, 0, 数据
        else:
            return cmd, arg0, arg1, b""

    def _read_specified_length(self, _len, checksum):
        data = bytearray()
        while _len > 0:
            temp = bytearray(self._handle.read(_len))
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

