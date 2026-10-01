"""从 icons/icon.png 生成多尺寸 icons/icon.ico。

为什么需要多尺寸：
    Windows 在不同地方取不同尺寸的图标 —— 标题栏/任务栏用 16/24/32，
    桌面快捷方式用 48，资源管理器大图标用 256。如果 ico 里只有 256 一张，
    系统只能现场缩小，小尺寸就会发虚、锯齿明显。

用法：
    .venv\\Scripts\\python.exe tools\\make_icon.py
"""

import os
import sys

from PIL import Image

ICO_PATH = os.path.join("icons", "icon.ico")
PNG_PATH = os.path.join("icons", "icon.png")

# Windows 常用尺寸；256 是 Vista 以后的大图标规格
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main():
    if not os.path.isfile(PNG_PATH):
        print(f"找不到源图 {PNG_PATH}")
        return 1

    src = Image.open(PNG_PATH).convert("RGBA")
    print(f"源图 {PNG_PATH}: {src.width}x{src.height} {src.mode}")

    # 源图小于 256 就先放大，否则 256 那张会是硬插值出来的
    if src.width < 256:
        print(f"提示：源图只有 {src.width}px，256 尺寸会被放大，建议提供 >= 256px 的方图")

    src.save(ICO_PATH, format="ICO", sizes=SIZES)
    print(f"已生成 {ICO_PATH} ({os.path.getsize(ICO_PATH)} bytes)，包含尺寸：")

    check = Image.open(ICO_PATH)
    for size in sorted(check.info.get("sizes", [])):
        print(f"   {size[0]}x{size[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
