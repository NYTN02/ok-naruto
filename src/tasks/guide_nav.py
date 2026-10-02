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

from src.tasks.page_nav import PageNavTask

# ---------------------------------------------------------------------------
# 指南
# ---------------------------------------------------------------------------
GUIDE_ENTRY = 'main_guide'      # 主页面上的「指南」入口
GUIDE_CANCEL = 'guide_cancel'   # 指南里的关闭按钮

# 列表两端各有一个"到头了"的标志物，用来判断还能不能往那个方向滑：
#   guide_listtop    可见 => 已经在列表最顶端，再往顶部滑是白费（手指往下拖）
#   guide_listbottom 可见 => 已经在列表最底部，再往底部滑是白费（手指往上拖）
GUIDE_LISTTOP = 'guide_listtop'
GUIDE_LISTBOTTOM = 'guide_listbottom'

# 在指南列表上滑动的锚点（相对坐标）。列表固定在屏幕左侧那一列，
# 用固定锚点比全屏乱滑稳。
GUIDE_SCROLL_X = 0.090
GUIDE_SCROLL_Y = 0.520

# 每次拖动的距离（相对屏幕高度）。
#
# ⚠️ 这个值必须保证**起点和终点都落在列表范围内**，否则手指会滑出列表区域、
#    手势不生效（实测过：0.35 时终点分别到 0.170 / 0.870，而列表实际范围是
#    0.162 ~ 0.828 —— 两端都出界了，往下拖那次基本没反应）。
#    列表范围是按标注量出来的：
#        guide_listtop     rel y = 0.162
#        guide_listbottom  rel y = 0.828
#    锚点在 0.520，理论上限是 min(0.520-0.162, 0.828-0.520) = 0.308，
#    再留点余量取 0.24 => 终点 0.280 / 0.760，稳稳在列表内。
GUIDE_SCROLL_DISTANCE = 0.24
GUIDE_SCROLL_SETTLE = 0.35      # 拖到终点后再按住多久才松开
GUIDE_SCROLL_AFTER = 0.6        # 松手后等列表停稳
GUIDE_SCROLL_MAX = 10           # 单向最多滑几次

# 各等待时长（秒）
GUIDE_ENTRY_TIMEOUT = 5.0       # 等 main_guide 出现
GUIDE_OPEN_WAIT = 1.8           # 点开指南后等列表加载
GUIDE_ITEM_TIMEOUT = 3.0        # 等条目/前往按钮出现
GUIDE_ITEM_WAIT = 1.5           # 点条目后等界面切换
GUIDE_GO_TIMEOUT = 5.0
GUIDE_GO_WAIT = 1.8

