# -*-coding:utf-8-*-
import struct, socket, os, select, re, threading, queue
from .params import *
from .sign_cryptography import CryptographySigner
from .exceptions import *
from .handle import *


class ADBDevice(object):

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

    def __init__(self, handle):
        self.handle = handle

        self.build_props = None
        self.device_state = None

        self.base_id = 1  # 用来产生自增id，保证唯一性
        self._active_shell_thread = None
        self.cmd_queue = queue.Queue()
        self.result_queue = queue.Queue()

    def send(self, cmd, arg0, arg1, data):
        msg = struct.pack(b'<6I', cmd, arg0, arg1,
                          len(data), self.calculate_checksum(data), cmd ^ 0xFFFFFFFF)
        self.handle.write(msg)
        self.handle.write(data)

    def send_ok(self, arg0, arg1):
        msg = struct.pack(b'<6I', OKAY, arg0, arg1,
                          len(b""), self.calculate_checksum(b""), OKAY ^ 0xFFFFFFFF)
        self.handle.write(msg)

    def send_close(self, arg0, arg1):
        msg = struct.pack(b'<6I', CLSE, arg0, arg1,
                          len(b""), self.calculate_checksum(b""), CLSE ^ 0xFFFFFFFF)
        self.handle.write(msg)

    def receive(self, cmd_list=None):
        while True:  # TODO 超时
            msg = bytearray(self.handle.read(24))
            cmd, arg0, arg1, data_length, data_checksum, unused_magic = struct.unpack(b'<6I', msg)
            print(cmd, arg0, arg1, data_length, data_checksum, unused_magic)
            if cmd in cmd_list:
                break
        if data_length > 0:
            data = bytearray()
            while data_length > 0:
                temp = bytearray(self.handle.read(data_length))
                if len(temp) != data_length:
                    print(
                        "Data_length {} does not match actual number of bytes read: {}".format(data_length, len(temp)))
                data += temp

                data_length -= len(temp)
            # print(data)
            actual_checksum = self.calculate_checksum(data)
            if actual_checksum != data_checksum:
                print("校验错误")
        else:
            data = b''

        return cmd, arg0, arg1, bytes(data)

    @property
    def rsa_key(self):
        return CryptographySigner(os.path.expanduser('~/.android/adbkey'))

    def authenticate(self):
        print("认证----------------------")
        data = b""
        self.send(CNXN, VERSION, MAX_ADB_DATA, b'host::%s\0' % socket.gethostname().encode())
        cmd, _, _, data = self.receive([CNXN, AUTH])
        if cmd == AUTH:
            signed_token = self.rsa_key.Sign(data)
            self.send(AUTH, AUTH_SIGNATURE, 0, signed_token)
            cmd, _, _, data = self.receive([CNXN, AUTH])
            print(cmd == CNXN and "CNXN")
            if cmd != CNXN:
                # None of the keys worked, so send a public key.
                self.send(AUTH, AUTH_RSAPUBLICKEY, 0, self.rsa_key.GetPublicKey() + b'\0')
                cmd, _, _, data = self.receive([CNXN])

        conn_str = data
        # Remove banner and colons after device state (state::banner)
        parts = conn_str.split(b'::')
        self.device_state = parts[0]
        self.build_props = str(parts[1].split(b';'))
        print("认证结束----------------------")

    @property
    def local_id(self):
        self.base_id += 1
        return self.base_id

    def establish_connection(self, payload):
        local_id = self.local_id
        self.send(OPEN, local_id, 0, payload)
        cmd, arg0, arg1, data = None, -1, -1, b""
        while arg1 != local_id:
            cmd, arg0, arg1, data = self.receive([OKAY, CLSE])
        if cmd == OKAY:
            return arg1, arg0
        elif cmd == CLSE:
            print(data)
            raise EstablishConnectionError("Target Device Closed")

    def shell(self, cmd):
        """只执行shell命令"""
        print("shell命令----------------------")
        local_id, remote_id = self.establish_connection("shell:{}\n".format(cmd).encode("utf-8"))
        cmd, result = WRTE, b""
        while cmd == WRTE:
            cmd, arg0, arg1, data = self.receive([WRTE, CLSE])
            if arg0 == remote_id and arg1 == local_id:
                if cmd == WRTE:
                    self.send_ok(local_id, remote_id)
                elif cmd == CLSE:
                    self.send_close(local_id, remote_id)
                result += data

        if cmd == CLSE:
            print("结束----------------------")
            return result.decode("utf-8")
        else:
            print(cmd)
            raise RunCommandError("illegal Command")

    def run_cmd_loop(self):
        print("active shell启动----------------")
        local_id, remote_id = self.establish_connection(b"shell:\n")
        _, arg0, arg1, data = self.receive([WRTE])
        self.send_ok(local_id, remote_id)
        if arg0 == remote_id and arg1 == local_id:
            print(data)

        while True:
            try:
                cmd = self.cmd_queue.get(block=False) + b"\n"
                self.send(WRTE, local_id, remote_id, cmd)
                result = b""
                while True:
                    cmd, arg0, arg1, data = self.receive([WRTE, OKAY])
                    if cmd == WRTE:
                        result += data
                        if b"@" in data and b":/" in data:
                            break
                        self.send_ok(local_id, remote_id)
                self.result_queue.put(re.sub(b"\\n[^\\n]*?@.*:/.*$", b'\n', result))
            except queue.Empty:
                time.sleep(1)

    def active_shell(self, cmd=None):
        if self._active_shell_thread is None:
            self._active_shell_thread = threading.Thread(target=self.run_cmd_loop)
            self._active_shell_thread.start()

        if cmd:
            if not isinstance(cmd, bytes):
                cmd = cmd.encode("utf-8")
            self.cmd_queue.put(cmd)

    def get_active_shell_result(self, block=True, timeout=None):
        return self.result_queue.get(block, timeout)

    def tcpip(self, port):
        print("启动远程模式----------------------")
        ip = self.ip()
        local_id, remote_id = self.establish_connection(
            "tcpip:{}\n".format(port).encode("utf-8"))
        # return self.ip() + ":" + str(port)
        cmd, result = WRTE, b""
        while cmd == WRTE:
            cmd, arg0, arg1, data = self.receive([WRTE, CLSE])
            if arg0 == remote_id and arg1 == local_id:
                result += data
                if cmd == WRTE:
                    self.send_ok(local_id, remote_id)
                elif cmd == CLSE:
                    self.send_close(local_id, remote_id)
        if 'restarting in TCP mode port: 5555' in result.decode("utf-8"):
            print("结束----------------------")
            return ip+":"+str(port)
        else:
            print(result)
            return None

    def ip(self):
        try:
            show_wlan_info = self.shell("ip -f inet addr show wlan0")
        except Exception as e:
            print("cannot get ip by 'ip -f inet addr show wlan0': %s" % e)
        else:
            res = re.search(r"inet (\d+\.){3}\d+", show_wlan_info)
            if res:
                ip = res.group().split(" ")[-1]
                return ip

    def query_file_attributes(self, remote_filepath):
        local_id, remote_id = self.establish_connection(b"sync:\n")
        data = struct.pack(b"<2I", int.from_bytes(b"STAT", byteorder="little"), len(remote_filepath))
        self.send(WRTE, local_id, remote_id, data+remote_filepath.encode("utf-8"))
        cmd, arg0, arg1, data = self.receive([OKAY])
        cmd, arg0, arg1, data = self.receive([WRTE])
        _, _mode, _size, timestamp = struct.unpack(b"<4I", data)
        self.send_ok(local_id, remote_id)
        self.send_close(local_id, remote_id)
        self.receive([CLSE])
        return bin(_mode), _size, time.localtime(timestamp)

    def push(self, local_filepath, remote_filepath):
        if os.path.isdir(local_filepath):
            return False
        # mode, _, _ = self.query_file_attributes(remote_filepath)
        # if mode == 0x0:
        #     raise FileNotFoundException("File not Found:{}".format(remote_filepath))

        local_id, remote_id = self.establish_connection(b"sync:\n")
        data = "{},{}".format(remote_filepath, os.stat(local_filepath).st_mode)
        self.send(WRTE, local_id, remote_id, struct.pack(b"<2I", int.from_bytes(b"SEND", byteorder="little"), len(data)))
        self.receive([OKAY])
        self.send(WRTE, local_id, remote_id, data.encode("utf-8"))
        self.receive([OKAY])
        with open(local_filepath, "rb") as f:
            while True:
                data = f.read(MAX_ADB_DATA)
                if data:
                    self.send(WRTE, local_id, remote_id, struct.pack(b"<2I", int.from_bytes(b"DATA", byteorder="little"), len(data)))
                    self.receive([OKAY])
                    self.send(WRTE, local_id, remote_id, data)
                    self.receive([OKAY])
                else:
                    break
        self.send(WRTE, local_id, remote_id, struct.pack(b"<2I", int.from_bytes(b"DONE", byteorder="little"), int(time.time())))
        self.receive([OKAY])
        _, _, _, res = self.receive([WRTE])
        cmd, _ = struct.unpack(b"<2I", res)
        if cmd.to_bytes(4, byteorder="little") == b"OKAY":
            print("ok")
        elif cmd.to_bytes(4, byteorder="little") == b"FAIL":
            print("fail")

        self.send_ok(local_id, remote_id)
        self.send(WRTE, local_id, remote_id, struct.pack(b"<2I", int.from_bytes(b"QUIT", byteorder="little"), 0))
        self.receive([CLSE])
        self.send_close(local_id, remote_id)

    def forward(self, local_port, remote_port):
        # local_id, remote_id = self.establish_connection(
        #     "tcp:{}".format(remote_port, socket.gethostname()).encode("utf-8")
        # )
        local_id, remote_id = self.establish_connection(
            b"tcp:" + struct.pack(b"<I", remote_port)
        )
        cmd, result = WRTE, b""
        while cmd == WRTE:
            cmd, arg0, arg1, data = self.receive([WRTE, CLSE])
            if arg0 == remote_id and arg1 == local_id:
                result += data
                if cmd == WRTE:
                    self.send_ok(local_id, remote_id)
                elif cmd == CLSE:
                    self.send_close(local_id, remote_id)











