"""火影忍者手游 —— 战斗界面按钮定位（圆形识别 + 按玩法切换的布局档案）。

为什么要用点击而不是按键
--------------------------------------------------------------------------
本项目通过 ok-script 的 ADB 通道连接 MuMu 模拟器（configs/devices.json 里
capture=ipc，preferred=MuMuPlayer-12.0-0），此时 ok-script 使用的输入后端是
``ok.device.interaction_methods.adb.ADBInteraction``，它的 ``send_key`` 实现是::

    self.device_manager.device.shell(f"input keyevent {key}")

也就是把 ``j`` / ``k`` / ``l`` 当成 **Android 按键事件** 注入系统。而火影忍者
是纯触屏手游，游戏内没有任何 Android 按键绑定；MuMu 的「键鼠映射」监听的是
**Windows 键盘事件**，ADB 注入的 keyevent 根本不会经过 MuMu 的映射层。
所以现象就是「键位配置读得到、send_key 也没报错，但游戏毫无反应」。

而 ``ADBInteraction.click`` 走的是 ``nemu_impl.click_nemu_ipc(x, y)``（MuMu 原生
触控注入），等价于真实手指点击，游戏完全响应——模板匹配点击入口能正常跳转、
实测 adb tap 也能让角色出招，都验证了这一点。

因此战斗操作改为：**在技能按钮上点按**。


为什么需要「布局档案」
--------------------------------------------------------------------------
不同玩法的战斗 HUD **布局完全不同**：

* 副本（丰饶之间 / 冒险）：普攻 + 一技能 + 二技能 + 大招，共 4 个圆，按钮偏大
* 练习场 / 决斗场：普攻 + 三个技能 + 一个带次数点的卷轴（替身），按钮更小、
  整体下移，右侧还多出密卷/通灵

拿副本的坐标去练习场点，就会点到背景上——看起来像「点击没生效」，实际是
坐标根本不是这个界面的按钮。所以这里给每个玩法一套 LAYOUT_PROFILES，
运行时用圆识别给每套档案打分，自动挑命中最多的那套：

* 命中核心按钮 ≥ 3/4 才认为布局可用，否则宁可**拒绝点击**并报错，
  也不去乱点。

按钮定位策略
--------------------------------------------------------------------------
1. 先验：布局档案按屏幕比例给出每个按钮的中心，分辨率无关。
2. 微调：HUD 区域做一次圆检测，候选圆按「圆心距离先验 + 半径是否符合该按钮
   特征」打分，一对一贪心分配到各按钮槽位；命中则用圆心，否则回退先验。
   ROI 只取右下角一小块，避免全屏 Hough 在战斗画面上产生几十个误检。
"""

from dataclasses import dataclass

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# 布局档案：相对坐标 (x, y)，取值 0~1，相对屏幕宽高
# ---------------------------------------------------------------------------

# 副本（丰饶之间 / 冒险）：实测自 1600x900 丰饶之间战斗画面
LAYOUT_INSTANCE = {
    '普攻': (0.878, 0.752),    # 金色拳头，右下角最大的圆
    '一技能': (0.733, 0.558),   # 按钮簇左侧中部
    '二技能': (0.714, 0.851),   # 按钮簇左下
    '大招': (0.891, 0.424),    # 按钮簇右上方；能量未满时图标变灰
    '替身': (0.672, 0.878),    # 副本内一般不存在，仅作兜底
    '密卷': (0.940, 0.233),    # 决斗场 HUD 的右侧竖排
    '通灵': (0.941, 0.380),
    '方向键': (0.175, 0.767),   # 左侧虚拟摇杆中心
}

# 练习场 / 决斗场：实测自 1600x900 练习场画面
LAYOUT_ARENA = {
    '普攻': (0.890, 0.800),
    '一技能': (0.900, 0.574),
    '二技能': (0.794, 0.686),
    '大招': (0.788, 0.891),
    '替身': (0.679, 0.889),    # 带橘色次数点的卷轴按钮
    '密卷': (0.940, 0.245),
    '通灵': (0.941, 0.385),
    '方向键': (0.175, 0.767),
}

