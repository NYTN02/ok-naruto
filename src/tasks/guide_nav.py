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

import sys
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

# ---------------------------------------------------------------------------
# 内缩的备用起止线（滑不动时的第二级补救）
#
# 为什么需要：**终点落在哪不重要，但起点必须落在列表的可触摸区域里**，
# 否则这一次拖动根本不会生效。而上面那两条线是两个方向的**起点**分别在
# 0.777 和 0.325 —— 起点位置本来就是不对称的：
#
#   往下找 起点 0.777（列表靠下）  ← 如果列表的可触摸区没到这么低，就整条失效
#   往上找 起点 0.325（列表靠上）  ← 通常落在列表里，所以"看起来正常"
#
# 这正好解释"只有一个方向滑不动"。所以滑不动时，再用一对**内缩**的线补救一次 ——
# 内缩后两个方向的起点都稳稳在列表内部，不会再踩这个坑。
# 注意"内缩"是**往列表中间收**：0.777/0.325 这对线收紧成 0.700/0.400，
# 两端都离列表边缘更远（一开始把 TO 写成 0.300 是往外扩了，方向搞反，被用例拦住）。
# 用户给定的那两条线仍是首选，不会被替换掉。
GUIDE_SCROLL_INNER_FROM_Y = 0.700
GUIDE_SCROLL_INNER_TO_Y = 0.400

# ---------------------------------------------------------------------------
# 条目只可能出现在左侧列表这一列里。
#
# ⚠️ 为什么必须限定区域：``self.ocr()`` 是**全屏**识别的，
#    而「指南」界面右侧有详情/预览面板，里面也会出现条目名称。
#    用户日志实证（2026-10-13）：
#        23:40:18 [指南] OCR 认到「积分赛」  (245, 508)    x=0.096  左侧 ✓
#        23:49:54 [指南] OCR 认到「丰饶之间」(1805, 744)   x=0.705  右侧 ✗
#        23:50:33 ERROR 没能通过指南进入丰饶之间，任务终止
#    也就是它把右侧面板里的同名文字当成了列表条目，点过去当然没反应。
#
#    右侧显示什么内容不由我们控制（跟游戏活动 / 玩家进度有关），
#    所以会出现"第一天能用、后来突然不行"—— 不是程序变了，是界面内容变了。
# ---------------------------------------------------------------------------
# OCR 容错：条目名的**前 N 个字**相同就认。
#
# ⚠️ 为什么需要：OCR 会把形近字认错、也会把长名字截断。实测出现过
#      「小队突袭」-> 「小队突装」(袭/装 形近, 置信度 0.85)
#      「任务集会所」-> 「任务集」  (被截断)
#   这时精确匹配的正则会判"没找到"，然后一路滑到底、白白浪费十几秒，
#   日志里却只写"滑遍都没找到"，极难定位。
#
# 2 个字（用户指定）。注意：前缀越短越容易匹配到别的文字 —— 比如「任务集会所」
# 取「任务」，而指南界面上本来就有一处独立显示「任务」的标签。所以：
#   * 只在**精确匹配失败后**才用前缀（前缀只是兜底，不是首选）
#   * 仍然限定在左侧列表区域内（GUIDE_LIST_HIT_*）
#   * 用前缀匹配到时会记 warning，日志里能看到
#   * 拿到框之后还要点它下方的「前往」才算成功，取错条目那一步也会失败
GUIDE_ENTRY_PREFIX_LEN_SAMPLE = '小队突袭 / 任务集会所 / 丰饶之间 / 积分赛 …'
GUIDE_ENTRY_PREFIX_LEN = 2

# 子类可覆盖：显式指定容错用的前缀（None = 按上面自动推导）
GUIDE_PREFIX_TEXT = None

GUIDE_LIST_HIT_X_MAX = 0.35          # 条目中心 x 超过这个值就认为不是列表条目
GUIDE_LIST_HIT_Y_MIN = 0.10
GUIDE_LIST_HIT_Y_MAX = 0.92

GUIDE_SCROLL_SETTLE = 0.35      # 拖到终点后再按住多久才松开

