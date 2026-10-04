"""页面导航：从任意子页面 / 弹窗一路退回到游戏主页面。

判据很简单：
    能模板匹配到 ``main_guide``（主页面上的"指南"入口）就认为在主页，
    否则认为不在主页。不在主页时，在当前画面里找各种"关闭/取消"按钮，
    找到一个就点掉，然后重新判断，如此循环直到回到主页或超时。

这样写的好处是不需要知道"现在这一层是什么面板"——不管是奖励弹窗、抽卡弹窗、
扫荡弹窗、活动弹窗，只要它有 X 就能退出去。
"""

from ok import BaseTask

import re
import time

# 主页面的标志性元素
# 主页面判据：**认「指南」入口 (main_guide)**。
#
# 原来认的是 main_adventure（主界面右下角"冒险"入口），改动原因：
# main_guide 在主页面上的位置/图案更稳定，实测比 main_adventure 可靠。
# 这个常量是全局的 —— is_main_page()、back_to_main() 全都走它，
# 所以改这一处就等于把"什么算在主页面"整体改掉。
MAIN_PAGE_FEATURE = 'main_guide' 


def _task_disabled(task):
    """任务是否已被「停止」置为不可用。

    ok-script 的停止有两个完全不同的入口：

      * 任务卡片上的停止 —— ``TaskCard.stop_clicked()`` 走的是
        ``task.disable() + task.unpause()``，只把该任务的 ``_enabled`` 置为 False，
        **不会**动 ``executor.exit_event``（那是设备/截图页停止按钮才做的）；
      * 设备/截图页上的停止 —— ``executor.stop()`` -> ``exit_event.set()``。

    所以两处都得看，只查 ``exit_is_set()`` 会漏掉任务栏那个按钮。
    """
    for attr in ('enabled', '_enabled'):
        try:
            value = getattr(task, attr)
        except Exception:
            continue
        if isinstance(value, bool) and not value:
            return True
    try:
        config = getattr(task, 'config', None)
        if config is not None and config.get('_enabled') is False:
            return True
    except Exception:
        pass
    return False

# 「点击任意位置关闭」这类提示的识别关键词。
# 游戏里这种提示的文案不完全固定（中间可能夹字、也可能写成"点击任意位置继续"），
# 所以用正则做包含匹配，不写死整句。
CLICK_ANYWHERE_PATTERNS = [
    re.compile(r'任意位置.*关闭'),
    re.compile(r'任意位置.*继续'),
    re.compile(r'点击任意位置'),
]