LAYOUT_PROFILES = {
    '副本': (LAYOUT_INSTANCE, {
        '普攻': (0.110, 0.160),
        '一技能': (0.062, 0.095),
        '二技能': (0.062, 0.095),
        '大招': (0.062, 0.095),
        '替身': (0.058, 0.095),
        '密卷': (0.045, 0.090),
        '通灵': (0.045, 0.090),
    }),
    '练习场': (LAYOUT_ARENA, {
        '普攻': (0.065, 0.120),
        '一技能': (0.062, 0.095),
        '二技能': (0.046, 0.078),
        '大招': (0.046, 0.078),
        '替身': (0.046, 0.078),
        '密卷': (0.045, 0.090),
        '通灵': (0.045, 0.090),
    }),
}

# 兼容旧代码：默认布局与半径
DEFAULT_LAYOUT = LAYOUT_INSTANCE
DEFAULT_PROFILE = '副本'
BUTTON_RADIUS = LAYOUT_PROFILES[DEFAULT_PROFILE][1]

# 判定「布局可用」的核心按钮，以及需要命中的最低比例
CORE_BUTTONS = ('普攻', '一技能', '二技能', '大招')
MIN_CORE_MATCH = 0.75

# 候选圆与先验圆心的最大允许距离（归一化）
DEFAULT_MAX_DISTANCE = 0.07


@dataclass
class ButtonHit:
    """一次按钮定位结果。"""

    name: str
    x: int
    y: int
    r: int = 0
    detected: bool = False
    distance: float = 0.0

    @property
    def source(self):
        return '圆识别' if self.detected else '固定布局'


def parse_layout(raw, fallback=None):
    """把配置里的 ``{'普攻': '0.88,0.752'}`` 解析成 ``{'普攻': (0.88, 0.752)}``。

    同时容忍已经是元组/列表的取值；解析失败时退回 fallback。
    """
    layout = dict(fallback if fallback is not None else DEFAULT_LAYOUT)
    if not raw:
        return layout

    for name, value in raw.items():
        try:
            if isinstance(value, str):
                parts = value.replace('，', ',').replace(' ', '').split(',')
                if len(parts) != 2:
                    continue
                x, y = float(parts[0]), float(parts[1])
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                x, y = float(value[0]), float(value[1])
            else:
                continue
        except (TypeError, ValueError):
            continue
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            layout[name] = (x, y)
    return layout


def layout_to_config(layout):
    """把布局字典转回便于写进配置文件的字符串形式。"""
    return {name: f'{xy[0]:.3f},{xy[1]:.3f}' for name, xy in layout.items()}


def detect_circles(frame, roi=(0.55, 0.15, 1.0, 1.0), radius_range=(0.04, 0.18),
                   param2=34, merge_ratio=0.6):
    """在右侧 HUD 区域做一次宽松的圆检测，返回去重后的候选圆列表。

    返回 ``[(x, y, r), ...]``，坐标为整帧像素坐标，按半径降序。

    ``merge_ratio``：圆心距离小于 ``merge_ratio * min(两圆半径)`` 时视为同一个
    按钮的重复检测（HoughCircles 经常在同一按钮上返回一大一小两个同心圆）。
    用较小半径做基准，可以避免把旁边真实的技能圆误并进一个大的误检圆里。
    """
    h, w = frame.shape[:2]
    x1, y1 = int(w * roi[0]), int(h * roi[1])
    x2, y2 = int(w * roi[2]), int(h * roi[3])
    sub = frame[y1:y2, x1:x2]
    if sub.size == 0:
        return []

    gray = cv2.medianBlur(cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY), 5)
    rmin = max(8, int(h * radius_range[0]))
    rmax = max(rmin + 1, int(h * radius_range[1]))

    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=max(rmin, int(h * 0.05)), param1=120, param2=param2,
        minRadius=rmin, maxRadius=rmax,
    )
    if circles is None:
        return []

    kept = []
    for x, y, r in sorted(np.round(circles[0]).astype(int), key=lambda c: -c[2]):
        gx, gy = int(x + x1), int(y + y1)
        if all(np.hypot(gx - kx, gy - ky) > merge_ratio * min(kr, r)
               for kx, ky, kr in kept):
            kept.append((gx, gy, int(r)))
    return kept


