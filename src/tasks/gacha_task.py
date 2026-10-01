from ok import BaseTask
import time


class GachaTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "招募"
        self.description = "自动免费招募（高级 + 普通）"

    def run(self):
        self.log_info("开始招募...")

        try:
            # 1. 点击主界面招募入口
            box = self.swipe_find('main_gacha', max_swipes=4, click=True)
            if not box:
                self.log_error("未找到招募入口，任务终止")
                return
            self.sleep(1.5)

            # 2. 高级招募（如果有免费次数）
            self.do_free_gacha('gacha_freegaozhao')

            # 3. 左侧往上滑，找"普通招募"
            self.click_normal_gacha()

            # 4. 普通招募免费
            self.do_free_gacha('gacha_freenormal')

        except Exception as e:
            self.log_error(f"执行出错: {e}")
        finally:
            # 5. 退出到主页面
            self.sleep(0.5)
            if self.safe_click_feature('gacha_cancel', threshold=0.8, time_out=3):
                self.log_info("已点击 gacha_cancel 退出")
            else:
                self.log_warning("未找到 gacha_cancel")

        self.log_info("招募任务结束")

    # ================= 免费招募通用逻辑 =================

    def do_free_gacha(self, free_feature):
        """
        检测 free_feature 是否存在：
        - 有 → 点击它，再点"确定"
        - 无 → 跳过
        """
        if self.find_one(free_feature, threshold=0.8):
            self.log_info(f"检测到 {free_feature}，点击它")
            if not self.safe_click_feature(free_feature, threshold=0.8, time_out=3):
                self.log_warning(f"点击 {free_feature} 失败")
                return
            self.sleep(1.5)

            # 点"确定"
            if self.click_ocr_text("确定", time_out=3):
                self.log_info("已点击'确定'")
                self.sleep(1.5)
            else:
                self.log_warning("未找到'确定'按钮")
        else:
            self.log_info(f"未检测到 {free_feature}，跳过")

    # ================= 普通招募查找 =================

    def click_normal_gacha(self):
        """
        在屏幕最左侧往上滑，让下方内容出现，找到"普通招募"点击。
        """
        self.log_info("[普通招募] 开始查找")
        self.sleep(1.0)

        for i in range(6):
            # 先 OCR 检测当前画面有没有"普通招募"
            if self.detect_ocr_text("普通招募"):
                self.log_info(f"[普通招募] 第 {i+1} 轮检测到'普通招募'")
                if self.click_ocr_text("普通招募", time_out=2):
                    self.log_info("已点击'普通招募'")
                    self.sleep(1.5)
                    return True
                else:
                    self.log_warning("点击'普通招募'失败")

            # 没找到就滑动：左侧 1/50 处往上滑（列表下方内容出现）
            self.log_info(f"[普通招募] 第 {i+1} 轮滑动查找")
            self.swipe_relative(0.02, 0.75, 0.02, 0.25, duration=0.4)
            self.sleep(1.0)

        self.log_warning("[普通招募] 滑动 6 次仍未找到'普通招募'")
        return False

    # ================= OCR 工具 =================

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