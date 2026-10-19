from src.tasks.guide_nav import GuideNavTask

# 进入方式：走「指南」列表（原来是在主页面找 main_mission，
# 但每个玩家主页背景不同、经常匹配不到；指南列表位置固定得多）
GUIDE_ITEM = 'guide_mission'
GUIDE_TEXT = '任务集'   # 指南列表里条目的文字（OCR 子串匹配）
# 显式指定容错前缀：自动推导会得到 2 字的「任务」，
# 而指南界面上本来就有一处独立的「任务」标签，容易误匹配。
GUIDE_PREFIX_TEXT = '任务集'
REWARD_ITEM_TEXT = '集会所'   # 走「奖励」时在每日任务里识别的文字
GUIDE_GO = 'guide_missiongo'

# 接取任务的尝试次数：首次 + 重试 2 次 = 最多进任务集会所 3 次。
# 每次失败都先回主页面再重新进入（用户指定的流程）。
ACCEPT_ATTEMPTS = 3

# 一轮里最多尝试接取几个任务
MAX_ACCEPT_LOOP = 15

# ---------------------------------------------------------------------------
# 领奖励（用户指定的流程）
#
# 点「可领取」→ **检测画面有没有变化** → 分两种情况：
#   A. 弹「是否一键领取所有奖励」确认框 → 点「确定」
#   B. 没有确认框但画面变了（直接弹物品展示界面）→ 点右上角 CLOSE_REL 关掉
# 然后回到循环顶部：没有「可领取」或看到 MISSION_NONE，就开始接取任务。
#
# ⚠️ 关键：**画面没变化时不能盲点**。以前的实现是"没找到确定就点屏幕中心"，
#    而那时可能什么都没弹出来 —— 屏幕中央很可能就是任务条目，一点就打开了
#    别的界面，后面的接取逻辑全乱。现在检测到没变化直接收手。
# ---------------------------------------------------------------------------
MISSION_NONE = 'mission_none'      # 领奖完成后出现的标记（= 可以开始接取了）
CLOSE_REL = (0.952, 0.051)         # 物品展示界面右上角的关闭位置（用户实测）
MAX_COLLECT_LOOP = 20              # 领奖循环上限
COLLECT_CLICK_WAIT = 0.6           # 点「可领取」后等多久再判断画面变化
CONFIRM_TEXT = '确定'               # 「是否一键领取所有奖励」确认框的按钮
CONFIRM_TIMEOUT = 1.5
CONFIRM_WAIT = 1.2
CLOSE_WAIT = 1.0                   # 点右上角关闭后等 1 秒（用户指定）

# 接取过程的三种结果
NO_MORE = 'no_more'      # 画面上已经没有「接取」了，正常收尾
FAILED = 'failed'        # 点了「接取」却没走到「出发」
ACCEPTED = 'accepted'    # 成功接取了一个