def match_buttons(candidates, layout, radius_map, frame_size,
                  max_distance=DEFAULT_MAX_DISTANCE):
    """把候选圆一对一分配给布局里的按钮槽位。

    贪心：得分 = 圆心距离（归一化） + 半径偏差惩罚。返回 ``{名称: ButtonHit}``，
    只包含成功匹配到的槽位。
    """
    h, w = frame_size
    scored = []
    for name, (rx, ry) in layout.items():
        if name not in radius_map:
            continue
        rmin, rmax = radius_map[name]
        expect_r = (rmin + rmax) / 2
        for cx, cy, r in candidates:
            rh = r / h
            if not rmin <= rh <= rmax:
                continue
            dist = float(np.hypot(cx / w - rx, cy / h - ry))
            if dist > max_distance:
                continue
            score = dist + abs(rh - expect_r) * 0.6
            scored.append((score, name, cx, cy, r, dist))

    scored.sort(key=lambda t: t[0])
    hits, used_names, used_circles = {}, set(), set()
    for _, name, cx, cy, r, dist in scored:
        if name in used_names or (cx, cy, r) in used_circles:
            continue
        used_names.add(name)
        used_circles.add((cx, cy, r))
        hits[name] = ButtonHit(name=name, x=cx, y=cy, r=r,
                               detected=True, distance=dist)
    return hits


def locate_buttons(frame, layout=None, radius_map=None, use_detection=True,
                   max_distance=DEFAULT_MAX_DISTANCE):
    """定位战斗界面所有按钮，返回 ``{名称: ButtonHit}``（含未命中的先验兜底）。"""
    layout = layout or DEFAULT_LAYOUT
    radius_map = radius_map or BUTTON_RADIUS
    h, w = frame.shape[:2]

    hits = {}
    if use_detection:
        candidates = detect_circles(frame)
        hits = match_buttons(candidates, layout, radius_map, (h, w), max_distance)

    for name, (rx, ry) in layout.items():
        if name not in hits:
            hits[name] = ButtonHit(name=name, x=int(rx * w), y=int(ry * h))
    return hits


def score_profile(frame, layout, radius_map, max_distance=DEFAULT_MAX_DISTANCE):
    """给一套布局档案在当前画面上的匹配程度打分。

    返回 ``(score, hits)``，score 是核心按钮的命中比例（0~1）。
    """
    h, w = frame.shape[:2]
    candidates = detect_circles(frame)
    hits = match_buttons(candidates, layout, radius_map, (h, w), max_distance)
    matched = sum(1 for n in CORE_BUTTONS if n in hits)
    return matched / len(CORE_BUTTONS), hits


def select_profile(frame, profiles=None, max_distance=DEFAULT_MAX_DISTANCE):
    """自动判断当前是哪套战斗 HUD 布局。

    返回 ``(profile_name, score, hits)``；score 最高的档案胜出。
    没有任何档案达到 MIN_CORE_MATCH 时，profile_name 返回 None，
    调用方应当拒绝点击而不是乱点。
    """
    profiles = profiles or LAYOUT_PROFILES
    best_name, best_score, best_hits = None, 0.0, {}
    for name, (layout, radii) in profiles.items():
        score, hits = score_profile(frame, layout, radii, max_distance)
        if score > best_score:
            best_name, best_score, best_hits = name, score, hits
    if best_score < MIN_CORE_MATCH:
        return None, best_score, best_hits
    return best_name, best_score, best_hits


def has_combat_ui(frame, min_small=2):
    """粗略判断当前是否处于战斗界面（任何玩法）。

    判据：右下角能找到一个大圆（普攻/技能）+ 至少 ``min_small`` 个小圆。
    战斗结束时所有按钮会一起消失，因此这个判据很适合做战斗结束检测。
    """
    if frame is None:
        return False
    h, w = frame.shape[:2]
    circles = detect_circles(frame)
    big = [c for c in circles if c[2] / h >= 0.05 and c[0] / w >= 0.65
           and c[1] / h >= 0.45]
    small = [c for c in circles if 0.04 <= c[2] / h <= 0.11]
    return bool(big) and len(small) >= min_small
