from src.tasks.page_nav import PageNavTask
import time

# 等 personal_share 出现的超时（秒）。
# 分享界面弹出后要加载一会儿，有时还要等推送动画，5 秒偏紧所以放宽到 15 秒。
PERSONAL_SHARE_TIMEOUT = 15

# 每一轮尝试里最多点几次"分享入口"。
# 点一次就弹出来的情况常见，但实测偶尔要再点才响应，所以给 3 次机会。
SHARE_ENTRY_CLICKS = 3
# 每次点完分享入口等多久再检测 share_qq（用户指定 1 秒）
SHARE_ENTRY_WAIT = 1.0

# 一轮里 3 次点击都没出现 share_qq 时，回主页面重新来过的次数。
SHARE_RETRY = 2

# 点中 share_qq 之后等 QQ 起来的时间
SHARE_QQ_WAIT = 3.0


class ShareTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "每日分享"
        self.description = "自动完成每日分享任务"

    def run(self):
        self.log_info("开始每日分享...")

        for attempt in range(SHARE_RETRY + 1):
            if attempt:
                self.log_warning(f"===== 重试第 {attempt} 次每日分享 =====")
                # 上一次失败可能停在分享界面/QQ 里，先退回主页面再重来
                if not self.is_main_page():
                    self.back_to_main(max_rounds=12, interval=0.8, log=False)
                self.sleep(1.0)

            if self.should_stop('每日分享'):
                return

            if self.run_once():
                self.log_info("每日分享任务结束")
                return

            self.log_warning(f"第 {attempt + 1} 次每日分享没走完")

        self.log_warning(f"重试 {SHARE_RETRY} 次仍未完成每日分享，本次跳过")
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    def run_once(self):
        """跑一轮：点分享入口最多 SHARE_ENTRY_CLICKS 次，直到 share_qq 出现。

        用户指定的做法：每次点完入口等 1 秒，检测有没有 share_qq；
        3 次都没出现就判这一轮失败（由 run() 回主页面重试）。

        返回 True 表示点中 share_qq 并完成了分享。
        """
        for i in range(1, SHARE_ENTRY_CLICKS + 1):
            if self.should_stop('每日分享'):
                return False

            # 1. 点击主界面分享入口 rel(0.068, 0.068)
            #    固定坐标点击，不依赖主页面背景，所以不受"背景各不相同"影响。
            self.click_relative(0.068, 0.068)
            self.log_info(f"第 {i}/{SHARE_ENTRY_CLICKS} 次点击分享入口")
            self.sleep(SHARE_ENTRY_WAIT)

            # 2. 先看 share_qq 出来了没有（用户指定的判据）
            if self.safe_click_feature('share_qq', threshold=0.8, time_out=1):
                self.log_info("检测到并点击了 share_qq")
                self.sleep(SHARE_QQ_WAIT)      # 等 QQ 打开
                return self.finish_share()

            # 3. 兼容：有的情况下点完入口先出现 personal_share
            #    （分享面板 -> 个人分享 -> QQ 这条链）。它在就点它，再等 share_qq。
            if self.safe_click_feature('personal_share', threshold=0.8, time_out=2):
                self.log_info("先出现了 personal_share，点它，继续等 share_qq")
                self.sleep(1.2)
                if self.safe_click_feature('share_qq', threshold=0.8,
                                           time_out=PERSONAL_SHARE_TIMEOUT):
                    self.log_info("检测到并点击了 share_qq")
                    self.sleep(SHARE_QQ_WAIT)
                    return self.finish_share()
                self.log_warning("点了 personal_share 但没等到 share_qq")

            self.log_warning(f"第 {i} 次点击分享入口后没出现 share_qq")

        return False

    def finish_share(self):
        """分享发出后的收尾：发返回键回到游戏。"""
        if self.press_back():
            self.log_info("已发送返回键")
        else:
            self.log_warning("返回键发送失败")
        self.sleep(2.0)
        return True

    # ================= ADB 发送返回键 =================

    def press_back(self):
        """用 ADB 发送安卓返回键（keyevent 4）"""
        for method in ['adb_shell', 'shell', 'send_adb', 'execute_adb']:
            if hasattr(self, method):
                try:
                    getattr(self, method)('input keyevent 4')
                    self.log_info(f"使用 self.{method}('input keyevent 4') 发送返回键")
                    return True
                except Exception as e:
                    self.log_info(f"self.{method} 失败: {e}")

        # 尝试通过 executor 或 device
        for obj_name in ['executor', 'device']:
            obj = getattr(self, obj_name, None)
            if obj is None:
                continue
            for method in ['adb_shell', 'shell', 'send_adb', 'execute_adb']:
                if hasattr(obj, method):
                    try:
                        getattr(obj, method)('input keyevent 4')
                        self.log_info(f"使用 self.{obj_name}.{method}('input keyevent 4') 发送返回键")
                        return True
                    except Exception as e:
                        self.log_info(f"self.{obj_name}.{method} 失败: {e}")

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

    def click_relative(self, rel_x, rel_y):
        x = int(self.width * rel_x)
        y = int(self.height * rel_y)
        self.click(x, y)
