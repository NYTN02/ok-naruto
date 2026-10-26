from src.tasks.page_nav import PageNavTask
import time

# 主界面左上角的分享入口（相对坐标）。固定坐标点击，不依赖主页面背景。
SHARE_ENTRY_REL = (0.068, 0.068)
# 点完入口等多久，让分享页面弹出来
SHARE_ENTRY_WAIT = 1.0

# 每次尝试里最多点几次 personal_share。
# 实测点一次不一定弹出 QQ 分享，要多点几次；给 3 次机会。
PERSONAL_SHARE_CLICKS = 3
# 每次点完 personal_share 等多久再检测分享渠道（用户指定 1 秒）
PERSONAL_SHARE_WAIT = 1.0
# 第 1 次等 personal_share 出现要久一点（分享页面在加载）；
# 页面已经在了，后面几次就不用等那么久。
PERSONAL_SHARE_TIMEOUT = 15
PERSONAL_SHARE_RECLICK_TIMEOUT = 3

# 检测 share_qq / share_wechat 时再宽限一点（分享面板有弹出动画）。
# 用户要求的是"点完等 1 秒再检测"，这里的 2 秒只是给动画留点余量。
SHARE_TARGET_TIMEOUT = 2.0

# 分享页打开后，如果不是直接出现 personal_share，可能先走「称号」引导页：
#   本周忍道称号 -> 本次获得格斗称号（一般这个顺序，也可能单独出现）
# 每页点「下一步」/「确定」翻过去，直到 personal_share 出现。
# 用短一点的子串做 OCR 匹配，抗误读。
TITLE_TEXTS = ('本周忍道', '格斗称号')
NEXT_TEXTS = ('下一步', '确定')
TITLE_STEP_TIMEOUT = 1.0     # 每轮找称号/下一步各等多久
TITLE_STEP_WAIT = 1.0        # 点完「下一步」/「确定」后等多久（用户指定）
TITLE_STEP_MAX = 10          # 最多翻几页，防止死循环
# 点中分享渠道之后等目标 App 起来的时间
SHARE_APP_WAIT = 3.0

# 分享渠道：QQ 或微信，点中哪个都算成功（按这个顺序优先）。
# 游戏里的分享面板两个按钮通常都在，用户装哪个用哪个。
SHARE_TARGETS = ('share_qq', 'share_wechat')

# 一轮里 3 次 personal_share 都没点出分享渠道时，回主页面重新来过的次数。
SHARE_RETRY = 2


class ShareTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "每日分享"
        self.description = "自动完成每日分享任务"

    def run(self):
        """每日分享：进分享页面 -> 点 personal_share 出分享渠道 -> 点掉它。

        用户指定的流程：

            点左上角分享入口，进入分享页面（一轮只点一次）
              若没出现 personal_share，先处理「称号」引导页
                （本周忍道称号 / 本次获得格斗称号 -> 点「下一步」/「确定」）
              检测并点击 personal_share（最多 3 次）
                每次点完等 1 秒，检测有没有 share_qq / share_wechat
                  有   -> 点它，继续后面的收尾步骤
                  没有 -> 再点一次 personal_share
              3 次都没有分享渠道 -> 回主页面，重新来一轮
            （共 SHARE_RETRY 次重试）

        分享渠道支持 **QQ 和微信**，点中哪个都算成功。
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

            self.log_warning(f"第 {attempt + 1} 轮没点出分享渠道"
                             f"（{' / '.join(SHARE_TARGETS)}）")

        self.log_warning(f"重试 {SHARE_RETRY} 次仍未完成每日分享，本次跳过")
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    def run_once(self):
        """跑一轮：进分享页面 -> 最多点 3 次 personal_share -> 出分享渠道就点掉。

        返回 True 表示点中某个分享渠道（QQ / 微信）并完成了分享。
        """
        # 1. 点左上角分享入口，进入分享页面（一轮只点这一次）
        self.click_relative(*SHARE_ENTRY_REL)
        self.log_info("已点击分享入口，进入分享页面")
        self.sleep(SHARE_ENTRY_WAIT)

        # 2. personal_share 没出来时，可能是「称号」引导页
        #    （本周忍道称号 / 本次获得格斗称号）—— 逐页点「下一步」/「确定」翻过去。
        #    两者都没有、personal_share 也没有 -> 说明分享页没打开，回主页面重试。
        for k in range(1, TITLE_STEP_MAX + 1):
            if self.should_stop('每日分享'):
                return False

            # personal_share 已经出来了，正常走后面的流程
            if self.find_one('personal_share', threshold=0.8):
                if k > 1:
                    self.log_info(f"personal_share 出来了（翻了 {k - 1} 页称号）")
                break

            title = next((t for t in TITLE_TEXTS
                          if self.ocr_has_text(t, time_out=TITLE_STEP_TIMEOUT)), None)
            if title is None:
                # 既没有 personal_share，也没有称号页 -> 分享页没打开
                self.log_warning("既没出现 personal_share 也没有称号页"
                                 "（本周忍道 / 格斗称号），本轮放弃，回主页面重试")
                return False

            clicked = next((t for t in NEXT_TEXTS
                            if self.ocr_click_text(t, time_out=TITLE_STEP_TIMEOUT)), None)
            if clicked is None:
                self.log_warning(f"看到「{title}」但没找到「下一步」/「确定」")
                return False
            self.log_info(f"第 {k}/{TITLE_STEP_MAX} 页：识别到「{title}」，点击「{clicked}」")
            self.sleep(TITLE_STEP_WAIT)

            # 点完「下一步」/「确定」后若 personal_share 出来了，直接跳出循环
            if self.find_one('personal_share', threshold=0.8):
                self.log_info(f"点完「{clicked}」后 personal_share 出来了，退出称号页循环")
                break
        else:
            self.log_warning(f"翻了 {TITLE_STEP_MAX} 页还没出现 personal_share，本轮放弃")
            return False

        # 3. 检测并点击 personal_share，最多 PERSONAL_SHARE_CLICKS 次
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

            # 3. 每次点完 personal_share 都查一次分享渠道（QQ / 微信）
            target = self.click_share_target()
            if target:
                self.log_info(f"检测到并点击了分享渠道：{target}")
                self.sleep(SHARE_APP_WAIT)      # 等目标 App 打开
                return self.finish_share()

            self.log_warning(f"第 {i} 次点击 personal_share 后没出现 "
                             f"{' / '.join(SHARE_TARGETS)}")

        return False

    # ================= OCR 助手 =================

    def ocr_has_text(self, keyword, time_out=1.0):
        """只检测有没有这段文字，不点击。"""
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        return bool(boxes)

    def ocr_click_text(self, keyword, time_out=1.0):
        """OCR 找到这段文字就点它，找不到返回 False。"""
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if not boxes:
            return False
        box = boxes[0] if isinstance(boxes, list) else boxes
        self.click_box(box)
        return True

    def click_share_target(self, time_out=SHARE_TARGET_TIMEOUT):
        """检测并点击分享渠道按钮，返回点中的是哪个；都没找到返回 None。

        支持 QQ 和微信（``SHARE_TARGETS``）。每一轮把两个都查一遍再等 ——
        不要"先把 share_qq 的超时等满再看微信"，那样微信会白等一个超时。
        """
        deadline = time.time() + time_out
        while True:
            for name in SHARE_TARGETS:
                box = self.find_one(name, threshold=0.8)
                if box:
                    self.click_box(box)
                    return name
            if time.time() >= deadline:
                return None
            if self.should_stop('每日分享'):
                return None
            self.sleep(0.3)

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
