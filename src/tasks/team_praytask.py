import re

from src.tasks.guide_nav import DAILY_TASK_PATTERN, GuideNavTask

# 点击 team_coinpray（祈福）时的尝试次数与间隔。
# 这个按钮点下去之后界面会卡一下/有动画，一次不一定点得中，
# 所以隔 2 秒重试，最多点 3 次。
COINPRAY_ATTEMPTS = 3
COINPRAY_INTERVAL = 2.0

# ---------------------------------------------------------------------------
# 进入方式：主页面 main_reward -> 「每日任务」 -> 左右滑动找 reward_teampray
#          -> 点它正下方的「立刻前往」 -> 进入含 team_coinpray/team_prayreward 的界面
#
# 原来是主页面滑动找 main_team，但每个玩家主页背景不同、经常匹配不到，
# 所以改走「每日任务」这条固定的入口。
# ---------------------------------------------------------------------------
REWARD_ENTRY = 'main_reward'        # 主页面上的每日任务/奖励入口
TEAMPRAY_ITEM = 'reward_teampray'   # 每日任务列表里的组织祈福条目（模板兜底）
TEAMPRAY_TEXT = '组织祈福'           # 条目的文字，OCR 识别用
TEAMPRAY_PATTERN = re.compile(re.escape(TEAMPRAY_TEXT))
GO_TEXT = '立刻前往'                 # 条目正下方的按钮文字

# 在每日任务列表上「按住屏幕中央 -> 左右拖动 -> 松开」
REWARD_SCROLL_X = 0.5
REWARD_SCROLL_Y = 0.5
REWARD_SCROLL_DISTANCE = 0.35       # 每次拖动的距离（相对屏幕宽度）
REWARD_SCROLL_MAX = 8               # 单向最多滑几次
REWARD_ENTRY_TIMEOUT = 5.0
REWARD_OPEN_WAIT = 1.8
REWARD_ITEM_TIMEOUT = 3.0


