"""通过「指南」入口进入各玩法。

为什么要改
--------------------------------------------------------------------------
每个玩家的主页面背景都不一样（等级、活动、皮肤都会改背景），直接模板匹配
``main_team`` / ``main_mission`` / ``main_pointrace`` 这类主页图标经常找不到。

「指南」是游戏里一个统一的入口列表，位置固定、内容稳定，所以在列表里滑动
找条目比在主页面找图标可靠得多。这个模块把这套进入流程收成一处，
任务集会所 / 排行榜 / 积分赛 / 小队突袭 / 丰饶之间 共用。

关于「按住 -> 拖动 -> 松开」
--------------------------------------------------------------------------
用户明确要求每次滑动都要是完整的手势，而不是快速一甩。

要留意 ok-script 在 MuMu IPC 这条路上的实现（``ADBInteraction.swipe_nemu``）：

    def swipe_nemu(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        points = insert_swipe(p0=(from_x, from_y), p3=(to_x, to_y))
        for point in points:
            self.capture.nemu_impl.down(*point)   # 沿途逐点按下（=拖动）
            time.sleep(0.010)
        while time.time() - start < settle_time:  # 在终点继续按住
            self.capture.nemu_impl.down(*p2)
            time.sleep(0.140)
        self.capture.nemu_impl.up()               # 松手

也就是说：

* ``duration`` 在这条路上**被忽略** —— 拖动速度由固定的 10ms/点决定，
  调大 duration 不会变慢，别在这里白费劲；
* ``settle_time`` 才是有用的旋钮 —— 它让手指在**终点继续按住**这么久再松开，
  这就是「按住 -> 拖动 -> 松开」里「按住」那部分的实际抓手。

所以下面的滑动都用 ``settle_time`` 来调手感。如果将来还是要更"黏"的拖动，
得直接驱动 ``nemu_impl.down/up`` 自己插值，但那会耦合 ok-script 的内部实现，
不到万不得已不做。
"""

import re
import time

import cv2
import numpy as np

from src.tasks.page_nav import PageNavTask

# ---------------------------------------------------------------------------
# 指南
# ---------------------------------------------------------------------------
GUIDE_ENTRY = 'main_guide'      # 主页面上的「指南」入口
GUIDE_CANCEL = 'guide_cancel'   # 指南里的关闭按钮

# 列表两端怎么判定：**用 OCR 认两端的条目文字**（用户指定）。
#   OCR 到「装备」     => 已经在列表最顶端，不能再往顶部滑
#   OCR 到「忍具锻造」 => 已经在列表最底部，不能再往底部滑
#
# 注：顶部判据最初写的是「天赋」，实测不对 —— 列表最上面那一项是「装备」。
#
# 为什么不用 guide_listtop / guide_listbottom 那两个模板：那两个标记很小，
# 滑过头就露不全、匹配不到，会出现"已经到头却还以为能继续滑"的假象。
# OCR 认条目文字稳得多。两个模板作为兜底保留（两条路都有更稳）。
GUIDE_LISTTOP = 'guide_listtop'
GUIDE_LISTBOTTOM = 'guide_listbottom'
GUIDE_TOP_TEXT = '装备'          # 列表最上面那一项
GUIDE_BOTTOM_TEXT = '忍具锻造'   # 列表最下面那一项
# ⚠️ 两端判据必须用**全等匹配**（^...$），不能用包含匹配。
#    踩过的坑：原来顶部判据写「天赋」，结果列表底部有一项叫「修罗天赋」，
#    它的 OCR 文本里也含「天赋」两个字 —— 于是滑到底部时被误判成"到顶了"，
#    方向判断反过来，往上找就永远收敛不了。
#    加锚点后就只认整条文本完全一致，不会被子串误触发。
GUIDE_TOP_PATTERN = re.compile(r'^' + re.escape(GUIDE_TOP_TEXT) + r'$')
GUIDE_BOTTOM_PATTERN = re.compile(r'^' + re.escape(GUIDE_BOTTOM_TEXT) + r'$')

