from ok import BaseTask
from src.tasks.page_nav import PageNavTask

class TestTask(PageNavTask):
    def run(self):
        # 等待识别并点击模板，超时 5 秒
        result = self.wait_click('main_adventure', threshold=0.8, time_out=5)
        if result:
            self.log_info("成功识别并点击了冒险按钮！")
        else:
            self.log_info("没有找到冒险按钮，请检查模板标注。")