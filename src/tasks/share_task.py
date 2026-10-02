from src.tasks.page_nav import PageNavTask
import time

# 等 personal_share 出现的超时（秒）。
# 分享界面弹出后要加载一会儿，有时还要等推送动画，5 秒偏紧所以放宽到 15 秒。
PERSONAL_SHARE_TIMEOUT = 15

# 失败后重试次数。分享界面偶尔弹不出来（点分享入口没反应 / 界面加载慢），
# 退回主页面重来一次通常就好，所以给一次重试。
SHARE_RETRY = 1


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
        """跑一次每日分享；走完整流程返回 True，中途失败返回 False。"""
        # 1. 点击主界面分享入口 rel(0.068, 0.068)
        #    这是固定坐标点击，不依赖主页面背景，所以不受"背景各不相同"影响。
        self.click_relative(0.068, 0.068)
        self.log_info("已点击分享入口")
        self.sleep(1.5)

        # 2. 点击 personal_share（等待时间放宽，见 PERSONAL_SHARE_TIMEOUT）
        if not self.safe_click_feature('personal_share', threshold=0.8,
                                       time_out=PERSONAL_SHARE_TIMEOUT):
            self.log_error(f"等了 {PERSONAL_SHARE_TIMEOUT} 秒仍未找到 personal_share")
            return False
        self.sleep(1.2)

        # 3. 点击 share_qq
        if not self.safe_click_feature('share_qq', threshold=0.8, time_out=5):
            self.log_error("未找到 share_qq")
            return False
        self.sleep(3.0)  # 等 QQ 打开

        # 4. ADB 发送返回键回到游戏
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
