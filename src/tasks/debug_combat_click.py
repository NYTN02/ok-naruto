"""战斗点击验证任务。

用途：在战斗界面运行，先识别当前玩法布局，再依次点击各技能按钮，每个按钮之间
留出足够间隔，方便肉眼确认「点到的是不是那个按钮、技能有没有真的放出来」。

为什么间隔要 6 秒
--------------------------------------------------------------------------
火影忍者每个技能都有施法动作，技能动画期间后续输入会被吃掉。间隔太短时只能看到
最后一个动作生效，看起来像"点了没反应"。实战循环里不需要这么保守（循环本身会
反复重试），但验证阶段必须给足间隔，否则无法判断是坐标错了还是被动画吞了。

早期是 2 秒，实测偏紧（大招动画长，后面的替身/密卷常被吃掉），所以统一放宽到 6 秒。

如果日志说"点击了"但游戏没反应，先看日志里的「识别为 XX 玩法」：
布局识别错了，坐标就会落在背景上——这是最常见的原因，而不是点击通道有问题。
"""

from src.tasks.combat_task import CombatTask

# 每个按键之间的间隔（秒）
CLICK_INTERVAL = 6.0

# 依次点击的按钮。密卷 / 通灵只在部分玩法 HUD 里有（练习场/决斗场），
# 布局里没有时会自动跳过，所以放进来是安全的。
CLICK_ORDER = [
    '普攻',
    '一技能',
    '二技能',
    '大招',
    '替身',
    '密卷',
    '通灵',
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
        self.log_info(f"按键间隔: {CLICK_INTERVAL} 秒")
        available = []
        for name in CLICK_ORDER:
            pos = self.get_button_pos(name)
            if pos is None:
                self.log_info(f"  {name} 布局里没有，将跳过")
            else:
                available.append((name, pos))
                self.log_info(f"  {name} 将点击: {pos}")

        self.sleep(1.5)
        for idx, (name, pos) in enumerate(available, 1):
            self.log_info(f"[{idx}/{len(available)}] 点击 {name} {pos}"
                          f"（之后等 {CLICK_INTERVAL} 秒）")
            self.click(pos[0], pos[1])
            self.sleep(CLICK_INTERVAL)

        self.log_info("点击验证完成。若角色依次出招，说明点击通道和坐标都正确；"
                      "若只有部分生效，说明间隔还不够，可继续调大 CLICK_INTERVAL。")
