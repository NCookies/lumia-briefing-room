"""외부 프로세스(ffmpeg·ffprobe) 실행 도우미. (plan-deploy.md D4)

콘솔 없는 빌드에서 자식 프로세스가 검은 콘솔 창을 띄우지 않게 하고,
앱이 죽으면 자식 ffmpeg 가 남지 않게 하며, 게임 중 프레임 저하를 줄이도록 우선순위를 낮춘다.
"""

import logging
import subprocess
import sys

log = logging.getLogger("lumia_briefing_room.procs")

CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9

_job_handle = None


def process_flags(*, low_priority: bool = False, platform: str | None = None) -> int:
    if (platform or sys.platform) != "win32":
        return 0
    flags = CREATE_NO_WINDOW
    if low_priority:
        flags |= BELOW_NORMAL_PRIORITY_CLASS
    return flags


def run_hidden(cmd, *, low_priority: bool = False, **kwargs):
    return subprocess.run(cmd, creationflags=process_flags(low_priority=low_priority), **kwargs)


def popen_hidden(cmd, *, low_priority: bool = False, **kwargs):
    return subprocess.Popen(cmd, creationflags=process_flags(low_priority=low_priority), **kwargs)


def lower_current_process_priority() -> bool:
    """앱 전체(분석 스레드와 자식 ffmpeg 포함)를 보통 이하 우선순위로 내린다. 자식은 이 값을 물려받는다."""
    if sys.platform != "win32":
        return False
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    return bool(kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS))


def kill_children_on_exit() -> bool:
    """이 프로세스를 '닫히면 안의 프로세스를 모두 죽이는' 작업 개체(Job Object)에 넣는다. 이후 만든 자식이 대상이다."""
    global _job_handle
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        log.warning("작업 개체를 만들지 못했다: %s", ctypes.get_last_error())
        return False
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)
    ) and kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
    if not ok:
        log.warning("프로세스를 작업 개체에 넣지 못했다: %s", ctypes.get_last_error())
        kernel32.CloseHandle(job)
        return False
    _job_handle = job
    return True
