from ok import BaseTask
import re
import time


class TeamFightTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "小队突袭"
        self.description = "自动进行小队突袭并领取贡献"  # 可选

    def run(self):
        self.log_info("开始小队突袭...")

        # ========== 循环两轮 ==========
        for round_idx in range(2):
            self.log_info(f"===== 第 {round_idx + 1} 轮 =====")

            # 1. 每轮都滑动查找 main_teamfight 并点击
            box = self.swipe_find('main_teamfight', max_swipes=4, click=True)
            if not box:
                self.log_error("未找到小队突袭入口，任务终止")
                return
            self.sleep(1.5)

            # 2. 检测"今日可收益次数：0/2"
            if self.detect_no_teamfight_chance():
                self.log_info("今日可收益次数为 0，退出")
                if self.wait_click_feature('popu_cancel', threshold=0.8, time_out=3):
                    self.log_info("已点击 popu_cancel 退出")
                else:
                    self.log_warning("未找到 popu_cancel")
                self.log_info("小队突袭任务结束（次数为 0）")
                return

            # 3. 点击队伍助力
            if not self.safe_click_feature('teamfight_teamhelp', threshold=0.8, time_out=5):
                self.log_error("未找到队伍助力按钮")
                self.cleanup_exit()
                return
            self.sleep(1.2)

            # 4. 第 1 轮才点我的助力 + 领取奖励
            if round_idx == 0:
                if not self.safe_click_feature('teamfight_mywork', threshold=0.8, time_out=5):
                    self.log_warning("未找到我的助力按钮，继续")
                self.sleep(1.2)

                if self.safe_click_feature('teamfight_getreward', threshold=0.8, time_out=3):
                    self.log_info("已点击领取奖励")
                    self.sleep(1.0)
                else:
                    self.log_info("没有奖励可领，跳过")

                if self.safe_click_feature('popu_cancel', threshold=0.8, time_out=3):
                    self.log_info("已点击 popu_cancel")
                    self.sleep(1.5)

            # 5. OCR 找"邀请"，找不到就滑动查找，点最上面的
            if not self.click_top_invite():
                self.log_error("未找到'邀请'，任务终止")
                self.cleanup_exit()
                return
            self.sleep(1.2)

            # 6. 点击出发
            if not self.safe_click_feature('teamfight_go', threshold=0.8, time_out=5):
                self.log_error("未找到出发按钮")
                self.cleanup_exit()
                return
            self.log_info("已点击出发")

            # 7. 等待画面回到主界面（最多 120 秒）
            if not self.wait_for_main_teamfight(timeout=120):
                self.log_error("等待 120 秒未回到主界面")
                self.cleanup_exit()
                return
            self.log_info(f"第 {round_idx + 1} 轮完成，已回到主界面")
            self.sleep(1.5)

        self.log_info("小队突袭任务结束")

    # ================= 检测次数用尽 =================

    def detect_no_teamfight_chance(self):
        """OCR 检测'今日可收益次数'是否为 0/x。返回 True 表示次数为 0"""
        result = self.ocr()
        if not result:
            return False

        for r in result:
            text = self._box_text(r)
            if '可收益次数' in text or '收益次数' in text:
                self.log_info(f"[次数检测] OCR: '{text}'")
                m = re.search(r'(\d+)\s*/\s*(\d+)', text)
                if m and int(m.group(1)) == 0:
                    return True
                if self._is_box_like(r):
                    for r2 in result:
                        if not self._is_box_like(r2):
                            continue
                        if abs(r2.y - r.y) < 30 and r2.x > r.x:
                            t2 = self._box_text(r2)
                            m = re.search(r'(\d+)\s*/\s*(\d+)', t2)
                            if m and int(m.group(1)) == 0:
                                self.log_info(f"[次数检测] 相邻OCR: '{t2}'")
                                return True
                            if m:
                                break
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

    # ================= "邀请"处理 =================

    def click_top_invite(self):
        if self.click_top_invite_ocr():
            return True

        for i in range(5):
            self.log_info(f"[邀请查找] 第 {i+1} 次滑动查找")
            self.swipe_relative(0.20, 0.75, 0.20, 0.25, duration=0.4)
            self.sleep(1.0)
            if self.click_top_invite_ocr():
                return True

        self.log_warning("滑动 5 次后仍未找到'邀请'")
        return False

    def click_top_invite_ocr(self):
        boxes = self.wait_ocr(match=["邀请"], time_out=1.0)
        if not boxes:
            return False
        if not isinstance(boxes, list):
            boxes = [boxes]

        boxes = [b for b in boxes if self._is_box_like(b)]
        if not boxes:
            return False

        topmost = min(boxes, key=lambda b: b.y)
        self.log_info(f"点击最上面的'邀请': ({topmost.x}, {topmost.y})")
        self.click_box(topmost)
        return True

    # ================= 等待回主界面 =================

    def wait_for_main_teamfight(self, timeout=120):
        start = time.time()
        while time.time() - start < timeout:
            box = self.find_one('main_teamfight', threshold=0.8)
            if box:
                self.log_info(f"检测到 main_teamfight，用时 {int(time.time() - start)} 秒")
                return True
            self.sleep(2.0)
        return False

    # ================= 兜底清理 =================

    def cleanup_exit(self, max_rounds=5):
        self.log_info("[清理] 开始尝试退出到主页面")
        for i in range(max_rounds):
            box = self.find_one('team_cancel', threshold=0.8)
            if box:
                self.click_box(box)
                self.log_info(f"[清理] 第 {i+1} 轮：点击 team_cancel")
                self.sleep(0.8)
                continue

            box = self.find_one('popu_cancel', threshold=0.8)
            if box:
                self.click_box(box)
                self.log_info(f"[清理] 第 {i+1} 轮：点击 popu_cancel")
                self.sleep(0.8)
                continue

            self.log_info("[清理] 已无残留弹窗，清理结束")
            break

    # ================= 通用工具 =================

    def _box_text(self, box):
        if isinstance(box, str):
            return box
        for attr in ('name', 'text', 'content'):
            v = getattr(box, attr, None)
            if v:
                return str(v)
        return str(box)

    def _is_box_like(self, r):
        return all(hasattr(r, a) for a in ('x', 'y', 'width', 'height'))

    def swipe_find(self, feature, max_swipes=4, click=False):
        self.log_info(f"[滑动查找] 检查当前画面是否有 '{feature}'")
        box = self.find_one(feature, threshold=0.8)
        if box:
            self.log_info(f"[滑动查找] 当前画面已找到 '{feature}'，无需滑动")
            return self._stable_click(feature, box, click)

        self.log_info(f"[滑动查找] 当前画面没找到，开始向左滑")
        for i in range(max_swipes):
            self.swipe_relative(0.85, 0.5, 0.15, 0.5, duration=0.3)
            self.sleep(0.7)
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 左滑 {i+1} 次后找到 '{feature}'")
                return self._stable_click(feature, box, click)

        self.log_info(f"[滑动查找] 左滑到底仍未找到，开始向右滑回")
        for i in range(max_swipes * 2):
            self.swipe_relative(0.15, 0.5, 0.85, 0.5, duration=0.3)
            self.sleep(0.7)
            box = self.find_one(feature, threshold=0.8)
            if box:
                self.log_info(f"[滑动查找] 右滑 {i+1} 次后找到 '{feature}'")
                return self._stable_click(feature, box, click)

        self.log_warning(f"[滑动查找] 左右滑遍仍未找到 '{feature}'")
        return None

    def _stable_click(self, feature, box, click):
        self.sleep(0.5)
        box2 = self.find_one(feature, threshold=0.8)
        if box2 is None:
            self.log_warning(f"'{feature}' 第二次识别丢失，放弃点击")
            return None

        dx = abs(box2.x - box.x)
        dy = abs(box2.y - box.y)
        threshold_x = int(self.width * 0.01)
        threshold_y = int(self.height * 0.01)

        if dx > threshold_x or dy > threshold_y:
            self.log_warning(f"'{feature}' 位置仍在变化 (dx={dx}, dy={dy})，再等一次")
            self.sleep(0.5)
            box3 = self.find_one(feature, threshold=0.8)
            if box3 is None:
                return None
            box2 = box3

        self.log_info(f"'{feature}' 位置已稳定: ({box2.x}, {box2.y})")
        if click:
            self.click_box(box2)
        return box2

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