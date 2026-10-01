from ok import BaseTask


class MissionTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "任务集会所"
        self.description = "自动领取奖励和接取任务"  # 可选

    def run(self):
        self.log_info("开始任务集会所...")

        # 1. 滑动查找任务集会所入口并点击
        box = self.swipe_find('main_mission', max_swipes=4, click=True)
        if not box:
            self.log_error("未找到任务集会所入口，任务终止")
            return
        self.sleep(1.2)  # 等待界面加载

        # 2. 先领所有"可领取"
        self.collect_all_rewards()

        # 3. 循环接取任务
        loop_count = 0
        max_loop = 15
        while loop_count < max_loop:
            loop_count += 1
            self.log_info(f"--- 第 {loop_count} 轮接取 ---")

            # 检测有没有"接取"
            if not self.click_ocr_text("接取", time_out=1.0):
                self.log_info("没有更多'接取'，结束循环")
                break
            self.sleep(1.2)  # 等待界面切换

            # 点击固定位置 rel(0.686, 0.210)
            self.click_relative(0.686, 0.210)
            self.sleep(1.2)

            # OCR 找"推荐小队"，有就点
            if self.click_ocr_text("推荐小队", time_out=1.0):
                self.sleep(0.8)

            # 点击"出发"
            if not self.wait_click_feature('mission_go', threshold=0.8, time_out=4):
                self.log_error("未找到'出发'按钮，跳出循环")
                break
            self.sleep(1.8)  # 等待出发与返回

            # 回到集会所后，可能又出现新的"可领取"
            self.collect_all_rewards()

        # 4. 退出任务集会所
        self.sleep(0.5)
        if self.wait_click_feature('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已退出任务集会所")
        else:
            self.log_warning("未找到退出按钮")

        self.log_info("任务集会所任务结束")

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