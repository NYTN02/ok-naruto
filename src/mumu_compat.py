"""让 ok-script 的原生 IPC 也能在 MuMu 15（以及以后的新版 MuMu）上工作。

背景
----
ok-script 的 IPC 实现把 **MuMu 12 的目录结构写死了**：

    # ok/capture/adb/nemu_ipc.py  NemuIpcImpl.__init__
    list_dll = [
        <root>/shell/sdk/external_renderer_ipc.dll,                 # MuMuPlayer12
        <root>/nx_device/12.0/shell/sdk/external_renderer_ipc.dll,  # ← 写死 12.0
    ]

    # ok/device/capture_methods/nemu_ipc.py  check_mumu_app_keep_alive_400
    vms/MuMuPlayer-12.0-<id>/configs/customer_config.json           # ← 写死 12.0

MuMu 15 的真实结构（用户实测）：

    D:\\MuMuPlayer\\nx_main\\sdk\\external_renderer_ipc.dll
    D:\\MuMuPlayer\\nx_device\\15.0\\shell\\sdk\\external_renderer_ipc.dll
    D:\\MuMuPlayer\\vms\\MuMuPlayer-15.0-0\\

也就是**只差"版本号那一段"**，DLL 本身是在的。所以原生 IPC 本来是能用的，
只是路径没适配 —— 用户因此被迫退到 ADB 截图（慢，而且会踩到其它坑）。

做法
----
不改第三方包的源码，而是在进程启动时打补丁：

  * ``NemuIpcImpl.__init__``：**先走原逻辑**（MuMu 12 行为完全不变），
    只有在报 ``NemuIpcIncompatible``（找不到 DLL）时才用扩展查找再试一遍。
  * 扩展查找**不依赖版本号**：直接 glob ``nx_device/*/``，这样 12.0 / 15.0 /
    以及以后的新版本都能命中，不会每换一版就要改一次代码。
  * ``check_mumu_app_keep_alive_400``：实例配置也按 ``vms/MuMuPlayer-*/`` 匹配，
    否则 MuMu 15 上"后台保活"这项检查会**静默失效**（原实现找不到文件只打警告）。

风险与兜底
----------
**未验证的部分**：MuMu 15 的 IPC ABI 是否与 12 兼容，只有实机测试能确定。
本模块只在"原逻辑已经失败"之后才介入，所以：

  * MuMu 12 用户：行为一字不变（原路径命中，补丁不生效）
  * MuMu 15 且 ABI 兼容：IPC 直接可用
  * MuMu 15 且 ABI 不兼容：仍然抛错 —— 调用方照旧回落到 ADB 截图，
    不会比打补丁之前更差
"""

import ctypes
import glob
import json
import os

try:
    from ok import Logger
    logger = Logger.get_logger(__name__)
except Exception:                                  # pragma: no cover
    import logging
    logger = logging.getLogger(__name__)

_patched = False

# 扩展查找用的通配模式（按优先级）。
# nx_device/*/ 是关键：版本号用 * 代替，所以 12.0 / 15.0 / 未来版本都能命中。
DLL_GLOBS = (
    'nx_device/*/shell/sdk/external_renderer_ipc.dll',
    'nx_main/sdk/external_renderer_ipc.dll',
    'nx_main/*/sdk/external_renderer_ipc.dll',
    'shell/sdk/external_renderer_ipc.dll',
)

# 递归兜底时不要进的目录：vms 下是虚拟机镜像，递归进去会非常慢
WALK_SKIP_DIRS = {'vms', 'data', 'logs', 'log', '.git', '__pycache__', 'cache'}
WALK_MAX_DEPTH = 3

DLL_NAME = 'external_renderer_ipc.dll'


def _norm(path):
    """归一化路径，用来判断两个候选是不是同一个文件。

    glob 返回的路径里分隔符可能混用（``nx_main/sdk/...`` 和 ``nx_main\\sdk\\...``
    指向同一个文件），不归一就会出现重复候选 —— 会白白多重试一遍加载。
    """
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(path)))
    except Exception:
        return path


def candidate_roots(nemu_folder, max_up=3):
    """把"可能的安装根"都列出来 —— 从 nemu_folder 开始逐级往上。

    ⚠️ 为什么不能假定 nemu_folder 就是安装根：
    ok-script 传进来的是 ``base_folder()`` = ``dirname(dirname(emulator.path))``，
    而 ``emulator.path`` 在不同 MuMu 版本下层级不一样::

        MuMu 12: <root>\\shell\\MuMuPlayer.exe
                 -> base_folder = <root>                       ✅ 正好是安装根
        MuMu 15: <root>\\nx_device\\15.0\\shell\\MuMuNxDevice.exe
                 -> base_folder = <root>\\nx_device\\15.0       ❌ 深了两层

    （MuMu 15 的那个路径是 ok-script 的 ``resolve_emulator_window_exe`` 拼出来的。）
    所以只按 nemu_folder 拼路径会拼到 ``<root>\\nx_device\\15.0\\nx_main\\sdk\\...``，
    而真实文件在 ``<root>\\nx_main\\sdk\\...`` —— 恰好找不到。

    逐级往上试就能同时覆盖这两种情况，而且不依赖盘符（C/D/E/F 盘都行，
    因为全是相对 nemu_folder 拼出来的相对路径）。
    """
    roots = []
    if not nemu_folder:
        return roots
    current = os.path.abspath(nemu_folder)
    for _ in range(max_up + 1):
        if current and current not in roots:
            roots.append(current)
        parent = os.path.dirname(current)
        if parent == current:          # 到盘根了
            break
        current = parent
    return roots


