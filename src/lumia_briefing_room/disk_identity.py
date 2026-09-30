"""두 경로가 같은 물리 디스크에 있는지. 드라이브 문자가 달라도(H:·S: 가 한 HDD 의 파티션) 같은 디스크일 수 있다."""

from __future__ import annotations

import os
from pathlib import Path

_IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x2D1080
_OPEN_EXISTING = 3
_FILE_SHARE_READ_WRITE = 0x1 | 0x2


def _drive(path: Path) -> str:
    return Path(path).drive.upper()


def physical_disk(path: Path) -> int | None:
    """Windows 물리 디스크 번호. 알 수 없으면(네트워크 드라이브, 권한, Windows 가 아님) None."""
    drive = _drive(path)
    if os.name != "nt" or len(drive) != 2 or not drive.endswith(":"):
        return None
    import ctypes
    from ctypes import wintypes

    class StorageDeviceNumber(ctypes.Structure):
        _fields_ = [("DeviceType", wintypes.DWORD), ("DeviceNumber", wintypes.DWORD), ("PartitionNumber", wintypes.DWORD)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID,
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateFileW(f"\\\\.\\{drive}", 0, _FILE_SHARE_READ_WRITE, None, _OPEN_EXISTING, 0, None)
    if handle is None or handle == wintypes.HANDLE(-1).value:
        return None
    try:
        out = StorageDeviceNumber()
        returned = wintypes.DWORD()
        ok = kernel32.DeviceIoControl(
            handle, _IOCTL_STORAGE_GET_DEVICE_NUMBER, None, 0, ctypes.byref(out), ctypes.sizeof(out), ctypes.byref(returned), None
        )
        return int(out.DeviceNumber) if ok else None
    finally:
        kernel32.CloseHandle(handle)


def same_disk(a: Path, b: Path) -> bool:
    disk_a, disk_b = physical_disk(a), physical_disk(b)
    if disk_a is not None and disk_b is not None:
        return disk_a == disk_b
    return _drive(a) != "" and _drive(a) == _drive(b)