# 在指南列表上滑动的手势（相对坐标），由用户实测指定。
#
# 列表固定在屏幕左侧那一列（x 取 0.100），两个方向各是一条固定的起止线：
#
#   往下找（想看列表更下面的内容）：按住 (0.100, 0.777) 滑到 (0.100, 0.325) 再松手
#   往上找（想看列表更上面的内容）：按住 (0.100, 0.325) 滑到 (0.100, 0.777) 再松手
#
# 注意手指方向和内容方向是反的：往下找时手指是**往上**拖的。
# 起点/终点都落在列表范围内（按标注量出来列表约 0.162 ~ 0.828），不会滑出列表。
GUIDE_SCROLL_X = 0.100
GUIDE_SCROLL_DOWN_FROM_Y = 0.777    # 往下找：起点（手指按住这里）
GUIDE_SCROLL_DOWN_TO_Y = 0.325      # 往下找：终点（拖到这里再松手）
GUIDE_SCROLL_UP_FROM_Y = 0.325      # 往上找：起点
GUIDE_SCROLL_UP_TO_Y = 0.777        # 往上找：终点

GUIDE_SCROLL_SETTLE = 0.35      # 拖到终点后再按住多久才松开
# 松手后等多久再去看画面。
#
# ⚠️ 这个值不能太小（当前 1 秒）：列表松手后还会靠惯性继续滚一会儿，
#    如果立刻做匹配/OCR，画面还在动/还在滚，就会出现
#    「明明画面里已经有要找的东西，却判定成没找到」的假失败 ——
#    实测 0.6 秒时就会偶发，所以固定给足 1 秒。
#    它同时也是"两次滑动之间的间隔"。
GUIDE_SCROLL_AFTER = 1.0

# 每个方向最多重复滑动多少次（用户指定：往下找、往上找各 20 次）
GUIDE_SCROLL_MAX = 20

# ---------------------------------------------------------------------------
# 「列表有没有真的动」——只用来发现"滑动出问题"，**不用来判定边界**
#
# 边界一律只认 guide_listtop / guide_listbottom 两个模板。
# 画面没动只说明这一下手势没生效（滑到列表外面 / 被动画吃掉），
# 那时如果手上没有边界标志，就不能当成"到头了"，否则会把明明还能滚的列表判死。
# 连续 GUIDE_STUCK_TOLERANCE 次滑不动才放弃该方向（单次可能只是偶发）。
# ---------------------------------------------------------------------------
GUIDE_LIST_SIG_X1, GUIDE_LIST_SIG_X2 = 0.05, 0.30   # 列表区域（相对坐标）
GUIDE_LIST_SIG_Y1, GUIDE_LIST_SIG_Y2 = 0.18, 0.80
GUIDE_LIST_MOVE_THRESHOLD = 2.0   # 平均灰度差小于这个值就认为"没动"
GUIDE_STUCK_TOLERANCE = 2         # 连续几次滑不动就放弃这个方向

# 各等待时长（秒）
GUIDE_ENTRY_TIMEOUT = 5.0       # 等 main_guide 出现
GUIDE_OPEN_WAIT = 1.8           # 点开指南后等列表加载
GUIDE_ITEM_TIMEOUT = 3.0        # 等条目/前往按钮出现
GUIDE_ITEM_WAIT = 1.5           # 点条目后等界面切换
GUIDE_GO_TIMEOUT = 5.0
GUIDE_GO_WAIT = 1.8

# 「立刻前往」这类入口文字的匹配（用正则做包含匹配，避免 OCR 多字少字就失配）
DAILY_TASK_PATTERN = re.compile(r'每日任务')

# 指南条目点开后的「前往」按钮文字。模板认不到时用它兜底。
GO_TEXT_PATTERN = re.compile(r'前往')