def find_ipc_dlls(nemu_folder):
    """按 MuMu 新版目录结构找出所有候选的 IPC DLL，返回路径列表。

    **不依赖版本号、也不依赖盘符** —— 全部相对 nemu_folder 及其上级目录拼出来。
    写死 12.0 正是 MuMu 15 用不了原生 IPC 的原因。
    """
    if not nemu_folder or not os.path.isdir(nemu_folder):
        return []

    found = []
    seen = set()
    for root in candidate_roots(nemu_folder):
        for pattern in DLL_GLOBS:
            for path in sorted(glob.glob(os.path.join(root, pattern))):
                key = _norm(path)
                if key not in seen:
                    seen.add(key)
                    found.append(path)
    # 注意这里**不提前 return**：要把所有候选都收齐。
    # 一个 DLL 存在不代表能加载（可能缺依赖库），多留几个备选给 patched_init
    # 按顺序重试 —— 之前写了 `if found: return`，结果只拿到一个就收手了。
    if found:
        return found

    # 兜底：有限深度递归（排除 vms 等大目录），防止 MuMu 以后又换布局
    for root in candidate_roots(nemu_folder, max_up=1):
        base_depth = os.path.abspath(root).rstrip('\\/').count(os.sep)
        for dirpath, dirs, files in os.walk(root):
            depth = os.path.abspath(dirpath).count(os.sep) - base_depth
            if depth >= WALK_MAX_DEPTH:
                dirs[:] = []
            else:
                dirs[:] = [d for d in dirs if d.lower() not in WALK_SKIP_DIRS]
            if DLL_NAME in files:
                path = os.path.join(dirpath, DLL_NAME)
                key = _norm(path)
                if key not in seen:
                    seen.add(key)
                    found.append(path)
        if found:
            return found
    return found


def find_keep_alive_configs(base_folder, player_id=None):
    """找出 ``vms/MuMuPlayer-*/configs/customer_config.json``。

    同样不写死版本号，也从多个候选根去找（base_folder 在 MuMu 15 上偏深）。
    ``player_id`` 能给就给（优先匹配当前实例）。
    """
    if not base_folder or not os.path.isdir(base_folder):
        return []
    paths = []
    seen = set()
    for root in candidate_roots(base_folder):
        for path in sorted(glob.glob(os.path.join(
                root, 'vms', 'MuMuPlayer-*', 'configs', 'customer_config.json'))):
            key = _norm(path)
            if key not in seen:
                seen.add(key)
                paths.append(path)
        if paths:
            break
    if player_id is not None:
        suffix = f'-{player_id}' + os.sep + 'configs' + os.sep + 'customer_config.json'
        paths.sort(key=lambda p: 0 if p.endswith(suffix) else 1)
    return paths


def apply():
    """打补丁。幂等；任何异常都不会影响程序启动。"""
    global _patched
    if _patched:
        return True
    try:
        _patch_nemu_ipc_dll()
        _patch_nemu_ipc_connect()
        _patch_keep_alive_check()
        _patched = True
        logger.info('[MuMu兼容] 已启用新版 MuMu（15+）的原生 IPC 路径适配')
        return True
    except Exception as e:                          # pragma: no cover
        logger.error(f'[MuMu兼容] 打补丁失败，将保持 ok-script 原始行为: {e}')
        return False


