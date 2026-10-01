# 任务开发

一次性任务示例位于 `src/tasks/MyOneTimeTask.py`，后台触发任务示例位于 `src/tasks/MyTriggerTask.py`。

## 创建任务

- 用户点击后执行一次的任务继承 `BaseTask`。
- 需要后台周期检查的任务继承 `TriggerTask`。
- 通用能力可以放在 `src/tasks/MyBaseTask.py`。

任务类通常在 `__init__()` 中设置名称、描述、默认配置和配置控件，在 `run()` 中实现自动化逻辑。

## 注册任务

在 `src/config.py` 中注册模块路径和类名：

```python
'onetime_tasks': [
    ['src.tasks.MyFirstTask', 'MyFirstTask'],
    ['ok', 'DiagnosisTask'],
],
```

后台任务使用 `trigger_tasks` 列表。

## 常用能力

- 修改 `default_config` 增加任务配置默认值。
- 修改 `config_type` 选择配置控件类型。
- 使用 `self.ocr()` 识别文字。
- 使用 `self.find_one()` 或 `self.find_feature()` 进行模板匹配。
- 使用 `self.info_set()` 在 UI 中展示任务状态。
- 使用 `self.log_info(..., notify=True)` 发送通知。

启用 `custom_tasks` 后，也可以在 GUI 中创建和编辑自定义任务脚本。

## 使用 AI 辅助开发

仓库内置以下 Agent Skills：

- `$ok-script-tasks`：创建、修改和注册任务类。
- `$ok-script-codegen`：根据需求或截图生成任务自动化逻辑。
- `$ok-script-i18n`：同步任务名称、描述和配置项翻译。

## 验证

```powershell
python main_debug.py
python -m unittest tests.TestMain
```

新增测试时，将文件放在 `tests/` 下；发布工作流会执行该目录中的测试文件。
