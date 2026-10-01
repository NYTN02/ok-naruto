"""战斗任务基类：战斗布局自动识别 + 点击式出招。

重要背景（详见 src/tasks/combat_ui.py 顶部说明）
--------------------------------------------------------------------------
本项目通过 ADB/IPC 通道连接 MuMu，ok-script 使用的输入后端是 ADBInteraction：

* ``send_key`` -> ``adb shell input keyevent j`` —— Android 按键事件。
  火影忍者手游没有任何 Android 按键绑定，MuMu 的键鼠映射监听的是 Windows
  键盘事件，两者根本不在一个层面，所以「键位能读、send_key 不报错，但游戏
  毫无反应」。
* ``click``    -> ``nemu_impl.click_nemu_ipc(x, y)`` —— MuMu 原生触控注入，
  等价真实手指点击，游戏正常响应。

因此战斗出招统一走 ``click_button()`` 点击技能按钮，按键方式仅作兼容保留。

关于「布局可信」
--------------------------------------------------------------------------
不同玩法 HUD 布局不同（副本 / 练习场 / 决斗场）。用副本坐标去练习场点，
会点到背景上，现象就是「日志显示点了，游戏没反应」。
所以出手前必须先 ``ensure_combat_layout()``：用圆识别给每套布局档案打分，
选出命中最多的那套；**没有任何档案达标就拒绝点击并报错**，绝不乱点。
"""

from src.tasks.combat_ui import (
    CORE_BUTTONS,
    LAYOUT_PROFILES,
    MIN_CORE_MATCH,
    ButtonHit,
    locate_buttons,
    layout_to_config,
    parse_layout,
    select_profile,
)
from src.tasks.page_nav import PageNavTask

LAYOUT_CONFIG_NAME = '火影忍者战斗布局'
MODE_KEY = '玩法'
MODE_AUTO = '自动'