# ----------------------------------------------------------------------
# 内部实现
# ----------------------------------------------------------------------
def _patch_nemu_ipc_dll():
    from ok.capture.adb import nemu_ipc

    original_init = nemu_ipc.NemuIpcImpl.__init__
    if getattr(original_init, '_mumu_compat', False):
        return

    def patched_init(self, nemu_folder, instance_id, display_id=0):
        # 先走 ok-script 原逻辑：MuMu 12 一律命中，补丁等于不存在
        #
        # 注意 original_error 要单独存一份：`except ... as e` 里的 e 在 except 块
        # 结束时会被 Python 自动 del 掉，块外再引用就是 NameError。
        original_error = None
        try:
            return original_init(self, nemu_folder, instance_id, display_id)
        except nemu_ipc.NemuIpcIncompatible as e:
            original_error = e
            logger.warning(
                f'[MuMu兼容] 按 MuMu12 的固定路径没找到 IPC DLL（{nemu_folder}），'
                f'改用扩展查找（适配 MuMu 15+）')

        dlls = find_ipc_dlls(nemu_folder)
        if not dlls:
            logger.error(f'[MuMu兼容] 扩展查找也没找到 {DLL_NAME}（{nemu_folder}）')
            raise original_error

        self.nemu_folder = nemu_folder
        self.instance_id = instance_id
        self.display_id = display_id
        self.lib = None
        last_load_error = None
        for dll in dlls:
            try:
                self.lib = ctypes.CDLL(dll)
                logger.info(f'[MuMu兼容] 已加载 IPC DLL: {dll}')
                break
            except OSError as e:
                last_load_error = e
                logger.error(f'[MuMu兼容] {dll} 存在但加载失败: {e}')
        if self.lib is None:
            logger.error(f'[MuMu兼容] 候选 DLL 都加载不了，最后一个错误: {last_load_error}')
            raise original_error

        self.connect_id = 0
        self.width = 0
        self.height = 0

    patched_init._mumu_compat = True
    nemu_ipc.NemuIpcImpl.__init__ = patched_init


def _patch_nemu_ipc_connect():
    """让 ``nemu_connect`` 在文件夹层级不对时换其它候选根再试。

    为什么需要这一层：``nemu_connect(nemu_folder, instance_id)`` 期望的是
    **安装根**（源码注释写的是 ``E:/ProgramFiles/MuMuPlayer-12.0``），
    而 ok-script 传进来的是 ``base_folder()`` = ``dirname(dirname(emulator.path))``。
    在 nx 布局（``nx_main`` + ``nx_device/<版本>``）下这个值可能是
    ``<root>``，也可能是偏深两层的 ``<root>/nx_device/<版本>`` ——
    取决于 ok-script 把哪个可执行文件填进了 ``emulator.path``。
    层级不对时 DLL 也许照样能找到，但 connect 会失败（表现就是"原生截图无响应"）。

    ⚠️ 这一段是**推测性兜底，未实机验证**：MuMu 15 上原生 IPC 到底卡在哪一步
    （找不到 DLL / connect 失败 / capture 失败）目前无法确定。
    所以只在原 connect 抛错之后才换根重试，跑得通就说明是这个原因，
    跑不通也不会比原来更差。
    """
    from ok.capture.adb import nemu_ipc

    original_connect = nemu_ipc.NemuIpcImpl.connect
    if getattr(original_connect, '_mumu_compat', False):
        return

    def patched_connect(self, on_thread=True):
        try:
            return original_connect(self, on_thread)
        except Exception as first_error:
            tried = self.nemu_folder
            alternatives = [r for r in candidate_roots(self.nemu_folder)
                            if _norm(r) != _norm(tried)]
            if not alternatives:
                raise
            logger.warning(
                f'[MuMu兼容] 用 {tried} 连接 IPC 失败（{first_error}），'
                f'改用其它候选根重试: {alternatives}')
            for root in alternatives:
                self.nemu_folder = root
                self.connect_id = 0
                try:
                    result = original_connect(self, on_thread)
                    logger.info(f'[MuMu兼容] 用候选根 {root} 连接成功')
                    return result
                except Exception as e:
                    logger.warning(f'[MuMu兼容] 候选根 {root} 连接也失败: {e}')
            self.nemu_folder = tried
            raise

    patched_connect._mumu_compat = True
    nemu_ipc.NemuIpcImpl.connect = patched_connect


def _patch_keep_alive_check():
    from ok.capture.adb.deep import deep_get
    from ok.device.capture_methods import nemu_ipc as capture_nemu_ipc

    cls = capture_nemu_ipc.NemuIpcCaptureMethod
    original = cls.check_mumu_app_keep_alive_400
    if getattr(original, '_mumu_compat', False):
        return

    def patched_check(self):
        base = self.base_folder()
        player_id = getattr(self.emulator, 'player_id', None)
        files = find_keep_alive_configs(base, player_id)
        if not files:
            logger.warning(
                f'[MuMu兼容] 没找到 vms/MuMuPlayer-*/configs/customer_config.json'
                f'（base={base}），跳过"后台保活"检查')
            return False

        data = None
        for path in files:
            try:
                with open(path, mode='r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f'[MuMu兼容] 读到实例配置: {path}')
                break
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.warning(f'[MuMu兼容] 解析 {path} 失败: {e}')
                continue
        if data is None:
            return False

        value = deep_get(data, keys='customer.app_keptlive', default=None)
        if str(value).lower() == 'true':
            logger.error(
                '请在 MuMu 模拟器设置 →「其他」里关闭「应用保活」'
                '（Please turn off "Keep alive in the background"）')
            + '；或把截图方式改成「ADB截图」'
            raise Exception(
                'Please turn off enable background keep alive in MuMuPlayer settings')
        return True

    patched_check._mumu_compat = True
    cls.check_mumu_app_keep_alive_400 = patched_check
