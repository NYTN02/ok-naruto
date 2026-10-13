"""指南列表滑动测试：单独测「往下找」和「往上找」，看哪个方向真的能滚。

为什么需要这个任务
------------------
用户反馈「往下找失效、往上找正常」，但两个方向的手势参数在代码里是**对称的**
（同 x、同距离 0.452、同 duration / settle），光看代码定不了因。
可能的候选有：
  * 起点位置：往下找按在 0.777（很靠下），往上找按在 0.325 —— 起点本来就不对称。
    终点落在哪不重要，但**起点必须落在列表的可触摸区域里**，否则这次拖动不生效。
  * 阈值偏高：「画面有没有动」是靠一张 32x32 灰度缩略图的平均差判断的
    （阈值 GUIDE_LIST_MOVE_THRESHOLD = 2.0）。小幅度滚动可能只有 0.5 左右，
    会被误判成"没动"。
  * 截图/操作路径：纯 adb 的 input swipe 会丢掉 settle_time。

这个任务**不做任何导航** —— 前提是你已经手动打开「指南」界面。
这样同一个界面就能连着跑几组参数（用户线 / 内缩线），不用每次来回点。

它把两个方向**拆开单独跑**，每次滑动后打印**画面差异实际数值**，
一眼就能区分上面三种：
    差异值很大（>2）      -> 手势生效，问题在别处（比如找不到条目本身）
    差异值 0.3~2          -> 手势生效但**被阈值判成没动** -> 阈值定高了
    差异值 ≈ 0            -> 手势真的没生效 -> 起点位置或操作路径问题

配置
----
  测试方向        往下找 / 往上找 / 两个都测
  起止线          用户线（0.777/0.325）/ 内缩线（0.700/0.400）
  每个方向滑几次  默认 5
  滑动间隔(秒)    默认 1.5
"""

from src.tasks.guide_nav import (
    GUIDE_CANCEL,
    GUIDE_SCROLL_DOWN_FROM_Y,
    GUIDE_SCROLL_DOWN_TO_Y,
    GUIDE_SCROLL_INNER_FROM_Y,
    GUIDE_SCROLL_INNER_TO_Y,
    GUIDE_SCROLL_UP_FROM_Y,
    GUIDE_SCROLL_UP_TO_Y,
    GUIDE_SCROLL_X,
    GuideNavTask,
)

DIRECTION_DOWN = '往下找'
DIRECTION_UP = '往上找'
DIRECTION_BOTH = '两个都测'
DIRECTIONS = [DIRECTION_BOTH, DIRECTION_DOWN, DIRECTION_UP]

LINE_USER = '用户线'
LINE_INNER = '内缩线'
LINES = [LINE_USER, LINE_INNER]


