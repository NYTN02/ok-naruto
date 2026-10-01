"""离线校验 combat_ui 的布局档案自动识别（不依赖 ok-script / 模拟器）。

用法:
    .venv\\Scripts\\python.exe tools\\test_combat_ui.py <图片> [<图片2> ...]
"""
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tasks.combat_ui import (  # noqa: E402
    CORE_BUTTONS,
    LAYOUT_PROFILES,
    has_combat_ui,
    locate_buttons,
    score_profile,
    select_profile,
)


def check(path):
    frame = cv2.imread(path)
    if frame is None:
        print(f"读取失败: {path}")
        return
    h, w = frame.shape[:2]
    print(f"\n================ {os.path.basename(path)}  {w}x{h} ================")
    print(f"是否战斗界面: {has_combat_ui(frame)}")

    print("--- 各布局档案得分（核心按钮命中比例）---")
    for name, (layout, radii) in LAYOUT_PROFILES.items():
        score, hits = score_profile(frame, layout, radii)
        matched = [n for n in CORE_BUTTONS if n in hits]
        print(f"  {name:5s} {score:.2f}  命中: {matched}")

    profile, score, hits = select_profile(frame)
    if profile is None:
        print(f"!! 没有档案达到阈值，最高仅 {score:.2f} -> 应当拒绝点击")
    else:
        print(f"--- 选用档案: {profile} (得分 {score:.2f}) ---")
        layout, radii = LAYOUT_PROFILES[profile]
        allhits = locate_buttons(frame, layout, radii)
        for name, hit in allhits.items():
            print(f"  {name:5s} -> ({hit.x:4d},{hit.y:4d}) r={hit.r:3d} "
                  f"rel=({hit.x / w:.3f},{hit.y / h:.3f}) {hit.source}")

    # 画出来
    vis = frame.copy()
    for name, hit in hits.items():
        cv2.circle(vis, (hit.x, hit.y), max(hit.r, 12), (0, 255, 0), 3)
        cv2.putText(vis, name, (hit.x - 40, hit.y - max(hit.r, 12) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    out = os.path.join("debug_output",
                       f"check_{os.path.splitext(os.path.basename(path))[0]}.png")
    os.makedirs("debug_output", exist_ok=True)
    cv2.imwrite(out, vis)
    print(f"标注图: {out}")


if __name__ == "__main__":
    args = sys.argv[1:] or ["debug_output/now.png"]
    for p in args:
        check(p)