class CombatTask(PageNavTask):
    """战斗任务基类：布局识别、按钮定位和点击式技能操作。

    同时继承了 PageNavTask 的页面导航能力（is_main_page / back_to_main 等）。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._combat_keys_cache = None
        self._layout_cache = None
        self._buttons = None
        self._profile = None

    # ------------------------------------------------------------------
    # 键位（保留：仅 MuMu 窗口 + 键鼠映射模式有效，ADB 模式下游戏不响应）
    # ------------------------------------------------------------------
    def get_combat_keys(self):
        """读取全局配置里的战斗键位（缓存一次）"""
        if self._combat_keys_cache is not None:
            return self._combat_keys_cache
        try:
            self._combat_keys_cache = self.get_global_config('火影忍者手游键位')
        except AttributeError:
            self._combat_keys_cache = self.executor.get_global_config('火影忍者手游键位')
        return self._combat_keys_cache

    def press_key_config(self, key_name):
        """按配置名发送按键（ADB 模式下游戏无响应，仅作兼容保留）"""
        keys = self.get_combat_keys()
        if not keys:
            self.log_warning("未读取到键位配置")
            return
        key = keys.get(key_name)
        if not key:
            self.log_warning(f"未配置键位: {key_name}")
            return
        self.send_key(key)

    # ------------------------------------------------------------------
    # 战斗布局
    # ------------------------------------------------------------------
    def get_layout_config(self):
        """读取「火影忍者战斗布局」全局配置，返回 (玩法模式, 原始配置)。"""
        raw = None
        try:
            raw = self.get_global_config(LAYOUT_CONFIG_NAME)
        except Exception as e:
            self.log_warning(f"读取「{LAYOUT_CONFIG_NAME}」失败，使用内置默认布局: {e}")
        if not raw:
            return MODE_AUTO, {}
        mode = str(raw.get(MODE_KEY) or MODE_AUTO).strip() or MODE_AUTO
        return mode, raw

    def resolve_profile(self, profile_name):
        """取某套布局档案，并用配置里的坐标覆盖。

        返回 ``(layout, radii)``。配置里非坐标的键（如「玩法」）会被 parse_layout
        自动忽略。
        """
        layout, radii = LAYOUT_PROFILES[profile_name]
        _, raw = self.get_layout_config()
        overrides = parse_layout(raw, {})
        layout = dict(layout)
        layout.update(overrides)
        return layout, dict(radii)

    def get_layout(self):
        """当前生效的布局（缓存）。"""
        if self._layout_cache is not None:
            return self._layout_cache
        mode, _ = self.get_layout_config()
        name = mode if mode in LAYOUT_PROFILES else '副本'
        layout, _ = self.resolve_profile(name)
        self._layout_cache = layout
        self._profile = name
        return layout

    def ensure_combat_layout(self, max_frames=8, log=True):
        """识别当前战斗界面用的是哪套布局，并缓存按钮坐标。

        返回 True 表示布局可信、可以出手；False 表示没认出布局（可能不在战斗
        界面，或是没适配的新玩法），调用方应当拒绝点击。

        做法：连续抓 ``max_frames`` 帧，每帧给所有布局档案打分，取最高分；
        分数达到 1.0 立刻提前结束（够确定了）。
        """
        mode, _ = self.get_layout_config()
        if mode != MODE_AUTO and mode in LAYOUT_PROFILES:
            profiles = {mode: LAYOUT_PROFILES[mode]}
            if log:
                self.log_info(f"[布局] 配置指定玩法「{mode}」，只按该档案识别")
        else:
            profiles = LAYOUT_PROFILES

        best_name, best_score, best_hits = None, 0.0, {}
        frame = None
        for _ in range(max_frames):
            frame = self.frame
            if frame is not None:
                name, score, hits = select_profile(frame, profiles)
                if name is not None and score > best_score:
                    best_name, best_score, best_hits = name, score, hits
                    if score >= 1.0:
                        break
            self.sleep(0.25)

        if best_name is None or frame is None:
            if log:
                self.log_error(
                    f"[布局] 认不出当前战斗布局（最高命中 {best_score:.2f}，"
                    f"需要 ≥{MIN_CORE_MATCH:.2f}）。为避免乱点已拒绝出手。"
                    f"请先跑「战斗按钮校准」任务确认界面。"
                )
            return False

        self._profile = best_name
        layout, radii = self.resolve_profile(best_name)
        # 用识别到的圆修正布局，未命中的保留档案先验
        hits = locate_buttons(frame, layout, radii)
        for name, hit in best_hits.items():
            hits[name] = hit
        self._buttons = hits
        self._layout_cache = {n: (h.x / frame.shape[1], h.y / frame.shape[0])
                              for n, h in hits.items()}

        if log:
            matched = [n for n in CORE_BUTTONS if n in best_hits]
            self.log_info(f"[布局] 识别为「{best_name}」玩法，核心按钮命中 "
                          f"{best_score:.2f} {matched}")
            for name in CORE_BUTTONS:
                hit = hits.get(name)
                if hit:
                    self.log_info(f"[布局]   {name}: ({hit.x},{hit.y}) "
                                  f"r={hit.r} {hit.source}")
        return True

    def refresh_combat_buttons(self, use_detection=True, log=False):
        """按当前布局重新抓一帧定位按钮（已知布局时用，不做档案识别）。"""
        frame = self.frame
        if frame is None:
            self.log_warning("未取到截图，无法定位战斗按钮")
            self._buttons = None
            return None

        layout = self.get_layout()
        radii = LAYOUT_PROFILES.get(self._profile or '副本',
                                    LAYOUT_PROFILES['副本'])[1]
        self._buttons = locate_buttons(frame, layout, radii,
                                       use_detection=use_detection)
        if log:
            h, w = frame.shape[:2]
            for name, hit in self._buttons.items():
                self.log_info(
                    f"[战斗按钮] {name}: ({hit.x},{hit.y}) "
                    f"rel=({hit.x / w:.3f},{hit.y / h:.3f}) r={hit.r} {hit.source}"
                )
        return self._buttons

    def get_button_pos(self, name):
        """取按钮屏幕坐标；没有缓存时按配置布局换算。"""
        if self._buttons and name in self._buttons:
            hit = self._buttons[name]
            return hit.x, hit.y
        rel = self.get_layout().get(name)
        if rel is None:
            return None
        return int(rel[0] * self.width), int(rel[1] * self.height)

    def describe_layout(self):
        """返回便于写回配置文件的布局字符串表。"""
        return layout_to_config(self.get_layout())

    # ------------------------------------------------------------------
    # 点击式出招
    # ------------------------------------------------------------------
    def click_button(self, name, after_sleep=0.0, log=False):
        """点击战斗界面上的某个按钮（普攻/一技能/二技能/大招/替身/密卷/通灵）。"""
        pos = self.get_button_pos(name)
        if pos is None:
            self.log_warning(f"布局里没有按钮: {name}")
            return False
        x, y = pos
        if log:
            self.log_info(f"点击 {name} ({x}, {y})")
        self.click(x, y)
        if after_sleep > 0:
            self.sleep(after_sleep)
        return True

    def in_combat(self):
        """当前是否处于战斗界面（战斗结束时所有技能按钮一起消失）。"""
        frame = self.frame
        if frame is None:
            return False
        from src.tasks.combat_ui import has_combat_ui
        return has_combat_ui(frame)

    def combat_ui_confidence(self):
        """基于缓存的按钮识别结果，给出 0~1 的「战斗界面」置信度。

        战斗结算时整个战斗 HUD 会一起消失，因此核心按钮的识别命中率是判断
        战斗是否结束的可靠信号。比 OCR 关键词稳，也不额外做一次圆检测。
        """
        if not self._buttons:
            return 0.0
        hit = sum(1 for n in CORE_BUTTONS
                  if n in self._buttons and self._buttons[n].detected)
        return hit / len(CORE_BUTTONS)

    # ---- 技能快捷方法：全部是点击 ----
    def skill_1(self, after_sleep=0.0):
        return self.click_button('一技能', after_sleep)

    def skill_2(self, after_sleep=0.0):
        return self.click_button('二技能', after_sleep)

    def ultimate(self, after_sleep=0.0):
        return self.click_button('大招', after_sleep)

    def normal_attack(self, after_sleep=0.0):
        return self.click_button('普攻', after_sleep)

    def substitution(self, after_sleep=0.0):
        return self.click_button('替身', after_sleep)

    def secret_scroll(self, after_sleep=0.0):
        return self.click_button('密卷', after_sleep)

    def summon(self, after_sleep=0.0):
        return self.click_button('通灵', after_sleep)

    # ------------------------------------------------------------------
    # 方向移动：拖动摇杆
    # ------------------------------------------------------------------
    def move(self, direction, duration=0.3):
        """把左侧虚拟摇杆朝某个方向拖动一段时间。

        direction: 'up' / 'down' / 'left' / 'right'
        """
        deltas = {
            'up': (0.0, -1.0),
            'down': (0.0, 1.0),
            'left': (-1.0, 0.0),
            'right': (1.0, 0.0),
        }
        if direction not in deltas:
            self.log_warning(f"未知方向: {direction}")
            return
        pos = self.get_button_pos('方向键')
        if pos is None:
            self.log_warning("布局里没有方向键")
            return
        cx, cy = pos
        radius = int(self.height * 0.06)
        dx, dy = deltas[direction]
        self.swipe(cx, cy, int(cx + dx * radius), int(cy + dy * radius),
                   duration=duration)

    def move_up(self, duration=0.3):
        self.move('up', duration)

    def move_down(self, duration=0.3):
        self.move('down', duration)

    def move_left(self, duration=0.3):
        self.move('left', duration)

    def move_right(self, duration=0.3):
        self.move('right', duration)
