"""战斗按钮校准 / 诊断任务。

用途：在战斗界面运行一次，导出一张标好所有按钮位置的图，并打印可直接抄进
「火影忍者战斗布局」全局配置的相对坐标表。

同时它会判断当前是哪种玩法的 HUD（副本 / 练习场），这很重要：
不同玩法布局不同，用错布局会"点了没反应"。

输出文件：debug_output/combat_layout_calib.png
"""

import os

import cv2
from ok import BaseTask

from src.tasks.combat_ui import (
    CORE_BUTTONS,
    LAYOUT_PROFILES,
    MIN_CORE_MATCH,
    detect_circles,
    has_combat_ui,
    locate_buttons,
    layout_to_config,
    parse_layout,
    score_profile,
    select_profile,
)

LAYOUT_CONFIG_NAME = '火影忍者战斗布局'
OUTPUT_DIR = 'debug_output'

COLOR_DETECTED = (0, 255, 0)        # 绿：圆识别命中
COLOR_PRIOR = (0, 165, 255)         # 橙：回退固定布局
COLOR_PRIOR_CENTER = (255, 0, 255)  # 品红：配置里的先验中心


class DebugCircleTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "战斗按钮校准"
        self.description = "在战斗界面运行，识别玩法布局、导出标注图并打印可复制的坐标表"

    def _forced_profile(self):
        """「火影忍者战斗布局」里显式指定的玩法；填「自动」或非法值返回 None。"""
        try:
            raw = self.get_global_config(LAYOUT_CONFIG_NAME) or {}
        except Exception as e:
            self.log_warning(f"读取「{LAYOUT_CONFIG_NAME}」失败，按自动识别校准: {e}")
            return None
        value = str(raw.get('玩法') or '').strip()
        return value if value in LAYOUT_PROFILES else None

    def run(self):
        self.log_info("开始战斗按钮校准，请在 3 秒内停在战斗界面...")
        self.sleep(3)

        frame = self.frame
        if frame is None:
            self.log_error("无法获取截图，任务终止")
            return
        h, w = frame.shape[:2]
        in_combat = has_combat_ui(frame)
        self.log_info(f"截图尺寸: {w}x{h}")
        self.log_info(f"是否判定为战斗界面: {in_combat}")

        # ---- 1. 各玩法档案得分，判断当前是哪种 HUD ----
        self.log_info("布局档案得分（核心按钮命中比例）:")
        for name, (layout, radii) in LAYOUT_PROFILES.items():
            score, hits = score_profile(frame, layout, radii)
            matched = [n for n in CORE_BUTTONS if n in hits]
            self.log_info(f"  {name:5s} {score:.2f}  命中: {matched}")

        auto_profile, auto_score, auto_hits = select_profile(frame)

        # 「玩法」里显式指定了就按它校准：校准时通常正是想固定看某一套 HUD，
        # 让自动识别去改判反而看不到想看的那套。
        forced = self._forced_profile()
        if forced is not None:
            score, best_hits = score_profile(frame, *LAYOUT_PROFILES[forced])
            layout, radii = LAYOUT_PROFILES[forced]
            profile = forced
            self.log_info(f"「玩法」配置里指定为「{forced}」，按它校准并出图"
                          f"（自动识别结果: {auto_profile or '都不达标'} {auto_score:.2f}）")
        elif auto_profile is None:
            self.log_warning(
                f"没有布局档案达标（最高 {auto_score:.2f}，需要 ≥{MIN_CORE_MATCH:.2f}）。"
                f"可能不在战斗界面，或是还没适配的新玩法。"
            )
            self.log_warning("为避免乱点，正式任务在识别不出布局时会拒绝出手。")
            self.log_warning("如果当前确实在战斗界面，可以在「火影忍者战斗布局」里把"
                             "「玩法」指定成对应玩法（副本 / 练习场）后重新校准。")
            layout, radii = LAYOUT_PROFILES['副本']
            profile = '副本(兜底)'
            score, best_hits = auto_score, auto_hits
        else:
            self.log_info(f"判定为「{auto_profile}」玩法布局（得分 {auto_score:.2f}）")
            layout, radii = LAYOUT_PROFILES[auto_profile]
            profile = auto_profile
            score, best_hits = auto_score, auto_hits

        # ---- 2. 打印候选圆，便于人工核对误检 ----
        circles = detect_circles(frame)
        self.log_info(f"HUD 区域候选圆（已去重）共 {len(circles)} 个:")
        for x, y, r in circles:
            self.log_info(f"  ({x:4d},{y:4d}) r={r:3d}  "
                          f"rel=({x / w:.3f},{y / h:.3f}) r/h={r / h:.4f}")

        # ---- 3. 定位每个逻辑按钮并画标注 ----
        hits = locate_buttons(frame, layout, radii)
        for name, hit in best_hits.items():
            hits[name] = hit

        vis = frame.copy()
        self.log_info("按钮定位结果:")
        for name, hit in hits.items():
            state = "圆识别" if hit.detected else "固定布局"
            self.log_info(
                f"  {name:5s} -> ({hit.x:4d},{hit.y:4d}) r={hit.r:3d} "
                f"rel=({hit.x / w:.3f},{hit.y / h:.3f}) {state} "
                f"漂移={hit.distance:.1f}px"
            )

            rel = layout.get(name)
            if rel is not None:
                px, py = int(rel[0] * w), int(rel[1] * h)
                cv2.circle(vis, (px, py), 4, COLOR_PRIOR_CENTER, -1)

            radius = max(hit.r, int(h * 0.03))
            is_core = name in CORE_BUTTONS
            color = COLOR_DETECTED if hit.detected else COLOR_PRIOR
            thickness = 4 if is_core else 2
            cv2.circle(vis, (hit.x, hit.y), radius, color, thickness)
            cv2.drawMarker(vis, (hit.x, hit.y), color, cv2.MARKER_CROSS, 24, 2)
            cv2.putText(vis, name, (hit.x - radius, hit.y - radius - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)

        cv2.putText(vis, f"{w}x{h}  profile={profile}  score={score:.2f}  "
                         f"in_combat={in_combat}",
                    (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.85,
                    (0, 255, 255), 2, cv2.LINE_AA)

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        out = os.path.join(OUTPUT_DIR, 'combat_layout_calib.png')
        cv2.imwrite(out, vis)
        self.log_info(f"标注图已保存: {os.path.abspath(out)}")
        self.log_info("绿圈=圆识别命中，橙圈=回退固定布局，品红点=档案里的先验中心")

        # ---- 4. 打印可直接抄进配置的坐标表 ----
        merged = dict(layout)
        for name, hit in hits.items():
            if hit.detected:
                merged[name] = (hit.x / w, hit.y / h)
        self.log_info(f"把下面内容填入全局配置「{LAYOUT_CONFIG_NAME}」"
                      f"（玩法={profile if profile in LAYOUT_PROFILES else '自动'}）:")
        self.log_info(f"  玩法: {profile if profile in LAYOUT_PROFILES else '自动'}")
        for name, value in layout_to_config(merged).items():
            self.log_info(f"  {name}: {value}")

        self.log_info("校准完成")
