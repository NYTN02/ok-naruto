"""实机验证「回到主页面」：打开一个子面板，确认能自动退出来。

步骤：
  1. 确认当前在主页（main_adventure 命中）
  2. 点开一个子面板
  3. 确认 main_adventure 不再命中，且 page_nav 能识别出某个 cancel 按钮
  4. 按 back_to_main 的逻辑点掉 cancel
  5. 确认 main_adventure 重新命中

用法:
    .venv\\Scripts\\python.exe tools\\verify_back_to_main.py [x y]
不传坐标则默认点主界面「丰饶之间」文字中心。
"""
import os
import subprocess
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ok.feature.FeatureSet import FeatureSet  # noqa: E402
from src.tasks.page_nav import CANCEL_FEATURES, MAIN_PAGE_FEATURE  # noqa: E402

ADB = os.path.join(ROOT, ".venv", "Lib", "site-packages", "adbutils", "binaries", "adb.exe")
SERIAL = "127.0.0.1:16384"
THRESHOLD = 0.8
OUT = os.path.join(ROOT, "debug_output")


def adb(*args):
    return subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True)


def grab(name):
    adb("shell", "screencap", "-p", "/sdcard/_b.png")
    path = os.path.join(OUT, name)
    adb("pull", "/sdcard/_b.png", path)
    adb("shell", "rm", "/sdcard/_b.png")
    return cv2.imread(path)


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    fs = FeatureSet(False, os.path.join(ROOT, "assets", "coco_annotations.json"),
                    0.002, 0.002, default_threshold=THRESHOLD)
    for n in [MAIN_PAGE_FEATURE] + CANCEL_FEATURES:
        fs.feature_exists(n)

    def match(frame, name):
        fs.width, fs.height = frame.shape[1], frame.shape[0]
        boxes = fs.find_feature(frame, name, threshold=THRESHOLD)
        return boxes[0] if boxes else None

    def cancels(frame):
        return [(n, match(frame, n)) for n in CANCEL_FEATURES if match(frame, n)]

    # ---- 1. 当前应该在主页 ----
    frame = grab("btm_1_main.png")
    box = match(frame, MAIN_PAGE_FEATURE)
    print(f"[1] {MAIN_PAGE_FEATURE}: "
          f"{'命中 ' + str((box.x, box.y, round(float(box.confidence), 3))) if box else '未命中'}")
    if not box:
        print("当前不在主页，请先手动回到主页再跑")
        return 1

    # ---- 2. 点开子面板（默认点「丰饶之间」文字中心）----
    x, y = (int(argv[0]), int(argv[1])) if len(argv) >= 2 else (770, 630)
    print(f"[2] 点击 ({x},{y}) 尝试打开子面板")
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(2.5)

    # ---- 3. 确认已离开主页，并找 cancel ----
    frame = grab("btm_2_panel.png")
    main_now = match(frame, MAIN_PAGE_FEATURE)
    found = cancels(frame)
    print(f"[3] 是否已离开主页: {'否（还在主页）' if main_now else '是 ✓'}")
    print(f"[3] 识别到的关闭按钮: {[(n, (b.x, b.y)) for n, b in found] or '无'}")

    if main_now:
        print("=> 面板没打开（可能点空了），换个坐标再试")
        return 1
    if not found:
        print("=> 已离开主页但没识别到 cancel 按钮，back_to_main 会一直等到超时")
        return 1

    # ---- 4. 按 back_to_main 的优先级点掉第一个 cancel ----
    name, b = found[0]
    px, py = b.x + b.width // 2, b.y + b.height // 2
    print(f"[4] 点击关闭按钮 {name} ({px},{py}) conf={round(float(b.confidence), 3)}")
    adb("shell", "input", "tap", str(px), str(py))
    time.sleep(2.0)

    # ---- 5. 确认回到主页 ----
    frame = grab("btm_3_after.png")
    back = match(frame, MAIN_PAGE_FEATURE)
    if back:
        print(f"[5] {MAIN_PAGE_FEATURE} 重新命中 "
              f"({back.x},{back.y}) conf={round(float(back.confidence), 3)}")
        print("=> 通过：点关闭按钮后成功回到主页面")
        return 0

    left = cancels(frame)
    print(f"[5] {MAIN_PAGE_FEATURE} 仍未命中；剩余可点按钮: {[n for n, _ in left] or '无'}")
    print("=> 还有一层，back_to_main 会继续循环（符合预期）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
