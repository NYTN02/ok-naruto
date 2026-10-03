from src.tasks.guide_nav import GuideNavTask
import re
import time

# 进入方式：走「指南」列表
GUIDE_ITEM = 'guide_teamfight'
GUIDE_TEXT = '小队突袭'   # 指南列表里条目的文字（OCR 识别）
GUIDE_GO = 'guide_teamfightgo'

# 战斗结算：检测到 teamfight_win 就不断点击它推进结算，直到它消失
TEAMFIGHT_WIN = 'teamfight_win'
TEAMFIGHT_WIN_INTERVAL = 1.0    # 两次点击之间的间隔

# 最多打几场（用户流程里是两场：打完一场后如果次数还有余、且还能看到队伍助力，
# 就再点一次 teamfight_teamhelp 再来一场）
MAX_ROUNDS = 2

# 「邀请」列表上滑时的 x 坐标（相对屏幕宽度）。
# 取很小的值贴着屏幕左边缘滑：这里不会压到邀请卡片本身，
# 拖动更稳（换成 0.20 之类的中间位置容易误触卡片或拖不动列表）。
INVITE_SWIPE_X = 0.025
INVITE_SWIPE_FROM_Y = 0.75
INVITE_SWIPE_TO_Y = 0.25
INVITE_SWIPE_DURATION = 0.4
INVITE_MAX_SWIPES = 5


