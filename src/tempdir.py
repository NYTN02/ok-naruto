"""确保 adb 能用上一个可写的临时目录。

为什么需要这个
--------------------------------------------------------------------------
adb 启动守护进程时会把自己的日志写到系统临时目录
（Windows 上是 ``%TMP%\\adb.log``，路径由 ``GetTempPath()`` 决定，
顺序是 TMP -> TEMP -> 用户目录）。这个写入一旦被拦，adb 守护进程就起不来：

    F adb : main.cpp:55 cannot open ...\\adb.log: Permission denied
    failed to start daemon

客户端随后报「由于目标计算机积极拒绝，无法连接 (10061)」，
在 ok-script 里表现为「模拟器连不上、任务跑不了」。

元凶通常是安全软件的 HIPS / 文件保护（实测过火绒）：它放行 cmd、PowerShell
这类系统程序，但会拦下 adb.exe、python.exe；项目目录如果被加进信任区就是可写的。

探测方式上有个坑
--------------------------------------------------------------------------
**不能用 ``tempfile.gettempdir()`` 来判断**。Python 发现候选目录不可写时会
*静默回退*（最终退到当前工作目录），于是 gettempdir() 返回一个可写的目录，
让人误以为 %TEMP% 没问题。必须直接拿环境变量里的真实路径去试写。

而且探测文件名要用 ``adb.log``：那正是 adb 要创建的文件，用别的名字探不出问题。
"""

import os

# adb 要创建的日志文件名，探测就用它
PROBE_NAME = 'adb.log'

# 放程序目录旁边，方便和程序一起被加进杀软信任区
TEMP_DIR_NAME = '.tmp'


def _can_create_adb_log(directory):
    """这个目录能不能创建/写入 adb.log —— adb 起不来的唯一硬性要求。"""
    try:
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, PROBE_NAME), 'a', encoding='utf-8'):
            pass
        return True
    except Exception:
        return False


def _system_temp_dirs():
    """按 GetTempPath() 的顺序（TMP -> TEMP）给出系统临时目录。"""
    seen = []
    for key in ('TMP', 'TEMP'):
        value = os.environ.get(key)
        if value and value not in seen:
            seen.append(value)
    return seen


def ensure_usable_temp(directory=None, logger=None):
    """保证 adb 能用上一个可写的临时目录。

    :param directory: 程序所在目录，默认取本文件所在目录的上一级
    :param logger: 可选日志回调，例如 print 或 task.log_info
    :return: 实际切换到的目录；没有改动任何东西时返回 None
    """
    def log(message):
        (logger or print)(message)

    # 系统临时目录只要有一个能写 adb.log，就什么都不用改（正常用户走这条）
    candidates = _system_temp_dirs()
    if not candidates:
        log('[临时目录] 没有配置 TMP/TEMP，跳过检查')
        return None
    if any(_can_create_adb_log(d) for d in candidates):
        return None

    log(f'[临时目录] 以下目录都无法创建 adb.log（多半被安全软件拦了）: {candidates}')

    base = directory or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback = os.path.join(base, TEMP_DIR_NAME)
    if not _can_create_adb_log(fallback):
        log(f'[临时目录] 备用目录也不可写: {fallback}，保持系统设置不变')
        return None

    # adb 走 GetTempPath()，它优先读 TMP；Python 的 tempfile 优先读 TEMP，
    # 所以只改 TMP 就能只影响 adb 这类原生程序，不动 Python 自己的行为。
    os.environ['TMP'] = fallback
    log(f'[临时目录] 已把 TMP 切到 {fallback}（adb 现在可以正常启动）')
    return fallback
