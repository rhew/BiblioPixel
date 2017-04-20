import os, sys, time, traceback

from . codes import CMDTYPE, LEDTYPE, SPIChipsets, BufferChipsets
from . devices import Devices, serial
from .. driver_base import DriverBase, ChannelOrder
from ... import log, util
from ... return_codes import RETURN_CODES, print_error, BiblioSerialError


class DriverSerial(DriverBase):
    """Main driver for Serial based LED strips"""

    def __init__(self, type, num, dev="",
                 c_order=ChannelOrder.RGB, SPISpeed=2,
                 gamma=None, restart_timeout=3,
                 device_id=None, hardwareID="1D50:60AB",
                 baudrate=921600):
        super().__init__(num, c_order=c_order, gamma=gamma)
        self.devices = Devices(hardwareID, baudrate)

        if SPISpeed < 1 or SPISpeed > 24 or not (type in SPIChipsets):
            SPISpeed = 1

        self._SPISpeed = SPISpeed
        self._com = None
        self._type = type
        self._bufPad = 0
        self.dev = dev
        self.device_version = 0
        self.device_id = device_id
        self._sync_packet = util.generate_header(CMDTYPE.SYNC, 0)

        if self.device_id is not None and (self.device_id < 0 or self.device_id > 255):
            raise ValueError("device_id must be between 0 and 255")

        resp = self._connect()
        if resp == RETURN_CODES.REBOOT:  # reboot needed
            log.info(
                "Reconfigure and reboot needed, waiting for controller to restart...")
            self._com.close()
            time.sleep(restart_timeout)
            resp = self._connect()
            if resp != RETURN_CODES.SUCCESS:
                print_error(resp)
            else:
                log.info("Reconfigure success!")
        elif resp != RETURN_CODES.SUCCESS:
            print_error(resp)

        if type in SPIChipsets:
            log.info("Using SPI Speed: %sMHz", self._SPISpeed)

    def cleanup(self):
        if self._com:
            log.info("Closing connection to: %s", self.dev)
            self._com.close()

    def _connect(self):
        try:
            self.devices.find_serial_devices()
            idv = self.devices.get_device(self.device_id)
            self.device_id, self.dev, self.device_version = idv
            try:
                self._com = serial.Serial(
                    self.dev, baudrate=self.devices.baudrate, timeout=5)
            except serial.SerialException as e:
                ports = self.devices.devices.values()
                error = "Invalid port specified. No COM ports available."
                if ports:
                    error = ("Invalid port specified. Try using one of: \n" +
                             "\n".join(ports))
                log.info(error)
                raise BiblioSerialError(error)

            packet = util.generate_header(CMDTYPE.SETUP_DATA, 4)
            packet.append(self._type)  # set strip type
            byteCount = self.bufByteCount()
            if self._type in BufferChipsets:
                if self._type == LEDTYPE.APA102 and self.device_version >= 2:
                    pass
                else:
                    self._bufPad = BufferChipsets[self._type](self.numLEDs) * 3
                    byteCount += self._bufPad

            packet.append(byteCount & 0xFF)  # set 1st byte of byteCount
            packet.append(byteCount >> 8)  # set 2nd byte of byteCount
            packet.append(self._SPISpeed)
            self._com.write(packet)

            resp = self._com.read(1)
            if len(resp) == 0:
                self.devices.error()

            return ord(resp)

        except serial.SerialException as e:
            error = ("Unable to connect to the device. Please check that "
                     "it is connected and the correct port is selected.")
            log.error(traceback.format_exc())
            log.error(error)
            raise e

    def set_brightness(self, brightness):
        super().set_brightness(brightness)
        packet = util.generate_header(CMDTYPE.BRIGHTNESS, 1)
        packet.append(self._brightness)
        self._com.write(packet)
        resp = ord(self._com.read(1))
        if resp == RETURN_CODES.SUCCESS:
            return True
        print_error(resp)

    def _send_packet(self):
        self._com.write(self._packet)

        resp = self._com.read(1)
        if len(resp) == 0:
            self.devices.error()
        if ord(resp) != RETURN_CODES.SUCCESS:
            print_error(ord(resp))

        self._com.flushInput()

    def _compute_packet(self):
        count = self.bufByteCount() + self._bufPad
        self._packet = util.generate_header(CMDTYPE.PIXEL_DATA, count)

        self._render()

        self._packet.extend(self._buf)
        self._packet.extend([0] * self._bufPad)

    def _send_sync(self):
        self._com.write(self._sync_packet)


class DriverTeensySmartMatrix(DriverSerial):
    def __init__(self, width, height, dev="", device_id=None,
                 hardwareID="16C0:0483"):
        super().__init__(type=LEDTYPE.GENERIC, num=width * height,
                         device_id=device_id, hardwareID=hardwareID)
        self.sync = self._send_sync
