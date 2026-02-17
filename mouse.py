import hashlib
import logging
import time
from ctypes import CDLL, POINTER, Structure, Union, c_int, c_long, c_ulong, sizeof, windll
from pathlib import Path

import numpy as np
import win32api
import win32con

from options import ghub_dll_path, ghub_dll_sha256, mouse_auto_shoot, mouse_native, mouse_wild_mouse
from screen import check_target_in_scope, screen_x_center, screen_y_center

logger = logging.getLogger(__name__)


def _resolve_driver_path(driver_path: str) -> Path:
    candidate = Path(driver_path)
    if candidate.is_absolute():
        return candidate
    return (Path(__file__).resolve().parent / candidate).resolve()


def _sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_ghub_driver() -> tuple[CDLL | None, bool]:
    try:
        dll_path = _resolve_driver_path(ghub_dll_path)
        if not dll_path.exists():
            logger.warning("Mouse DLL not found, using native mouse fallback", extra={"dll_path": str(dll_path)})
            return None, False

        expected_sha256 = ghub_dll_sha256.strip().lower()
        if expected_sha256:
            actual_sha256 = _sha256_file(dll_path)
            if actual_sha256 != expected_sha256:
                logger.error(
                    "Mouse DLL checksum mismatch. Driver will be disabled.",
                    extra={"dll_path": str(dll_path), "actual_sha256": actual_sha256},
                )
                return None, False

        driver = CDLL(str(dll_path))
        is_open = bool(driver.mouse_open())
        if not is_open:
            logger.warning("Mouse DLL loaded but mouse_open() returned false")
        else:
            logger.info("Mouse DLL loaded successfully", extra={"dll_path": str(dll_path)})
        return driver, is_open
    except Exception:
        logger.exception("Failed to initialize mouse DLL, using native mouse fallback")
        return None, False


LONG = c_long
DWORD = c_ulong
ULONG_PTR = POINTER(DWORD)
gm: CDLL | None = None
gmok = False
_driver_init_attempted = False

class MOUSEINPUT(Structure):
    _fields_ = (('dx', LONG),
                ('dy', LONG),
                ('mouseData', DWORD),
                ('dwFlags', DWORD),
                ('time', DWORD),
                ('dwExtraInfo', ULONG_PTR))


class _INPUTunion(Union):
    _fields_ = (('mi', MOUSEINPUT), ('mi', MOUSEINPUT))


class INPUT(Structure):
    _fields_ = (('type', DWORD),
                ('union', _INPUTunion))

def SendInput(*inputs):
    nInputs = len(inputs)
    LPINPUT = INPUT * nInputs
    pInputs = LPINPUT(*inputs)
    cbSize = c_int(sizeof(INPUT))
    return windll.user32.SendInput(nInputs, pInputs, cbSize)

def Input(structure):
    return INPUT(0, _INPUTunion(mi=structure))

def MouseInput(flags, x, y, data):
    return MOUSEINPUT(x, y, data, flags, 0, None)

def Mouse(flags, x=0, y=0, data=0):
    return Input(MouseInput(flags, x, y, data))


def _ensure_ghub_driver_loaded() -> None:
    global gm, gmok, _driver_init_attempted
    if _driver_init_attempted:
        return
    _driver_init_attempted = True

    if mouse_native:
        logger.debug("mouse_native=True, skipping external mouse DLL initialization")
        gm = None
        gmok = False
        return

    gm, gmok = _load_ghub_driver()


def mouse_xy(x: int, y: int):
    _ensure_ghub_driver_loaded()
    if gmok:
        return gm.moveR(x, y)
    return SendInput(Mouse(0x0001, x, y))

def mouse_down(key: int = 1):
    _ensure_ghub_driver_loaded()
    if gmok:
        return gm.press(key)
    if key == 1:
        return SendInput(Mouse(0x0002))
    if key == 2:
        return SendInput(Mouse(0x0008))
    return None

def mouse_up(key: int = 1):
    _ensure_ghub_driver_loaded()
    if gmok:
        return gm.release()
    if key == 1:
        return SendInput(Mouse(0x0004))
    if key == 2:
        return SendInput(Mouse(0x0010))
    return None

def mouse_close():
    global gmok, gm
    _ensure_ghub_driver_loaded()
    if gmok:
        gmok = False
        if gm is not None:
            return gm.mouse_close()
    return None

def win32_raw_mouse_move(x=None, y=None, target_x=None, target_y=None, target_w=None, target_h=None, distance=None):
    bScope = False
    
    if distance is not None and distance > 1:
        pass
    else:
        x = None
        y = None

    if mouse_wild_mouse and x is not None and y is not None:
        x, y = wind_mouse(screen_x_center, screen_y_center, x,y)

    if mouse_native == True and x is not None and y is not None:
        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, int(x), int(y), 0, 0)

    if mouse_native == False and x is not None and y is not None:
        mouse_xy(int(x), int(y))

    if target_x is not None and target_y is not None and mouse_auto_shoot == True:
        bScope = check_target_in_scope(target_x, target_y, target_w, target_h)
    if mouse_auto_shoot == True and bScope == False:
        mouse_up()

    if mouse_auto_shoot and bScope and x is not None and y is not None:
        win32_raw_mouse_click(x=int(x), y=int(y))

def win32_raw_mouse_click(x: int, y: int):
    if mouse_native:
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, int(x), int(y), 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, int(x), int(y), 0, 0)
    else:
        mouse_down()

def calculate_mouse_speed(x, y):
    global x0, y0, t0
    if x0 is not None and y0 is not None and t0 is not None:
        dx = x - x0
        dy = y - y0
        dt = time.time() - t0
        v_x = dx / dt
        v_y = dy / dt
        return (v_x, v_y)
    x0, y0, t0 = x, y, time.time()

x0, y0, t0 = None, None, None

sqrt3 = np.sqrt(3)
sqrt5 = np.sqrt(5)

def wind_mouse(start_x, start_y, dest_x, dest_y, G_0=9, W_0=3, M_0=15, D_0=12, move_mouse=lambda x,y: None):
    current_x,current_y = start_x,start_y
    v_x = v_y = W_x = W_y = 0
    try:
        while (dist:=np.hypot(dest_x - start_x, dest_y - start_y)) >= 1:
            W_mag = min(W_0, dist)
            if dist >= D_0:
                W_x = W_x/sqrt3 + (2*np.random.random()-1)*W_mag/sqrt5
                W_y = W_y/sqrt3 + (2*np.random.random()-1)*W_mag/sqrt5
            else:
                W_x /= sqrt3
                W_y /= sqrt3
                if M_0 < 3:
                    M_0 = np.random.random()*3 + 3
                else:
                    M_0 /= sqrt5
            v_x += W_x + G_0*(dest_x-start_x)/dist
            v_y += W_y + G_0*(dest_y-start_y)/dist
            v_mag = np.hypot(v_x, v_y)
            if v_mag > M_0:
                v_clip = M_0/2 + np.random.random()*M_0/2
                v_x = (v_x/v_mag) * v_clip
                v_y = (v_y/v_mag) * v_clip
            start_x += v_x
            start_y += v_y
            move_x = int(np.round(start_x))
            move_y = int(np.round(start_y))
            if current_x != move_x or current_y != move_y:
                move_mouse(current_x:=move_x,current_y:=move_y)
        return current_x,current_y
    except Exception:
        logger.exception("wind_mouse failed")
        return 0, 0
