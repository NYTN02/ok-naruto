"""实机验证：按自动识别出的布局依次点击技能按钮，抓帧看技能是否真的释放。

判据：技能释放后按钮会进入冷却（变暗 + 显示倒计时数字）。
与任务里的 CombatTask 使用同一套 combat_ui 逻辑，只是不经过 ok-script GUI。

用法:
    .venv\\Scripts\\python.exe tools\\verify_click.py
"""
import os
import subprocess
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.tasks.combat_ui import LAYOUT_PROFILES, locate_buttons, select_profile  # noqa: E402

ADB = r".venv\Lib\site-packages\adbutils\binaries\adb.exe"
SERIAL = "127.0.0.1:16384"
OUT = "debug_output"
CLUSTER = (1000, 440, 1600, 900)


def sh(*args):
    return subprocess.run([ADB, "-s", SERIAL, *args], capture_output=True)


def grab():
    sh("shell", "screencap", "-p", "/sdcard/_v.png")
    sh("pull", "/sdcard/_v.png", os.path.join(OUT, "_v.png"))
    sh("shell", "rm", "/sdcard/_v.png")
    return cv2.imread(os.path.join(OUT, "_v.png"))


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1) 自动识别玩法布局
    best = None
    for _ in range(6):
        frame = grab()
        if frame is None:
            time.sleep(0.3)
            continue
        name, score, hits = select_profile(frame)
        if name and (best is None or score > best[1]):
            best = (name, score, hits)
            if score >= 1.0:
                break
        time.sleep(0.25)

    if best is None:
        print("认不出布局，终止")
        return 1
    profile, score, _ = best
    print(f"识别为「{profile}」布局，得分 {score:.2f}")
    layout, radii = LAYOUT_PROFILES[profile]

    frame = grab()
    h, w = frame.shape[:2]
    hits = locate_buttons(frame, layout, radii)
    for n in ('普攻', '一技能', '二技能', '大招'):
        hit = hits.get(n)
        print(f"  {n} -> ({hit.x},{hit.y}) r={hit.r} {hit.source}")

    # 2) 依次点击，间隔 2 秒，抓点击后的按钮簇
    tiles = []
    order = [('普攻', 2.0), ('一技能', 2.5), ('二技能', 2.5), ('大招', 2.5)]
    for name, wait in order:
        hit = hits.get(name)
        if hit is None:
            continue
        before = grab()
        sh("shell", "input", "tap", str(hit.x), str(hit.y))
        time.sleep(0.45)
        after = grab()
        time.sleep(wait)

        x1, y1, x2, y2 = CLUSTER
        b = before[y1:y2, x1:x2]
        a = after[y1:y2, x1:x2]
        b = cv2.resize(b, None, fx=0.8, fy=0.8)
        a = cv2.resize(a, None, fx=0.8, fy=0.8)
        row = np.hstack([b, a])
        bar = np.zeros((36, row.shape[1], 3), np.uint8)
        cv2.putText(bar, f"click {name} at ({hit.x},{hit.y})  [left=before right=after]",
                    (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        tiles.append(np.vstack([bar, row]))
        print(f"已点击 {name} ({hit.x},{hit.y})")

    wmin = min(t.shape[1] for t in tiles)
    montage = np.vstack([t[:, :wmin] for t in tiles])
    path = os.path.join(OUT, "verify_click_montage.png")
    cv2.imwrite(path, montage)
    print(f"对比图: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
