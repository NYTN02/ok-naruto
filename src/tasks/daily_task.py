"""一键日常：按固定顺序把已实现的日常任务全部跑一遍。

顺序（按日常习惯排的，和勾选顺序无关）：
    回到主页面 -> 领取铜币 -> 任务集会所 -> 积分赛 -> 好友体力赠送与收取
    -> 排行榜点赞 -> 组织祈福 -> 小队突袭 -> 领取一乐拉面 -> 精英副本
    -> 招募 -> 丰饶之间 -> 每日分享 -> 每日活跃奖励

设计要点：
  * 开始前先 back_to_main()，保证从一个已知状态出发。
  * 每个子任务开始前再确认一次「是否已经在主页面」，不在才退回，避免
    上一个任务把界面留在子面板里导致下一个任务找不到入口。
  * 单个子任务抛异常只记录并继续，不会中断整条日常链；最后给出成功/失败汇总。
"""

import time

from qfluentwidgets import FluentIcon

from src.tasks.back_to_main_task import BackToMainTask  # noqa: F401  (注册顺序参考)
from src.tasks.coin_task import CoinTask
from src.tasks.coinorgin_task import CoinOrginTask
from src.tasks.friend_task import FriendTask
from src.tasks.gacha_task import GachaTask
from src.tasks.jingying_task import JingYingTask
from src.tasks.mission_task import MissionTask
from src.tasks.noodle_task import NoodleTask
from src.tasks.page_nav import PageNavTask
from src.tasks.pointrace_task import PointRaceTask
from src.tasks.qiandao_task import QianDaoTask
from src.tasks.ranklist_task import RankListTask
from src.tasks.reward_task import RewardTask
from src.tasks.share_task import ShareTask
from src.tasks.team_praytask import TeamPrayTask
from src.tasks.teamfight_task import TeamFightTask

# (任务类, 展示名)。展示名用于日志和「执行任务」多选配置，顺序即执行顺序。
DAILY_TASKS = [
    (QianDaoTask, "每日签到"),
    (CoinTask, "领取铜币"),
    (MissionTask, "任务集会所"),
    (PointRaceTask, "积分赛"),
    (FriendTask, "好友体力赠送与收取"),
    (RankListTask, "排行榜点赞"),
    (TeamPrayTask, "组织祈福"),
    (TeamFightTask, "小队突袭"),
    (NoodleTask, "领取一乐拉面"),
    (JingYingTask, "精英副本"),
    (GachaTask, "招募"),
    (CoinOrginTask, "丰饶之间"),
    (ShareTask, "每日分享"),
    (RewardTask, "每日活跃奖励"),
]

TASK_LABELS = [label for _, label in DAILY_TASKS]

# 每个子任务开始前，最多花多少轮确认回到主页面
ENSURE_MAIN_ROUNDS = 8
ENSURE_MAIN_INTERVAL = 0.8

# 首次运行「一键日常」时弹出的使用前提（确认后才开始跑）
FIRST_RUN_ALERT = (
    "运行「一键日常」前请确认：\n"
    "\n"
    "1. 使用 MuMu 模拟器 12（目前只在 MuMu 上测试过）。\n"
    "2. 模拟器分辨率设为 16:9，推荐 1600x900。\n"
    "3. 游戏内按键布局保持默认：不要把技能/普攻按钮拖到别的位置或改大小，"
    "脚本是按固定位置点击的。\n"
    "4. 从游戏主页面（能看见右下角「冒险」）运行，并先关掉所有活动/公告弹窗。\n"
    "   一键日常开始时会自动尝试退出弹窗回到主页面，但手动关掉更稳。\n"
    "5. 模拟器需开启 ADB 调试。\n"
    "\n"
    "点「确认」开始执行，点「取消」先回去调整。"
)


