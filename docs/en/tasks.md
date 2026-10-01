# Task Development

The one-time task example is `src/tasks/MyOneTimeTask.py`; the background trigger example is `src/tasks/MyTriggerTask.py`.

## Create a Task

- Inherit from `BaseTask` for a task that runs when the user starts it.
- Inherit from `TriggerTask` for periodic background checks.
- Put shared behavior in `src/tasks/MyBaseTask.py`.

Task classes typically set their name, description, defaults, and widgets in `__init__()`, then implement automation in `run()`.

## Register a Task

Register the module path and class name in `src/config.py`:

```python
'onetime_tasks': [
    ['src.tasks.MyFirstTask', 'MyFirstTask'],
    ['ok', 'DiagnosisTask'],
],
```

Use `trigger_tasks` for background tasks.

## Common Capabilities

- Add defaults with `default_config`.
- Select widget types with `config_type`.
- Recognize text with `self.ocr()`.
- Match templates with `self.find_one()` or `self.find_feature()`.
- Display task state with `self.info_set()`.
- Send notifications with `self.log_info(..., notify=True)`.

With `custom_tasks` enabled, scripts can also be created and edited in the GUI.

## AI-Assisted Development

The repository includes these Agent Skills:

- `$ok-script-tasks`: create, modify, and register task classes.
- `$ok-script-codegen`: generate automation logic from descriptions or screenshots.
- `$ok-script-i18n`: synchronize translations for tasks and configuration.

## Verify

```powershell
python main_debug.py
python -m unittest tests.TestMain
```

Place additional tests under `tests/`; the release workflow runs test files from that directory.
