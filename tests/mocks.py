# ============================================================
# tests/mocks.py
# Mock MicroPython modules for host-side testing
# ============================================================

import sys
import time as _real_time

# ---- Mock 'time' module to match MicroPython API ----
class MockTime:
    _offset = 0  # controllable fake time

    def time(self):
        return _real_time.time() + self._offset

    def localtime(self, t=None):
        if t is None:
            t = self.time()
        return _real_time.localtime(t)

    def sleep(self, s):
        pass  # instant in tests

mock_time = MockTime()
sys.modules["time"] = mock_time


# ---- Mock 'os' module ----
class MockPath:
    """Mock os.path module."""
    @staticmethod
    def join(*parts):
        return "/".join(str(p).rstrip("/") for p in parts)
    
    @staticmethod
    def dirname(path):
        parts = str(path).rstrip("/").split("/")
        return "/".join(parts[:-1]) if len(parts) > 1 else "/"
    
    @staticmethod
    def exists(path):
        # Simple check for testing
        return True

class MockOS:
    """
    In-memory filesystem mock.
    Tracks files and their sizes without touching real disk.
    """
    def __init__(self):
        self._files = {}  # path → size in bytes
        self.environ = {"USERNAME": "testuser", "HOME": "/home/testuser"}  # for getpass module
        self.path = MockPath()

    def listdir(self, path):
        prefix = path.rstrip("/") + "/"
        names  = set()
        for p in self._files:
            if p.startswith(prefix):
                rest = p[len(prefix):]
                if "/" not in rest:
                    names.add(rest)
        if not names and path not in ("/", ""):
            raise OSError(f"No such directory: {path}")
        return list(names)

    def mkdir(self, path):
        self._files[path] = 0

    def stat(self, path):
        if path not in self._files:
            raise OSError(f"No such file: {path}")
        # Return tuple matching MicroPython os.stat
        # index 6 = file size
        return (0, 0, 0, 0, 0, 0, self._files[path], 0, 0, 0)

    def remove(self, path):
        if path in self._files:
            del self._files[path]

    def statvfs(self, path):
        # block_size, fragment_size, blocks, free_blocks...
        # Simulate 16MB flash, 10MB free
        block_size   = 4096
        total_blocks = 4096   # 16MB
        free_blocks  = 2560   # 10MB
        return (block_size, block_size, total_blocks,
                free_blocks, free_blocks, 0, 0, 0, 0, 255)

    def set_file_size(self, path, size):
        """Test helper — set a file's reported size."""
        self._files[path] = size

mock_os = MockOS()
sys.modules["os"] = mock_os


# ---- Mock 'network' module ----
class MockWLAN:
    def __init__(self, mode):
        self._connected = False
        self._active    = False

    def active(self, state=None):
        if state is not None:
            self._active = state
        return self._active

    def connect(self, ssid, password):
        self._connected = True  # instant connect in tests

    def isconnected(self):
        return self._connected

    def disconnect(self):
        self._connected = False

    def ifconfig(self):
        return ("192.168.1.100", "255.255.255.0",
                "192.168.1.1", "8.8.8.8")

class MockNetwork:
    STA_IF = 0
    def WLAN(self, mode):
        return MockWLAN(mode)

sys.modules["network"] = MockNetwork()


# ---- Mock 'urequests' module ----
class MockResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
    def close(self):
        pass

class MockUrequests:
    last_payload = None
    force_status = 200

    def post(self, url, data=None, headers=None, timeout=None):
        MockUrequests.last_payload = data
        return MockResponse(MockUrequests.force_status)

sys.modules["urequests"] = MockUrequests()


# ---- Mock 'bluetooth' module ----
class MockBluetooth:
    def BLE(self):
        return None

sys.modules["bluetooth"]    = MockBluetooth()
sys.modules["micropython"]  = type(sys)("micropython")
sys.modules["uasyncio"]     = type(sys)("uasyncio")