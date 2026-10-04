from ok import BaseTask
from src.tasks.page_nav import ADVENTURE_ENTRY_REL, MAIN_PAGE_FEATURE
import re
import time


class JingYingTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "精英副本"
        self.description = "自动扫荡精英副本"

    def run(self):
        self.log_info("开始精英副本...")

        try:
            # 1. 点击主界面冒险入口 —— 固定坐标 rel(0.909, 0.869)
            #    原来是用模板匹配 main_adventure 再滑动查找，位置本来就固定，
            #    没必要匹配；而且每个人主页背景不同，模板匹配常失败。
            self.click_relative(*ADVENTURE_ENTRY_REL)
            self.sleep(1.5)

            # 2. 点击精英副本
            if not self.safe_click_feature('adventure_jingying', threshold=0.8, time_out=5):
                self.log_error("未找到精英副本按钮")
                return
            self.sleep(1.2)

            # 3. 点击快速扫荡
            if not self.safe_click_feature('jingying_quick', threshold=0.8, time_out=5):
                self.log_error("未找到快速扫荡按钮")
                return
            self.sleep(1.0)

            # 4. 点击扫荡
            if not self.safe_click_feature('jingying_clean', threshold=0.8, time_out=5):
                self.log_error("未找到扫荡按钮")
                return
            self.log_info("已点击扫荡")
            self.sleep(2.0)  # 等弹窗出现

            # 5. 检测 clean_buynoodle（优先，因为是错误情况）
            if self.find_one('clean_buynoodle', threshold=0.8):
                self.log_info("检测到 clean_buynoodle，点击 clean_cancel")
                self.safe_click_feature('clean_cancel', threshold=0.8, time_out=3)
                self.exit_to_main()
                self.log_info("精英副本任务结束")
                return

            # 6. 检测 jingying_goahead（二次确认）
            if self.find_one('jingying_goahead', threshold=0.8):
                self.log_info("检测到 jingying_goahead，点击它")
                self.safe_click_feature('jingying_goahead', threshold=0.8, time_out=3)
                self.sleep(1.5)
            else:
                self.log_info("未出现 jingying_goahead 和 clean_buynoodle")

            # 7. 处理扫荡结果（"扫荡结束" → 点"确定"）
            self.handle_scan_result()

        except Exception as e:
            self.log_error(f"执行出错: {e}")
        finally:
            # 8. 退出到主页面
            self.exit_to_main()

        self.log_info("精英副本任务结束")

    # ================= 退出到主页面 =================

    def exit_to_main(self, max_rounds=8):
        """
        反复尝试退出到主页面。
        退出成功标志：
          1. 回到主页面（见到 MAIN_PAGE_FEATURE）
          2. 找不到 popu_cancel
        """
        self.log_info("[退出] 开始尝试退出到主页面")
        for i in range(max_rounds):
            # 检查是否已回到主页面
            if self.find_one(MAIN_PAGE_FEATURE, threshold=0.8):
                self.log_info(f"[退出] 第 {i+1} 轮：检测到主页面标志，已回到主页面")
                return True

            # 尝试点 popu_cancel
            if self.safe_click_feature('popu_cancel', threshold=0.8, time_out=1):
                self.log_info(f"[退出] 第 {i+1} 轮：点击 popu_cancel")
                self.sleep(1.0)
                continue

            # 没有 popu_cancel 也没有主页面标志，再等一次确认
            self.sleep(1.0)
            if self.find_one(MAIN_PAGE_FEATURE, threshold=0.8):
                self.log_info(f"[退出] 第 {i+1} 轮：检测到主页面标志，已回到主页面")
                return True
            if not self.find_one('popu_cancel', threshold=0.8):
                self.log_info(f"[退出] 第 {i+1} 轮：没有 popu_cancel，退出结束")
                return True

        self.log_warning(f"[退出] 达到最大轮数 {max_rounds}，未确认回到主页面")
        return False

    # ================= 处理扫荡结果 =================

    def handle_scan_result(self):
        """
        16 秒内轮询检测"扫荡结束"，检测到就点"确定"
        """
        for attempt in range(8):  # 8 次 × 2 秒 = 16 秒
            self.sleep(2.0)

            if self.detect_ocr_text("扫荡结束"):
                self.log_info("检测到'扫荡结束'")
                if self.click_ocr_text("确定", time_out=3):
                    self.log_info("已点击'确定'")
                    self.sleep(1.0)
                else:
                    self.log_warning("未找到'确定'按钮")
                return True

        self.log_info("16 秒内未检测到'扫荡结束'")
        return False

    def detect_ocr_text(self, keyword):
        """OCR 检测屏幕上是否有某关键词，不点击"""
        boxes = self.wait_ocr(match=[keyword], time_out=1.0)
        return bool(boxes)

    def click_ocr_text(self, keyword, time_out=2.0):
        """OCR 查找包含关键词的文字并点击"""
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    # ================= 安全点击 =================

    def safe_click_feature(self, feature, threshold=0.8, time_out=5):
        """找到就点击返回 True；超时返回 False（不抛异常）"""
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