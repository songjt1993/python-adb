# -*-coding:utf-8-*-
import select, usb1, time, traceback, threading
from .exceptions import *


class USBHandle(object):

    def __init__(self, **kwargs):
        self.port_path = kwargs.get("port_path")
        self.usb_device = kwargs.get("usb_device")
        self.config = kwargs.get("config")
        self.read_endpoint = kwargs.get("read_endpoint")
        self.write_endpoint = kwargs.get("write_endpoint")
        self.max_read_packet_len = kwargs.get("max_read_packet_len")
        self.handle = kwargs.get("handle")
        self.lock = threading.Lock()

    def write(self, data):
        self.lock.acquire()
        try:
            print("[{}]>>>:{}".format("USB", data))
            return self.handle.bulkWrite(self.write_endpoint, data)
        except:
            pass
        finally:
            self.lock.release()

    def read(self, data_length, timeout=None):
        self.lock.acquire()
        try:
            data = self.handle.bulkRead(self.read_endpoint, data_length)
            print("[{}]<<<:{}".format("USB", data))
        except:
            data = b""
            traceback.print_exc()
        finally:
            self.lock.release()
        return data



class TCPHandle(object):

    def __init__(self, serial_number, connection, timeout_s=None):
        self.serial_number = serial_number
        self._connection = connection
        self._timeout_s = timeout_s
        # if timeout_s:
        #     self._connection.setblocking(False)

    def write(self, data):
        print("[{}]>>>:{}".format("TCP", data))
        _, writeable, _ = select.select([], [self._connection], [], self._timeout_s)
        if writeable:
            return self._connection.send(data)
        msg = 'Sending data to {} timed out after {}s. No data was sent.'.format(
            self.serial_number, self._timeout_s)
        raise TcpTimeoutException(msg)

    def read(self, data_length):
        readable, _, _ = select.select([self._connection], [], [], self._timeout_s)
        # print(data_length)
        if readable:
            data = self._connection.recv(data_length)
            print("[{}]<<<:{}".format("TCP", data))
            return data
        msg = 'Reading from {} timed out (Timeout {}s)'.format(
            self.serial_number, self._timeout_s)
        raise TcpTimeoutException(msg)
