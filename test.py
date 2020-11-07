# -*-coding:utf-8-*-
import usb1, struct, socket

CLASS = 0xFF
SUBCLASS = 0x42
PROTOCOL = 0x01
VERSION = 0x01000000
MAX_ADB_DATA = 4096

ctx = usb1.USBContext()

adb_device = None
adb_setting = None
for device in ctx.getDeviceList(skip_on_error=True):
    for setting in device.iterSettings():
        if (CLASS, SUBCLASS, PROTOCOL) == (setting.getClass(), setting.getSubClass(), setting.getProtocol()):
            adb_device = device
            adb_setting = setting

_port_path = [adb_device.getBusNumber()] + adb_device.getPortNumberList()
print("[port_path] {}".format(_port_path))

def MakeWireIDs(ids):
    id_to_wire = {
        cmd_id: sum(c << (i * 8) for i, c in enumerate(bytearray(cmd_id)))
        for cmd_id in ids
    }
    wire_to_id = {wire: cmd_id for cmd_id, wire in id_to_wire.items()}
    return id_to_wire, wire_to_id

def CalculateChecksum(data):
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

def Open(dev):
    """Opens the USB device for this setting, and claims the interface."""
    # Make sure we close any previous handle open to this usb device.
    port_path = tuple(_port_path)
    # with self._HANDLE_CACHE_LOCK:
    #     old_handle = self._HANDLE_CACHE.get(port_path)
    #     if old_handle is not None:
    #         old_handle.Close()
    #
    # self._read_endpoint = None
    # self._write_endpoint = None

    for endpoint in adb_setting.iterEndpoints():
        address = endpoint.getAddress()
        if address & usb1.libusb1.USB_ENDPOINT_DIR_MASK:
            _read_endpoint = address
            _max_read_packet_len = endpoint.getMaxPacketSize()
        else:
            _write_endpoint = address

    # assert _read_endpoint is not None
    # assert _write_endpoint is not None

    handle = dev.open()
    iface_number = adb_setting.getNumber()
    # try:
    #     if (platform.system() != 'Windows'
    #             and handle.kernelDriverActive(iface_number)):
    #         handle.detachKernelDriver(iface_number)
    # except usb1.USBError as e:
    #     if e.value == usb1.LIBUSB_ERROR_NOT_FOUND:
    #         _LOG.warning('Kernel driver not found for interface: %s.', iface_number)
    #     else:
    #         raise
    handle.claimInterface(iface_number)
    # adb_device = handle
    # _interface_number = iface_number

    # with self._HANDLE_CACHE_LOCK:
    #     self._HANDLE_CACHE[port_path] = self
    # # When this object is deleted, make sure it's closed.
    # weakref.ref(self, self.Close)
    return handle

commands, constants = MakeWireIDs([b'SYNC', b'CNXN', b'AUTH', b'OPEN', b'OKAY', b'CLSE', b'WRTE'])

format = b'<6I'
arg0=VERSION
arg1=MAX_ADB_DATA
banner = socket.gethostname().encode()
data=b'host::%s\0' % banner

msg = struct.pack(format, commands[b'CNXN'], VERSION, MAX_ADB_DATA,
                           len(data), CalculateChecksum(data), commands[b'CNXN']^0xFFFFFFFF)

read_endpoint = None
write_endpoint = None
max_read_packet_len = 0
iface_number = adb_setting.getNumber()
for end_point in adb_setting.iterEndpoints():
    address = end_point.getAddress()
    if address & usb1.libusb1.USB_ENDPOINT_DIR_MASK:
        read_endpoint = address
        max_read_packet_len = end_point.getMaxPacketSize()
    else:
        write_endpoint = address
print("[r,w] {} {}".format(read_endpoint, write_endpoint))

adb_device = Open(adb_device)
adb_device.claimInterface(iface_number)
adb_device.bulkWrite(write_endpoint, msg)
adb_device.bulkWrite(write_endpoint, data)


while True:
    msg = bytearray(adb_device.bulkRead(read_endpoint, 24))
    cmd, arg0, arg1, data_length, data_checksum, unused_magic = struct.unpack(format, msg)
    command = constants[cmd]
    print(command, arg0, arg1, data_length, data_checksum, unused_magic)
    if command in [b'CNXN', b'AUTH']:
        break

print("跳出")
if data_length > 0:
    data = bytearray()
    while data_length > 0:
        temp = bytearray(adb_device.bulkRead(read_endpoint, data_length))
        if len(temp) != data_length:
            print(
                "Data_length {} does not match actual number of bytes read: {}".format(data_length, len(temp)))
        data += temp

        data_length -= len(temp)

    actual_checksum = CalculateChecksum(data)
    if actual_checksum != data_checksum:
        print("校验错误")
else:
    data = b''

adb_device.releaseInterface(iface_number)
adb_device.close()

print(command, arg0, arg1, bytes(data))