class DailyTask(PageNavTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "一键日常"
        self.description = ("按顺序自动完成全部日常任务。"
                            "前提：MuMu 模拟器、16:9 分辨率、游戏内默认按键布局，"
                            "并从游戏主页面运行（先关掉活动弹窗）。")
        self.icon = FluentIcon.SYNC
        # 首次运行时弹窗提示使用前提，确认后才开跑
        self.add_first_run_alert(FIRST_RUN_ALERT)

        self.default_config.update({
            "执行任务": list(TASK_LABELS),
            "任务间回到主页面": True,
        })
        self.config_description.update({
            "执行任务": "勾选本次要跑的任务。执行顺序固定（按日常习惯排序），与勾选顺序无关。",
            "任务间回到主页面": "每个任务开始前先确认已经在主页面，保证起始状态一致（推荐开启）。",
        })
        self.config_type.update({
            "执行任务": {"type": "multi_selection", "options": list(TASK_LABELS)},
        })

    # ------------------------------------------------------------------
    def run(self):
        selected = self._selected_tasks()
        if not selected:
            self.log_warning("「执行任务」一个都没勾选，什么都不会做")
            return

        total = len(selected)
        self.log_info(f"=== 一键日常开始，共 {total} 个任务 ===")
        self.log_info("计划 [0] 回到主页面")
        for i, (_, label) in enumerate(selected, 1):
            self.log_info(f"计划 [{i}/{total}] {label}")
        self.info_set("进度", f"0/{total}")
        # 每次从头开始：清掉上一次的运行痕迹（有没有失败、进度到哪）
        self.info_set("成功", "")
        self.info_set("失败任务", "")

        # 1. 起始状态：先回到主页面
        if self.should_stop('开始前'):
            return
        if self.back_to_main(max_rounds=20, interval=1.0):
            self.log_info("已回到主页面，开始执行日常")
        else:
            self.log_warning("开始前未能确认回到主页面，仍会继续尝试各任务")

        succeeded, failed = [], []
        stopped = False
        for i, (cls, label) in enumerate(selected, 1):
            # 每轮开头都查一次停止：任务栏的「停止」只置 _enabled=False，
            # 不做这个检查的话点了停止还会一路跑完（实测踩过）。
            if self.should_stop('一键日常'):
                stopped = True
                break

            self.log_info(f"===== [{i}/{total}] {label} 开始 =====")

            # 2. 任务间回到主页面：不在主页才退，避免白等
            if self.config.get("任务间回到主页面", True) and i > 1:
                if not self.is_main_page():
                    self.log_info(f"[{label}] 当前不在主页面，先退回主页面")
                    if not self.back_to_main(max_rounds=ENSURE_MAIN_ROUNDS,
                                             interval=ENSURE_MAIN_INTERVAL,
                                             log=False):
                        self.log_warning(f"[{label}] 未能回到主页面，仍尝试执行该任务")

            # 3. 执行子任务，出错只记录不中断
            ok = self.run_sub_task(cls)
            if ok:
                succeeded.append(label)
                self.log_info(f"===== [{i}/{total}] {label} 完成 =====")
            else:
                failed.append(label)
                self.log_warning(f"===== [{i}/{total}] {label} 失败/异常，继续下一个 =====")

            self.info_set("进度", f"{i}/{total}")

        # 4. 收尾
        if stopped or self.should_stop('收尾'):
            self.log_warning(f"一键日常已被停止，剩余任务不再执行"
                             f"（已完成 {len(succeeded)}/{total}）")
            self.info_set("成功", f"{len(succeeded)}/{total}（已停止）")
            self.info_set("进度", f"{len(succeeded)}/{total}（已停止）")
            return

        self.back_to_main(max_rounds=ENSURE_MAIN_ROUNDS,
                          interval=ENSURE_MAIN_INTERVAL)

        self.log_info(f"=== 一键日常结束：成功 {len(succeeded)}/{total} ===")
        if succeeded:
            self.log_info(f"成功: {'、'.join(succeeded)}")
        if failed:
            self.log_warning(f"失败: {'、'.join(failed)}")
        self.info_set("成功", f"{len(succeeded)}/{total}")
        if failed:
            self.info_set("失败任务", "、".join(failed))

    # ------------------------------------------------------------------
    def _selected_tasks(self):
        """按 DAILY_TASKS 的固定顺序，过滤出被勾选的任务。"""
        chosen = self.config.get("执行任务")
        if not chosen:
            return []
        chosen = set(chosen)
        return [(cls, label) for cls, label in DAILY_TASKS if label in chosen]

    def run_sub_task(self, cls):
        """运行一个子任务，返回 True/False（异常不向外抛）。

        这里直接调 ``task.run()``，而不是 ok-script 的 ``run_task_by_class``：
        后者会把异常重新抛出去，中断整条日常链；这里要的是"失败就跳过下一个"。
        同时补上 execute() 里对子任务做的状态处理（running / start_time / info），
        保证任务自身的逻辑看到的状态和单独运行时一致。
        """
        try:
            task = self.get_task_by_class(cls)
        except Exception as e:
            self.log_error(f"查找任务 {cls.__name__} 失败: {e}", e)
            return False

        if task is None:
            self.log_warning(f"任务管理器里没有 {cls.__name__}，跳过")
            return False

        label = getattr(task, "name", cls.__name__)
        old_info = task.info
        task.info = self.info
        task.start_time = time.time()
        task.running = True
        # 让子任务知道自己的父任务是谁 —— 子任务的 stop_requested() 靠这个
        # 判断"一键日常被停了没有"（子任务自己从未被单独启用过，
        # 不能拿它自己的 _enabled 当判据）。见 page_nav.stop_requested()。
        task._parent_task = self
        try:
            task.run()
            return True
        except Exception as e:
            self.log_error(f"{label} 执行异常: {e}", e)
            # 出异常后界面状态未知，试着退回到主页面，给下一个任务一个干净起点
            try:
                self.back_to_main(max_rounds=ENSURE_MAIN_ROUNDS,
                                  interval=ENSURE_MAIN_INTERVAL, log=False)
            except Exception:
                pass
            return False
        finally:
            task.running = False
            task.info = old_info
            task._parent_task = None
