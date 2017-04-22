from .. import gamma as _gamma
from .. import data_maker
import threading, time


class ChannelOrder:
    RGB = 0, 1, 2
    RBG = 0, 2, 1
    GRB = 1, 0, 2
    GBR = 1, 2, 0
    BRG = 2, 0, 1
    BGR = 2, 1, 0

    ORDERS = RGB, RBG, GRB, GBR, BRG, BGR


class DriverBase(object):
    """Base driver class to build other drivers from."""

    # If set_device_brightness is not empty, it's a method that allows you
    # to directly set the brightness for the device.
    #
    # If it is empty, then the brightness is used as a scale factor in rendering
    # the pixels.
    set_device_brightness = None

    def __init__(self, num=0, width=0, height=0, c_order=ChannelOrder.RGB,
                 gamma=None, maker=data_maker.MAKER):
        if num == 0:
            num = width * height
            if num == 0:
                raise ValueError("Either num, or width and height are needed!")

        self.numLEDs = num
        gamma = gamma or _gamma.DEFAULT
        self.gamma = gamma

        self.c_order = c_order
        self.perm = ChannelOrder.ORDERS.index(c_order)

        self.layout = None

        self.width = width
        self.height = height
        self._buf = maker.make_packet(self.bufByteCount())

        self.lastUpdate = 0
        self.brightness_lock = threading.Lock()
        self._brightness = 255

    def set_layout(self, layout):
        pass

    def set_colors(self, colors, pos):
        self._colors = colors
        self._pos = pos

    def cleanup(self):
        pass

    def bufByteCount(self):
        return 3 * self.numLEDs

    def sync(self):
        """

        The sync() method is called after the entire frame has been
        sent to the device to indicate that it may now be displayed.

        This is particularly useful when there are multiple drivers comprising
        one display which all need to display the next frame at exactly the same
        time.
        """
        pass

    def _compute_packet(self):
        """Compute the packet from the colors and position.

        Eventually, this will run on the compute thread.
        """
        pass

    def _send_packet(self):
        """Send the packet to the driver.

        Eventually, this will run on an I/O thread.
        """
        pass

    def update_colors(self):
        start = time.time()

        with self.brightness_lock:
            # Swap in a new brightness.
            brightness, self._waiting_brightness = (
                self._waiting_brightness, None)

        if brightness is not None:
            self._brightness = brightness
            if self.set_device_brightness:
                self.set_device_brightness(brightness)

        self._compute_packet()
        self._send_packet()

        self.lastUpdate = time.time() - start

    def set_brightness(self, brightness):
        with self.brightness_lock:
            self._waiting_brightness = brightness

    def _render(self):
        if self.set_device_brightness:
            level = 1.0
        else:
            level = self._brightness / 255.0
        gam, (r, g, b) = self.gamma.get, self.c_order
        for i in range(self.numLEDs):
            c = [int(level * x) for x in self._colors[i + self._pos]]
            self._buf[i * 3:(i + 1) * 3] = gam(c[r]), gam(c[g]), gam(c[b])
