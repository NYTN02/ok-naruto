from ok import BaseTask


class DebugKeyTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "键位API诊断"

    def run(self):
        self.log_info("=== 含 key/press/input 的方法 ===")
        methods = [a for a in dir(self)
                   if not a.startswith('_')
                   and any(k in a.lower() for k in ('key', 'press', 'input', 'send'))]
        for m in methods:
            self.log_info(f"  {m}")

        self.log_info("=== 尝试常见方法名 ===")
        for name in ['press_key', 'send_key', 'key_press', 'key_down',
                     'key_up', 'send_key_down', 'send_key_up',
                     'input_key', 'hotkey', 'press', 'mouse_click']:
            has = hasattr(self, name)
            self.log_info(f"  {name}: {'存在' if has else '不存在'}")

        self.log_info("诊断结束")