from src.tasks.page_nav import PageNavTask
import time

# 主界面左上角的分享入口（相对坐标）。固定坐标点击，不依赖主页面背景。
SHARE_ENTRY_REL = (0.068, 0.068)
# 点完入口等多久，让分享页面弹出来
SHARE_ENTRY_WAIT = 1.0

# 每次尝试里最多点几次 personal_share。
# 实测点一次不一定弹出 QQ 分享，要多点几次；给 3 次机会。
PERSONAL_SHARE_CLICKS = 3
# 每次点完 personal_share 等多久再检测 share_qq（用户指定 1 秒）
PERSONAL_SHARE_WAIT = 1.0
# 第 1 次等 personal_share 出现要久一点（分享页面在加载）；
# 页面已经在了，后面几次就不用等那么久。
PERSONAL_SHARE_TIMEOUT = 15
PERSONAL_SHARE_RECLICK_TIMEOUT = 3

# 检测 share_qq 时再宽限一点（QQ 分享面板有弹出动画）。
# 用户要求的是"点完等 1 秒再检测"，这里的 2 秒只是给动画留点余量。
SHARE_QQ_TIMEOUT = 2.0
# 点中 share_qq 之后等 QQ 起来的时间
SHARE_QQ_WAIT = 3.0

# 一轮里 3 次 personal_share 都没点出 share_qq 时，回主页面重新来过的次数。
SHARE_RETRY = 2


class ShareTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "每日分享"
        self.description = "自动完成每日分享任务"

    def run(self):
        """每日分享：进分享页面 -> 点 personal_share 出 QQ 分享 -> 点掉它。

        用户指定的流程：

            点左上角分享入口，进入分享页面（一轮只点一次）
              检测并点击 personal_share（最多 3 次）
                每次点完等 1 秒，检测有没有 share_qq
                  有   -> 点 share_qq，继续后面的收尾步骤
                  没有 -> 再点一次 personal_share
              3 次都没有 share_qq -> 回主页面，重新来一轮
            （共 SHARE_RETRY 次重试）
        """
        self.log_info("开始每日分享...")

        for attempt in range(SHARE_RETRY + 1):
            if attempt:
                self.log_warning(f"===== 第 {attempt}/{SHARE_RETRY} 次重试每日分享 =====")
                # 上一轮可能停在分享页面/QQ 里，先退回主页面再重来
                if not self.is_main_page():
                    self.back_to_main(max_rounds=12, interval=0.8, log=False)
                self.sleep(1.0)

            if self.should_stop('每日分享'):
                return

            if self.run_once():
                self.log_info("每日分享任务结束")
                return

            self.log_warning(f"第 {attempt + 1} 轮没点出 share_qq")

        self.log_warning(f"重试 {SHARE_RETRY} 次仍未完成每日分享，本次跳过")
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    def run_once(self):
        """跑一轮：进分享页面 -> 最多点 3 次 personal_share -> 出 share_qq 就点掉。

        返回 True 表示点中 share_qq 并完成了分享。
        """
        # 1. 点左上角分享入口，进入分享页面（一轮只点这一次）
        self.click_relative(*SHARE_ENTRY_REL)
        self.log_info("已点击分享入口，进入分享页面")
        self.sleep(SHARE_ENTRY_WAIT)

        # 2. 检测并点击 personal_share，最多 PERSONAL_SHARE_CLICKS 次
        for i in range(1, PERSONAL_SHARE_CLICKS + 1):
            if self.should_stop('每日分享'):
                return False

            timeout = (PERSONAL_SHARE_TIMEOUT if i == 1
                       else PERSONAL_SHARE_RECLICK_TIMEOUT)
            if not self.safe_click_feature('personal_share', threshold=0.8,
                                           time_out=timeout):
                # 连 personal_share 都找不到，说明分享页面没打开/已经关掉了，
                # 再点也没用 —— 直接判本轮失败，让 run() 回主页面重来
                self.log_warning(f"第 {i}/{PERSONAL_SHARE_CLICKS} 次没找到 personal_share"
                                 f"（分享页面可能没打开）")
                return False

            self.log_info(f"第 {i}/{PERSONAL_SHARE_CLICKS} 次点击 personal_share")
            self.sleep(PERSONAL_SHARE_WAIT)

            # 3. 每次点完 personal_share 都查一次 share_qq
            if self.safe_click_feature('share_qq', threshold=0.8,
                                       time_out=SHARE_QQ_TIMEOUT):
                self.log_info("检测到并点击了 share_qq")
                self.sleep(SHARE_QQ_WAIT)      # 等 QQ 打开
                return self.finish_share()

            self.log_warning(f"第 {i} 次点击 personal_share 后没出现 share_qq")

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
        """等 feature 出现并点击它；超时返回 False（不抛异常）。"""
        start = time.time()
        while time.time() - start < time_out:
            if self.should_stop('每日分享'):
                return False
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
