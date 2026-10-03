from src.tasks.guide_nav import GuideNavTask

# 进入方式：走「指南」列表（原来是在主页面找 main_ranklist，
# 每个玩家主页背景不同，经常匹配不到）
GUIDE_ITEM = 'guide_ranklist'
GUIDE_TEXT = '排行榜'   # 指南列表里条目的文字（OCR 识别）
GUIDE_GO = 'guide_ranklistgo'


class RankListTask(GuideNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "排行榜点赞"
        self.description = "自动点赞排行榜（第一个）"  # 可选

    def run(self):
        self.log_info("开始排行榜点赞...")

        # 1. 走「指南」进入排行榜
        if not self.enter_guide(GUIDE_TEXT, GUIDE_GO, item_feature=GUIDE_ITEM):
            self.log_error("没能通过指南进入排行榜，任务终止")
            return
        self.sleep(1.5)

        # 2. 尝试点击点赞按钮
        if self.wait_click('ranklist_firstgood', threshold=0.8, time_out=5):
            self.log_info("已点击点赞")
            self.sleep(1.0)
        else:
            self.log_info("未找到点赞按钮，直接退出")

        # 3. 点击 popu_cancel 退出
        if self.wait_click('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击退出")
        else:
            self.log_warning("未找到退出按钮")

        self.log_info("排行榜点赞任务结束")

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