import libevdev
import time
from screeninfo import get_monitors


class VirtualKeyboard:
    """
    A class to control a virtual keyboard device using libevdev.
    """

    def __init__(self):
        self.uinput_device = None
        self._create_device()

    def _create_device(self):
        device = libevdev.Device()
        device.name = "Python Virtual Keyboard"

        # Enable the generic KEY event type
        device.enable(libevdev.EV_KEY)

        # Enable the specific keys we want to press.
        device.enable(libevdev.EV_KEY.KEY_F2)
        device.enable(libevdev.EV_KEY.KEY_F3)

        try:
            self.uinput_device = device.create_uinput_device()
            # A short sleep is good practice to allow the system to recognize the new device
            time.sleep(0.5)
        except OSError as e:
            print(f"Error creating virtual keyboard: {e}")
            print("Please ensure you have the correct udev permissions.")
            raise

    def tap_key(self, key_code):
        """Simulates a key press and release (a 'tap')."""
        if not self.uinput_device:
            return

        events = [
            # Key press
            libevdev.InputEvent(key_code, value=1),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
            # Key release
            libevdev.InputEvent(key_code, value=0),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
        ]
        self.uinput_device.send_events(events)

    def close(self):
        """Closes the keyboard device."""
        self.uinput_device = None


class VirtualTablet:
    """
    A virtual absolute pointing device using libevdev/uinput.
    Absolute coordinates map directly to screen pixels, avoiding the
    coordinate-tracking complexity of a relative mouse device.
    """

    def __init__(self):
        self.screen_width = 1920
        self.screen_height = 1080
        self.uinput_device = None
        self._get_screen_resolution()
        self._create_device()
        self.is_pen_down = False

    def _get_screen_resolution(self):
        try:
            primary_monitor = next(m for m in get_monitors() if m.is_primary)
            self.screen_width = primary_monitor.width
            self.screen_height = primary_monitor.height
        except StopIteration:
            if get_monitors():
                monitor = get_monitors()[0]
                self.screen_width = monitor.width
                self.screen_height = monitor.height

    def _create_device(self):
        device = libevdev.Device()
        device.name = "Python Virtual Tablet"

        device.enable(
            libevdev.EV_ABS.ABS_X,
            libevdev.InputAbsInfo(minimum=0, maximum=self.screen_width - 1),
        )
        device.enable(
            libevdev.EV_ABS.ABS_Y,
            libevdev.InputAbsInfo(minimum=0, maximum=self.screen_height - 1),
        )
        device.enable(libevdev.EV_KEY.BTN_LEFT)
        device.enable(libevdev.EV_KEY.BTN_TOOL_PEN)
        device.enable(libevdev.EV_KEY.BTN_TOUCH)

        try:
            self.uinput_device = device.create_uinput_device()
            time.sleep(0.5)
        except OSError as e:
            print(f"Error creating virtual tablet: {e}")
            print("Please ensure you have the correct udev permissions.")
            raise

    def _pen_down(self):
        if not self.is_pen_down:
            events = [
                libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, value=1),
                libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, value=1),
                libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
            ]
            self.uinput_device.send_events(events)
            self.is_pen_down = True

    def _pen_up(self):
        if self.is_pen_down:
            events = [
                libevdev.InputEvent(libevdev.EV_KEY.BTN_TOOL_PEN, value=0),
                libevdev.InputEvent(libevdev.EV_KEY.BTN_TOUCH, value=0),
                libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
            ]
            self.uinput_device.send_events(events)
            self.is_pen_down = False

    def move_to(self, x, y):
        if not self.uinput_device:
            return
        target_x = max(0, min(x, self.screen_width - 1))
        target_y = max(0, min(y, self.screen_height - 1))
        self._pen_down()
        events = [
            libevdev.InputEvent(libevdev.EV_ABS.ABS_X, value=target_x),
            libevdev.InputEvent(libevdev.EV_ABS.ABS_Y, value=target_y),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
        ]
        self.uinput_device.send_events(events)

    def click(self):
        if not self.uinput_device:
            return
        events = [
            libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, value=1),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
            libevdev.InputEvent(libevdev.EV_KEY.BTN_LEFT, value=0),
            libevdev.InputEvent(libevdev.EV_SYN.SYN_REPORT, value=0),
        ]
        self.uinput_device.send_events(events)

    def close(self):
        if self.uinput_device:
            self._pen_up()
            self.uinput_device = None


class VirtualInputController:
    """
    Manages both a virtual tablet and a virtual keyboard.
    """

    def __init__(self):
        self.tablet = VirtualTablet()
        self.keyboard = VirtualKeyboard()

    def move_to(self, x, y):
        """Moves the cursor to the absolute position (x, y)."""
        self.tablet.move_to(x, y)

    def click(self):
        """Performs a left click at the current location."""
        self.tablet.click()

    def press_f3(self):
        """Presses and releases the F2 key."""
        self.keyboard.tap_key(libevdev.EV_KEY.KEY_F3)

    def press_f2(self):
        """Presses and releases the F2 key."""
        self.keyboard.tap_key(libevdev.EV_KEY.KEY_F2)

    def close(self):
        """Closes both virtual devices."""
        self.tablet.close()
        self.keyboard.close()
        print("All virtual devices closed.")
