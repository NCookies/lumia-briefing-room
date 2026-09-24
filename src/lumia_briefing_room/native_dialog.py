"""윈도우 기본 폴더·파일 선택 창(탐색기 형태)을 띄운다.

앱 서버는 사용자 PC 에서 돌기 때문에 서버가 직접 창을 띄우고 고른 경로만 웹 UI 에 돌려준다.
tkinter 의 askdirectory 는 옛날 트리 형태라 쓰지 않고, 탐색기와 같은 IFileOpenDialog 를 ctypes 로 부른다.
"""

import ctypes
import sys
from collections.abc import Sequence
from ctypes import WINFUNCTYPE, byref, c_long, c_uint, c_ulong, c_ushort, c_ubyte, c_void_p, c_wchar_p
from pathlib import Path

_CLSID_FILE_OPEN_DIALOG = "{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}"
_IID_FILE_OPEN_DIALOG = "{d57c7288-d4ad-4768-be02-9d969532d960}"
_IID_SHELL_ITEM = "{43826d1e-e718-42ee-bc55-a1e261c37bfe}"

_FOS_ALLOWMULTISELECT = 0x200
_FOS_PICKFOLDERS = 0x20
_FOS_FORCEFILESYSTEM = 0x40
_FOS_FILEMUSTEXIST = 0x1000
_SIGDN_FILESYSPATH = 0x80058000
_COINIT_APARTMENTTHREADED = 2
_RPC_E_CHANGED_MODE = c_long(0x80010106).value
_CANCELLED = c_long(0x800704C7).value


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", c_ubyte * 8)]


class _FilterSpec(ctypes.Structure):
    _fields_ = [("name", c_wchar_p), ("spec", c_wchar_p)]


def _guid(text: str) -> _GUID:
    guid = _GUID()
    ctypes.windll.ole32.CLSIDFromString(c_wchar_p(text), byref(guid))
    return guid


def _method(obj: c_void_p, index: int, *argtypes):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
    fn = WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtable[index])

    def call(*args) -> int:
        return fn(obj, *args)

    return call


def _check(hr: int) -> None:
    if hr < 0:
        raise OSError(f"HRESULT 0x{hr & 0xFFFFFFFF:08X}")


def _release(obj: c_void_p) -> None:
    if obj:
        _method(obj, 2)()


def _item_path(item: c_void_p) -> str:
    name = c_void_p()
    _check(_method(item, 5, c_ulong, ctypes.POINTER(c_void_p))(_SIGDN_FILESYSPATH, byref(name)))
    try:
        return ctypes.wstring_at(name.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(name)


def _set_start_folder(dialog: c_void_p, initial: str) -> None:
    if not initial or not Path(initial).is_dir():
        return
    item = c_void_p()
    iid = _guid(_IID_SHELL_ITEM)
    hr = ctypes.windll.shell32.SHCreateItemFromParsingName(c_wchar_p(initial), None, byref(iid), byref(item))
    if hr < 0 or not item:
        return
    try:
        _method(dialog, 12, c_void_p)(item)
    finally:
        _release(item)


def _show(*, title: str, initial: str, options: int, filters: Sequence[tuple[str, str]] = ()) -> list[str] | None:
    """창을 띄워 고른 경로들을 돌려준다. 취소하면 None."""
    if sys.platform != "win32":
        raise OSError("윈도우에서만 쓸 수 있습니다")

    ole32 = ctypes.windll.ole32
    co_hr = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    initialized = co_hr >= 0 and co_hr != _RPC_E_CHANGED_MODE
    dialog = c_void_p()
    try:
        clsid, iid = _guid(_CLSID_FILE_OPEN_DIALOG), _guid(_IID_FILE_OPEN_DIALOG)
        _check(ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(dialog)))

        current = c_uint()
        _check(_method(dialog, 10, ctypes.POINTER(c_uint))(byref(current)))
        _check(_method(dialog, 9, c_uint)(current.value | options | _FOS_FORCEFILESYSTEM))
        _check(_method(dialog, 17, c_wchar_p)(title))
        specs = (_FilterSpec * len(filters))(*[_FilterSpec(name, spec) for name, spec in filters])
        if filters:
            _check(_method(dialog, 4, c_uint, ctypes.POINTER(_FilterSpec))(len(filters), specs))
        _set_start_folder(dialog, initial)

        owner = ctypes.windll.user32.GetForegroundWindow()
        hr = _method(dialog, 3, c_void_p)(owner)
        if hr == _CANCELLED:
            return None
        _check(hr)

        paths: list[str] = []
        if options & _FOS_ALLOWMULTISELECT:
            results = c_void_p()
            _check(_method(dialog, 27, ctypes.POINTER(c_void_p))(byref(results)))
            try:
                count = c_uint()
                _check(_method(results, 7, ctypes.POINTER(c_uint))(byref(count)))
                for i in range(count.value):
                    item = c_void_p()
                    _check(_method(results, 8, c_uint, ctypes.POINTER(c_void_p))(i, byref(item)))
                    try:
                        paths.append(_item_path(item))
                    finally:
                        _release(item)
            finally:
                _release(results)
        else:
            item = c_void_p()
            _check(_method(dialog, 20, ctypes.POINTER(c_void_p))(byref(item)))
            try:
                paths.append(_item_path(item))
            finally:
                _release(item)
        return paths
    finally:
        _release(dialog)
        if initialized:
            ole32.CoUninitialize()


def pick_folder(initial: str = "", title: str = "폴더 선택") -> str | None:
    paths = _show(title=title, initial=initial, options=_FOS_PICKFOLDERS)
    return paths[0] if paths else None


def pick_video_files(initial: str = "", title: str = "영상 파일 선택") -> list[str]:
    patterns = ";".join(f"*{ext}" for ext in (".mp4", ".mkv", ".ts", ".webm", ".mov"))
    paths = _show(
        title=title,
        initial=initial,
        options=_FOS_ALLOWMULTISELECT | _FOS_FILEMUSTEXIST,
        filters=[("영상 파일", patterns), ("모든 파일", "*.*")],
    )
    return paths or []
