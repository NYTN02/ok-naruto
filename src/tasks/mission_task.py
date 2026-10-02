from src.tasks.guide_nav import GuideNavTask

# 进入方式：走「指南」列表（原来是在主页面找 main_mission，
# 但每个玩家主页背景不同、经常匹配不到；指南列表位置固定得多）
GUIDE_ITEM = 'guide_mission'
GUIDE_GO = 'guide_missiongo'

# 没能接取到任务时，回主页面重新进入任务集会所再试的次数。
# 「没能接取」包含三种：没进得去界面 / 一次都没点到「接取」 / 点到了但没走到「出发」。
# 用户明确要求「没点到接取」也要重进重试，所以 empty 不再是终止条件。
MAX_ACCEPT_RETRY = 2

# 一轮里最多尝试接取几个任务
MAX_ACCEPT_LOOP = 15

# 接取过程的三种结果
NO_MORE = 'no_more'      # 画面上已经没有「接取」了，正常收尾
FAILED = 'failed'        # 点了「接取」却没走到「出发」
ACCEPTED = 'accepted'    # 成功接取了一个


class MissionTask(GuideNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "任务集会所"
        self.description = "自动领取奖励和接取任务"  # 可选
        self._last_round_had_attempt = False

    def run(self):
        self.log_info("开始任务集会所...")

        for attempt in range(MAX_ACCEPT_RETRY + 1):
            if attempt:
                self.log_warning(f"===== 重新进入任务集会所（第 {attempt} 次重试）=====")

            status, accepted = self.run_once()

            if status == 'ok':
                self.log_info(f"本次成功接取 {accepted} 个任务")
                self.log_info("任务集会所任务结束")
                return

            # 没能接取到任务 —— 三种情况都算：
            #   no_entry  没进得去任务集会所界面（指南入口那步失败）
            #   empty     进去了但一次都没点到「接取」
            #   failed    点到了「接取」但没走到「出发」
            reason = {
                'no_entry': "没能进入任务集会所界面",
                'empty': "进入了界面但一次都没点到「接取」",
                'failed': "点到了「接取」但没走到「出发」",
            }.get(status, status)
            self.log_warning(f"没有成功接取任务：{reason}")

            if attempt < MAX_ACCEPT_RETRY:
                # 回主页面，下一轮 run_once() 会重新走指南进来
                self.log_warning(f"回主页面后重新进入任务集会所再试"
                                 f"（{attempt + 1}/{MAX_ACCEPT_RETRY}）")
                self.back_to_main(max_rounds=15, interval=0.8)
                self.sleep(1.0)
            else:
                self.log_warning(f"重试 {MAX_ACCEPT_RETRY} 次仍未接取到任务，本次跳过")
                self.back_to_main(max_rounds=15, interval=0.8, log=False)

    def run_once(self):
        """跑一轮任务集会所。

        :return: ``(status, accepted)``
                 status: 'no_entry'  没找到入口
                         'empty'     本来就没有可接取的任务（正常，不算失败）
                         'failed'    点了「接取」但没走到「出发」
                         'ok'        至少成功接取了一个
        """
        self._last_round_had_attempt = False

        # 1. 走「指南」进入任务集会所
        if not self.enter_guide(GUIDE_ITEM, GUIDE_GO):
            return 'no_entry', 0
        self.sleep(1.2)  # 等待界面加载

        # 2. 先领所有"可领取"
        self.collect_all_rewards()

        # 3. 循环接取任务
        accepted = 0
        for loop_count in range(1, MAX_ACCEPT_LOOP + 1):
            if self.should_stop('任务集会所接取'):
                break
            self.log_info(f"--- 第 {loop_count} 轮接取 ---")
            result = self.accept_one_mission()

            if result == NO_MORE:
                self.log_info("没有更多'接取'，结束循环")
                break

            if result == FAILED:
                self.log_warning("这一次接取没有成功（没走到'出发'）")
                break

            accepted += 1
            # 回到集会所后，可能又出现新的"可领取"
            self.collect_all_rewards()

        # 4. 退出任务集会所
        self.sleep(0.5)
        if self.wait_click_feature('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已退出任务集会所")
        else:
            self.log_warning("未找到退出按钮")

        if accepted:
            return 'ok', accepted
        # 一次没接上：区分"本来就没得接"和"接了但失败"
        return ('failed' if self._last_round_had_attempt else 'empty'), 0

    def accept_one_mission(self):
        """尝试接取一个任务，返回 NO_MORE / FAILED / ACCEPTED。

        判定"没有成功接取"的依据：点了「接取」以及后面那个固定坐标之后，
        界面本该切到选小队 / 确认页（那里有「出发」按钮）。如果等不到
        ``mission_go``，就说明这次接取没成功 —— 多半是被弹窗挡住了，
        所以调用方要先点 popu_cancel 退回主页面再重跑。
        """
        # 检测有没有"接取"
        if not self.click_ocr_text("接取", time_out=1.0):
            return NO_MORE

        self._last_round_had_attempt = True
        self.sleep(1.2)  # 等待界面切换

        # 点击固定位置 rel(0.686, 0.210)
        self.click_relative(0.686, 0.210)
        self.sleep(1.2)

        # OCR 找"推荐小队"，有就点
        if self.click_ocr_text("推荐小队", time_out=1.0):
            self.sleep(0.8)

        # 点击"出发"
        if not self.wait_click_feature('mission_go', threshold=0.8, time_out=4):
            self.log_warning("没等到'出发'按钮，判定这次接取失败")
            try:
                if self.find_one('popu_cancel', threshold=0.8):
                    self.log_warning("画面上有 popu_cancel，应该是被弹窗挡住了")
            except Exception:
                pass
            return FAILED

        self.sleep(1.8)  # 等待出发与返回
        return ACCEPTED

    # ---------------- 通用工具方法 ----------------

    def swipe_find(self, feature, max_swipes=4, click=False):
        """
        先检查当前画面，没有才左右滑动查找。
        每次找到都经过 _stable_click 确认稳定后才点击。
        """
        # ---- Step 1: 先看当前画面 ----
        self.log_info(f"[滑动查找] 检查当前画面是否有 '{feature}'")
        box = self.find_one(feature, threshold=0.8)
        if box:
            self.log_info(f"[滑动查找] 当前画面已找到 '{feature}'，无需滑动")
            return self._stable_click(feature, box, click)

        # ---- Step 2: 向左滑（看右侧内容）----
        self.log_info(f"[滑动查找] 当前画面没找到，开始向左滑")
        for i in range(max_swipes):
            self.swipe_relative(0.85, 0.5, 0.15, 0.5, duration=0.3)
            self.sleep(0.7)  # 等惯性停稳
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 左滑 {i + 1} 次后找到 '{feature}'")
                return self._stable_click(feature, box, click)

        # ---- Step 3: 向右滑回（看左侧内容）----
        self.log_info(f"[滑动查找] 左滑到底仍未找到，开始向右滑回")
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
        """
        确认画面已经稳定后再点击。
        连续两次识别，box 位置差异小于阈值才认为稳定。
        """
        self.sleep(0.5)  # 再等一会，让惯性动画彻底结束
        box2 = self.find_one(feature, threshold=0.8)
        if box2 is None:
            self.log_warning(f"'{feature}' 第二次识别丢失，放弃点击")
            return None

        # 位置差异阈值：屏幕宽高的 1%
        dx = abs(box2.x - box.x)
        dy = abs(box2.y - box.y)
        threshold_x = int(self.width * 0.01)
        threshold_y = int(self.height * 0.01)

        if dx > threshold_x or dy > threshold_y:
            self.log_warning(
                f"'{feature}' 位置仍在变化 (dx={dx}, dy={dy})，再等一次"
            )
            self.sleep(0.5)
            box3 = self.find_one(feature, threshold=0.8)
            if box3 is None:
                return None
            box2 = box3

        self.log_info(f"'{feature}' 位置已稳定: ({box2.x}, {box2.y})")
        if click:
            self.click_box(box2)
        return box2

    def click_ocr_text(self, keyword, time_out=0.5):
        """OCR 查找包含关键词的文字并点击"""
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    def collect_all_rewards(self):
        """循环点击所有'可领取'，处理确认框和领取后的物品展示界面"""
        count = 0
        for _ in range(20):
            if not self.click_ocr_text("可领取", time_out=1.0):
                break
            self.sleep(0.5)
            count += 1

            # 情况A：弹出"是否一键领取所有奖励"确认框
            if self.click_ocr_text("确定", time_out=1.5):
                self.log_info("点击了'确定'，一键领取所有奖励")
                self.sleep(1.2)
                # 展示界面出现后，点屏幕中间关闭
                self.click_relative(0.5, 0.5)
                self.sleep(0.8)
            else:
                # 情况B：没有确认框，直接弹出物品展示界面
                # 也点一下屏幕中间，把展示界面关掉
                self.click_relative(0.5, 0.5)
                self.sleep(0.8)

        if count > 0:
            self.log_info(f"共点击 {count} 次'可领取'")

    def click_relative(self, rel_x, rel_y):
        """按相对坐标点击（0~1）"""
        x = int(self.width * rel_x)
        y = int(self.height * rel_y)
        self.click(x, y)
        self.log_info(f"点击相对坐标 ({rel_x}, {rel_y}) -> ({x}, {y})")

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        """按相对坐标滑动（0~1）"""
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)