from ok import BaseTask
from src.tasks.page_nav import PageNavTask


class FriendTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "好友体力赠送与收取"
        self.description = "自动赠送好友体力和收取体力"  # 可选

    def run(self):
        self.log_info("开始好友赠礼...")

        # ========== 第一阶段：游戏好友 ==========
        if not self.wait_click('main_friend', threshold=0.8, time_out=5):
            self.log_error("未找到好友入口，任务终止")
            return
        self.sleep(1.2)

        if not self.wait_click('friend_gamefriend', threshold=0.8, time_out=5):
            self.log_error("未找到游戏好友，任务终止")
            return
        self.sleep(1.2)

        if not self.wait_click('friend_send', threshold=0.8, time_out=5):
            self.log_error("未找到赠送按钮，任务终止")
            return
        self.sleep(1.0)  # 等 1 秒

        if self.wait_click('friend_receive', threshold=0.8, time_out=5):
            self.log_info("游戏好友：已点击领取")
        else:
            self.log_warning("游戏好友：未找到领取按钮")

        self.sleep(1.0)
        if self.click_ocr_text("确认", time_out=2.0):
            self.log_info("游戏好友：已点击确认")
        else:
            self.log_info("游戏好友：未检测到确认")

        # ========== 第二阶段：QQ 好友 ==========
        self.sleep(1.0)

        if not self.wait_click('friend_qqfriend', threshold=0.8, time_out=5):
            self.log_error("未找到 QQ 好友标签")
            self._exit()
            return
        self.sleep(1.0)

        if not self.wait_click('friend_send', threshold=0.8, time_out=5):
            self.log_error("未找到赠送按钮")
            self._exit()
            return
        self.sleep(1.0)  # 等 1 秒

        if self.wait_click('friend_receive', threshold=0.8, time_out=5):
            self.log_info("QQ好友：已点击领取")
        else:
            self.log_warning("QQ好友：未找到领取按钮")

        self.sleep(1.0)
        if self.click_ocr_text("确认", time_out=2.0):
            self.log_info("QQ好友：已点击确认")
        else:
            self.log_info("QQ好友：未检测到确认")

        # ========== 第三阶段：退出 ==========
        self.sleep(1.0)
        if self.wait_click('friend_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 friend_cancel 返回主页面")
        else:
            self.log_warning("未找到 friend_cancel 按钮")

        self.log_info("好友赠礼任务结束")

    # ================= 通用工具 =================

    def click_ocr_text(self, keyword, time_out=0.5):
        """OCR 查找包含关键词的文字并点击"""
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    def _exit(self):
        """失败时尝试点击 friend_cancel 退出"""
        if self.wait_click('friend_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 friend_cancel 退出")

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