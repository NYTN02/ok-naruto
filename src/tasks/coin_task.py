from ok import BaseTask


class CoinTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "领取铜币"
        self.description = "自动领取铜币奖励"  # 可选

    def run(self):
        self.log_info("开始领取铜币...")

        # 1. 滑动找到铜币图标（不点击）
        coin_icon = self.swipe_find('main_coin_icon', max_swipes=4, click=False)
        if not coin_icon:
            self.log_error("未找到铜币图标，任务终止")
            return

        # 2. 用屏幕宽度比例计算右移量（184 / 1920 ≈ 0.096）
        offset_x = int(self.width * 0.096)
        click_x = coin_icon.x + coin_icon.width + offset_x
        click_y = coin_icon.y + coin_icon.height // 2

        self.click(click_x, click_y)
        self.log_info(f"点击铜币加号: ({click_x}, {click_y})")
        self.sleep(1.2)

        # 3. 循环点"免费一次"，最后一定要点退出
        try:
            for i in range(5):
                free_btn = self.find_one('coin_freetoget', threshold=0.8)
                if not free_btn:
                    self.log_info("免费一次按钮已消失")
                    break
                self.click_box(free_btn)
                self.log_info(f"第 {i+1} 次点击免费一次")
                self.sleep(1.2)
            else:
                self.log_warning("达到最大次数，按钮仍未消失")
        finally:
            self.sleep(0.5)
            if self.wait_click_feature('coin_cancel', threshold=0.8, time_out=3):
                self.log_info("已点击退出")
            else:
                self.log_warning("未找到退出按钮")

        self.log_info("铜币领取任务结束")

    # ---------------- 通用工具方法（与 MissionTask 相同） ----------------

    def swipe_find(self, feature, max_swipes=4, click=False):
        box = self.find_one(feature, threshold=0.8)
        if box:
            if click:
                self.click_box(box)
            return box

        for _ in range(max_swipes):
            self.swipe_relative(0.85, 0.5, 0.15, 0.5, duration=0.3)
            self.sleep(0.5)
            box = self.find_one(feature, threshold=0.8)
            if box:
                if click:
                    self.click_box(box)
                return box

        for _ in range(max_swipes * 2):
            self.swipe_relative(0.15, 0.5, 0.85, 0.5, duration=0.3)
            self.sleep(0.5)
            box = self.find_one(feature, threshold=0.8)
            if box:
                if click:
                    self.click_box(box)
                return box

        return None

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)