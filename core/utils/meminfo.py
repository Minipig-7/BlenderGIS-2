"""Detect available system RAM without external dependencies.

Used by the raster import memory guard to prevent Blender crashes
when importing very large rasters.
"""

import sys
import logging

log = logging.getLogger(__name__)


def getFreeRAM() -> int:
    """Return available RAM in bytes (memory available to a new allocation)."""
    plat = sys.platform
    try:
        if plat == 'win32':
            return _getFreeRAMWindows()
        elif plat == 'linux':
            return _getFreeRAMLinux()
        elif plat == 'darwin':
            return _getFreeRAMMacOS()
        else:
            log.debug(f'Unsupported platform {plat}, return 0 (memory guard disabled)')
            return 0
    except Exception:
        # Never block an import because RAM detection failed,
        # returning 0 lets the caller skip the memory guard
        log.error('Cannot detect available RAM', exc_info=True)
        return 0


def _getFreeRAMWindows() -> int:
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong),
            ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong),
            ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong),
            ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong),
            ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise OSError('GlobalMemoryStatusEx failed')
    return int(stat.ullAvailPhys)


def _getFreeRAMLinux() -> int:
    with open('/proc/meminfo', 'r') as f:
        for line in f:
            if line.startswith('MemAvailable:'):
                # value is in kB
                return int(line.split()[1]) * 1024
    raise OSError('MemAvailable not found in /proc/meminfo')


def _getFreeRAMMacOS() -> int:
    import os
    pageSize = os.sysconf('SC_PAGESIZE')
    availPages = os.sysconf('SC_AVPHYS_PAGES')
    return int(pageSize * availPages)
