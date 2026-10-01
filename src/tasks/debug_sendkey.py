from ok import BaseTask
import time


class DebugSendKeyTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "键盘发送测试"

    def run(self):
        # 1. 读取键位配置
        try:
            keys = self.get_global_config('火影忍者手游键位')
            self.log_info(f"=== 键位配置 ===")
            self.log_info(f"  完整内容: {keys}")
            if keys:
                for k, v in keys.items():
                    self.log_info(f"  {k} = {v!r} (type={type(v).__name__})")
        except Exception as e:
            self.log_error(f"读取键位失败: {e}")
            return

        if not keys:
            self.log_error("键位配置为空")
            return

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