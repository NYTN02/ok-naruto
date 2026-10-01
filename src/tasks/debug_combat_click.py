"""战斗点击验证任务。

用途：在战斗界面运行，先识别当前玩法布局，再依次点击各技能按钮，每个按钮之间
留出足够间隔，方便肉眼确认「点到的是不是那个按钮、技能有没有真的放出来」。

为什么默认间隔 2 秒
--------------------------------------------------------------------------
火影忍者每个技能都有施法动作，技能动画期间后续输入会被吃掉。间隔太短时只能看到
最后一个动作生效，看起来像"点了没反应"。实战循环里不需要这么保守（循环本身会
反复重试），但验证阶段必须给足间隔，否则无法判断是坐标错了还是被动画吞了。

如果日志说"点击了"但游戏没反应，先看日志里的「识别为 XX 玩法」：
布局识别错了，坐标就会落在背景上——这是最常见的原因，而不是点击通道有问题。
"""

from src.tasks.combat_task import CombatTask

# (按钮名, 点击后等待秒数)
CLICK_ORDER = [
    ('普攻', 1.5),
    ('一技能', 2.0),
    ('二技能', 2.0),
    ('大招', 2.5),
    ('替身', 2.0),
]


class DebugCombatClickTask(CombatTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "战斗点击验证"
        self.description = "识别当前玩法布局后依次点击各按钮，用于确认点击坐标是否准确"

    def run(self):
        self.log_info("开始战斗点击验证，先在战斗界面识别布局...")

        if not self.ensure_combat_layout(log=True):
            self.log_error("没识别出当前战斗布局，已中止（避免乱点）。"
                           "请确认停在战斗界面，或先跑「战斗按钮校准」。")
            return

        self.log_info(f"当前布局档案: {self._profile}")
        for name in ('普攻', '一技能', '二技能', '大招'):
            pos = self.get_button_pos(name)
            self.log_info(f"  {name} 将点击: {pos}")

        self.sleep(1.5)
        for name, wait in CLICK_ORDER:
            pos = self.get_button_pos(name)
            if pos is None:
                self.log_warning(f"布局里没有 {name}，跳过")
                continue
            self.log_info(f"点击 {name} {pos}")
            self.click(pos[0], pos[1])
            self.sleep(wait)

        self.log_info("点击验证完成。若角色依次出招，说明点击通道和坐标都正确；"
                      "若只有部分生效，把间隔调大再看（技能动画会吃掉输入）。")
