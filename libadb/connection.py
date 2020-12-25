# -*-coding:utf-8-*-
import time
from threading import Thread
from queue import Queue, Empty
from .protocol import *


class Connection(object):

    def __init__(self, proto, local_id, remote_id):
        print("\nConnection: {} {}\n".format(local_id, remote_id))
        self._proto = proto
        self._local_id = local_id
        self._remote_id = remote_id
        self.queue = Queue(10000)

        self.task = Thread(target=self._read_data)
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

    def _read_data(self):
        while True:
            cmd, _, _, data = self._proto.receive(self._local_id, self._remote_id)
            print("[{}<{}]{}".format(self._local_id, self._remote_id, hex(cmd)))
            if cmd == CLSE:
                break
            else:
                self.queue.put(data)
