"""回到主页面（一键退出当前所有面板 / 弹窗）。

用途：不管现在停在哪个子页面，运行这个任务都会一路点关闭按钮退回到主页面。

判定逻辑（见 src/tasks/page_nav.py）：
    * 能匹配到 main_adventure -> 已经在主页，什么都不做
    * 否则 -> 在当前画面依次找
      popu_cancel / reward_cancel / gacha_cancel / clean_cancel /
      activity_cancel / team_cancel / friend_cancel / coin_cancel，
      找到哪个就点哪个，然后重新判断，直到回到主页或超过重试次数。
"""

from src.tasks.page_nav import CANCEL_FEATURES, PageNavTask


class BackToMainTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "回到主页面"
        self.description = "自动点掉当前所有弹窗 / 面板，退回到游戏主页面"

    def run(self):
        self.log_info("检查当前是否在主页面...")

        if self.is_main_page():
            self.log_info("已经在主页面，无需操作")
            return

        self.log_info(f"不在主页面，将依次尝试关闭按钮: {', '.join(CANCEL_FEATURES)}")
        if self.back_to_main(max_rounds=40, interval=1.0):
            self.log_info("已回到主页面")
        else:
            self.log_warning("未能回到主页面，请检查是否卡在无法用这些按钮关闭的界面")