# ---------------------------------------------------------------------------
# 手势时长：**不同操作路径下含义完全不同**，必须区分
#
# ok-script 的 swipe 有三条路（ok/device/interaction_methods/adb.py:101）：
#
#   ① 原生 IPC（MuMu）：swipe_nemu —— duration 被忽略，靠 settle_time
#                        在终点反复 down 来实现"按住"
#   ② uiautomator2    ：swipe_u2  —— touch.down/move/up + settle_time，也能"按住"
#   ③ 纯 adb          ：``input swipe x1 y1 x2 y2 <ms>``
#                        ★ settle_time 被**完全丢弃**，根本没有"按住"这回事
#
# 我们的手势本来是"按住 -> 拖 -> 终点按住 0.35 秒 -> 松手"：
# 在 ① ② 上是标准拖拽；在 ③ 上退化成"拖完立刻松手"= 一次快速**甩动**，
# 实测这种列表根本不滚 —— 表现就是「指南界面上下滑动失灵」。
#
# 所以 ③ 只能靠**加长 duration** 弥补：拖得慢，系统才当拖拽而不是甩动。
# 打包版没有 uiautomator2（见 requirements.txt），ADB 用户必定走 ③。
GUIDE_SWIPE_DURATION_IPC = 0.5       # ① ②："按住"由 settle_time 负责
GUIDE_SWIPE_DURATION_ADB = 1.5       # ③   ：拉长，避免被当成甩动
GUIDE_SWIPE_DURATION_ADB_SLOW = 2.5  # ③   ：加强版，滑不动时再慢一档
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
GUIDE_LIST_MOVE_THRESHOLD = 2.0
# 判断画面有没有变化用的阈值（整屏缩略图的平均灰度差）。
# 用在领奖流程里：点「可领取」之后要确认画面确实变了，否则不能盲点下一步。
SCREEN_CHANGE_THRESHOLD = 2.0   # 平均灰度差小于这个值就认为"没动"
GUIDE_STUCK_TOLERANCE = 2         # 连续几次滑不动就放弃这个方向

# 各等待时长（秒）
GUIDE_ENTRY_TIMEOUT = 5.0       # 等 main_guide 出现
# 点完 main_guide 之后等多久，再确认"是不是真的进指南了"
GUIDE_ENTRY_VERIFY_WAIT = 1.0
# 「滑不动」时用来冲掉卡住触摸状态的小拖动（见 cleanup_stuck_touch）
GUIDE_CLEANUP_REL = (0.5, 0.45)

# 滑不动时先"点一下列表"再滑（用户建议的做法）。
# 坐标落在指南左侧列表区域内（x=0.106 在 0.05~0.30 之间，y=0.458 在中部），
# 所以这一下点的是列表本身 —— 相当于给列表一次完整的 down+up。
GUIDE_PRESS_REL = (0.106, 0.458)
GUIDE_PRESS_WAIT = 0.3     # 中性位置：不在左侧列表里，避免误点条目
GUIDE_CLEANUP_PX = 30               # 超过触摸阈值，不会被当成点击
GUIDE_CLEANUP_WAIT = 0.4
# ADB 通道清状态时那条 drag 的时长（毫秒）
GUIDE_CLEANUP_ADB_MS = 200
# 点不开就重试几次（见 open_guide 的说明）
GUIDE_ENTRY_ATTEMPTS = 3
GUIDE_OPEN_WAIT = 1.8           # 点开指南后等列表加载
GUIDE_ITEM_TIMEOUT = 3.0        # 等条目/前往按钮出现
GUIDE_ITEM_WAIT = 1.5           # 点条目后等界面切换
GUIDE_GO_TIMEOUT = 5.0
GUIDE_GO_WAIT = 1.8

# 「立刻前往」这类入口文字的匹配（用正则做包含匹配，避免 OCR 多字少字就失配）
DAILY_TASK_PATTERN = re.compile(r'每日任务')

# 「前往」按钮文字。模板认不到时用它兜底。
GO_TEXT_PATTERN = re.compile(r'前往')

# ---------------------------------------------------------------------------
# 进入方式：「忍界指引」（走指南列表）还是「奖励」（走每日任务）
#
# 两条路各有适用场景：指南列表条目标注稳定但有 20+ 项、要上下滑动找；
# 每日任务是横向的少数几张卡，找起来快，而且每张卡自带「立刻前往」。
# 所以做成任务级选项，一键日常也可以统一指定。
#
# 注意：**不是每个任务都在每日任务里**（排行榜就没有），
# 所以只有确实存在的任务才把「奖励」加进选项中。
# ---------------------------------------------------------------------------
ENTRY_MODE_KEY = '进入方式'
ENTRY_MODE_GUIDE = '忍界指引'
ENTRY_MODE_REWARD = '奖励'
# 「奖励」进入方式已停用（实测有问题：左右滑不动、条目定位不稳）。
# 保留常量与 enter_reward 的实现，以后要恢复只需把选项加回来 + 这里改 True。
REWARD_MODE_ENABLED = False

# 走「奖励」（每日任务）时需要的东西
REWARD_ENTRY = 'main_reward'          # 主页面上的每日任务/奖励入口
GO_TEXT = '立刻前往'                   # 条目正下方的按钮文字
# 左右滑动用**固定的两条线**（用户实测指定），不再用"屏幕中央 + 距离"算：
#     往左找（想看列表更左边的内容）：按住 (0.355, 0.378) 滑到 (0.808, 0.368)
#     往右找（想看列表更右边的内容）：按住 (0.808, 0.368) 滑到 (0.355, 0.378)
# 手指方向和内容方向是反的：往左找时手指往**右**拖。
REWARD_SCROLL_LEFT_FROM = (0.355, 0.378)
REWARD_SCROLL_LEFT_TO = (0.808, 0.368)
REWARD_SCROLL_RIGHT_FROM = (0.808, 0.368)
REWARD_SCROLL_RIGHT_TO = (0.355, 0.378)

