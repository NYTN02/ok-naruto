# 应用与运行目标配置

## 应用设置

在 `src/config.py` 中至少检查：

- `gui_title`：应用窗口名称。
- `gui_icon`：GUI 图标路径。
- `supported_resolution`：支持的画面比例和最低分辨率。
- `links`：项目主页、反馈渠道和社区链接。
- `onetime_tasks`、`trigger_tasks`：任务注册列表。

## 运行目标

`windows`、`adb`、`browser` 必须至少配置一种，也可以同时配置多种。

### Windows 原生游戏

配置 `windows` 中的：

- `exe`：游戏进程文件名列表。
- `hwnd_class`：可选的窗口类名，用于提高窗口匹配准确度。
- `interaction`：允许使用的输入方式及优先级。
- `capture_method`：允许使用的截图方式及优先级。
- HDR 和后台截图相关选项。

### Android 模拟器或设备

在 `adb.packages` 中填写游戏包名。MuMu 模拟器可使用原生截图和输入；其他模拟器或设备通常通过 ADB 工作。

### 浏览器游戏

取消 `browser` 示例配置的注释，并设置：

```python
'browser': {
    'url': 'https://example.com/game',
    'nick': 'Browser',
    'resolution': (1280, 720),
},
```

浏览器目标还需要 `playwright`。将它加入 `pyproject.toml` 中需要浏览器目标的
profile，然后重新编译对应的 `requirements.txt` 或 `requirements-web.txt`，
确保本地环境和 GitHub 打包环境都会安装该依赖。

## 替换图标

用自己的资源替换 `icons/icon.png` 和 `icons/icon.ico`。保持文件名不变可以避免额外配置；如需改名，同步修改 `src/config.py` 和 `pyappify.yml` 中的路径。

## 更新仓库

修改 `pyappify.yml` 中应用名称、profile 名称和 `git_url`：

- 正式发布建议使用独立的轻量更新仓库。
- 前期测试可以直接使用源码仓库。
- 使用独立更新仓库时，同步修改 `.github/workflows/build.yml` 中的同步目标和 Secrets。

初始化后，搜索并替换模板遗留的 `ok-script-app`、`ok-oldking`、仓库 URL、安装包名称和社区链接。
