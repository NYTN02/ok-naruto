from ok import BaseTask


class TeamPrayTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "组织祈福"
        self.description = "自动进行组织祈福并领取奖励"  # 可选

    def run(self):
        self.log_info("开始组织祈福...")

        # ========== 1. 进入组织 ==========
        box = self.swipe_find('main_team', max_swipes=4, click=True)
        if not box:
            self.log_error("未找到组织入口，任务终止")
            return
        self.sleep(1.5)

        # ========== 2. 点击玩法 ==========
        if not self.wait_click_feature('team_playway', threshold=0.8, time_out=5):
            self.log_error("未找到玩法按钮")
            self.cleanup_exit()
            return
        self.sleep(1.2)

        # ========== 3. OCR 点击最左边的"前往" ==========
        if not self.click_leftmost_ocr("前往", time_out=3.0):
            self.log_error("未找到'前往'按钮")
            self.cleanup_exit()
            return
        self.sleep(1.5)

        # ========== 4. 点击 team_coinpray ==========
        if not self.wait_click_feature('team_coinpray', threshold=0.8, time_out=5):
            self.log_warning("未找到 team_coinpray，尝试退出")
            self.cleanup_exit()
            return
        self.sleep(1.2)

        # ========== 4.5 检测"今日次数已达上限" ==========
        if self.click_ocr_text("今日次数已达上限", time_out=2.0):
            self.log_info("检测到'今日次数已达上限'，点击确定")
            self.sleep(1.0)
            if self.click_ocr_text("确定", time_out=3.0):
                self.log_info("已点击确定，继续祈福流程")
            else:
                self.log_warning("未找到'确定'按钮，继续祈福流程")
            self.sleep(1.0)
        else:
            self.log_info("未检测到次数上限提示，直接继续祈福流程")

        # ========== 5. 循环点 team_prayreward 和三个 getreward ==========
        max_rounds = 10
        for i in range(max_rounds):
            clicked_any = False

            box = self.find_one('team_prayreward', threshold=0.8)
            if box:
                self.click_box(box)
                self.log_info(f"第 {i+1} 轮：点击 team_prayreward")
                self.sleep(1.0)
                clicked_any = True

            for name in ['team_getreward', 'team_getreward2', 'team_getreward3']:
                box = self.find_one(name, threshold=0.8)
                if box:
                    self.click_box(box)
                    self.log_info(f"第 {i+1} 轮：点击 {name}")
                    self.sleep(1.0)
                    clicked_any = True
                else:
                    self.log_info(f"第 {i+1} 轮：未找到 {name}，跳过")

            if not clicked_any:
                self.log_info(f"第 {i+1} 轮：什么都没找到，退出循环")
                break
        else:
            self.log_warning(f"达到最大轮数 {max_rounds}，强制退出循环")

        # ========== 6. 点击右上角关闭 ==========
        self.click_relative(0.956, 0.051)
        self.sleep(1.0)

        # ========== 7. 点击 popu_cancel ==========
        if self.wait_click_feature('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 popu_cancel")
            self.sleep(1.0)

        # ========== 8. 点击 team_cancel 退出到主页面 ==========
        if self.wait_click_feature('team_cancel', threshold=0.8, time_out=3):
            self.log_info("已点击 team_cancel")
        else:
            self.log_warning("未找到 team_cancel")

        # ========== 9. 最终兜底：清理残留弹窗 ==========
        self.cleanup_exit()

        self.log_info("组织祈福任务结束")

    # ================= OCR 工具 =================

    def click_ocr_text(self, keyword, time_out=0.5):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    def click_leftmost_ocr(self, keyword, time_out=3.0):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if not boxes:
            return False
        if not isinstance(boxes, list):
            boxes = [boxes]

        boxes = [b for b in boxes if self._is_box_like(b)]
        if not boxes:
            return False

        leftmost = min(boxes, key=lambda b: b.x)
        self.log_info(f"点击最左边的'{keyword}': ({leftmost.x}, {leftmost.y})")
        self.click_box(leftmost)
        return True

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
        self.log_info(f"点击相对坐标 ({rel_x}, {rel_y}) -> ({x}, {y})")

    def swipe_relative(self, rel_x1, rel_y1, rel_x2, rel_y2, duration=0.3):
        x1 = int(self.width * rel_x1)
        y1 = int(self.height * rel_y1)
        x2 = int(self.width * rel_x2)
        y2 = int(self.height * rel_y2)
        self.swipe(x1, y1, x2, y2, duration=duration)