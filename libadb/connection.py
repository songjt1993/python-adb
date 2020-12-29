# -*-coding:utf-8-*-
import time, select, os
from threading import Thread
from queue import Queue, Empty
from .protocol import *
from .exceptions import *


class BasicConnection(object):

    def __init__(self, proto, local_id, remote_id):
        print("\nConnection: {} {}\n".format(local_id, remote_id))
        self._proto = proto
        self._local_id = local_id
        self._remote_id = remote_id
        self.queue = Queue(10000)

        self.task = Thread(target=self.main_loop, daemon=True)
        self.task.start()

    def close(self):
        self._proto.send(CLSE, self._local_id, self._remote_id)

    def output(self):
        res = b""
        while True:
            try:
                res += self.queue.get(block=False)
            except Empty:
                break
        return res

    def input(self, cmd):
        pass

    def is_closed(self):
        return not self.task.is_alive()

    def wait(self):
        while not self.is_closed():
            # print(self.task.is_alive())
            time.sleep(0.5)

    def main_loop(self):
        while True:
            try:
                cmd, _, _, data = self._proto.receive(self._local_id, self._remote_id, timeout=500)
                print("[{}<{}]{}".format(self._local_id, self._remote_id, name(cmd)))
                if cmd == CLSE:
                    break
                else:
                    self.queue.put(data)
            except TimeOutError:
                time.sleep(10000)


class PushConnection(BasicConnection):
    SEND = 0x444e4553
    STA2 = 0x32415453
    DATA = 0x41544144
    DONE = 0x454e4f44
    QUIT = 0x54495551
    FAIL = 0x4c494146

    def __init__(self, proto, local_id, remote_id, local_filepath, remote_filepath):
        self._local_filepath = local_filepath
        self._remote_filepath = remote_filepath
        super(PushConnection, self).__init__(proto, local_id, remote_id)

        # self.task = Thread(target=self.send_loop, daemon=True)
        # self.task.start()

    def main_loop(self):
        # self.send(self.STA2, self._remote_filepath.encode("utf-8"))

        data = "{},{}".format(self._remote_filepath, os.stat(self._local_filepath).st_mode).encode("utf-8")
        self.send(self.SEND, data)

        with open(self._local_filepath, "rb") as f:
            while True:
                data = f.read(MAX_ADB_DATA - 10)
                if data:
                    self.send(self.DATA, data)
                else:
                    break

        self.send(self.DONE, int(time.time()))
        self.receive()
        self.send(self.QUIT, 0)
        self._proto.receive(self._local_id, self._remote_id, cmd=(CLSE, ))
        self._proto.send(CLSE, self._local_id, self._remote_id)

    def check_sta(self):
        data = struct.pack(b"<2I", self.STA2, len(self._remote_filepath))+self._remote_filepath.encode("utf-8")
        self._proto.send(WRTE, self._local_id, self._remote_id, data)
        cmd, _, _, data = self._proto.receive(self._local_id, self._remote_id)
        if cmd == WRTE:
            data.unpack(b"<2I")

    def send(self, cmd, data):
        if cmd in [self.DONE, self.QUIT]:
            package = struct.pack(b"<2I", cmd, data)
        else:
            package = struct.pack(b"<2I", cmd, len(data)) + data
        self._proto.send(WRTE, self._local_id, self._remote_id, package)
        cmd, _, _, _ = self._proto.receive(self._local_id, self._remote_id)
        if cmd != OKAY:
            raise Exception("{} Fail".format(name(cmd)))

    def receive(self):
        cmd, _, _, data = self._proto.receive(local_id=self._local_id, remote_id=self._remote_id)
        print(data)
        cmd, = struct.unpack(b"<I", data[0:4])
        if cmd == OKAY:
            return cmd, -1, b""
        elif cmd == self.FAIL:
            _len, data = struct.unpack(b"<I", data[4:8]), data[8:]
            return cmd, _len, data
        elif cmd == self.STA2:
            return cmd, -1, data[4:]
        else:
            return -1, -1, b""






