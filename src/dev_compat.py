"""开发模式下的降噪补丁。

跑源码（main_debug.py）时没有 pyappify 可执行文件，ok-script 的
UpdateCard 会去调 pyappify 检查更新 -> FileNotFoundError -> 打一整段
ERROR + Traceback 到日志里，看起来像出了大问题，其实在开发模式下
"检查更新"这件事本来就不可能做到。

这里把它降成一条 warning，日志干净些；打包版不受影响（那边能找到可执行文件）。
"""

import logging

_applied = False


def apply():
    """把 UpdateCard 的 pyappify 异常降噪。重复调用安全。"""
    global _applied
    if _applied:
        return
    try:
        from ok.ui.qt.about.UpdateCard import UpdateCard
    except Exception:
        return          # 找不到就算了，不该因为这个起不来

    original_run = getattr(UpdateCard, 'run', None)
    if original_run is None:
        return

    def patched_run(self, *args, **kwargs):
        try:
            return original_run(self, *args, **kwargs)
        except Exception as e:
            # 只压 pyappify 找不到可执行文件这一类；别的异常照旧抛
            name = type(e).__name__
            if name != 'FileNotFoundError':
                raise
            logging.getLogger('dev_compat').warning(
                '[开发模式] 跳过检查更新（没找到 pyappify 可执行文件，'
                '打包版才有）：%s', e)
            return None

    UpdateCard.run = patched_run
    _applied = True
