from ok import BaseTask
import re

# 挑战没成功时额外重试的次数（1 表示最多打两次）
CHALLENGE_RETRY = 1

# 本队战力：先在画面里找 pointrace_personalpower 图标，再 OCR 它右侧的数字。
# 原来靠全屏 OCR 找「本队战力」这几个字，那个词受字体和背景影响、识别不稳；
# 图标是固定图，模板匹配很稳，数值又固定在图标右侧同一行。
POWER_FEATURE = 'pointrace_personalpower'
POWER_RETRY = 3                  # 最多尝试几轮
POWER_REGION_WIDTH_RATIO = 2.5   # 向右扫的宽度 = 图标宽 × 这个倍数
# 垂直方向要收紧：放宽太多会把上下行的数字也框进来。
# 取 0.3 => 区域高 = 图标高 × 1.6，刚好裹住同一行。
POWER_REGION_PAD_RATIO = 0.3


class PointRaceTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "积分赛"
        self.description = "自动领取积分赛奖励并进行挑战"  # 可选

    def run(self):
        self.log_info("开始积分赛...")

        # ========== 1. 进入积分赛 ==========
        box = self.swipe_find('main_pointrace', max_swipes=4, click=True)
        if not box:
            self.log_error("未找到积分赛入口，任务终止")
            return
        self.sleep(1.2)

        # 点击屏幕中央五次
        for i in range(5):
            self.click_relative(0.5, 0.5)
            self.sleep(0.8)

        # ========== 2. 循环挑战 ==========
        max_loops = 20
        exit_reason = "正常结束"

        for loop in range(max_loops):
            self.log_info(f"--- 第 {loop + 1} 轮 ---")

            # 2.1 检查挑战次数（在中间页面检测）
            if self.check_challenge_count_zero():
                exit_reason = "挑战次数为 0"
                self.log_info(exit_reason)
                break

            # 2.2 如果有 pointrace_challenge，点击进入选对手页面
            if self.find_one('pointrace_challenge', threshold=0.8):
                self.log_info("检测到 pointrace_challenge，点击进入选对手页面")
                if not self.wait_click_feature('pointrace_challenge',
                                                threshold=0.8, time_out=3):
                    exit_reason = "点击 pointrace_challenge 失败"
                    self.log_error(exit_reason)
                    break
                self.sleep(1.5)

            # 2.3 识别本队战力
            my_power = self.get_my_power()
            if my_power is None:
                exit_reason = "无法识别本队战力"
                self.log_error(exit_reason)
                break
            self.log_info(f"本队战力: {my_power} 万")

            # 2.4 识别所有对手
            opponents = self.get_opponents()
            self.log_info(f"识别到 {len(opponents)} 个对手")
            for o in opponents:
                self.log_info(f"  对手战力 {o['power']} 万 @ y={o['y']}")

            # 2.5 找低战力目标
            target = None
            for opp in opponents:
                if opp['power'] < my_power:
                    target = opp
                    break

            if target is None:
                self.log_info("没有低于自己战力的对手，尝试刷新")
                if not self.wait_click_feature('pointrace_coinfresh',
                                                threshold=0.8, time_out=3):
                    exit_reason = "刷新按钮消失且无低战力对手"
                    self.log_info(exit_reason)
                    break
                self.sleep(2.0)
                continue

            # 2.6 挑战（挑战没成功就重试一次）
            challenged = False
            for try_idx in range(CHALLENGE_RETRY + 1):
                if try_idx:
                    self.log_warning(f"挑战没成功，重试第 {try_idx} 次")

                # 找挑战按钮
                challenge = self.find_challenge_for(target['y'], target['box'])
                if challenge is None:
                    exit_reason = f"未找到战力 {target['power']} 万对应的挑战按钮"
                    self.log_warning(exit_reason)
                    break

                self.log_info(f"选择对手: 战力 {target['power']} 万，点击挑战 "
                              f"({challenge[0]}, {challenge[1]})")
                self.click(challenge[0], challenge[1])
                self.sleep(1.5)

                # 2.7 轮询等待挑战结果
                if self.wait_challenge_result():
                    challenged = True
                    break

            if not challenged:
                exit_reason = f"挑战未成功（最多尝试 {CHALLENGE_RETRY + 1} 次）"
                self.log_error(exit_reason)
                break

            self.sleep(2.0)

        self.log_info(f"循环结束原因: {exit_reason}")

        # ========== 3. 退出 ==========
        self.sleep(0.5)
        if self.wait_click_feature('popu_cancel', threshold=0.8, time_out=3):
            self.log_info("已退出积分赛")
        else:
            self.log_warning("未找到退出按钮")

        self.log_info("积分赛任务结束")

    # ================= 挑战结果轮询 =================

    def wait_challenge_result(self, max_polls=30, interval=2.0):
        """挑战后轮询等待结果：识别到'当前积分'或'确定'就算成功。

        默认 30 次 × 2 秒 ≈ 60 秒。
        """
        for attempt in range(max_polls):
            if self.click_ocr_text("当前积分", time_out=1.0):
                self.log_info(f"第 {attempt + 1} 次轮询识别到'当前积分'")
                self.sleep(1.0)
                if not self.click_ocr_text("确定", time_out=5):
                    self.log_warning("未找到'确定'按钮")
                return True

            if self.click_ocr_text("确定", time_out=1.0):
                self.log_info(f"第 {attempt + 1} 次轮询识别到'确定'")
                return True

            self.sleep(interval)

        self.log_warning(f"{max_polls} 次轮询内未检测到'当前积分'或'确定'")
        return False

    # ================= 挑战次数检测 =================

    def check_challenge_count_zero(self):
        """OCR 检测'挑战次数'是否为 0/x。返回 True 表示次数为 0"""
        result = self.ocr()
        if not result:
            return False

        for r in result:
            text = self._box_text(r)
            if '挑战次数' in text:
                self.log_info(f"[挑战次数] OCR: '{text}'")
                m = re.search(r'(\d+)\s*/\s*(\d+)', text)
                if m:
                    current = int(m.group(1))
                    if current == 0:
                        return True
                elif self._is_box_like(r):
                    # 数字可能和关键词分开
                    for r2 in result:
                        if not self._is_box_like(r2):
                            continue
                        if abs(r2.y - r.y) < 30 and r2.x > r.x:
                            t2 = self._box_text(r2)
                            m = re.search(r'(\d+)\s*/\s*(\d+)', t2)
                            if m:
                                self.log_info(f"[挑战次数] 相邻OCR: '{t2}'")
                                if int(m.group(1)) == 0:
                                    return True
                                break
        return False

    # ================= 本队战力 =================

    def get_my_power(self):
        """找 pointrace_personalpower 图标，再 OCR 它右侧的数字，返回「万」为单位的值。

        改用模板定位的原因：「本队战力」这四个字用全屏 OCR 找不稳定
        （字体、描边、背景都会影响），而图标是固定图案，模板匹配稳得多；
        数值固定在图标右侧同一行，只需要在图标右边一条窄区域做 OCR，
        既快又不容易读到别的数字。
        """
        for attempt in range(1, POWER_RETRY + 1):
            box = None
            try:
                box = self.find_one(POWER_FEATURE, threshold=0.8)
            except Exception as e:
                self.log_warning(f"[本队战力] 第 {attempt} 次查找图标出错: {e}")

            if box is not None:
                self.log_info(f"[本队战力] 第 {attempt} 次找到 {POWER_FEATURE} "
                              f"({box.x}, {box.y}, {box.width}x{box.height})")
                power = self.read_power_right_of(box)
                if power is not None:
                    return power
            else:
                self.log_warning(f"[本队战力] 第 {attempt} 次没找到 {POWER_FEATURE} 图标")

            if attempt < POWER_RETRY:
                self.sleep(1.0)

        self.log_warning(f"{POWER_RETRY} 次重试后仍未读到本队战力")
        return None

    def read_power_right_of(self, box):
        """在 icon 右侧同一行做 OCR，取出最靠近图标的那个数字。

        取「最靠左」而不是「最长」的数字：数值紧跟在图标右边，
        再往右可能还有别的数字（比如排名），按位置取才不会被带跑。
        """
        w, h = self.width, self.height
        x1 = (box.x + box.width) / w
        x2 = min(1.0, (box.x + box.width * (1 + POWER_REGION_WIDTH_RATIO)) / w)
        y1 = max(0.0, (box.y - box.height * POWER_REGION_PAD_RATIO) / h)
        y2 = min(1.0, (box.y + box.height * (1 + POWER_REGION_PAD_RATIO)) / h)

        self.log_info(f"[本队战力] 在图标右侧 OCR: "
                      f"rel=({x1:.3f},{y1:.3f})->({x2:.3f},{y2:.3f})")
        try:
            result = self.ocr(x1, y1, x2, y2, log=True)
        except Exception as e:
            self.log_warning(f"[本队战力] 右侧区域 OCR 出错: {e}")
            return None

        candidates = []
        for r in (result or []):
            text = self._box_text(r)
            nums = re.findall(r'\d+', text)
            if not nums:
                continue
            candidates.append((getattr(r, 'x', 0), max(nums, key=len), text))

        if not candidates:
            self.log_warning("[本队战力] 图标右侧没读到数字")
            return None

        candidates.sort(key=lambda c: c[0])
        _, number, text = candidates[0]
        self.log_info(f"[本队战力] OCR 原文 '{text}' → {number} 万")
        return int(number)

    # ================= 对手战力 =================

    def get_opponents(self):
        """全屏 OCR 找所有'小队战力xxxx万'，返回带 y 坐标的列表"""
        result = self.ocr()
        if not result:
            return []

        opponents = []
        for r in result:
            text = self._box_text(r)
            if '本队' in text:
                continue
            m = re.search(r'[小认以][队队认]?战力[：:]?\s*(\d+)\s*万', text)
            if not m:
                continue
            if not self._is_box_like(r):
                continue
            power = int(m.group(1))
            opponents.append({
                'power': power,
                'y': r.y + r.height // 2,
                'box': r,
            })
            self.log_info(f"对手战力 OCR 原文: '{text}' @ y={r.y}")

        opponents.sort(key=lambda x: x['y'])
        return opponents

    # ================= 挑战按钮匹配 =================

    def find_challenge_for(self, y_center, enemy_box):
        """
        找到与 enemy 中心 y 最接近、且在 enemy 右侧的挑战按钮。
        """
        result = self.ocr()
        if not result:
            self.log_warning("OCR 无结果")
            return None

        enemy_right = enemy_box.x + enemy_box.width
        best = None
        best_diff = float('inf')

        for r in result:
            if not self._is_box_like(r):
                continue
            text = self._box_text(r)
            if '挑战' not in text:
                continue
            if r.x <= enemy_right:
                continue
            challenge_center_y = r.y + r.height // 2
            diff = abs(challenge_center_y - y_center)
            if diff < best_diff:
                best_diff = diff
                best = r

        if best is None:
            self.log_warning("enemy 右侧没有找到任何'挑战'按钮")
            return None

        max_diff = int(self.height * 0.15)
        if best_diff > max_diff:
            self.log_warning(
                f"最近的'挑战'按钮中心 y 差 {best_diff}px，"
                f"超过 {max_diff}px，放弃点击"
            )
            return None

        click_x = best.x + best.width // 2
        click_y = best.y + best.height // 2
        self.log_info(f"匹配到'挑战': ({click_x}, {click_y})，y 差 {best_diff}px")
        return (click_x, click_y)

    # ================= OCR 工具 =================

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

    # ================= 通用工具 =================

    def click_ocr_text(self, keyword, time_out=0.5):
        boxes = self.wait_ocr(match=[keyword], time_out=time_out)
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            self.click_box(box)
            return True
        return False

    def swipe_find(self, feature, max_swipes=4, click=False):
        """
        先检查当前画面，没有才左右滑动查找。
        """
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
        """找到后等画面稳定，再识别一次，位置没变才点击"""
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
            self.log_warning(
                f"'{feature}' 位置仍在变化 (dx={dx}, dy={dy})，再等一次"
            )
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