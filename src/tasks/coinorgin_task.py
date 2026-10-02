"""丰饶之间（经验副本）自动化。

流程（和最初的设计保持一致）：
    主界面点「指南」进入丰饶之间 -> 点「挑战」进入战斗
    -> 识别战斗布局后，用点击技能按钮的方式打输出
    -> **OCR 看到「经验」（结算界面）就停止战斗循环**
    -> **持续点击屏幕中央跳过结算，直到出现 main_adventure 回到主界面**

进入方式变化：原来是在主界面滑动找 ``main_coinorign`` 图标，但每个玩家的
主页面背景不同、经常匹配不到；改成走「指南」列表（见 guide_nav.py），
在固定位置滑动找 ``guide_coinorign`` 再点它的「前往」。

关于出招方式：本项目走 ADB/IPC 通道，``send_key`` 注入的是 Android keyevent，
火影忍者手游不响应；只有 ``click``（MuMu 原生触控注入）才有效。因此战斗循环
全部使用 CombatTask.click_button() 点击技能按钮，详见 src/tasks/combat_ui.py。

关于布局识别：进战斗后先 ensure_combat_layout() 判断当前是哪种玩法 HUD。
识别不出来就**拒绝出手**并退出——宁可什么都不做，也不要在错误坐标上乱点。
"""

import re
import time

from src.tasks.combat_task import CombatTask

# 进入方式：走「指南」列表
GUIDE_ITEM = 'guide_coinorign'
GUIDE_TEXT = '丰饶之间'   # 指南列表里条目的文字（OCR 识别）
GUIDE_GO = 'guide_coinorigngo'

# 战斗结算界面的关键词：看到任意一个就认为这一局打完了。
# 注意用正则做包含匹配——ok-script 传纯字符串时是**精确匹配**，
# match=['击败'] 不会命中「击败20个掘金贼」。
BATTLE_END_PATTERNS = [
    re.compile(r'经验'),
    re.compile(r'挑战成功'),
    re.compile(r'战斗结束'),
    re.compile(r'副本完成'),
    re.compile(r'获得奖励'),
]

# 主判据（OCR 结算关键词）的检查间隔（轮）
OCR_CHECK_EVERY = 2
# 辅助判据（技能按钮整体消失）的刷新间隔（轮）与连续确认次数
UI_CHECK_EVERY = 3
UI_GONE_CONFIRM = 2