class DebugGuideScrollTask(GuideNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "指南滑动测试"
        self.description = ("在「指南」界面里单独测上下滑动，"
                            "打印每次滑动前后的画面差异，用来定位手势失效")
        self.default_config.update({
            '测试方向': DIRECTION_BOTH,
            '起止线': LINE_USER,
            '每个方向滑几次': 5,
            '滑动间隔(秒)': 1.5,
        })
        self.config_type.update({
            # ⚠️ drop_down 必须带 options —— ok-script 的 ConfigItemFactory 里是
            # `LabelAndDropDown(config_desc, the_type['options'], ...)`，少了这个键
            # 会抛 KeyError: 'options'。而任务配置是在**主窗口初始化**时构建的，
            # 所以一个坏的 config_type 会让**整个程序起不来**（不是只坏这个任务）。
            # 已经加用例 test_config_types_are_valid 守住这类错误。
            '测试方向': {'type': 'drop_down', 'options': list(DIRECTIONS)},
            '起止线': {'type': 'drop_down', 'options': list(LINES)},
        })
        self.config_description.update({
            '测试方向': '单独测哪个方向；「两个都测」会先测往下、再测往上',
            '起止线': (f'{LINE_USER} = {GUIDE_SCROLL_DOWN_FROM_Y}/{GUIDE_SCROLL_DOWN_TO_Y}；'
                       f'{LINE_INNER} = {GUIDE_SCROLL_INNER_FROM_Y}/{GUIDE_SCROLL_INNER_TO_Y}'
                       f'（起点更靠列表中间）'),
            '每个方向滑几次': '每个方向连续滑几次；次数多一点才看得出趋势',
            '滑动间隔(秒)': '两次滑动之间等多久，列表惯性滚动需要时间',
        })

    # ------------------------------------------------------------------
    def run(self):
        self.log_info("=== 指南滑动测试开始 ===")
        self.log_info("前提：**请先手动打开「指南」界面再运行本任务** —— "
                      "它不做任何导航（不回主页面、不点指南入口、结束时也不退出），"
                      "这样同一个界面可以连着测几组参数")
        self.log_info("结果怎么看：差异值 >2 手势生效；0.3~2 说明动了但被阈值判成没动；"
                      "≈0 才是真的没生效")

        if not self._looks_like_guide_page():
            self.log_warning(f"没看到 {GUIDE_CANCEL}，当前可能不在「指南」界面 —— "
                             f"滑动可能落在别的地方。仍然继续执行，请自行核对画面")

        to_test = self._directions_to_test()
        summary = []
        for to_bottom in to_test:
            summary.append(self._test_one_direction(to_bottom))
        self._print_summary(summary)

        self.log_info("=== 指南滑动测试结束（界面保持原样，方便再跑一组）===")

    # ------------------------------------------------------------------
    def _looks_like_guide_page(self):
        """轻量判断当前是不是在指南界面（看到 guide_cancel 就算）。

        只是提醒，不会拦住任务 —— 万一模板认不出来也不该让测试跑不了。
        """
        try:
            return self._safe_find_one(GUIDE_CANCEL) is not None
        except Exception:
            return False

    def _directions_to_test(self):
        choice = self.config.get('测试方向', DIRECTION_BOTH)
        if choice == DIRECTION_DOWN:
            return [True]
        if choice == DIRECTION_UP:
            return [False]
        return [True, False]

    def _test_one_direction(self, to_bottom):
        """测一个方向，返回 (方向名, 平均差异, 最大差异, 次数)。"""
        direction = '往下找' if to_bottom else '往上找'
        inner = self.config.get('起止线', LINE_USER) == LINE_INNER
        times = int(self.config.get('每个方向滑几次', 5) or 5)
        interval = float(self.config.get('滑动间隔(秒)', 1.5) or 1.5)

        if inner:
            from_y = GUIDE_SCROLL_INNER_FROM_Y if to_bottom else GUIDE_SCROLL_INNER_TO_Y
            to_y = GUIDE_SCROLL_INNER_TO_Y if to_bottom else GUIDE_SCROLL_INNER_FROM_Y
            line_name = LINE_INNER
        else:
            from_y = GUIDE_SCROLL_DOWN_FROM_Y if to_bottom else GUIDE_SCROLL_UP_FROM_Y
            to_y = GUIDE_SCROLL_DOWN_TO_Y if to_bottom else GUIDE_SCROLL_UP_TO_Y
            line_name = LINE_USER

        self.log_info(f"----- 开始测试「{direction}」-----")
        self.log_info(f"起止线：{line_name}  x={GUIDE_SCROLL_X}  "
                      f"y {from_y} -> {to_y}"
                      f"（{int(self.height * from_y)} -> {int(self.height * to_y)}）")
        self.log_info(f"当前路径支持 settle_time：{self.uses_settle_time()}"
                      f"（False = 纯 adb，settle_time 会被丢掉）")

        diffs = []
        for i in range(1, times + 1):
            if self.should_stop('指南滑动测试'):
                break
            if to_bottom and self.at_guide_bottom():
                self.log_info(f"[{direction}] 第 {i} 次前已到底（OCR/模板判到底部），"
                              f"先停 —— 这不是手势问题")
                break
            if not to_bottom and self.at_guide_top():
                self.log_info(f"[{direction}] 第 {i} 次前已到顶（OCR/模板判到顶部），"
                              f"先停 —— 这不是手势问题")
                break

            before = self.list_thumb()
            # 直接用底层手势，不走 _sweep_entry 的补救逻辑 ——
            # 这里要测的是"这一种手势本身行不行"，加了补救就看不清了
            self.scroll_guide(to_bottom=to_bottom, inner=inner)
            after = self.list_thumb()
            diff = self.diff_value(before, after)
            diffs.append(diff)
            self.log_info(f"[{direction}] 第 {i}/{times} 次：画面差异 {diff:.3f}")
            self.sleep(interval)

        if not diffs:
            self.log_warning(f"[{direction}] 一次都没滑成（可能已在列表端点）")
            return direction, None, None, 0
        avg = sum(diffs) / len(diffs)
        self.log_info(f"[{direction}] 小结：{len(diffs)} 次，平均差异 {avg:.3f}，"
                      f"最大 {max(diffs):.3f}")
        return direction, avg, max(diffs), len(diffs)

    def diff_value(self, before, after):
        """算两张缩略图的平均绝对差（和 list_moved 用的是同一个量）。

        这里**只打印数值、不做判定**：测试任务的目的就是看真实数字。
        """
        import numpy as np
        if before is None or after is None:
            return -1.0
        return float(np.abs(before - after).mean())

    def _print_summary(self, summary):
        self.log_info("===== 指南滑动测试结果 =====")
        for direction, avg, mx, count in summary:
            if avg is None:
                self.log_info(f"  {direction}: 没滑成（0 次）—— 可能已经在列表端点")
                continue
            if avg > 2.0:
                verdict = "手势生效"
            elif avg > 0.3:
                verdict = "疑似生效但被阈值(2.0)判成没动"
            else:
                verdict = "手势没生效"
            self.log_info(f"  {direction}: {count} 次，平均差异 {avg:.3f}，"
                          f"最大 {mx:.3f} -> {verdict}")
        self.log_info("说明：起点必须落在列表的可触摸区域里，否则整次拖动不生效。"
                      "若「往下找」≈0 而「往上找」正常，试试把起止线换成「内缩线」再测一次。")