class TeamPrayTask(GuideNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "组织祈福"
        self.description = "自动进行组织祈福并领取奖励"  # 可选

    def run(self):
        self.log_info("开始组织祈福...")

        # ========== 1. 走「每日任务」进入祈福界面 ==========
        if not self.enter_teampray():
            self.log_error("没能进入祈福界面，任务终止")
            return
        self.sleep(1.5)

        # ========== 2. 点击玩法 ==========
        if not self.wait_click_feature('team_playway', threshold=0.8, time_out=5):
            self.log_error("未找到玩法按钮")
            self.cleanup_exit()
            return
        self.sleep(1.2)

        # ========== 3. OCR 点击最左边的"前往" ==========
        if not self.click_leftmost_ocr("前往", time_out=3.0):
            self.log_error("未找到'前往'按钮")
            self.cleanup_exit()
            return
        self.sleep(1.5)

        # ========== 4. 点击 team_coinpray（最多 3 次，每次间隔 2 秒）==========
        if not self.click_coinpray():
            self.log_warning("3 次都没点到 team_coinpray，尝试退出")
            self.cleanup_exit()
            return
        self.sleep(1.2)

        # ========== 4.5 检测"今日次数已达上限" ==========
        if self.click_ocr_text("今日次数已达上限", time_out=2.0):
            self.log_info("检测到'今日次数已达上限'，点击确定")
            self.sleep(1.0)
            if self.click_ocr_text("确定", time_out=3.0):
                self.log_info("已点击确定，继续祈福流程")
            else:
                self.log_warning("未找到'确定'按钮，继续祈福流程")
            self.sleep(1.0)
        else:
            self.log_info("未检测到次数上限提示，直接继续祈福流程")

        # ========== 5. 循环点 team_prayreward 和三个 getreward ==========
        max_rounds = 10
        for i in range(max_rounds):
            if self.should_stop('组织祈福领奖'):
                break
            clicked_any = False

            box = self.find_one('team_prayreward', threshold=0.8)
            if box:
                self.click_box(box)
                self.log_info(f"第 {i+1} 轮：点击 team_prayreward")
                self.sleep(1.0)
                clicked_any = True

            for name in ['team_getreward', 'team_getreward2', 'team_getreward3']:
                box = self.find_one(name, threshold=0.8)
                if box:
                    self.click_box(box)
                    self.log_info(f"第 {i+1} 轮：点击 {name}")
                    self.sleep(1.0)
                    clicked_any = True
                else:
                    self.log_info(f"第 {i+1} 轮：未找到 {name}，跳过")

            if not clicked_any:
                self.log_info(f"第 {i+1} 轮：什么都没找到，退出循环")
                break
        else:
            self.log_warning(f"达到最大轮数 {max_rounds}，强制退出循环")

        # ========== 6. 点击右上角关闭 ==========
        self.click_relative(0.956, 0.051)
        self.sleep(1.0)

        # ========== 7. 点击 popu_cancel ==========
        if self.wait_click_feature('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 popu_cancel")
            self.sleep(1.0)

        # ========== 8. 点击 team_cancel 退出到主页面 ==========
        if self.wait_click_feature('team_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 team_cancel")
        else:
            self.log_warning("未找到 team_cancel")

        # ========== 9. 最终兜底：清理残留弹窗 ==========
        self.cleanup_exit()

        self.log_info("组织祈福任务结束")

    # ================= 祈福按钮 =================

    def click_coinpray(self):
        """尝试点击 team_coinpray 最多 ``COINPRAY_ATTEMPTS`` 次，每次间隔 2 秒。

        返回 True 表示至少点中了一次。
        """
        for attempt in range(1, COINPRAY_ATTEMPTS + 1):
            box = None
            try:
                box = self.find_one('team_coinpray', threshold=0.8)
            except Exception as e:
                self.log_warning(f"第 {attempt} 次查找 team_coinpray 出错: {e}")

            if box:
                self.click_box(box)
                self.log_info(f"第 {attempt}/{COINPRAY_ATTEMPTS} 次点击 team_coinpray "
                              f"({box.x}, {box.y})")
                return True

            self.log_warning(f"第 {attempt}/{COINPRAY_ATTEMPTS} 次没找到 team_coinpray")
            if attempt < COINPRAY_ATTEMPTS:
                self.sleep(COINPRAY_INTERVAL)

        return False

    # ================= 进入祈福界面 =================

    def enter_teampray(self):
        """走「每日任务」进入组织祈福。

        流程（按需求）：
          1. 主页面点 main_reward
          2. OCR 识别并点击「每日任务」
          3. 按住屏幕中央左右滑动（每次都是按住-拖动-松开），
             找到 reward_teampray
          4. OCR 找 reward_teampray **正下方**的「立刻前往」并点击
             -> 进入包含 team_coinpray / team_prayreward 的界面

        任何一步失败都会退出到主页面再返回 False。
        """
        # 0. main_reward 在主界面上，先确保在主页
        if not self.is_main_page():
            self.log_info("当前不在主页面，先退回主页面")
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

        # 1. 点 main_reward
        if not self.click_feature(REWARD_ENTRY, time_out=REWARD_ENTRY_TIMEOUT):
            self.log_error(f"未找到 {REWARD_ENTRY}，无法进入每日任务")
            return False
        self.sleep(REWARD_OPEN_WAIT)

        # 2. OCR 点「每日任务」
        if not self.click_text(DAILY_TASK_PATTERN, time_out=REWARD_ENTRY_TIMEOUT):
            self.log_error("没找到「每日任务」")
            self.exit_reward()
            return False
        self.sleep(REWARD_OPEN_WAIT)

        # 3. 滑动 + OCR 找「组织祈福」条目
        box = self.find_reward_item(TEAMPRAY_ITEM)
        if box is None:
            self.log_warning(f"每日任务里滑遍都没找到「{TEAMPRAY_TEXT}」")
            self.exit_reward()
            return False

        # 4. 点它正下方的「立刻前往」
        if not self.click_below(box, GO_TEXT, time_out=REWARD_GO_TIMEOUT):
            self.log_warning(f"没找到「{TEAMPRAY_TEXT}」正下方的「{GO_TEXT}」")
            self.exit_reward()
            return False
        self.sleep(REWARD_OPEN_WAIT)

        self.log_info("已进入组织祈福界面")
        return True

    def find_reward_item(self, feature, max_swipes=REWARD_SCROLL_MAX):
        """在每日任务列表里左右滑动找条目，返回 Box 或 None。

        **优先 OCR 认「组织祈福」这几个字**（列表条目本身就是文字），
        认不到再用 reward_teampray 模板兜底。

        先往左拖（看右边的内容），再往右拖（看回左边）。
        """
        box = self.find_teampray_on_screen()
        if box is not None:
            self.log_info(f"[每日任务] 当前画面已看到「{TEAMPRAY_TEXT}」")
            return box

        for i in range(1, max_swipes + 1):
            self.log_info(f"[每日任务] 向左滑 {i}/{max_swipes} 次找「{TEAMPRAY_TEXT}」")
            self.scroll_reward(direction=1)
            box = self.find_teampray_on_screen()
            if box is not None:
                self.log_info(f"[每日任务] 向左滑 {i} 次后找到「{TEAMPRAY_TEXT}」")
                return box

        for i in range(1, max_swipes * 2 + 1):
            self.log_info(f"[每日任务] 向右滑 {i}/{max_swipes * 2} 次找「{TEAMPRAY_TEXT}」")
            self.scroll_reward(direction=-1)
            box = self.find_teampray_on_screen()
            if box is not None:
                self.log_info(f"[每日任务] 向右滑 {i} 次后找到「{TEAMPRAY_TEXT}」")
                return box

        return None

    def find_teampray_on_screen(self):
        """当前画面找「组织祈福」：先 OCR 文字，再退回 reward_teampray 模板。"""
        try:
            boxes = self.ocr(match=[TEAMPRAY_PATTERN])
        except Exception as e:
            self.log_debug(f"OCR 找「{TEAMPRAY_TEXT}」出错: {e}")
            boxes = None
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            if all(hasattr(box, a) for a in ('x', 'y', 'width', 'height')):
                self.log_info(f"[每日任务] OCR 认到「{TEAMPRAY_TEXT}」({box.x}, {box.y})")
                return box
        box = self._safe_find_one(TEAMPRAY_ITEM)
        if box is not None:
            self.log_info(f"[每日任务] OCR 没认到，改用模板 {TEAMPRAY_ITEM} 找到条目")
        return box

    def scroll_reward(self, direction=1):
        """在每日任务列表上「按住屏幕中央 -> 左右拖动 -> 松开」。

        direction=1 往左拖（内容右移，看右边）；-1 反之。
        """
        y = int(self.height * REWARD_SCROLL_Y)
        half = REWARD_SCROLL_DISTANCE / 2
        x_from = int(self.width * (REWARD_SCROLL_X + (half if direction > 0 else -half)))
        x_to = int(self.width * (REWARD_SCROLL_X - (half if direction > 0 else -half)))
        self.gesture(x_from, y, x_to, y)

    def exit_reward(self):
        """从每日任务界面退出到主页面。

        先试 reward_cancel（每日任务界面的关闭按钮），再退回主页面兜底。
        """
        if self.click_feature('reward_cancel', time_out=REWARD_ITEM_TIMEOUT):
            self.log_info("已点击 reward_cancel")
            self.sleep(1.2)
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    # ================= OCR 工具 =================

    def click_ocr_text(self, keyword, time_out=0.5):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    def click_leftmost_ocr(self, keyword, time_out=3.0):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if not boxes:
            return False
        if not isinstance(boxes, list):
            boxes = [boxes]

        boxes = [b for b in boxes if self._is_box_like(b)]
        if not boxes:
            return False

        leftmost = min(boxes, key=lambda b: b.x)
        self.log_info(f"点击最左边的'{keyword}': ({leftmost.x}, {leftmost.y})")
        self.click_box(leftmost)
        return True

    # ================= 兜底清理 =================

    def cleanup_exit(self, max_rounds=5):
        self.log_info("[清理] 开始尝试退出到主页面")
        for i in range(max_rounds):
            box = self.find_one('team_cancel', threshold=0.8)
            if box:
                self.click_box(box)
                self.log_info(f"[清理] 第 {i+1} 轮：点击 team_cancel")
                self.sleep(0.8)
                continue

            box = self.find_one('popu_cancel', threshold=0.8)
            if box:
                self.click_box(box)
                self.log_info(f"[清理] 第 {i+1} 轮：点击 popu_cancel")
                self.sleep(0.8)
                continue

            self.log_info("[清理] 已无残留弹窗，清理结束")
            break

    # ================= 通用工具 =================

    def _is_box_like(self, r):
        return all(hasattr(r, a) for a in ('x', 'y', 'width', 'height'))

    def swipe_find(self, feature, max_swipes=4, click=False):
        self.log_info(f"[滑动查找] 检查当前画面是否有 '{feature}'")
        box = self.find_one(feature, threshold=0.8)
        if box:
            self.log_info(f"[滑动查找] 当前画面已找到 '{feature}'，无需滑动")
            return self._stable_click(feature, box, click)

        self.log_info(f"[滑动查找] 当前画面没找到，开始向左滑")
        for i in range(max_swipes):
            self.swipe_relative(0.85, 0.5, 0.15, 0.5, duration=0.3)
            self.sleep(0.7)
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 左滑 {i+1} 次后找到 '{feature}'")
                return self._stable_click(feature, box, click)

        self.log_info(f"[滑动查找] 左滑到底仍未找到，开始向右滑回")
        for i in range(max_swipes * 2):
            self.swipe_relative(0.15, 0.5, 0.85, 0.5, duration=0.3)
            self.sleep(0.7)
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 右滑 {i+1} 次后找到 '{feature}'")
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
        self.log_info(f"点击相对坐标 ({rel_x}, {rel_y}) -> ({x}, {y})")

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)