class MissionTask(GuideNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "任务集会所"
        self.description = "自动领取奖励和接取任务"  # 可选
        self.add_entry_mode_config(REWARD_ITEM_TEXT)

        self._last_round_had_attempt = False

    def run(self):
        """任务集会所：**一次进入**里完成"领奖励 + 接取任务"。

        用户指定的流程（不再分成两次进入）：

            进入任务集会所
              -> 循环领奖励，直到**没有「可领取」**或**出现 mission_none**
              -> 接着接取任务（就在同一个界面里）
            接取没成功 -> 回主页面重新进入再试（最多 ACCEPT_ATTEMPTS 次）
            连续几次都不行 -> 判定为异常，跳过任务集会所

        为什么不再分两阶段：领奖和接取本来就在同一个界面，来回进出只是白等；
        而且分阶段时"接取失败"会把领奖也赔进去。现在一次做完，
        只有**接取没成功**才回主页面重进。
        """
        self.log_info("开始任务集会所...")

        for attempt in range(1, ACCEPT_ATTEMPTS + 1):
            if self.should_stop('任务集会所'):
                return

            if not self.enter_mission_hall():
                self.log_warning(f"第 {attempt} 次进入任务集会所失败")
            else:
                self.log_info(f"第 {attempt}/{ACCEPT_ATTEMPTS} 次进入")
                self.collect_rewards()
                accepted, ok = self.accept_missions()
                self.exit_mission_hall()

                if accepted:
                    self.log_info(f"成功接取 {accepted} 个任务")
                    self.log_info("任务集会所任务结束")
                    return
                if not ok:
                    self.log_warning(f"第 {attempt} 次没有接取到任务")
                else:
                    self.log_warning(f"第 {attempt} 次没有可接取的任务")

            if attempt < ACCEPT_ATTEMPTS:
                self.log_warning(f"回主页面后重新进入再试（{attempt}/{ACCEPT_ATTEMPTS}）")
                self.back_to_main(max_rounds=15, interval=0.8)
                self.sleep(1.0)

        self.log_error(f"连续 {ACCEPT_ATTEMPTS} 次都没接取到任务，判定为异常，跳过任务集会所")
        self.back_to_main(max_rounds=15, interval=0.8, log=False)

    def collect_rewards(self, max_loops=MAX_COLLECT_LOOP):
        """领奖励：循环点「可领取」，直到没有可领的或出现 MISSION_NONE。

        每一步都**先检测画面有没有变化**再决定下一步做什么（见文件开头的说明）。
        """
        self.log_info("[领奖] 开始领取奖励")
        for i in range(1, max_loops + 1):
            if self.should_stop('任务集会所领奖'):
                return

            # 领奖结束的两种信号：看到 mission_none，或没有「可领取」了
            if self._safe_find_one(MISSION_NONE):
                self.log_info(f"[领奖] 看到 {MISSION_NONE}，领奖结束，开始接取任务")
                return

            before = self.screen_thumb()
            if not self.click_ocr_text("可领取", time_out=1.0):
                self.log_info("[领奖] 画面上没有「可领取」了，领奖结束")
                return
            self.log_info(f"[领奖] 第 {i} 次点击「可领取」")
            self.sleep(COLLECT_CLICK_WAIT)

            if not self.screen_changed(before, self.screen_thumb()):
                # 画面没变 = 这一下没生效（或者本来就没东西可领）。
                # **不能盲点** —— 屏幕中央多半是任务条目，点在它上面会打开别的界面。
                self.log_warning("[领奖] 点了「可领取」但画面没变化，"
                                 "不盲点（避免误点到任务条目），结束领奖")
                return

            # A. 「是否一键领取所有奖励」确认框
            if self.click_ocr_text(CONFIRM_TEXT, time_out=CONFIRM_TIMEOUT):
                self.log_info("[领奖] 点击了「确定」（一键领取所有奖励）")
                self.sleep(CONFIRM_WAIT)
                continue

            # B. 没有确认框但画面变了 -> 直接弹了物品展示界面，点右上角关掉
            self.log_warning(f"[领奖] 没有确认框但画面变了，"
                             f"点右上角 rel{CLOSE_REL} 关掉展示界面")
            self.click_relative(*CLOSE_REL)
            self.sleep(CLOSE_WAIT)      # 用户指定：等 1 秒再看有没有「可领取」

        self.log_warning(f"[领奖] 达到循环上限 {max_loops} 次，先去做接取")

    # ------------------------------------------------------------------
    # 步骤拆分
    # ------------------------------------------------------------------
    def enter_mission_hall(self):
        """走「指南」进入任务集会所界面。"""
        if not self.enter_by_mode(GUIDE_TEXT, GUIDE_GO,
                                          reward_item_text=REWARD_ITEM_TEXT,
                                          item_feature=GUIDE_ITEM):
            return False
        self.sleep(1.2)   # 等界面加载
        return True

    def exit_mission_hall(self):
        """点 popu_cancel 退出任务集会所界面。"""
        self.sleep(0.5)
        if self.wait_click('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已退出任务集会所")
        else:
            self.log_warning("未找到退出按钮")

    def accept_missions(self):
        """在任务集会所界面里接取任务。

        :return: ``(accepted, ok)``
                 accepted 成功接取的数量
                 ok       True 表示流程正常走完（包括"确实没有可接取的"）；
                         False 表示中途失败（接取点了却没走到出发）
        """
        accepted = 0
        for loop_count in range(1, MAX_ACCEPT_LOOP + 1):
            if self.should_stop('任务集会所接取'):
                break
            self.log_info(f"--- 第 {loop_count} 轮接取 ---")
            result = self.accept_one_mission()

            if result == NO_MORE:
                self.log_info("没有更多'接取'，结束循环")
                return accepted, True

            if result == FAILED:
                self.log_warning("这一次接取没有成功（没走到'出发'）")
                return accepted, False

            accepted += 1
            # 回到集会所后可能又冒出「可领取」，顺手再收一次
            self.collect_rewards()

        return accepted, True

    def accept_one_mission(self):
        """尝试接取一个任务，返回 NO_MORE / FAILED / ACCEPTED。

        判定"没有成功接取"的依据：点了「接取」以及后面那个固定坐标之后，
        界面本该切到选小队 / 确认页（那里有「出发」按钮）。如果等不到
        ``mission_go``，就说明这次接取没成功 —— 多半是被弹窗挡住了，
        所以调用方要先点 popu_cancel 退回主页面再重跑。
        """
        # 检测有没有"接取"
        before = self.screen_thumb()
        if not self.click_ocr_text("接取", time_out=1.0):
            return NO_MORE

        self._last_round_had_attempt = True
        self.sleep(1.2)  # 等待界面切换

        # 点了「接取」但画面没变化 -> 再点一次（用户建议）
        if not self.screen_changed(before, self.screen_thumb()):
            self.log_warning("点了「接取」但画面没变化，再点一次")
            self.click_ocr_text("接取", time_out=1.0)
            self.sleep(1.2)

        # 点击固定位置 rel(0.686, 0.210)
        self.click_relative(0.686, 0.210)
        self.sleep(1.2)

        # OCR 找"推荐小队"，有就点
        if self.click_ocr_text("推荐小队", time_out=1.0):
            self.sleep(0.8)

        # 点击"出发"
        if not self.wait_click('mission_go', threshold=0.8, time_out=4):
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