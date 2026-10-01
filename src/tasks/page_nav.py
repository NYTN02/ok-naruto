"""页面导航：从任意子页面 / 弹窗一路退回到游戏主页面。

判据很简单：
    能模板匹配到 ``main_adventure``（主界面右下角那个"冒险"入口）就认为在主页，
    否则认为不在主页。不在主页时，在当前画面里找各种"关闭/取消"按钮，
    找到一个就点掉，然后重新判断，如此循环直到回到主页或超时。

这样写的好处是不需要知道"现在这一层是什么面板"——不管是奖励弹窗、抽卡弹窗、
扫荡弹窗、活动弹窗，只要它有 X 就能退出去。
"""

from ok import BaseTask

# 主页面的标志性元素
MAIN_PAGE_FEATURE = 'main_adventure'

# 关闭 / 取消类按钮，按优先级排列。同屏出现多个时先试前面的。
# 这些都是 assets/coco_annotations.json 里已标注的特征名。
CANCEL_FEATURES = [
    'popu_cancel',      # 通用弹窗右上角 X
    'reward_cancel',    # 奖励界面关闭
    'gacha_cancel',     # 抽卡/招募关闭
    'clean_cancel',     # 扫荡关闭
    'activity_cancel',  # 活动界面关闭
    'team_cancel',      # 组织界面关闭
    'friend_cancel',    # 好友界面关闭
    'coin_cancel',      # 铜币界面关闭
]


class PageNavTask(BaseTask):
    """提供「判断是否在主页」和「退回主页」能力，供各任务继承。"""

    MAIN_PAGE_FEATURE = MAIN_PAGE_FEATURE
    CANCEL_FEATURES = CANCEL_FEATURES
    DEFAULT_THRESHOLD = 0.8

    # ------------------------------------------------------------------
    # 判断
    # ------------------------------------------------------------------
    def is_main_page(self, threshold=None):
        """当前是否在游戏主页面。"""
        box = self._safe_find_one(self.MAIN_PAGE_FEATURE, threshold)
        return box is not None

    def find_cancel_button(self, threshold=None, features=None):
        """在当前画面找任意一个关闭/取消按钮。

        返回 ``(名称, Box)``；一个都没找到就返回 ``(None, None)``。
        """
        thr = self._threshold(threshold)
        for name in (features if features is not None else self.CANCEL_FEATURES):
            if not self._feature_exists(name):
                continue
            box = self._safe_find_one(name, thr)
            if box is not None:
                return name, box
        return None, None

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def click_cancel_if_any(self, threshold=None, features=None, after_sleep=0.8):
        """找到任意一个关闭按钮就点掉，返回点到的按钮名；没有可点的返回 None。"""
        name, box = self.find_cancel_button(threshold, features)
        if name is None:
            return None
        self.log_info(f"点击关闭按钮 {name} "
                      f"({box.x + box.width // 2}, {box.y + box.height // 2})")
        self.click_box(box)
        if after_sleep > 0:
            self.sleep(after_sleep)
        return name

    def back_to_main(self, max_rounds=40, interval=1.0, threshold=None,
                     features=None, log=True):
        """从任意子页面 / 弹窗一路退回到主页面。

        :param max_rounds: 最多尝试多少轮，防止在互相弹出的面板之间死循环
        :param interval: 每轮之间的等待（点完关闭按钮后给界面留出动画时间）
        :param threshold: 模板匹配阈值，默认 0.8
        :param features: 自定义关闭按钮列表，默认用 CANCEL_FEATURES
        :return: True 表示已经回到主页面

        每一轮：先看是不是已经在主页（是就直接返回）；不是就在当前画面找
        关闭按钮，点到就点，点不到就只等待（不乱点别的地方，免得又点进新面板）。
        """
        thr = self._threshold(threshold)
        if log:
            self.log_info("开始退回主页面...")

        for i in range(max_rounds):
            if self.is_main_page(thr):
                if log:
                    self.log_info("已回到主页面（main_adventure）")
                return True

            name = self.click_cancel_if_any(thr, features, after_sleep=0)
            if name is None and log:
                self.log_debug(f"第 {i + 1} 轮没有找到可点的关闭按钮，等待中...")
            self.sleep(interval)

        if self.is_main_page(thr):
            if log:
                self.log_info("已回到主页面（main_adventure）")
            return True

        if log:
            self.log_warning(f"{max_rounds} 轮后仍未回到主页面（main_adventure）")
        return False

    # ------------------------------------------------------------------
    # 内部小工具
    # ------------------------------------------------------------------
    def _threshold(self, threshold):
        return self.DEFAULT_THRESHOLD if threshold is None else threshold

    def _feature_exists(self, name):
        """模板不存在时直接跳过，避免 find_one 抛 ValueError。"""
        try:
            return self.feature_exists(name)
        except Exception:
            return False

    def _safe_find_one(self, name, threshold=None):
        """找不到、模板不存在、或识别过程报错，都返回 None。"""
        if not self._feature_exists(name):
            return None
        try:
            return self.find_one(name, threshold=self._threshold(threshold))
        except Exception as e:
            self.log_debug(f"查找 {name} 失败: {e}")
            return None