class TeamFightTask(GuideNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "小队突袭"
        self.description = "自动进行小队突袭并领取贡献"  # 可选

    def run(self):
        """小队突袭：打一场 -> 看还能不能再打 -> 能就再来一场，最多 MAX_ROUNDS 场。

        用户指定的流程：

            原步骤 1~6（进指南 / 查次数 / 队伍助力 / 领奖 / 邀请 / 出发）
            第 7 步：等战斗结束，检测到 teamfight_win 就不断点击直到它消失
            然后检查有没有 teamfight_teamhelp：
                没有 -> 尝试退出到主页面（打不了了）
                有   -> OCR 查「今日可收益次数」
                        0/x  -> 点 popu_cancel 退出，任务结束
                        不是 -> 点 teamfight_teamhelp，再做原步骤 5、6（邀请/出发）
                                -> 再等一场打完、点 teamfight_win
                                -> 再判断一次（同上）

        注意打完一场会回到**小队突袭界面**（teamfight_teamhelp 就在那里），
        不是主界面 —— 所以判据用 teamfight_teamhelp，不能再等 main_teamfight。
        """
        self.log_info("开始小队突袭...")

        # ========== 原步骤 1~4（只在最开始做一次）==========
        # 1. 走「指南」进入小队突袭
        if not self.enter_guide(GUIDE_TEXT, GUIDE_GO, item_feature=GUIDE_ITEM):
            self.log_error("没能通过指南进入小队突袭，任务终止")
            return
        self.sleep(1.5)

        # 2. 检测"今日可收益次数：0/2"
        if self.detect_no_teamfight_chance():
            self.log_info("今日可收益次数为 0，退出")
            self.exit_with_popu_cancel()
            self.log_info("小队突袭任务结束（次数为 0）")
            return

        # 3. 点击队伍助力
        if not self.safe_click_feature('teamfight_teamhelp', threshold=0.8, time_out=5):
            self.log_error("未找到队伍助力按钮")
            self.cleanup_exit()
            return
        self.sleep(1.2)

        # 4. 点我的助力 + 领取奖励
        self.claim_rewards()

        # ========== 原步骤 5~6：邀请 + 出发，开打 ==========
        if not self.prepare_and_start_battle():
            self.cleanup_exit()
            return

        # ========== 第 7 步起：打完 -> 判断能不能再来一场 ==========
        for round_idx in range(MAX_ROUNDS):
            self.log_info(f"===== 第 {round_idx + 1}/{MAX_ROUNDS} 场战斗 =====")

            # 7. 等战斗结束：点 teamfight_win 直到消失
            if not self.settle_teamfight_win():
                self.log_warning("没能正常走完结算，尝试退出到主页面")
                self.cleanup_exit()
                return

            # 打完回到小队突袭界面：看还能不能继续
            if self._safe_find_one('teamfight_teamhelp') is None:
                self.log_warning("没有 teamfight_teamhelp，无法继续，退出到主页面")
                self.cleanup_exit()
                return

            # 有队伍助力，说明还在小队突袭界面 —— 查次数
            if self.detect_no_teamfight_chance():
                self.log_info("今日可收益次数为 0，点 popu_cancel 退出")
                self.exit_with_popu_cancel()
                self.log_info("小队突袭任务结束")
                return

            # 次数还没用完，但已经打满 MAX_ROUNDS 场就收工
            if round_idx >= MAX_ROUNDS - 1:
                self.log_info(f"已打满 {MAX_ROUNDS} 场，任务结束")
                self.cleanup_exit()
                return

            # 还能再来一场：点队伍助力，再做步骤 5~6
            self.log_info("次数还有余，点 teamfight_teamhelp 再来一场")
            if not self.safe_click_feature('teamfight_teamhelp', threshold=0.8, time_out=5):
                self.log_error("未找到队伍助力按钮")
                self.cleanup_exit()
                return
            self.sleep(1.2)

            if not self.prepare_and_start_battle():
                self.cleanup_exit()
                return

    # ================= 流程步骤 =================

    def claim_rewards(self):
        """原步骤 4：点我的助力 + 领取奖励 + 关掉奖励弹窗。"""
        if not self.safe_click_feature('teamfight_mywork', threshold=0.8, time_out=5):
            self.log_warning("未找到我的助力按钮，继续")
        self.sleep(1.2)

        if self.safe_click_feature('teamfight_getreward', threshold=0.8, time_out=3):
            self.log_info("已点击领取奖励")
            self.sleep(1.0)
        else:
            self.log_info("没有奖励可领，跳过")

        if self.safe_click_feature('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 popu_cancel")
            self.sleep(1.5)

    def prepare_and_start_battle(self):
        """原步骤 5~6：OCR 找「邀请」点最上面那个，再点「出发」。"""
        if not self.click_top_invite():
            self.log_error("未找到'邀请'，任务终止")
            return False
        self.sleep(1.2)

        if not self.safe_click_feature('teamfight_go', threshold=0.8, time_out=5):
            self.log_error("未找到出发按钮")
            return False
        self.log_info("已点击出发，进入战斗")
        return True

    def exit_with_popu_cancel(self):
        """点 popu_cancel 退出小队突袭界面。"""
        if self.wait_click('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 popu_cancel 退出")
        else:
            self.log_warning("未找到 popu_cancel")

    # ================= 检测次数用尽 =================

    def detect_no_teamfight_chance(self):
        """OCR 检测'今日可收益次数'是否为 0/x。返回 True 表示次数为 0"""
        result = self.ocr()
        if not result:
            return False

        for r in result:
            text = self._box_text(r)
            if '可收益次数' in text or '收益次数' in text:
                self.log_info(f"[次数检测] OCR: '{text}'")
                m = re.search(r'(\d+)\s*/\s*(\d+)', text)
                if m and int(m.group(1)) == 0:
                    return True
                if self._is_box_like(r):
                    for r2 in result:
                        if not self._is_box_like(r2):
                            continue
                        if abs(r2.y - r.y) < 30 and r2.x > r.x:
                            t2 = self._box_text(r2)
                            m = re.search(r'(\d+)\s*/\s*(\d+)', t2)
                            if m and int(m.group(1)) == 0:
                                self.log_info(f"[次数检测] 相邻OCR: '{t2}'")
                                return True
                            if m:
                                break
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

    # ================= "邀请"处理 =================

    def click_top_invite(self):
        if self.click_top_invite_ocr():
            return True

        for i in range(INVITE_MAX_SWIPES):
            self.log_info(f"[邀请查找] 第 {i+1} 次滑动查找 "
                          f"(x={INVITE_SWIPE_X} {INVITE_SWIPE_FROM_Y}->{INVITE_SWIPE_TO_Y})")
            self.swipe_relative(INVITE_SWIPE_X, INVITE_SWIPE_FROM_Y,
                                INVITE_SWIPE_X, INVITE_SWIPE_TO_Y,
                                duration=INVITE_SWIPE_DURATION)
            self.sleep(1.0)
            if self.click_top_invite_ocr():
                return True

        self.log_warning(f"滑动 {INVITE_MAX_SWIPES} 次后仍未找到'邀请'")
        return False

    def click_top_invite_ocr(self):
        boxes = self.wait_ocr(match=["邀请"], time_out=1.0)
        if not boxes:
            return False
        if not isinstance(boxes, list):
            boxes = [boxes]

        boxes = [b for b in boxes if self._is_box_like(b)]
        if not boxes:
            return False

        topmost = min(boxes, key=lambda b: b.y)
        self.log_info(f"点击最上面的'邀请': ({topmost.x}, {topmost.y})")
        self.click_box(topmost)
        return True

    # ================= 等待回主界面 =================

    def settle_teamfight_win(self, wait_timeout=180, max_clicks=30):
        """第 7 步：等这一场打完，并点掉胜利结算。

        分两段：
          A. 等 ``teamfight_win`` **出现**（它就是"这局打完了"的信号）
          B. 检测到之后**不断点击它**，直到它消失

        打完会回到**小队突袭界面**（不是主界面），所以这里不等 main_teamfight ——
        由调用方用 teamfight_teamhelp 判断接下来怎么做。
        """
        # A. 等结算出现
        start = time.time()
        while time.time() - start < wait_timeout:
            if self.should_stop('小队突袭等待结算'):
                return False
            if self._safe_find_one(TEAMFIGHT_WIN) is not None:
                self.log_info(f"检测到 {TEAMFIGHT_WIN}（用时 {int(time.time() - start)} 秒），"
                              f"开始点结算")
                break
            self.sleep(2.0)
        else:
            self.log_warning(f"{wait_timeout} 秒内没等到 {TEAMFIGHT_WIN}，本局判定异常")
            return False

        # B. 不断点，直到它消失
        clicks = 0
        for _ in range(max_clicks):
            if self.should_stop('小队突袭结算'):
                return False
            box = self._safe_find_one(TEAMFIGHT_WIN)
            if box is None:
                self.log_info(f"{TEAMFIGHT_WIN} 已消失（共点了 {clicks} 次），结算完成")
                return True
            clicks += 1
            self.click_box(box)
            self.log_info(f"第 {clicks} 次点击 {TEAMFIGHT_WIN} ({box.x}, {box.y})，推进结算")
            self.sleep(TEAMFIGHT_WIN_INTERVAL)

        self.log_warning(f"点了 {max_clicks} 次 {TEAMFIGHT_WIN} 仍未消失")
        return False

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

    def _box_text(self, box):
        if isinstance(box, str):
            return box
        for attr in ('name', 'text', 'content'):
            v = getattr(box, attr, None)
            if v:
                return str(v)
        return str(box)

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

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)