# 关闭 / 取消类按钮，按优先级排列。同屏出现多个时先试前面的。
# 这些都是 assets/coco_annotations.json 里已标注的特征名。
CANCEL_FEATURES = [
    'popu_cancel',             # 通用弹窗右上角 X
    # 走「指南」入口的任务（任务集会所/排行榜/积分赛/小队突袭/丰饶之间）
    # 中途失败时可能停在指南界面上，必须有办法从那里退出来，
    # 否则 back_to_main 会一直找不到可点的按钮、卡到超时。
    'guide_cancel',
    'reward_cancel',           # 奖励界面关闭（组织祈福走「每日任务」入口也会用到）
    'gacha_cancel',            # 抽卡/招募关闭
    'clean_cancel',            # 扫荡关闭
    'activity_cancel',         # 活动界面关闭
    'activity_qiandaocancel',  # 每月签到面板关闭
    'team_cancel',             # 组织界面关闭
    'friend_cancel',           # 好友界面关闭
    'coin_cancel',             # 铜币界面关闭
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
                    self.log_info(f"已回到主页面（{self.MAIN_PAGE_FEATURE}）")
                return True

            name = self.click_cancel_if_any(thr, features, after_sleep=0)
            if name is None and log:
                self.log_debug(f"第 {i + 1} 轮没有找到可点的关闭按钮，等待中...")
            self.sleep(interval)

        if self.is_main_page(thr):
            if log:
                self.log_info(f"已回到主页面（{self.MAIN_PAGE_FEATURE}）")
            return True

        if log:
            self.log_warning(f"{max_rounds} 轮后仍未回到主页面（{self.MAIN_PAGE_FEATURE}）")
        return False

    # ------------------------------------------------------------------
    # 「点击任意位置关闭」提示
    # ------------------------------------------------------------------
    def find_click_anywhere(self):
        """找「点击任意位置关闭」这类提示，返回它的 Box；没有就返回 None。"""
        try:
            boxes = self.ocr(match=self.CLICK_ANYWHERE_PATTERNS)
        except Exception as e:
            self.log_debug(f"检测「任意位置关闭」失败: {e}")
            return None
        if not boxes:
            return None
        return boxes[0] if isinstance(boxes, list) else boxes

    def dismiss_click_anywhere(self):
        """检测到「点击任意位置关闭」就点掉，然后一路退到主页面。

        这类提示一般出现在战斗结束 / 领奖之后。流程是：
          1. 点一下把提示关掉（提示上写着"任意位置"，点提示文字本身最稳，
             不会误触到别的按钮）；
          2. 之后往往还会弹出带 X 的弹窗（popu_cancel 等），
             用 back_to_main() 逐个点掉，直到回到主页面。

        :return: True 表示确实遇到并处理了这种提示。
                 调用方通常应当据此结束当前这一轮（因为已经被踢回主页面了）。
        """
        box = self.find_click_anywhere()
        if box is None:
            return False

        self.log_info("检测到「点击任意位置关闭」，点掉它")
        try:
            self.click_box(box)
        except Exception as e:
            self.log_warning(f"点击「任意位置关闭」失败，改点屏幕中央: {e}")
            self.click(int(self.width * 0.5), int(self.height * 0.5))
        self.sleep(1.0)

        # 之后可能还有带 X 的弹窗（含 popu_cancel），逐个点掉直到回到主页面
        self.back_to_main(max_rounds=15, interval=0.8)
        return True

    # ------------------------------------------------------------------
    # 停止判断
    # ------------------------------------------------------------------
    def stop_requested(self):
        """用户是否已经要求停止这个任务。

        为什么要自己判断：ok-script 的「停止」有两个完全不同的入口 ——

          * 任务卡片上的停止：``TaskCard.stop_clicked()`` 走
            ``task.disable() + unpause()``，只把该任务的 ``_enabled`` 置成 False，
            **不会**动 ``executor.exit_event``；
          * 设备 / 截图页上的停止：``executor.stop()`` -> ``exit_event.set()``。

        只查 ``exit_is_set()`` 会漏掉任务栏那个按钮 —— 这正是
        「在一键日常那一栏点了停止，任务却还在继续操作」的原因。

        还有一个坑：一键日常是把子任务的 ``run()`` 直接调起来的
        （见 daily_task.run_sub_task），而子任务实例通常**从未被单独启用过**，
        它自己的 ``_enabled`` 一直是 False。如果无脑把「enabled 为 False」
        当成停止信号，子任务会一上来就判定成"已停止"、什么都不做。
        所以只有当我们在本次运行里**见过它是启用的**（``_saw_enabled``）时，
        才把 disable 当作停止信号。
        """
        # 1) executor 级别的停止：设备/截图页的停止按钮、退出程序
        try:
            if self.exit_is_set():
                return True
        except Exception:
            pass

        # 2) 作为子任务运行时，只看父任务（一键日常）
        parent = getattr(self, '_parent_task', None)
        if parent is not None:
            return _task_disabled(parent)

        # 3) 单独运行时看自己的 enabled
        if _task_disabled(self):
            if getattr(self, '_saw_enabled', False):
                return True
        else:
            self._saw_enabled = True
        return False

    def should_stop(self, where=''):
        """循环里用的语法糖：要停就记一条日志并返回 True。

        用法::

            if self.should_stop('战斗循环'):
                return
        """
        if self.stop_requested():
            self.log_warning(f"收到停止指令，中断{('：' + where) if where else ''}")
            return True
        return False

    def wait_feature(self, feature, time_out=5.0, interval=0.5):
        """等一个元素出现；出现返回它的 Box，超时返回 None（不抛异常）。

        用在"这里应该会出现某个东西，但要给游戏一点时间"的地方。
        之前小队突袭就是栽在这：打完结算后**只查了一次** teamfight_teamhelp，
        界面还没切回来就说"没有 teamfight_teamhelp，无法继续"，
        于是只打了一场就退出了。给它几秒钟就够了。
        """
        deadline = time.time() + time_out
        while True:
            box = self._safe_find_one(feature)
            if box is not None:
                return box
            if time.time() >= deadline:
                return None
            if self.should_stop('等待元素'):
                return None
            self.sleep(interval)

    def wait_click(self, feature, threshold=0.8, time_out=5.0, **kwargs):
        """等一个元素出现并点击它；**找不到就返回 False，不抛异常**。

        为什么要有这个包装：ok-script 的 ``wait_click_feature`` 默认
        ``raise_if_not_found=True``，超时会抛 ``WaitFailedException``；
        而我们代码里到处写的是::

            if not self.wait_click('xxx', time_out=5):
                ...按"没找到"处理...

        意思是"找不到当 False"。两边假设不一致，一旦某个元素没出现
        （比如界面改版、入口变了），异常会一路冒到 DailyTask，
        整个任务被记成"执行异常"而中断 —— 组织祈福实测踩过这个坑
        （新版入口已经直接进祈福界面了，却还去等旧的 team_playway）。

        所以统一走这里：``raise_if_not_found=False`` + 兜住异常，
        调用方的 ``if not`` 判断才真的成立。
        """
        kwargs.pop('raise_if_not_found', None)
        try:
            # 注意这里调的是 ok-script 的 wait_click_feature，**不是自己** ——
            # 批量替换调用点时差点把它一起改成 self.wait_click，那就成无限递归了
            return bool(self.wait_click_feature(
                feature, threshold=threshold, time_out=time_out,
                raise_if_not_found=False, **kwargs))
        except Exception as e:
            self.log_warning(f"等待并点击 {feature} 失败（按未找到处理）: {e}")
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
