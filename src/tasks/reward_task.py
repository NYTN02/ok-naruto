from ok import BaseTask
import time


class RewardTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "每日活跃奖励"
        self.description = "自动领取每日活跃度奖励"

    def run(self):
        self.log_info("开始领取每日活跃奖励...")

        try:
            # 1. 点击主界面奖励入口
            box = self.swipe_find('main_reward', max_swipes=4, click=True)
            if not box:
                self.log_error("未找到奖励入口，任务终止")
                return
            self.sleep(1.5)

            # 2. OCR 识别并点击"每日任务"
            if not self.click_ocr_text("每日任务", time_out=5.0):
                self.log_error("未找到'每日任务'，任务终止")
                return
            self.sleep(1.5)

            # 3. 依次点击四个活跃度宝箱（点击标记上方 0.087 屏幕高度）
            for name in ['reward_10', 'reward_40', 'reward_80', 'reward_100']:
                if self.click_above_feature(name, offset_rel=0.087):
                    self.log_info(f"已点击 {name} 上方")
                else:
                    self.log_info(f"未找到 {name}（可能已领取），跳过")
                self.sleep(1.0)

        except Exception as e:
            self.log_error(f"执行出错: {e}")
        finally:
            # 4. 退出到主页面
            self.sleep(0.5)
            if self.safe_click_feature('reward_cancel', threshold=0.8, time_out=3):
                self.log_info("已点击 reward_cancel 退出")
            else:
                self.log_warning("未找到 reward_cancel")

        self.log_info("每日活跃奖励任务结束")

    # ================= 点击标记上方 =================

    def click_above_feature(self, feature, offset_rel=0.087, threshold=0.8, time_out=3):
        """
        找到 feature 后，点击它上方 offset_rel * screen_height 的位置。
        """
        start = time.time()
        while time.time() - start < time_out:
            box = self.find_one(feature, threshold=threshold)
            if box:
                box_center_y_rel = (box.y + box.height // 2) / self.height
                target_y_rel = box_center_y_rel - offset_rel
                click_x = box.x + box.width // 2
                click_y = int(self.height * target_y_rel)
                self.log_info(
                    f"找到 {feature} @ rel_y={box_center_y_rel:.3f}，"
                    f"点击上方 rel_y={target_y_rel:.3f} -> ({click_x}, {click_y})"
                )
                self.click(click_x, click_y)
                return True
            self.sleep(0.3)
        return False

    # ================= OCR 工具 =================

    def click_ocr_text(self, keyword, time_out=2.0):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
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