REWARD_SCROLL_MAX = 8                 # 单向最多滑几次
# 滑动之后等画面停稳再 OCR + 点击（秒）。
# ⚠️ 不能省：横向列表松手后还有惯性滚动，立刻 OCR 拿到的坐标在点下去时
#    已经过期，会点错位置 —— 用户实测就是这个现象。
REWARD_SCROLL_AFTER = 2.0
REWARD_ENTRY_TIMEOUT = 5.0
REWARD_OPEN_WAIT = 1.8
REWARD_DAILY_TASK_ATTEMPTS = 3        # 点「每日任务」的重试次数


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

    def uses_settle_time(self):
        """当前滑动路径是否支持 settle_time（也就是能不能"在终点按住"）。

        见 GUIDE_SWIPE_DURATION_* 的说明：只有 IPC 和 uiautomator2 支持，
        纯 adb 的 ``input swipe`` 会把 settle_time 丢掉。
        """
        interaction = getattr(self.executor, 'interaction', None)
        if interaction is None:
            return False
        capture = getattr(interaction, 'capture', None)
        if capture is not None:
            try:
                from ok.device.capture_methods.nemu_ipc import NemuIpcCaptureMethod
                if isinstance(capture, NemuIpcCaptureMethod):
                    return True
            except Exception:
                pass
        return bool(getattr(interaction, 'use_u2', False))

    def default_swipe_duration(self, slow=False):
        """按当前路径给出合适的 duration（秒）。"""
        if self.uses_settle_time():
            return GUIDE_SWIPE_DURATION_IPC
        return GUIDE_SWIPE_DURATION_ADB_SLOW if slow else GUIDE_SWIPE_DURATION_ADB

    def gesture(self, x1, y1, x2, y2, settle=GUIDE_SCROLL_SETTLE,
                after=GUIDE_SCROLL_AFTER, duration=None):
        """一次完整的「按住 -> 拖动 -> 松开」。

        参数作用随路径而变（见 GUIDE_SWIPE_DURATION_*）：

        * ``settle``   —— 拖到终点后继续按住多久才松手。**只在 IPC / u2 上有效**；
        * ``duration`` —— 拖动本身的时长。IPC 上被忽略；**纯 adb 上这是唯一能
                          影响"被当成拖拽还是甩动"的参数**，所以要按路径取值；
        * ``after``    —— 松手后等多久才继续往下走。它同时是**两次滑动之间的间隔**，
                          必须给足（当前 1 秒），否则列表还在惯性滚动时就去匹配，
                          会出现「明明在画面上却判定没找到」的假失败。
        """
        if duration is None:
            duration = self.default_swipe_duration()
        self.log_info(f"[手势] 按住拖动 ({x1},{y1}) -> ({x2},{y2}) "
                      f"duration={duration}s settle={settle}s 之后等 {after}s")
        self.swipe(x1, y1, x2, y2, duration=duration, settle_time=settle, after_sleep=after)

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

    def scroll_guide(self, to_bottom=True, slow=False, inner=False):
        """在指南列表上滑一次（手势起止点见模块开头的 GUIDE_SCROLL_* 常量）。

        ``to_bottom=True``  -> 想看列表**更下面**的内容：按住 0.777 滑到 0.325
        ``to_bottom=False`` -> 想看列表**更上面**的内容：按住 0.325 滑到 0.777

        手指方向和内容方向是反的，很容易搞混，所以参数按"想看哪边的内容"命名：
        手指往上拖时内容跟着往上走，看到的是更下面的条目。

        ``slow=True``   用更慢的拖动（纯 adb 路径滑不动时靠它补救）。
        ``inner=True``  改用**内缩**的起止线（起点不在列表可触摸区时靠它补救，
                        见 GUIDE_SCROLL_INNER_* 的说明）。
        """
        x = int(self.width * GUIDE_SCROLL_X)
        if inner:
            # 内缩后两个方向都用同一对内边界，起点稳稳在列表里
            if to_bottom:
                y_from = int(self.height * GUIDE_SCROLL_INNER_FROM_Y)
                y_to = int(self.height * GUIDE_SCROLL_INNER_TO_Y)
            else:
                y_from = int(self.height * GUIDE_SCROLL_INNER_TO_Y)
                y_to = int(self.height * GUIDE_SCROLL_INNER_FROM_Y)
        elif to_bottom:
            y_from = int(self.height * GUIDE_SCROLL_DOWN_FROM_Y)
            y_to = int(self.height * GUIDE_SCROLL_DOWN_TO_Y)
        else:
            y_from = int(self.height * GUIDE_SCROLL_UP_FROM_Y)
            y_to = int(self.height * GUIDE_SCROLL_UP_TO_Y)
        self.gesture(x, y_from, x, y_to, duration=self.default_swipe_duration(slow=slow))

    def screen_thumb(self):
        """整屏小灰度缩略图，用来判断"画面有没有变化"。

        和 list_thumb 的区别：那个只看指南左侧列表那一块，这个是整屏 ——
        领奖时的确认框/物品展示界面会在屏幕中间，得看全屏。
        """
        try:
            frame = self.frame
        except Exception as e:
            self.log_debug(f"取画面失败，跳过「有没有变化」判断: {e}")
            return None
        if frame is None:
            return None
        return cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (32, 32)).astype('int16')

    def screen_changed(self, before, after, threshold=SCREEN_CHANGE_THRESHOLD):
        """画面是否有明显变化；拿不到画面时保守地当成"有变化"。"""
        if before is None or after is None:
            return True
        diff = float(np.abs(before - after).mean())
        changed = diff > threshold
        self.log_info(f"[画面] 变化差异 {diff:.2f}（阈值 {threshold}）-> "
                      f"{'有变化' if changed else '没变化'}")
        return changed

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
        """滑动前后列表画面是否明显变化；拿不到画面时保守地当成"动了"。

        差异值用 **info** 级打印（不是 debug）：这是判断"手势有没有生效"的唯一依据，
        用户日志里必须看得到，否则只能靠猜。
        """
        if before is None or after is None:
            return True
        diff = float(np.abs(before - after).mean())
        moved = diff > GUIDE_LIST_MOVE_THRESHOLD
        self.log_info(f"[指南] 滑动前后画面差异 {diff:.2f}"
                      f"（阈值 {GUIDE_LIST_MOVE_THRESHOLD}）-> "
                      f"{'有变化' if moved else '没变化'}")
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

    # ------------------------------------------------------------------
    # 进入方式：忍界指引 / 奖励
    # ------------------------------------------------------------------
    def add_entry_mode_config(self, reward_item_text=None):
        """登记「进入方式」选项。

        :param reward_item_text: 走「奖励」（每日任务）时用来识别条目的文字。
            传 None 表示这个任务在每日任务里**没有**，那就不提供「奖励」选项
            （比如排行榜）—— 免得用户选了以后永远进不去。
        """
        # ⚠️ 「奖励」（每日任务）方式已按要求**停用** —— 实测有问题
        # （左右滑不动、条目定位不稳）。这里仍然收下 reward_item_text 但不使用，
        # 各任务的调用点不用改；以后要恢复只需把下面两行放回来。
        options = [ENTRY_MODE_GUIDE]
        # if reward_item_text:
        #     options.append(ENTRY_MODE_REWARD)
        self.default_config[ENTRY_MODE_KEY] = ENTRY_MODE_GUIDE
        self.config_type[ENTRY_MODE_KEY] = {'type': 'drop_down', 'options': options}
        self.config_description[ENTRY_MODE_KEY] = (
            f'{ENTRY_MODE_GUIDE}：走游戏里的「指南」列表（条目多，要上下滑找）；'
            f'{ENTRY_MODE_REWARD}：走「奖励 → 每日任务」（卡片少，找得快）'
            if len(options) > 1 else
            '这个任务在每日任务里没有，只能走「指南」')

    def supports_entry_mode(self):
        """这个任务是否**真的**登记了「进入方式」选项。

        不能直接 return True —— 组织祈福也继承本类，但它走的是自己那套
        main_reward 流程，并没有登记这个选项。按 config_type 里有没有来判断最准，
        也免得一键日常往一个不认这个键的任务里塞配置。
        """
        return ENTRY_MODE_KEY in getattr(self, 'config_type', {})

    def entry_mode(self):
        return self.config.get(ENTRY_MODE_KEY, ENTRY_MODE_GUIDE)

    def enter_by_mode(self, guide_text, guide_go, reward_item_text=None,
                      item_feature=None):
        """按「进入方式」选项决定走哪条路进入玩法。"""
        mode = self.entry_mode()
        # 「奖励」方式已停用：即使配置里还残留旧值也强制走指南
        if mode == ENTRY_MODE_REWARD and reward_item_text and REWARD_MODE_ENABLED:
            self.log_info(f"进入方式：{ENTRY_MODE_REWARD}（每日任务）")
            return self.enter_reward(reward_item_text)
        self.log_info(f"进入方式：{ENTRY_MODE_GUIDE}（指南列表）")
        return self.enter_guide(guide_text, guide_go, item_feature=item_feature)

    def enter_reward(self, item_text, max_swipes=REWARD_SCROLL_MAX):
        """走「奖励 → 每日任务」进入玩法。

        流程（和组织祈福一样）::

            点 main_reward
              -> OCR 点「每日任务」
              -> 横向左右滑动找条目（OCR 认 item_text）
              -> 点条目**正下方**的「立刻前往」

        每日任务里的条目是横向排列的卡片，所以是左右滑而不是上下滑。
        """
        if not self.is_main_page():
            self.log_info("当前不在主页面，先退回主页面")
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

        if not self.click_feature(REWARD_ENTRY, time_out=REWARD_ENTRY_TIMEOUT):
            self.log_error(f"未找到 {REWARD_ENTRY}，无法走「奖励」进入「{item_text}」")
            return False
        self.sleep(REWARD_OPEN_WAIT)

        # 必须真正点进「每日任务」子页面才能左右滑 —— 用户反馈过"左右滑都没反应"，
        # 原因多半就是这一步没成，滑在了奖励主页上。所以这里给几次重试。
        entered = False
        for attempt in range(1, REWARD_DAILY_TASK_ATTEMPTS + 1):
            if self.click_text(DAILY_TASK_PATTERN, time_out=REWARD_ENTRY_TIMEOUT):
                entered = True
                break
            self.log_warning(f"第 {attempt}/{REWARD_DAILY_TASK_ATTEMPTS} 次没找到"
                             f"「每日任务」，重试")
            self.sleep(1.0)
        if not entered:
            self.log_error(f"点了 {REWARD_DAILY_TASK_ATTEMPTS} 次都没找到「每日任务」，"
                           f"无法走「奖励」进入（左右滑动必须在每日任务页面里做）")
            return False
        self.sleep(REWARD_OPEN_WAIT)

        box = self.find_reward_item(item_text, max_swipes)
        if box is None:
            self.log_warning(f"每日任务里左右滑遍都没找到「{item_text}」")
            self.exit_reward()
            return False

        # 再确认一次画面稳定：box 是刚 OCR 出来的，但列表可能还在微动，
        # 而「立刻前往」是按 anchor 的位置关系找的，anchor 一动就可能点偏
        self.sleep(REWARD_SCROLL_AFTER)
        if not self.click_below(box, GO_TEXT_PATTERN, time_out=REWARD_ENTRY_TIMEOUT):
            self.log_warning(f"没找到「{item_text}」正下方的「{GO_TEXT}」")
            self.exit_reward()
            return False
        self.sleep(REWARD_OPEN_WAIT)
        self.log_info(f"已通过「奖励」进入「{item_text}」")
        return True

    def find_reward_item(self, item_text, max_swipes=REWARD_SCROLL_MAX):
        """在每日任务列表里左右滑动找条目，返回 Box 或 None。

        先往左拖（看右边的内容），再往右拖（看回左边）。
        """
        pattern = re.compile(re.escape(item_text))
        box = self.find_reward_item_on_screen(pattern)
        if box is not None:
            self.log_info(f"[每日任务] 当前画面已看到「{item_text}」")
            return box

        # 先往右找（列表一般从左端开始，目标多半在右边），再折返往左找
        for i in range(1, max_swipes + 1):
            if self.should_stop('每日任务滑动'):
                return None
            self.log_info(f"[每日任务] 往右找 {i}/{max_swipes}：「{item_text}」")
            self.scroll_reward(to_left=False)
            self.sleep(REWARD_SCROLL_AFTER)      # 等画面停稳，否则会点错位置
            box = self.find_reward_item_on_screen(pattern)
            if box is not None:
                self.log_info(f"[每日任务] 往右找 {i} 次后找到「{item_text}」")
                return box

        for i in range(1, max_swipes * 2 + 1):
            if self.should_stop('每日任务滑动'):
                return None
            self.log_info(f"[每日任务] 往左找 {i}/{max_swipes * 2}：「{item_text}」")
            self.scroll_reward(to_left=True)
            self.sleep(REWARD_SCROLL_AFTER)      # 同上
            box = self.find_reward_item_on_screen(pattern)
            if box is not None:
                self.log_info(f"[每日任务] 往左找 {i} 次后找到「{item_text}」")
                return box
        return None

    def find_reward_item_on_screen(self, pattern):
        """当前画面 OCR 找每日任务条目。"""
        try:
            boxes = self.ocr(match=[pattern])
        except Exception as e:
            self.log_debug(f"OCR 找「{pattern.pattern}」出错: {e}")
            boxes = None
        if boxes:
            if not isinstance(boxes, list):
                boxes = [boxes]
            for box in boxes:
                if all(hasattr(box, a) for a in ('x', 'y', 'width', 'height')):
                    self.log_info(f"[每日任务] OCR 认到「{pattern.pattern}」"
                                  f"({box.x}, {box.y})")
                    return box
        return None

    def scroll_reward(self, to_left=True):
        """在「奖励 → 每日任务」页面上左右滑一次（固定起止线）。

        ``to_left=True``  想看**更左边**的内容：按住 (0.355,0.378) 滑到 (0.808,0.368)
        ``to_left=False`` 想看**更右边**的内容：按住 (0.808,0.368) 滑到 (0.355,0.378)

        手指方向和内容方向是反的，所以参数按"想看哪边的内容"命名 ——
        和指南那边（to_bottom）保持同一套习惯，免得又搞反。
        """
        if to_left:
            (fx, fy), (tx, ty) = REWARD_SCROLL_LEFT_FROM, REWARD_SCROLL_LEFT_TO
        else:
            (fx, fy), (tx, ty) = REWARD_SCROLL_RIGHT_FROM, REWARD_SCROLL_RIGHT_TO
        self.gesture(int(self.width * fx), int(self.height * fy),
                     int(self.width * tx), int(self.height * ty),
                     duration=self.default_swipe_duration())

    def exit_reward(self):
        """点 reward_cancel / popu_cancel 退出每日任务界面。"""
        for name in ('reward_cancel', 'popu_cancel'):
            if self.click_feature(name, time_out=2.0):
                self.log_info(f"已点击 {name} 退出每日任务")
                self.sleep(1.0)
                return
        if not self.is_main_page():
            self.back_to_main(max_rounds=12, interval=0.8, log=False)

    def cleanup_stuck_touch(self):
        """滑不动时的补救：**先在列表上点一下**（用户建议），再走兜底拖动。

        当前顺序：
          ① 点一下 rel(0.106, 0.458)（落在指南左侧列表内）—— 用户建议
          ② 兜底：ADB 通道 `input swipe` 小拖动
          ③ 再兜底：IPC 通道小拖动

        历史（为什么变成现在这样）：

        为什么换通道（测试版本日志2.txt 实测）::

            [往下找] 第 1/5 次：画面差异 0.000  指纹 118974 -> 118974
            [指南] 补一次小拖动…（IPC 注入）
            [往下找] ✗ 清理手势没用，指纹 118974 -> 118974

        IPC 版本的小拖动**同样被吞掉** —— 说明那一刻 MuMu 的原生注入通道整体失效，
        而用户手动滑一下能恢复。所以这里改用 `adb shell input swipe`：
        它走 adbd / Android 输入系统，和原生 IPC 注入是两条独立的路。

        * 仍然用**小拖动**而不是点击 —— 位移超过触摸阈值，不会被当成点击
        * 起点在中性位置（不在左侧列表里），避免误触条目
        * 拿不到 device_manager.shell 时退回 IPC 版本（聊胜于无）
        """
        # ★ 第一步（用户建议）：先在列表上**点一下**，再靠调用方去滑。
        # 点击 = 一次完整的 down + up，比拖动更"干净"；
        # 而实测拖动（含 ADB 通道）都无效，所以换成点击试试。
        px = int(self.width * GUIDE_PRESS_REL[0])
        py = int(self.height * GUIDE_PRESS_REL[1])
        try:
            self.log_info(f"[指南] 先在列表上点一下 rel{GUIDE_PRESS_REL}"
                          f"（{px},{py}）再滑 —— 试试能不能解开卡住的触摸状态")
            self.click(px, py)
            self.sleep(GUIDE_PRESS_WAIT)
            self.reset_scene()      # 让下一步取到新画面，别用点击前的旧帧
        except Exception as e:
            self.log_debug(f"点列表失败（继续后面的兜底）: {e}")

        x = int(self.width * GUIDE_CLEANUP_REL[0])
        y = int(self.height * GUIDE_CLEANUP_REL[1])
        y2 = y - GUIDE_CLEANUP_PX

        sent = False
        try:
            # ⚠️ 必须把整条命令当**一个字符串**传：BaseDevice.shell() 只收
            # 2~6 个位置参数，拆成 7 个会 TypeError（上次就是这么静默退回 IPC 的）。
            cmd = f'input swipe {x} {y} {x} {y2} {GUIDE_CLEANUP_ADB_MS}'
            self.executor.device_manager.shell(cmd)
            sent = True
            self.log_info(f"[指南] 已用 **ADB 通道**发一次小拖动清状态: {cmd}")
        except Exception as e:
            self.log_warning(f"[指南] ADB 通道清状态失败（{e}），退回 IPC 版本")

        if not sent:
            try:
                self.gesture(x, y, x, y2, duration=0.2)
                self.log_info("[指南] 已用 IPC 通道发一次小拖动清状态")
            except Exception as e:
                self.log_debug(f"清状态手势也失败（不影响后续）: {e}")

        self.sleep(GUIDE_CLEANUP_WAIT)

    def open_guide(self, attempts=GUIDE_ENTRY_ATTEMPTS):
        """点开「指南」，并**确认真的进入了指南界面**。

        为什么要确认：实测出现过"报已点击，但界面根本没换"的情况 ——
        那时后面所有滑动都在**主页面左侧那一列图标**上做，永远找不到条目，
        而且日志看起来一切正常（手势、画面差异都有），极难排查。

        判据（用户提出）：点完等 GUIDE_ENTRY_VERIFY_WAIT，如果**还能看到
        main_guide**（它是主页面上的指南入口图标，进了指南界面就看不到它了），
        说明还停在主页面 -> 这次没点开 -> 重试。

        这样"进入失败"会在**最外层就被发现**，不会再让后续步骤白跑。
        """
        for i in range(1, attempts + 1):
            if self.should_stop('打开指南'):
                return False
            if not self.click_feature(GUIDE_ENTRY, time_out=GUIDE_ENTRY_TIMEOUT):
                self.log_error(f"未找到 {GUIDE_ENTRY}")
                return False
            self.sleep(GUIDE_ENTRY_VERIFY_WAIT)
            if self._safe_find_one(GUIDE_ENTRY) is None:
                self.log_info(f"已进入指南界面（第 {i} 次尝试）")
                self.sleep(GUIDE_OPEN_WAIT)
                return True
            self.log_warning(f"第 {i}/{attempts} 次点了 {GUIDE_ENTRY} 但还是停在主页面"
                             f"（还能看到 {GUIDE_ENTRY}），进入指南失败，重试")
            self.sleep(0.5)
        self.log_error(f"连续 {attempts} 次都没能进入指南界面")
        return False

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

        # 2. 点开指南（**必须确认真的进去了**）
        if not self.open_guide():
            self.log_error(f"没能进入指南界面，无法通过指南进入「{item_text}」")
            return False

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

    def _entry_patterns(self, item_pattern):
        """返回要尝试的匹配模式：先精确，再前缀容错。

        前缀容错是为了对付 OCR 把形近字认错（小队突袭 -> 小队突装）
        和把长名字截断（任务集会所 -> 任务集）。见 GUIDE_ENTRY_PREFIX_LEN。
        """
        patterns = [item_pattern]

        # 子类可以显式指定容错用的前缀（GUIDE_PREFIX_TEXT）：
        # 有些条目的自动 2 字前缀会撞上界面上别的文字，必须手动指定。
        # 先看类属性，再看**任务所在模块**的同名常量
        # （本项目的任务常量都写在模块级，例如 mission_task.GUIDE_PREFIX_TEXT）。
        explicit = getattr(self, 'GUIDE_PREFIX_TEXT', None)
        if explicit is None:
            mod = sys.modules.get(type(self).__module__)
            explicit = getattr(mod, 'GUIDE_PREFIX_TEXT', None)
        if explicit is not None:
            if explicit and explicit != item_pattern.pattern:
                patterns.append(re.compile(re.escape(explicit)))
            return patterns

        plain = re.sub(r'[^\w\u4e00-\u9fff]', '', item_pattern.pattern)
        if len(plain) >= GUIDE_ENTRY_PREFIX_LEN:
            prefix = plain[:GUIDE_ENTRY_PREFIX_LEN]
            if prefix != item_pattern.pattern:
                patterns.append(re.compile(re.escape(prefix)))
        return patterns

    def _find_entry_by_ocr(self, pattern):
        """按一个模式在左侧列表区域里找条目，返回 Box 或 None。"""
        try:
            boxes = self.ocr(match=[pattern])
        except Exception as e:
            self.log_debug(f"OCR 找条目出错: {e}")
            return None
        if not boxes:
            return None
        if not isinstance(boxes, list):
            boxes = [boxes]
        width = getattr(self, 'width', 0) or 1
        height = getattr(self, 'height', 0) or 1
        rejected = []
        for box in boxes:
            if not all(hasattr(box, a) for a in ('x', 'y', 'width', 'height')):
                continue
            cx = (box.x + box.width / 2) / width
            cy = (box.y + box.height / 2) / height
            if (cx <= GUIDE_LIST_HIT_X_MAX
                    and GUIDE_LIST_HIT_Y_MIN <= cy <= GUIDE_LIST_HIT_Y_MAX):
                return box
            rejected.append((box.x, box.y, round(cx, 3)))
        if rejected:
            self.log_warning(f"[指南] OCR 认到「{pattern.pattern}」但都不在"
                             f"左侧列表区域内（x 上限 {GUIDE_LIST_HIT_X_MAX}）："
                             f"{rejected}，忽略")
        return None

    def find_entry_on_screen(self, item_pattern, templates):
        """在当前画面里找条目：先 OCR 文字（含前缀容错），再退回模板。

        OCR 是全屏的，所以只在左侧列表区域里认（见 GUIDE_LIST_HIT_*）；
        精确匹配失败时用前缀再试一次（对付形近字认错和名字截断）。
        """
        patterns = self._entry_patterns(item_pattern)
        for i, pattern in enumerate(patterns):
            box = self._find_entry_by_ocr(pattern)
            if box is not None:
                if i > 0:
                    self.log_warning(f"[指南] 精确匹配没找到「{item_pattern.pattern}」，"
                                     f"用前缀「{pattern.pattern}」容错匹配到了"
                                     f"（多半是 OCR 认错字或截断了）")
                self.log_info(f"[指南] OCR 认到「{pattern.pattern}」"
                              f"({box.x}, {box.y}) 在列表区域内")
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
        画面没动又没有边界标志 => 判定为滑动出问题。

        "滑不动"会分三级处理，不会一次就放弃：

          1. 先用**更慢**的拖动补救一次（纯 adb 路径下，"拖太快被当成甩动"
             是最常见的原因，见 GUIDE_SWIPE_DURATION_*）
          2. 仍不动才计入 stuck_streak
          3. 连续 ``GUIDE_STUCK_TOLERANCE`` 次才放弃这个方向
        """
        direction = '下' if to_bottom else '上'
        boundary = GUIDE_LISTBOTTOM if to_bottom else GUIDE_LISTTOP
        stuck_streak = 0
        slow_retry_used = False      # 每个方向只做一次"慢速拖动"补救
        inner_retry_used = False     # 每个方向只做一次"换另一条起止线"补救
        inner_mode = False           # 当前用哪条线（换线生效后一直用它）

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
            self.scroll_guide(to_bottom=to_bottom, inner=inner_mode)

            box = self.find_entry_on_screen(item_pattern, templates)
            if box is not None:
                self.log_info(f"[指南] 往{direction}找 {i} 次后找到「{item_pattern.pattern}」")
                return box

            if self.list_moved(before, self.list_thumb()):
                stuck_streak = 0
                continue

            # ---- 画面没动：先确认边界 ----
            if to_bottom and self.at_guide_bottom():
                self.log_info(f"[指南] 已经到底（看到 {GUIDE_LISTBOTTOM}），停止往{direction}找")
                return None
            if not to_bottom and self.at_guide_top():
                self.log_info(f"[指南] 已经到顶（看到 {GUIDE_LISTTOP}），停止往{direction}找")
                return None

            # ---- 不是边界：两级补救，都失败才计入 stuck ----
            #
            # 补救阶梯（每级只做一次）：
            #   ① 更慢的拖动 —— 纯 adb 的 input swipe 会丢掉 settle_time，
            #      "拖太快被当成甩动"是最常见的失效原因
            #   ② 内缩的起止线 —— 起点可能没落在列表的可触摸区里
            #      （往下找的起点 0.777 尤其可疑，见 GUIDE_SCROLL_INNER_*）
            if not slow_retry_used and not self.uses_settle_time():
                slow_retry_used = True
                self.log_warning(
                    f"[指南] 往{direction}滑之后画面没动，且当前是纯 adb 操作"
                    f"（不支持 settle_time），改用更慢的拖动"
                    f"（{GUIDE_SWIPE_DURATION_ADB_SLOW}s）补救一次")
                before = self.list_thumb()
                self.scroll_guide(to_bottom=to_bottom, slow=True)
                box = self.find_entry_on_screen(item_pattern, templates)
                if box is not None:
                    self.log_info(f"[指南] 慢速拖动后找到「{item_pattern.pattern}」")
                    return box
                if self.list_moved(before, self.list_thumb()):
                    self.log_info("[指南] 慢速拖动生效了，继续正常滑动")
                    stuck_streak = 0
                    continue
                self.log_warning("[指南] 慢速拖动也没能让画面变化")

            if not inner_retry_used:
                inner_retry_used = True
                # ★ 换成**另一条**起止线再试（用户实测：换线能立刻恢复）
                new_inner = not inner_mode
                new_name = '内缩线' if new_inner else '用户线'
                self.log_warning(
                    f"[指南] 往{direction}滑不动 —— 换成另一条起止线「{new_name}」再试"
                    f"（用户实测：换线往往就能滑）")
                before = self.list_thumb()
                self.scroll_guide(to_bottom=to_bottom, inner=new_inner)
                box = self.find_entry_on_screen(item_pattern, templates)
                if box is not None:
                    self.log_info(f"[指南] 换线后找到「{item_pattern.pattern}」")
                    return box
                if self.list_moved(before, self.list_thumb()):
                    self.log_info(f"[指南] 换成「{new_name}」生效了，"
                                  f"后面一直用这条线滑动")
                    inner_mode = new_inner     # 之后都用这条线，不再换回去
                    stuck_streak = 0
                    continue
                self.log_warning(f"[指南] 换成「{new_name}」也没能让画面变化")

            stuck_streak += 1
            # 仍然按用户当初的要求"判定为滑动出问题"（不能悄悄当成到头了），
            # 但级别用 warning —— 实测更常见的原因是"这个方向本来就已经到头"：
            # 指南列表**不保证一打开就停在顶部**，初始位置跟账号状态有关。
            # 用户日志里就能看到同一个人两次运行，一次一打开就认出「忍具锻造」
            # （=已经在底部），另一次没有。所以报 ERROR 会把人吓到以为坏了。
            self.log_warning(
                f"[指南] 往{direction}滑之后画面没有变化，也没看到 {boundary} —— "
                f"判定为滑动出问题（手势没生效），第 {stuck_streak}/{GUIDE_STUCK_TOLERANCE} 次；"
                f"也可能是这个方向本来就已经到头")
            if stuck_streak >= GUIDE_STUCK_TOLERANCE:
                self.log_warning(f"[指南] 放弃往{direction}找（换另一个方向继续找，"
                                 f"两边都扫过才算找遍整个列表）")
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
