"""键盘发送诊断（已停用，仅供追溯问题用）。

结论先说：ADB 通道下 send_key 注入的是 Android keyevent，而游戏的按键映射
监听的是 Windows 键盘事件，两者不在一个层面 —— 所以「键位读得到、send_key
也不报错，但游戏毫无反应」。本项目现在改用 ADB 点击坐标出招，
「火影忍者手游键位」配置项已停用（见 src/config.py），
这个任务也已在 config.py 的 onetime_tasks 里注释掉，不会出现在界面上。

保留文件是为了以后要排查通道问题时能临时启用；所以这里不再读那个已停用的
配置，改用内置的样例键位。
"""

from ok import BaseTask
import time

# 不再依赖「火影忍者手游键位」配置（已停用），用内置样例
SAMPLE_KEYS = {
    '一技能': 'j',
    '二技能': 'k',
    '大招': 'l',
    '普攻': 'u',
}


class DebugSendKeyTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "键盘发送测试"

    def run(self):
        keys = SAMPLE_KEYS
        self.log_info("=== 键位配置已停用，使用内置样例键位 ===")
        self.log_info(f"  完整内容: {keys}")
        for k, v in keys.items():
            self.log_info(f"  {k} = {v!r} (type={type(v).__name__})")

        # 2. 检查 send_key 方法
        self.log_info(f"=== send_key 方法 ===")
        self.log_info(f"  send_key: {hasattr(self, 'send_key')}")
        self.log_info(f"  send_key_down: {hasattr(self, 'send_key_down')}")
        self.log_info(f"  send_key_up: {hasattr(self, 'send_key_up')}")

        # 3. 依次发送所有键位，每次 1.5 秒
        self.log_info("=== 开始依次发送按键（请让 MuMu 保持前台）===")
        for name, key in keys.items():
            self.log_info(f"发送 {name} => {key!r}")
            try:
                self.send_key(key)
            except Exception as e:
                self.log_error(f"  send_key 失败: {e}")
            self.sleep(1.5)

        self.log_info("=== 测试完成 ===")