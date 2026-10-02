"""每日签到。

流程：
    主页面 -> 点 main_activity 打开活动页
    -> 沿屏幕左边缘往上滑，直到 OCR 识别出「每月签到」
    -> 点「每月签到」
    -> 找到 activity_qiandao 并点击
    -> 点 activity_qiandaocancel 退回主页面

关于上滑的 x 坐标
--------------------------------------------------------------------------
签到入口不在活动页第一屏，需要一路往上滑。滑动点取**屏幕最左边**
（x = 0.015），贴着边栏/滚动条拖，避免压到活动卡片本身导致误触或拖不动。
这和 teamfight_task 里找「邀请」用的是同一个思路。

需要先标注的模板
--------------------------------------------------------------------------
* main_activity         主界面右上角「活动」入口（已有）
* activity_qiandao       每月签到面板里的签到按钮（**需要标注**）
* activity_qiandaocancel 签到面板的关闭/返回按钮（**需要标注**）

后两个还没进 assets/coco_annotations.json。任务开头会先检查，缺了就直接
退出并提示去标注，而不是抛 FeatureSet: xxx not found in featureDict。
"""

import re
import time

from src.tasks.page_nav import PageNavTask

# 上滑位置：贴左边缘
SWIPE_X = 0.015
SWIPE_FROM_Y = 0.75
SWIPE_TO_Y = 0.25
SWIPE_DURATION = 0.4

# 最多滑几次（活动列表比较长，留够余量）
MAX_SWIPES = 10

# 目标文字用正则做包含匹配；ok-script 传纯字符串是精确匹配
SIGN_IN_TEXT = re.compile(r'每月签到')

# 本任务依赖的模板
REQUIRED_FEATURES = ('main_activity', 'activity_qiandao', 'activity_qiandaocancel')


class QianDaoTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "每日签到"
        self.description = "打开活动页上滑找到「每月签到」并领取"

    def run(self):
        self.log_info("开始每日签到...")

        # 0. 模板自检：缺模板时给明确提示，别等到 find_one 抛异常
        missing = [n for n in REQUIRED_FEATURES if not self._feature_exists(n)]
        if missing:
            self.log_error(f"缺少模板 {missing}，请先用开发工具的「模板」功能标注，任务终止")
            return

        # 1. main_activity 在主界面右上角，先确保在主页
        if not self.is_main_page():
            self.log_info("当前不在主页面，先退回主页面")
            self.back_to_main(max_rounds=10, interval=0.8, log=False)

        # 2. 打开活动页
        if not self.safe_click_feature('main_activity', threshold=0.8, time_out=5):
            self.log_error("未找到活动入口 main_activity，任务终止")
            return
        self.log_info("已打开活动页")
        self.sleep(1.5)

        # 3. 上滑直到看到「每月签到」
        if not self.swipe_until_sign_in():
            self.log_warning(f"上滑 {MAX_SWIPES} 次仍未看到'每月签到'，放弃本次签到")
            self.back_to_main(max_rounds=10, interval=0.8)
            self.log_info("每日签到任务结束（未找到条目）")
            return

        # 4. 点「每月签到」
        if not self.click_sign_in_text():
            self.log_warning("点击'每月签到'失败")
            self.back_to_main(max_rounds=10, interval=0.8)
            self.log_info("每日签到任务结束")
            return
        self.log_info("已点击「每月签到」")
        self.sleep(1.2)

        # 5. 点签到
        signed = self.safe_click_feature('activity_qiandao', threshold=0.8, time_out=5)
        if signed:
            self.log_info("已点击签到")
        else:
            # 没出现 activity_qiandao（比如今天已经签到过，或签到面板没弹出来），
            # 直接走下面的关闭流程退回主页面
            self.log_warning("未出现 activity_qiandao，直接点 activity_qiandaocancel 返回主页面")
        self.sleep(1.2)

        # 6. 关掉签到面板回主页面（上面两种情况都要做）
        if self.safe_click_feature('activity_qiandaocancel', threshold=0.8, time_out=5):
            self.log_info("已点击 activity_qiandaocancel")
        else:
            self.log_warning("未找到 activity_qiandaocancel，改用通用退出")
        self.sleep(1.0)

        if not self.is_main_page():
            self.back_to_main(max_rounds=10, interval=0.8)

        self.log_info("每日签到任务结束")

    # ================= 滑动找「每月签到」 =================

    def swipe_until_sign_in(self):
        """每轮先看当前画面有没有「每月签到」，没有就沿左边缘上滑一格。"""
        for i in range(MAX_SWIPES):
            if self.find_sign_in_text() is not None:
                self.log_info(f"第 {i} 次检查时已看到'每月签到'，无需再滑")
                return True

            self.log_info(f"[签到查找] 第 {i+1} 次上滑 "
                          f"(x={SWIPE_X} {SWIPE_FROM_Y}->{SWIPE_TO_Y})")
            self.swipe_relative(SWIPE_X, SWIPE_FROM_Y, SWIPE_X, SWIPE_TO_Y,
                                duration=SWIPE_DURATION)
            self.sleep(1.0)

        return self.find_sign_in_text() is not None

    def find_sign_in_text(self):
        boxes = self.ocr(match=[SIGN_IN_TEXT])
        if not boxes:
            return None
        return boxes[0] if isinstance(boxes, list) else boxes

    def click_sign_in_text(self):
        box = self.wait_ocr(match=[SIGN_IN_TEXT], time_out=2.0)
        if not box:
            return False
        box = box[0] if isinstance(box, list) else box
        self.log_info(f"点击'每月签到': ({box.x}, {box.y})")
        self.click_box(box)
        return True

    # ================= 通用工具 =================

    def safe_click_feature(self, feature, threshold=0.8, time_out=5):
        start = time.time()
        while time.time() - start < time_out:
            box = self.find_one(feature, threshold=threshold)
            if box:
                self.click_box(box)
                return True
            self.sleep(0.3)
        return False

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)
