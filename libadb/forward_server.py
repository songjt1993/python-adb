# -*-coding:utf-8-*-
import socket, time, select
from threading import Thread
from .protocol import *


class Worker(Thread):

    def __init__(self, s, proto, local_id, port):
        super(Worker, self).__init__()
        self._s = s
        self._proto = proto
        self._local_id = local_id
        self._remote_id = -1
        self._port = port

        self._cls = False
        self._first = True

    def run(self):
        with self._s:
            while not self._cls:
                # 转发输入流
                rlist, _, _ = select.select([self._s], [], [], 0.1)
                if rlist:
                    data = rlist[0].recv(MAX_ADB_DATA)
                    if data and self._first:
                        self._first = False
                        self.create_connection()
                    if data:
                        self._proto.send(WRTE, self._local_id, self._remote_id, data)
                # 转发输出流
                cmd, _, _, data = self._proto.receive(self._local_id, self._remote_id, timeout=100)
                if cmd == WRTE:
                    _, wlist, _ = select.select([], [self._s], [], 0.1)
                    if wlist:
                        wlist[0].sendall(data)

    def create_connection(self):
        self._proto._clear_cache(local_id=self._local_id)

        self._proto.send(OPEN, self._local_id, 0, "tcp:{}\0".format(self._port).encode("utf-8"))
        cmd, self._remote_id, _, _ = self._proto.receive(local_id=self._local_id)
        if cmd != OKAY:
            self._s.close()
            raise Exception("Fail to establish connection")


class ProxyServer(Thread):

    def __init__(self, host, lport, rport, proto):
        super(ProxyServer, self).__init__()
        self._host = host
        self._lport = lport
        self._rport = rport
        self._proto = proto
        self._base = 11
        self.workers = []

        self.cls = False

    @property
    def new_id(self):
        self._base += 2
        return self._base

    def run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self._host, self._lport))
            s.listen(10)  # 最多只能连接一个
            while not self.cls:
                conn, addr = s.accept()
                print('Connected by', addr, conn)
                worker = Worker(conn, self._proto, self.new_id, self._rport)
                worker.start()
                self.workers.append(worker)