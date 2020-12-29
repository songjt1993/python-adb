# -*-coding: utf-8-*-
import socket, os, time
from .protocol import *
from .forward_server import *
from .connection import *
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric import utils

# 秘钥路径
RSA_KEY_PATH = os.path.expanduser('~/.android/adbkey')


class AndroidDevice(object):

    def __init__(self, handle):
        self._base_id = 10
        self._proto = ADBProtocol(handle)

        # info 字段
        self.device_state = None
        self.build_props = None

        self.forward_list = {}

        self.authenticate()

    @property
    def new_id(self):
        self._base_id += 2
        return self._base_id

    @staticmethod
    def sign(rsa_key_path, data):
        with open(rsa_key_path) as rsa_prv_file:
            rsa_key = serialization.load_pem_private_key(
                rsa_prv_file.read().encode(encoding="utf-8"), None, default_backend())
            return rsa_key.sign(
                data, padding.PKCS1v15(), utils.Prehashed(hashes.SHA1()))

    @staticmethod
    def get_public_key(rsa_key_path):
        with open(rsa_key_path + '.pub') as rsa_pub_file:
            return rsa_pub_file.read().encode(encoding="utf-8")

    def authenticate(self):
        self._proto.send(CNXN, VERSION, MAX_ADB_DATA, b'host::%s\0' % socket.gethostname().encode())
        cmd, _, _, data = self._proto.receive(cmd=[CNXN, AUTH])
        if cmd == AUTH:
            signed_token = self.sign(RSA_KEY_PATH, data)
            self._proto.send(AUTH, AUTH_SIGNATURE, 0, signed_token)
            cmd, _, _, data = self._proto.receive(cmd=[CNXN, AUTH])
            if cmd != CNXN:
                # None of the keys worked, so send a public key.
                self._proto.send(AUTH, AUTH_RSAPUBLICKEY, 0, self.get_public_key(RSA_KEY_PATH) + b'\0')
                cmd, _, _, data = self._proto.receive([CNXN], timeout=5000)

        if cmd == CNXN:
            conn_str = data
            # Remove banner and colons after device state (state::banner)
            parts = conn_str.split(b'::')
            self.device_state = parts[0]
            self.build_props = str(parts[1].split(b';'))
        else:
            raise Exception("Fail to Authenticate")
        print("\n\n")

    def shell(self, cmd):
        local_id = self.new_id
        self._proto._clear_cache(local_id=local_id)
        self._proto.send(OPEN, local_id, 0, "shell:{}\n".format(cmd).encode("utf-8"))
        cmd, remote_id, _, _ = self._proto.receive(local_id=local_id)
        if cmd == OKAY:
            return BasicConnection(self._proto, local_id, remote_id)
        else:
            raise Exception("Fail to establish connection")

    def push(self, local_filepath, remote_filepath):
        if os.path.isdir(local_filepath):
            return False

        local_id = self.new_id
        self._proto._clear_cache(local_id=local_id)
        self._proto.send(OPEN, local_id, 0, b"sync:\n")
        cmd, remote_id, _, _ = self._proto.receive(local_id=local_id)

        if cmd != OKAY:
            raise Exception("Fail to establish connection")

        data = "{},{}".format(remote_filepath, os.stat(local_filepath).st_mode)
        self._proto.send(WRTE, local_id, remote_id,
                         struct.pack(b"<2I", int.from_bytes(b"SEND", byteorder="little"), len(data)))
        cmd, remote_id, _, _ = self._proto.receive(local_id=local_id, remote_id=remote_id)

        if cmd != OKAY:
            raise Exception("Fail to send Path")

        self._proto.send(WRTE, local_id, remote_id, data.encode("utf-8"))
        cmd, remote_id, _, _ = self._proto.receive(local_id=local_id, remote_id=remote_id)

        if cmd != OKAY:
            raise Exception("Fail to send Encoding")

        with open(local_filepath, "rb") as f:
            while True:
                data = f.read(MAX_ADB_DATA)
                if data:
                    self._proto.send(WRTE, local_id, remote_id, struct.pack(b"<2I", int.from_bytes(b"DATA", byteorder="little"), len(data)))
                    cmd, remote_id, _, _ = self._proto.receive(local_id=local_id, remote_id=remote_id)
                    if cmd != OKAY:
                        raise Exception("Fail to send Data 1")

                    self._proto.send(WRTE, local_id, remote_id, data)
                    cmd, remote_id, _, _ = self._proto.receive(local_id=local_id, remote_id=remote_id)
                    if cmd != OKAY:
                        raise Exception("Fail to send Data 2")
                else:
                    break

        self._proto.send(WRTE, local_id, remote_id,
                         struct.pack(b"<2I", int.from_bytes(b"DONE", byteorder="little"), int(time.time())))
        cmd, remote_id, _, _ = self._proto.receive(local_id=local_id, remote_id=remote_id)
        if cmd != OKAY:
            raise Exception("Fail to send DONE")

        _, _, _, res = self._proto.receive(local_id=local_id, remote_id=remote_id, cmd=[WRTE])
        cmd, _ = struct.unpack(b"<2I", res)
        if cmd.to_bytes(4, byteorder="little") == b"OKAY":
            print("push success")
        elif cmd.to_bytes(4, byteorder="little") == b"FAIL":
            print("fail to push")

        self._proto.send(OKAY, local_id, remote_id)
        self._proto.send(WRTE, local_id, remote_id, struct.pack(b"<2I", int.from_bytes(b"QUIT", byteorder="little"), 0))
        self._proto.receive(local_id, remote_id, cmd=[CLSE])
        self._proto.send(CLSE, local_id, remote_id)

    def forward(self, local_p, remote_p):
        server = self.forward_list["tcp:{} tcp:{}".format(local_p, remote_p)] = ProxyServer("127.0.0.1", local_p, remote_p, self._proto)
        server.start()




