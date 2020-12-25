# -*-coding: utf-8-*-
import socket, os
from .protocol import *
from .connection import Connection
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

        self.authenticate()

    @property
    def new_id(self):
        self._base_id += 1
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
                cmd, _, _, data = self._proto.receive([CNXN], ms=5000)

        if cmd == CNXN:
            conn_str = data
            # Remove banner and colons after device state (state::banner)
            parts = conn_str.split(b'::')
            self.device_state = parts[0]
            self.build_props = str(parts[1].split(b';'))
        else:
            raise Exception("Fail to Authenticate")

    def shell(self, cmd):
        local_id = self.new_id
        self._proto._clear_cache(local_id=local_id)
        self._proto.send(OPEN, local_id, 0, "shell:{}\n".format(cmd).encode("utf-8"))
        cmd, remote_id, _, _ = self._proto.receive(local_id=local_id)
        if cmd == OKAY:
            return Connection(self._proto, local_id, remote_id)
        else:
            raise Exception("Fail to establish connection")
