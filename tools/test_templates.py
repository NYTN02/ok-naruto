"""离线验证模板匹配：main_adventure 与各 cancel 按钮在实机画面上的匹配情况。

直接用 ok 的 FeatureSet 对截图做模板匹配，不依赖 ok-script GUI。

用法:
    .venv\\Scripts\\python.exe tools\\test_templates.py <截图> [<截图2> ...]
"""
import os
import subprocess
import sys

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ok.feature.FeatureSet import FeatureSet  # noqa: E402
from src.tasks.page_nav import CANCEL_FEATURES, MAIN_PAGE_FEATURE  # noqa: E402

ADB = os.path.join(ROOT, ".venv", "Lib", "site-packages", "adbutils", "binaries", "adb.exe")
SERIAL = "127.0.0.1:16384"
THRESHOLD = 0.8

NAMES = [MAIN_PAGE_FEATURE] + CANCEL_FEATURES


def grab(path):
    subprocess.run([ADB, "-s", SERIAL, "shell", "screencap", "-p", "/sdcard/_t.png"],
                   capture_output=True)
    subprocess.run([ADB, "-s", SERIAL, "pull", "/sdcard/_t.png", path],
                   capture_output=True)
    subprocess.run([ADB, "-s", SERIAL, "shell", "rm", "/sdcard/_t.png"],
                   capture_output=True)
    return cv2.imread(path)


def make_feature_set():
    coco = os.path.join(ROOT, "assets", "coco_annotations.json")
    return FeatureSet(False, coco, 0.002, 0.002, default_threshold=THRESHOLD)


def main(paths):
    fs = make_feature_set()
    # 预热：让 FeatureSet 把模板切出来
    for n in NAMES:
        fs.feature_exists(n)

    if not paths:
        os.makedirs(os.path.join(ROOT, "debug_output"), exist_ok=True)
        p = os.path.join(ROOT, "debug_output", "_tpl.png")
        grab(p)
        paths = [p]

    for path in paths:
        frame = cv2.imread(path)
        if frame is None:
            print(f"读不到 {path}")
            continue
        h, w = frame.shape[:2]
        print(f"\n===== {os.path.basename(path)}  {w}x{h} =====")
        # FeatureSet 需要知道画面尺寸
        fs.width, fs.height = w, h
        main_hit = fs.find_feature(frame, MAIN_PAGE_FEATURE, threshold=THRESHOLD)
        print(f"  {MAIN_PAGE_FEATURE}: {'命中 ' + str([(b.x, b.y, b.width, b.height, round(b.confidence, 3)) for b in main_hit]) if main_hit else '未命中'}")

        found = []
        for n in CANCEL_FEATURES:
            try:
                boxes = fs.find_feature(frame, n, threshold=THRESHOLD)
            except Exception as e:
                print(f"  {n}: 匹配异常 {e}")
                continue
            if boxes:
                found.append((n, boxes[0]))
        if found:
            print("  可点的关闭按钮:")
            for n, b in found:
                print(f"    {n}: ({b.x},{b.y},{b.width},{b.height}) "
                      f"conf={b.confidence:.3f}")
        else:
            print("  可点的关闭按钮: 无")
        print(f"  => is_main_page = {bool(main_hit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