# 「立刻前往」这类入口文字的匹配（用正则做包含匹配，避免 OCR 多字少字就失配）
DAILY_TASK_PATTERN = re.compile(r'每日任务')


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
        真正起作用的是 ``settle``（拖到终点后继续按住多久才松手）。
        """
        self.log_info(f"[手势] 按住拖动 ({x1},{y1}) -> ({x2},{y2}) "
                      f"settle={settle}s")
        self.swipe(x1, y1, x2, y2, duration=0.5, settle_time=settle, after_sleep=after)

    # ------------------------------------------------------------------
    # 指南列表
    # ------------------------------------------------------------------
    def at_guide_top(self):
        """是否已经在指南列表最顶端（看到 guide_listtop）。"""
        self._warn_if_bounds_features_missing()
        return self._safe_find_one(GUIDE_LISTTOP) is not None

    def at_guide_bottom(self):
        """是否已经在指南列表最底部（看到 guide_listbottom）。"""
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
        """在指南列表上滑一次（锚点 rel 0.090, 0.520）。

        ``to_bottom=True``  -> 想看列表**更下面**的内容：手指**往上**拖
        ``to_bottom=False`` -> 想看列表**更上面**的内容：手指**往下**拖

        手指方向和内容方向是反的，很容易搞混，所以参数按"想看哪边的内容"命名：
        手指往下拖时内容跟着往下走，看到的是更上面的条目
        （用户描述的「按住往下滑动（滚动向上的意思）」就是这个方向）。
        """
        x = int(self.width * GUIDE_SCROLL_X)
        y_from = int(self.height * GUIDE_SCROLL_Y)
        # 想看更下面 => 手指往上 => 终点 y 更小
        delta = -GUIDE_SCROLL_DISTANCE if to_bottom else GUIDE_SCROLL_DISTANCE
        y_to = int(self.height * (GUIDE_SCROLL_Y + delta))
        self.gesture(x, y_from, x, y_to)

    def find_in_guide(self, feature, max_swipes=GUIDE_SCROLL_MAX):
        """在指南列表里上下滑动找 feature，找到返回它的 Box，否则 None。

        先往下找（列表通常从上面开始），再往回往上找。
        每一轮滑之前先看指南两端有没有到头：

          * 看到 guide_listbottom => 已经在最底部，往下的方向再滑也没用，直接收手
          * 看到 guide_listtop    => 已经在最顶端，往上的方向再滑也没用，直接收手

        没有这个判断的话，到了边界还会一直空滑到次数上限：既浪费时间，
        又会因为反复拖动让列表来回弹、更难定位。
        """
        box = self._safe_find_one(feature)
        if box is not None:
            self.log_info(f"[指南] 当前画面已看到 {feature}")
            return box

        # ---- 往下找：手指往上拖 ----
        for i in range(1, max_swipes + 1):
            if self.at_guide_bottom():
                self.log_info(f"[指南] 已经到底（看到 {GUIDE_LISTBOTTOM}），停止往下找")
                break
            self.log_info(f"[指南] 往下找 {i}/{max_swipes}：{feature}")
            self.scroll_guide(to_bottom=True)
            box = self._safe_find_one(feature)
            if box is not None:
                self.log_info(f"[指南] 往下找 {i} 次后找到 {feature}")
                return box

        # ---- 往回往上找：手指往下拖 ----
        for i in range(1, max_swipes * 2 + 1):
            if self.at_guide_top():
                self.log_info(f"[指南] 已经到顶（看到 {GUIDE_LISTTOP}），停止往上找")
                break
            self.log_info(f"[指南] 往上找 {i}/{max_swipes * 2}：{feature}")
            self.scroll_guide(to_bottom=False)
            box = self._safe_find_one(feature)
            if box is not None:
                self.log_info(f"[指南] 往上找 {i} 次后找到 {feature}")
                return box

        return None

    def exit_guide(self):
        """点 guide_cancel 退回主页面。"""
        if self.click_feature(GUIDE_CANCEL, time_out=GUIDE_ITEM_TIMEOUT):
            self.log_info(f"已点击 {GUIDE_CANCEL} 退出指南")
            self.sleep(1.2)
        else:
            self.log_warning(f"没找到 {GUIDE_CANCEL}，改用通用方式退回主页面")
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    def enter_guide(self, item_feature, go_feature, max_swipes=GUIDE_SCROLL_MAX):
        """走「指南」进入某个玩法：点指南 -> 滑到条目 -> 点条目 -> 点「前往」。

        任何一步失败都会点 guide_cancel 退回主页面再返回 False，
        让调用方干净地放弃这个任务，而不是停在半路。

        :param item_feature: 指南列表里的条目模板，如 'guide_mission'
        :param go_feature:   点完条目后出现的「前往」按钮模板，如 'guide_missiongo'
        """
        # 1. main_guide 在主界面上，先确保在主页
        if not self.is_main_page():
            self.log_info("当前不在主页面，先退回主页面")
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

        # 2. 点开指南
        if not self.click_feature(GUIDE_ENTRY, time_out=GUIDE_ENTRY_TIMEOUT):
            self.log_error(f"未找到 {GUIDE_ENTRY}，无法通过指南进入 {item_feature}")
            return False
        self.sleep(GUIDE_OPEN_WAIT)

        # 3. 滑动找条目
        if self.find_in_guide(item_feature, max_swipes) is None:
            self.log_warning(f"指南里滑遍都没找到 {item_feature}")
            self.exit_guide()
            return False

        # 4. 点条目
        if not self.click_feature(item_feature, time_out=GUIDE_ITEM_TIMEOUT):
            self.log_warning(f"点击 {item_feature} 失败")
            self.exit_guide()
            return False
        self.sleep(GUIDE_ITEM_WAIT)

        # 5. 点「前往」
        if not self.click_feature(go_feature, time_out=GUIDE_GO_TIMEOUT):
            self.log_warning(f"没找到 {go_feature}（{item_feature} 的「前往」按钮）")
            self.exit_guide()
            return False
        self.sleep(GUIDE_GO_WAIT)

        self.log_info(f"已通过指南进入 {item_feature}")
        return True

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
