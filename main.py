import ok
from src.config import config
from src.tempdir import ensure_usable_temp

if __name__ == '__main__':
    # 必须在 ok.start() 之前：adb 是在启动模拟器时才被拉起来的，
    # 临时目录不可写会导致 adb 守护进程起不来（表现为「目标计算机积极拒绝」）
    ensure_usable_temp()
    config = config
    ok = ok.OK(config)
    ok.start()