class GuideNavTask(PageNavTask):
    """会走「指南」入口的任务基类。

    在 PageNavTask（判断主页 / 退回主页）之上加了：
      * ``click_feature``   等模板出现并点击
      * ``gesture``         统一的「按住 -> 拖动 -> 松开」
      * ``scroll_guide``    在指南列表上滑一次
      * ``find_in_guide``   在指南列表里滑着找条目
      * ``enter_guide``     完整进入流程（含 guide_cancel 兜底）
      * ``click_below``     OCR 找某个条目正下方的按钮并点击
    """

    # ------------------------------------------------------------------
    # 基础动作
    # ------------------------------------------------------------------
    def click_feature(self, feature, threshold=0.8, time_out=5.0):
        """在 time_out 秒内等 feature 出现并点击；成功返回 True。"""
        if not self._feature_exists(feature):
            self.log_error(f"模板 {feature} 不存在（可能还没标注），无法点击")
            return False
        start = time.time()
        while time.time() - start < time_out:
            box = self._safe_find_one(feature, threshold)
            if box is not None:
                self.click_box(box)
                self.log_info(f"已点击 {feature} ({box.x}, {box.y})")
                return True
            self.sleep(0.3)
        return False

    def click_text(self, pattern, time_out=3.0):
        """等 OCR 出现 pattern 并点击；成功返回 True。

        pattern 建议传 re.compile(...)，这样是包含匹配；传纯字符串是精确匹配。
        """
        start = time.time()
        while time.time() - start < time_out:
            try:
                boxes = self.ocr(match=[pattern])
            except Exception as e:
                self.log_debug(f"OCR「{pattern}」出错: {e}")
                boxes = None
            if boxes:
                box = boxes[0] if isinstance(boxes, list) else boxes
                if all(hasattr(box, a) for a in ('x', 'y')):
                    self.click_box(box)
                    self.log_info(f"已点击「{pattern}」({box.x}, {box.y})")
                    return True
            self.sleep(0.4)
        return False

    def gesture(self, x1, y1, x2, y2, settle=GUIDE_SCROLL_SETTLE, after=GUIDE_SCROLL_AFTER):
        """一次完整的「按住 -> 拖动 -> 松开」。

        注意 ``duration`` 在 MuMu IPC 这条路上被忽略（见模块开头），
        真正起作用的是：

        * ``settle`` —— 拖到终点后继续按住多久才松手（"按住"的手感）；
        * ``after``  —— 松手后等多久才继续往下走。它同时是**两次滑动之间的间隔**，
          必须给足（当前 1 秒），否则列表还在惯性滚动时就去匹配模板，
          会出现「明明在画面上却判定没找到」的假失败。
        """
        self.log_info(f"[手势] 按住拖动 ({x1},{y1}) -> ({x2},{y2}) "
                      f"settle={settle}s 之后等 {after}s")
        self.swipe(x1, y1, x2, y2, duration=0.5, settle_time=settle, after_sleep=after)

    # ------------------------------------------------------------------
    # 指南列表
    # ------------------------------------------------------------------
    def _ocr_has(self, pattern):
        """OCR 是否能在当前画面认出 pattern。"""
        try:
            return bool(self.ocr(match=[pattern]))
        except Exception as e:
            self.log_debug(f"OCR「{pattern.pattern}」出错: {e}")
            return False

    def at_guide_top(self):
        """是否已经在指南列表最顶端。

        判据：OCR 认出列表最上面那一项「天赋」。认不到再用 guide_listtop 模板兜底。
        """
        if self._ocr_has(GUIDE_TOP_PATTERN):
            self.log_info(f"[指南] OCR 认出「{GUIDE_TOP_TEXT}」，判定已在列表顶部")
            return True
        self._warn_if_bounds_features_missing()
        return self._safe_find_one(GUIDE_LISTTOP) is not None

    def at_guide_bottom(self):
        """是否已经在指南列表最底部。

        判据：OCR 认出列表最下面那一项「忍具锻造」。认不到再用 guide_listbottom 兜底。
        """
        if self._ocr_has(GUIDE_BOTTOM_PATTERN):
            self.log_info(f"[指南] OCR 认出「{GUIDE_BOTTOM_TEXT}」，判定已在列表底部")
            return True
        self._warn_if_bounds_features_missing()
        return self._safe_find_one(GUIDE_LISTBOTTOM) is not None

    def _warn_if_bounds_features_missing(self):
        """两个边界模板缺了就告警一次 —— 缺了不会报错，但边界判断会失效。"""
        if getattr(self, '_guide_bounds_warned', False):
            return
        self._guide_bounds_warned = True
        for name in (GUIDE_LISTTOP, GUIDE_LISTBOTTOM):
            if not self._feature_exists(name):
                self.log_warning(f"模板 {name} 不存在，指南列表的边界判断会失效，"
                                 f"滑动会一直做到次数上限")

    def scroll_guide(self, to_bottom=True):
        """在指南列表上滑一次（手势起止点见模块开头的 GUIDE_SCROLL_* 常量）。

        ``to_bottom=True``  -> 想看列表**更下面**的内容：按住 0.777 滑到 0.325
        ``to_bottom=False`` -> 想看列表**更上面**的内容：按住 0.325 滑到 0.777

        手指方向和内容方向是反的，很容易搞混，所以参数按"想看哪边的内容"命名：
        手指往上拖时内容跟着往上走，看到的是更下面的条目。
        """
        x = int(self.width * GUIDE_SCROLL_X)
        if to_bottom:
            y_from = int(self.height * GUIDE_SCROLL_DOWN_FROM_Y)
            y_to = int(self.height * GUIDE_SCROLL_DOWN_TO_Y)
        else:
            y_from = int(self.height * GUIDE_SCROLL_UP_FROM_Y)
            y_to = int(self.height * GUIDE_SCROLL_UP_TO_Y)
        self.gesture(x, y_from, x, y_to)

    def list_thumb(self):
        """给指南列表区域算一张小灰度缩略图，用来判断滑动前后画面有没有变。"""
        try:
            frame = self.frame
        except Exception as e:
            self.log_debug(f"取画面失败，跳过「有没有动」判断: {e}")
            return None
        if frame is None:
            return None
        h, w = frame.shape[:2]
        roi = frame[int(h * GUIDE_LIST_SIG_Y1):int(h * GUIDE_LIST_SIG_Y2),
                    int(w * GUIDE_LIST_SIG_X1):int(w * GUIDE_LIST_SIG_X2)]
        if roi.size == 0:
            return None
        return cv2.resize(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (32, 32)).astype('int16')

    def list_moved(self, before, after):
        """滑动前后列表画面是否明显变化；拿不到画面时保守地当成"动了"。"""
        if before is None or after is None:
            return True
        diff = float(np.abs(before - after).mean())
        moved = diff > GUIDE_LIST_MOVE_THRESHOLD
        self.log_debug(f"[指南] 滑动前后画面差异 {diff:.2f} -> {'有变化' if moved else '没变化'}")
        return moved

    def exit_guide(self):
        """点 guide_cancel 退回主页面。"""
        if self.click_feature(GUIDE_CANCEL, time_out=GUIDE_ITEM_TIMEOUT):
            self.log_info(f"已点击 {GUIDE_CANCEL} 退出指南")
            self.sleep(1.2)
        else:
            self.log_warning(f"没找到 {GUIDE_CANCEL}，改用通用方式退回主页面")
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    def enter_guide(self, item_text, go_feature, item_feature=None,
                    max_swipes=GUIDE_SCROLL_MAX):
        """走「指南」进入某个玩法。

        :param item_text:    指南列表里条目的**文字**，用 OCR 识别并点击，
                             如 '任务集会所' / '积分赛' / '排行榜' / '小队突袭' / '丰饶之间'
        :param go_feature:   点完条目后出现的「前往」按钮模板，如 'guide_missiongo'
        :param item_feature: 条目模板。OCR 认不出来时用它兜底（可选）。
                             列表里条目文字随时可能被改，而模板是固定图案，
                             两条路都有更稳。

        流程::

            点 main_guide
              -> 滑动 + OCR 找到条目文字（找不到则用模板兜底）并点击
              -> 点「前往」（模板优先，认不到再用 OCR 找「前往」）

        任何一步失败都会点 guide_cancel 退回主页面再返回 False，
        让调用方干净地放弃这个任务，而不是停在半路。
        """
        # 1. main_guide 在主界面上，先确保在主页
        if not self.is_main_page():
            self.log_info("当前不在主页面，先退回主页面")
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

        # 2. 点开指南
        if not self.click_feature(GUIDE_ENTRY, time_out=GUIDE_ENTRY_TIMEOUT):
            self.log_error(f"未找到 {GUIDE_ENTRY}，无法通过指南进入「{item_text}」")
            return False
        self.sleep(GUIDE_OPEN_WAIT)

        # 3. 滑动 + OCR 找条目
        box = self.find_entry_in_guide(item_text, item_feature, max_swipes)
        if box is None:
            self.log_warning(f"指南里滑遍都没找到「{item_text}」")
            self.exit_guide()
            return False

        # 4. 点条目
        self.click_box(box)
        self.log_info(f"已点击「{item_text}」({box.x}, {box.y})")
        self.sleep(GUIDE_ITEM_WAIT)

        # 5. 点「前往」：先试模板，认不到再用 OCR 找「前往」两个字
        if not self.click_feature(go_feature, time_out=GUIDE_GO_TIMEOUT):
            self.log_warning(f"没找到 {go_feature}，改用 OCR 找「前往」")
            if not self.click_text(GO_TEXT_PATTERN, time_out=GUIDE_GO_TIMEOUT):
                self.log_warning(f"「{item_text}」的「前往」按钮也没识别到")
                self.exit_guide()
                return False
        self.sleep(GUIDE_GO_WAIT)

        self.log_info(f"已通过指南进入「{item_text}」")
        return True

    def find_entry_in_guide(self, item_text, item_feature=None, max_swipes=GUIDE_SCROLL_MAX):
        """在指南列表里滑动找条目，返回它的 Box；找不到返回 None。

        优先用 OCR 认文字（列表条目本身就是文字），认不到再用模板兜底。
        两个方向各最多滑 ``max_swipes`` 次（默认 20）。
        """
        item_pattern = re.compile(re.escape(item_text))
        templates = [item_feature] if item_feature else []

        # 先看当前画面
        box = self.find_entry_on_screen(item_pattern, templates)
        if box is not None:
            self.log_info(f"[指南] 当前画面已看到「{item_text}」")
            return box

        # 先朝底部方向找
        box = self._sweep_entry(item_pattern, templates, to_bottom=True, max_swipes=max_swipes)
        if box is not None:
            return box

        # 再折返朝顶部方向找
        return self._sweep_entry(item_pattern, templates, to_bottom=False, max_swipes=max_swipes)

    def find_entry_on_screen(self, item_pattern, templates):
        """在当前画面里找条目：先 OCR 文字，再退回模板。"""
        try:
            boxes = self.ocr(match=[item_pattern])
        except Exception as e:
            self.log_debug(f"OCR 找条目出错: {e}")
            boxes = None
        if boxes:
            box = boxes[0] if isinstance(boxes, list) else boxes
            if all(hasattr(box, a) for a in ('x', 'y')):
                self.log_info(f"[指南] OCR 认到「{item_pattern.pattern}」"
                              f"({box.x}, {box.y})")
                return box
        for name in templates:
            box = self._safe_find_one(name)
            if box is not None:
                self.log_info(f"[指南] OCR 没认到，改用模板 {name} 找到条目")
                return box
        return None

    def _sweep_entry(self, item_pattern, templates, to_bottom, max_swipes):
        """朝一个方向滑，每一站都找一次条目；找到返回 Box，否则 None。

        边界只由 guide_listtop / guide_listbottom 判定；
        画面没动又没有边界标志 => 判定为滑动出问题，重试几次仍不行才放弃。
        """
        direction = '下' if to_bottom else '上'
        boundary = GUIDE_LISTBOTTOM if to_bottom else GUIDE_LISTTOP
        stuck_streak = 0

        for i in range(1, max_swipes + 1):
            if self.should_stop('指南滑动'):
                return None

            # ---- 边界判据：只认模板 ----
            if to_bottom and self.at_guide_bottom():
                self.log_info(f"[指南] 已经到底（看到 {GUIDE_LISTBOTTOM}），停止往{direction}找")
                return None
            if not to_bottom and self.at_guide_top():
                self.log_info(f"[指南] 已经到顶（看到 {GUIDE_LISTTOP}），停止往{direction}找")
                return None

            self.log_info(f"[指南] 往{direction}找 {i}/{max_swipes}：「{item_pattern.pattern}」")
            before = self.list_thumb()
            self.scroll_guide(to_bottom=to_bottom)

            box = self.find_entry_on_screen(item_pattern, templates)
            if box is not None:
                self.log_info(f"[指南] 往{direction}找 {i} 次后找到「{item_pattern.pattern}」")
                return box

            if self.list_moved(before, self.list_thumb()):
                stuck_streak = 0
                continue

            # ---- 画面没动：不是边界，是滑动出问题 ----
            if to_bottom and self.at_guide_bottom():
                self.log_info(f"[指南] 已经到底（看到 {GUIDE_LISTBOTTOM}），停止往{direction}找")
                return None
            if not to_bottom and self.at_guide_top():
                self.log_info(f"[指南] 已经到顶（看到 {GUIDE_LISTTOP}），停止往{direction}找")
                return None

            stuck_streak += 1
            self.log_error(
                f"[指南] 往{direction}滑之后画面没有变化，"
                f"但也没看到 {boundary} —— 判定为滑动出问题（手势没生效），"
                f"第 {stuck_streak}/{GUIDE_STUCK_TOLERANCE} 次")
            if stuck_streak >= GUIDE_STUCK_TOLERANCE:
                self.log_error(f"[指南] 连续 {stuck_streak} 次滑不动，放弃往{direction}找")
                return None
            self.sleep(0.5)

        return None

    # ------------------------------------------------------------------
    # OCR 辅助
    # ------------------------------------------------------------------
    def click_below(self, anchor, pattern, time_out=5.0):
        """OCR 找 anchor **正下方**的 pattern 并点击。

        用于「点某个条目正下方的『立刻前往』」这种布局：
        横向取离 anchor 中心最近、纵向必须在 anchor 下沿之下的那一条，
        避免误点到旁边条目的按钮。
        """
        start = time.time()
        while time.time() - start < time_out:
            try:
                boxes = self.ocr(match=[pattern])
            except Exception as e:
                self.log_debug(f"OCR「{pattern}」出错: {e}")
                boxes = None

            if boxes:
                if not isinstance(boxes, list):
                    boxes = [boxes]
                cx = anchor.x + anchor.width / 2
                bottom = anchor.y + anchor.height
                best = None
                best_score = None
                for b in boxes:
                    if not all(hasattr(b, a) for a in ('x', 'y', 'width', 'height')):
                        continue
                    bx = b.x + b.width / 2
                    by = b.y + b.height / 2
                    if by < bottom:
                        continue          # 不在下方，跳过
                    score = (abs(bx - cx), by)
                    if best_score is None or score < best_score:
                        best, best_score = b, score

                if best is not None:
                    px, py = best.x + best.width // 2, best.y + best.height // 2
                    self.log_info(f"点击条目正下方的「{pattern}」({px}, {py})")
                    self.click(px, py)
                    return True
                self.log_debug(f"识别到「{pattern}」但都不在条目下方")
            self.sleep(0.5)
        return False