class CoinOrginTask(CombatTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "丰饶之间"
        self.description = "自动刷丰饶之间经验副本"

    def run(self):
        self.log_info("开始丰饶之间...")

        # 1. 走「指南」进入丰饶之间
        if not self.enter_guide(GUIDE_TEXT, GUIDE_GO, item_feature=GUIDE_ITEM):
            self.log_error("没能通过指南进入丰饶之间，任务终止")
            return
        self.sleep(1.5)

        # 2. 轮询检测"挑战"，最多等 10 秒
        if not self.wait_for_ocr("挑战", time_out=10):
            self.log_warning("未出现'挑战'，开始点 popu_cancel 逐层退出到主界面")
            if not self.retreat_to_main():
                self.log_warning("未能回到主界面，任务结束")
            return

        # 3. 点击"挑战"
        if not self.click_ocr_text("挑战", time_out=3.0):
            self.log_error("点击'挑战'失败，开始点 popu_cancel 逐层退出到主界面")
            if not self.retreat_to_main():
                self.log_warning("未能回到主界面，任务结束")
            return

        # 4. 等进入战斗、识别布局，然后打到 OCR 看见"经验"为止
        self.sleep(1.5)
        if not self.ensure_combat_layout(max_frames=12, log=True):
            # 没能识别出战斗界面，说明多半根本没进战斗（"挑战"没点生效，
            # 或者被弹窗挡住）。这种情况该关弹窗退回主界面，而不是在非战斗
            # 画面上点屏幕中央。
            self.log_error("未识别出战斗布局，判定未进入战斗")
            if not self.retreat_to_main():
                self.log_warning("未能回到主界面，任务结束")
            return

        self.log_info("已进入战斗，开始点击式技能循环（持续到出现'经验'）")
        self.battle_loop()

        # 5. 持续点击屏幕中央跳过结算，直到出现 main_adventure
        self.return_to_main()

        self.log_info("丰饶之间任务结束")

    # ================= 战斗循环 =================

    def battle_loop(self, max_loops=300, grace_loops=0):
        """点击技能按钮输出，直到看到结算界面。

        每个循环：普攻连点补伤害，再依次丢一技能/二技能/大招。
        大招能量未满时点了没反应，所以不用额外判断，直接点即可；技能有冷却，
        点了也不亏，循环会反复重试。

        结束判定（主 + 辅）：
          主：OCR 到「经验」等结算关键词 —— 这是本任务原本的需求，也是最先
              能确认"这局打完了"的信号，每 ``OCR_CHECK_EVERY`` 轮查一次。
          辅：核心技能按钮连续 ``UI_GONE_CONFIRM`` 次刷新都消失 —— 结算时整个
              战斗 HUD 会一起消失，比 OCR 更快一点，但要连续确认，以免被技能
              动画期间的 HUD 隐藏误判。

        ``grace_loops``：前若干轮不做结束判定，避免刚进战斗误判"已结束"。
        """
        gone_streak = 0
        for i in range(max_loops):
            # 用户点了停止就立刻收手（这个循环最多 300 轮，不查会一直打下去）
            if self.should_stop('战斗循环'):
                return False

            # 主判据：结算界面 OCR（"经验"等）
            if i >= grace_loops and i % OCR_CHECK_EVERY == 0:
                # 战斗途中可能弹「点击任意位置关闭」（被踢出 / 断线等）。
                # 处理完通常已经被送回主页面，本局就到此为止。
                if self.dismiss_click_anywhere():
                    self.log_warning("战斗中出现「任意位置关闭」，已退回主页面，本局结束")
                    return True

                if self.detect_ocr_text_any(BATTLE_END_PATTERNS):
                    self.log_info(f"第 {i + 1} 轮 OCR 检测到结算界面（经验），战斗结束")
                    return True

            # 辅助判据：技能按钮整体消失，连续确认
            if i % UI_CHECK_EVERY == 0:
                self.refresh_combat_buttons()
                if (self._buttons is not None
                        and self.combat_ui_confidence() < 0.5):
                    gone_streak += 1
                    if i >= grace_loops and gone_streak >= UI_GONE_CONFIRM:
                        self.log_info(f"第 {i + 1} 轮技能按钮连续 {gone_streak} 次消失，"
                                      f"判定战斗结束")
                        return True
                else:
                    gone_streak = 0

            self.normal_attack(after_sleep=0.08)
            self.normal_attack(after_sleep=0.12)
            self.skill_1()
            self.skill_2()
            self.sleep(0.12)
            self.ultimate()
            self.sleep(0.3)

        self.log_warning(f"达到最大循环 {max_loops} 轮，仍未检测到结算界面")
        return False

    def retreat_to_main(self, max_rounds=40, interval=1.0):
        """退回主页面。

        直接用 PageNavTask.back_to_main()：不在主页时依次尝试
        popu_cancel / reward_cancel / gacha_cancel / clean_cancel /
        activity_cancel / team_cancel / friend_cancel / coin_cancel，
        点到哪个算哪个，循环直到出现 main_adventure。

        这里保留一个同名的薄封装，方便本任务里语义化调用，也便于以后单独调整
        重试次数而不影响其它任务。
        """
        self.log_info("不在主页面，开始点关闭按钮逐层退出...")
        return self.back_to_main(max_rounds=max_rounds, interval=interval)

    def return_to_main(self, max_clicks=60, interval=1.0):
        """持续点击屏幕中央推进结算，直到出现 main_adventure 回到主界面。

        对应最初的需求：看到"经验"之后，每隔 ``interval`` 秒点一次屏幕中央，
        最多点 ``max_clicks`` 次，直到模板匹配到主界面的 main_adventure。
        """
        self.log_info("开始持续点击屏幕中央，跳过结算直到回到主界面...")
        self.sleep(1.0)
        for i in range(max_clicks):
            if self.should_stop('结算点击'):
                return False
            # 结算 / 领奖时可能弹「点击任意位置关闭」，先把它和后续弹窗清掉
            if self.dismiss_click_anywhere():
                self.log_info("已处理「任意位置关闭」提示")
            self.click_relative(0.5, 0.5)
            self.sleep(interval)
            if self.find_one('main_adventure', threshold=0.8):
                self.log_info(f"第 {i + 1} 次点击后检测到 main_adventure，已回到主界面")
                return True
        self.log_warning(f"{int(max_clicks * interval)} 秒内未检测到 main_adventure")
        return False

    # ================= OCR 工具 =================

    def detect_ocr_text(self, keyword):
        """判断画面里是否存在某个文本（字符串按精确匹配）。"""
        boxes = self.wait_ocr(match=[keyword], time_out=1.0)
        return bool(boxes)

    def detect_ocr_text_any(self, patterns):
        """按正则模式列表做包含匹配（单次整屏 OCR，不做等待重试）。

        一次 ``ocr()`` 约 0.15~0.3 秒，所以战斗循环里每 2 轮才查一次；
        用 ``wait_ocr`` 那种带超时的轮询每轮要花 1 秒，把出招节奏拖垮。
        """
        return bool(self.ocr(match=patterns))

    def click_ocr_text(self, keyword, time_out=2.0):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    def wait_for_ocr(self, keyword, time_out=15):
        start = time.time()
        while time.time() - start < time_out:
            if self.detect_ocr_text(keyword):
                return True
            self.sleep(0.5)
        return False

    # ================= 安全点击 =================

    def safe_click_feature(self, feature, threshold=0.8, time_out=5):
        start = time.time()
        while time.time() - start < time_out:
            box = self.find_one(feature, threshold=threshold)
            if box:
                self.click_box(box)
                return True
            self.sleep(0.3)
        return False

    # ================= 通用工具 =================

    def swipe_find(self, feature, max_swipes=4, click=False):
        self.log_info(f"[滑动查找] 检查当前画面是否有 '{feature}'")
        box = self.find_one(feature, threshold=0.8)
        if box:
            self.log_info(f"[滑动查找] 当前画面已找到 '{feature}'，无需滑动")
            return self._stable_click(feature, box, click)

        for i in range(max_swipes):
            self.swipe_relative(0.85, 0.5, 0.15, 0.5, duration=0.3)
            self.sleep(0.7)
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 左滑 {i + 1} 次后找到 '{feature}'")
                return self._stable_click(feature, box, click)

        for i in range(max_swipes * 2):
            self.swipe_relative(0.15, 0.5, 0.85, 0.5, duration=0.3)
            self.sleep(0.7)
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 右滑 {i + 1} 次后找到 '{feature}'")
                return self._stable_click(feature, box, click)

        self.log_warning(f"[滑动查找] 左右滑遍仍未找到 '{feature}'")
        return None

    def _stable_click(self, feature, box, click):
        self.sleep(0.5)
        box2 = self.find_one(feature, threshold=0.8)
        if box2 is None:
            self.log_warning(f"'{feature}' 第二次识别丢失，放弃点击")
            return None

        dx = abs(box2.x - box.x)
        dy = abs(box2.y - box.y)
        threshold_x = int(self.width * 0.01)
        threshold_y = int(self.height * 0.01)

        if dx > threshold_x or dy > threshold_y:
            self.log_warning(f"'{feature}' 位置仍在变化 (dx={dx}, dy={dy})，再等一次")
            self.sleep(0.5)
            box3 = self.find_one(feature, threshold=0.8)
            if box3 is None:
                return None
            box2 = box3

        self.log_info(f"'{feature}' 位置已稳定: ({box2.x}, {box2.y})")
        if click:
            self.click_box(box2)
        return box2

    def click_relative(self, rel_x, rel_y):
        x = int(self.width * rel_x)
        y = int(self.height * rel_y)
        self.click(x, y)

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)
