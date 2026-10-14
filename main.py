import ok
from src.config import config
from src.dev_compat import apply as apply_dev_compat
from src.mumu_compat import apply as apply_mumu_compat
from src.tempdir import ensure_usable_temp

if __name__ == '__main__':
    # 必须在 ok.start() 之前：adb 是在启动模拟器时才被拉起来的，
    # 临时目录不可写会导致 adb 守护进程起不来（表现为「目标计算机积极拒绝」）
    ensure_usable_temp()
    # 必须在启动前：给 ok-script 的原生 IPC 打上「新版 MuMu（15+）路径适配」补丁。
    # 补丁是幂等的，且只在原来找不到 DLL 时才介入，MuMu 12 行为不变。
    apply_mumu_compat()
    apply_dev_compat()
    config = config
    ok = ok.OK(config)
    ok.start()
