from ok import BaseTask
from src.tasks.page_nav import MAIN_PAGE_FEATURE, PageNavTask

class TestTask(PageNavTask):
    def run(self):
        # 等待识别并点击主页面标志（MAIN_PAGE_FEATURE = main_guide），超时 5 秒
        result = self.wait_click(MAIN_PAGE_FEATURE, threshold=0.8, time_out=5)
        if result:
            self.log_info(f"成功识别并点击了主页面标志 {MAIN_PAGE_FEATURE}！")
        else:
            self.log_info(f"没有找到主页面标志 {MAIN_PAGE_FEATURE}，请检查模板标注。")