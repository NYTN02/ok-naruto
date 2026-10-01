# Quick Start

## 1. Create a Repository From the Template

Click [Use this template](https://github.com/ok-oldking/ok-script-app/generate) on GitHub, create your repository, and clone it:

```bash
git clone https://github.com/<your-github-name>/<your-repository>.git
cd <your-repository>
```

Choose either initialization path:

- **Use an AI coding tool (recommended):** In Codex, enter `Use $initialize-ok-script-app to initialize this repository.` With another tool, ask it to read `.agents/skills/initialize-ok-script-app/SKILL.md` first. The initializer gathers the game, runtime targets, repositories, icons, and first-task requirements before editing files.
- **Initialize manually:** Continue with this page and the linked guides.

## 2. Install Python 3.12 and Project Dependencies

Install [Python 3.12.10](https://www.python.org/downloads/release/python-31210/), then run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
$PypiIndex = "https://pypi.org/simple/"
python -m pip install --index-url $PypiIndex --upgrade pip
```

Install one dependency profile for the app's runtime target. For the Qt desktop UI:

```powershell
python -m pip install --index-url $PypiIndex --no-deps --upgrade -r requirements.txt
python main_debug.py
```

For the web UI:

```powershell
python -m pip install --index-url $PypiIndex --no-deps --upgrade -r requirements-web.txt
python web_main_debug.py
```

The lock files provide reproducible installations and are recommended for daily
development. To resolve the latest compatible dependencies directly from
`pyproject.toml`, use the applicable command instead:

```powershell
python -m pip install --index-url $PypiIndex ".[qt]"
python -m pip install --index-url $PypiIndex ".[web]"
```

Run only the command for your target. The official PyPI index endpoint for pip is
`https://pypi.org/simple/`, not the website root `https://pypi.org/`. Using the
website root can report `No matching distribution found` even when the package
exists.

Administrator privileges are normally unnecessary. If the target game runs as administrator, launch the automation app at the same privilege level or capture and input may not work.

## 3. Initialize the App

1. Set the application identity, runtime targets, icons, and update repository in [App configuration](configuration.md).
2. Create and register the first task with [Task development](tasks.md).
3. Start Debug mode:

```powershell
python main_debug.py
```

4. Run tests:

```powershell
python -m unittest tests.TestMain
```

5. After validation, configure the workflows and push a tag using [Packaging and release](release.md).
