"""Optional X11 trigger. Never grabs keys or injects input."""
import ctypes as C
import ctypes.util
import os


class PointerMonitor:
    def __init__(self):
        self.display = None
        if os.environ.get('XDG_SESSION_TYPE') == 'wayland' or os.environ.get('WAYLAND_DISPLAY'):
            return
        name = C.util.find_library('X11')
        if not name:
            return
        self.lib = C.CDLL(name)
        self.lib.XOpenDisplay.argtypes = [C.c_char_p]
        self.lib.XOpenDisplay.restype = C.c_void_p
        self.lib.XDefaultRootWindow.argtypes = [C.c_void_p]
        self.lib.XDefaultRootWindow.restype = C.c_ulong
        self.lib.XQueryPointer.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                                          C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_int),
                                          C.POINTER(C.c_int), C.POINTER(C.c_uint)]
        self.lib.XCloseDisplay.argtypes = [C.c_void_p]
        self.display = self.lib.XOpenDisplay(None)
        if self.display:
            self.root = self.lib.XDefaultRootWindow(self.display)

    def state(self):
        if not self.display:
            return None
        root, child = C.c_ulong(), C.c_ulong()
        x, y, wx, wy, mask = C.c_int(), C.c_int(), C.c_int(), C.c_int(), C.c_uint()
        ok = self.lib.XQueryPointer(self.display, self.root, C.byref(root), C.byref(child), C.byref(x),
                                   C.byref(y), C.byref(wx), C.byref(wy), C.byref(mask))
        return (x.value, y.value, bool(mask.value & 1 and mask.value & 256)) if ok else None

    def close(self):
        if self.display:
            self.lib.XCloseDisplay(self.display)
            self.display = None
