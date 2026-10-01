# ok-script-app

[English](README_en.md) | 中文

ok-script-app 是一个基于 [ok-script](https://github.com/ok-oldking/ok-script) 的 Python 自动化项目模板，支持为 Windows 原生游戏、Android 模拟器和浏览器游戏创建带 GUI 的自动化应用。

这个仓库提供任务示例、OCR、模板匹配、配置控件、测试、i18n、EXE 打包和更新发布配置。它是起步工程和功能演示，不是某个具体游戏的自动化成品。

## 文档

完整文档已整理为 MkDocs 网站源文件：

- [文档首页](docs/index.md)
- [快速开始](docs/getting-started.md)
- [应用与运行目标配置](docs/configuration.md)
- [任务开发](docs/tasks.md)
- [打包与发布](docs/release.md)
- [构建文档网站](docs/documentation.md)
- [English documentation](docs/en/index.md)

## 快速预览

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
$PypiIndex = "https://pypi.org/simple/"
python -m pip install --index-url $PypiIndex --upgrade pip
python -m pip install --index-url $PypiIndex --no-deps --upgrade -r requirements.txt
python main_debug.py
```

直接依赖统一维护在 `pyproject.toml`。`requirements.txt` 是 Qt profile 的锁定
文件，`requirements-web.txt` 是 Web profile 的锁定文件；请勿直接编辑这些
生成文件。Web profile 请将上面的依赖和启动命令分别替换为
`requirements-web.txt` 和 `python web_main_debug.py`。官方 PyPI 的 pip 索引地址
必须包含 `/simple/`；`https://pypi.org/` 不是有效的包索引地址。

详细的仓库初始化、目标配置、首个任务和 tag 打包流程请阅读[快速开始](docs/getting-started.md)。

## 构建文档网站

```powershell
python -m pip install --index-url https://pypi.org/simple/ -r requirements-docs.txt
python -m mkdocs serve
```

访问 `http://127.0.0.1:8000/` 预览。生成静态 HTML：

```powershell
python -m mkdocs build --strict
```

输出位于 `site/`。`.github/workflows/docs.yml` 可将网站自动发布到 GitHub Pages，具体设置见[文档网站说明](docs/documentation.md)。

## 社区

- 用户群：`1097603920`
- 开发者群：`938132715`
- [Discord](https://discord.gg/vVyCatEBgA)

## 致谢

- [ok-script](https://github.com/ok-oldking/ok-script)
- [OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
- [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
