<div align="center">
  <h1 align="center">
    <img src="icons/icon.png" width="200" alt="ok-naruto logo"/>
    <br/>
    ok-naruto
  </h1>

  <p>
    An image-recognition-based daily-task automation tool for <b>Naruto Mobile</b> (火影忍者手游),
    with background mode support, developed with <a href="https://ok-script.com">ok-script</a>.
  </p>

  <p><i>Simulates touch input through the emulator's ADB / native input interface. No memory reading, no file modification.</i></p>
</div>

<div align="center">

![Platform](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/NYTN02/ok-naruto)](https://github.com/NYTN02/ok-naruto/releases)

</div>

### [中文说明](README.md) | English

---

## ⚠️ Disclaimer

This is an external helper tool. It only simulates normal user interface interaction to skip repetitive daily
chores in Naruto Mobile. It does **not** read game memory, modify game files or data, or touch network packets.

This project is open source and free, for personal learning and exchange only. Do not use it for any commercial purpose.

**Please note**: using any third-party automation tool may violate the game's Terms of Service and may put your
account at risk of warning, restriction, or ban. Use it at your own discretion; any consequence is your own
responsibility and has nothing to do with this project or its developer.

**By downloading and using this software you confirm that you have read, understood and accepted the above.**

## 🚀 Quick Start

### Requirements

| Item | Requirement |
|---|---|
| OS | Windows 10 / 11 |
| Emulator | **MuMu Player 12** — only MuMu has been tested; other emulators are not guaranteed to work |
| Resolution | Set the emulator to a **16:9** resolution; **1600x900** recommended |
| ADB | ADB debugging must be enabled (MuMu default port is 16384) |
| In-game | Keep the **default in-game button layout** |

> ⚠️ **About the default button layout**: the script clicks the skill / attack / ultimate buttons at fixed
> screen positions. If you have dragged or resized those buttons in game, the clicks will miss.
> Please restore the default button layout in the game settings.

### Steps

1. Start MuMu Player and set the resolution to 1600x900 (or any other 16:9 resolution).
2. Launch Naruto Mobile and **log in to the main screen** (the one with the 冒险 button at the bottom right).
3. **Close all activity / announcement popups** so the main screen is clean.
   ("Daily" will try to close popups and return to the main screen automatically, but doing it manually is safer.)
4. Run `ok-naruto`, pick the **一键日常 / Daily** task and press start.
5. On the first run a dialog explains the requirements; confirm it to begin.

You can keep using your PC while it runs — it captures the emulator natively and injects touch events,
so the game window does not need to stay in the foreground.

## ✨ Features

### One-click Daily

Runs every daily task in a fixed order. If one task fails it is recorded and the run continues;
a summary of successes and failures is printed at the end.

```
Return to main screen
 → Daily check-in → Coins → Mission Hall → Point Race → Friend stamina send/receive
 → Rank list likes → Team prayer → Team raid → Ichiraku ramen
 → Elite dungeon → Recruit → Battle of Fertility → Daily share
 → Daily activity reward
```

Each task can be individually enabled/disabled in the task configuration (all enabled by default).

### Individual tasks

Every item above can also be run on its own:

| Task | Description |
|---|---|
| 每日签到 | Daily check-in: scroll the activity page to find "每月签到" |
| 领取铜币 | Claim free coins |
| 任务集会所 | Claim mission hall rewards |
| 积分赛 | Point race |
| 好友体力赠送与收取 | Send / receive friend stamina |
| 排行榜点赞 | Like the rank list |
| 组织祈福 | Team prayer |
| 小队突袭 | Team raid |
| 领取一乐拉面 | Claim free Ichiraku ramen |
| 精英副本 | Elite dungeon |
| 招募 | Free recruit |
| 丰饶之间 | Battle of Fertility (auto combat) |
| 每日分享 | Daily share |
| 每日活跃奖励 | Daily activity chests |

### Other

* **Background mode** — native emulator capture and touch injection, no need to keep the window focused.
* **Auto combat** — for dungeon modes, circle detection locates the normal-attack / skill / ultimate
  buttons and clicks them. No keyboard mapping needed.
* **Auto popup closing** — a built-in "return to main screen" routine tries
  `popu_cancel` / `guide_cancel` / `reward_cancel` / `gacha_cancel` / `clean_cancel` /
  `activity_cancel` / `activity_qiandaocancel` / `team_cancel` / `friend_cancel` /
  `coin_cancel` to dismiss panels one layer at a time.

## 🔧 Troubleshooting

1. **Clicks do nothing / task stuck** — make sure the resolution is 16:9, the in-game button layout is
   default, and that you started from the main screen.
2. **"Cannot find the Battle of Fertility entrance"** — the main screen scrolls horizontally and the
   script swipes to look for it. If it never finds it, an activity popup may be covering the entrance.
3. **"Cannot recognise the current combat layout"** — the current battle mode is not supported yet.
   Run the debug task "战斗按钮校准" to export an annotated screenshot to
   `debug_output/combat_layout_calib.png`.
4. **Antivirus false positive** — add the install folder to your antivirus whitelist (including Windows Defender).
5. **Changed the in-game button layout** — please restore it to default.

## 💻 For Developers

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --no-deps -r requirements.txt

python main.py          # normal
python main_debug.py    # debug mode with the developer tools window
```

Run tests (they also act as the CI release gate):

```powershell
.\.venv\Scripts\Activate.ps1
.\run_tests.ps1
```

Packaging is done by GitHub Actions on a `v*` tag — see [RELEASE.md](RELEASE.md) (Chinese).

## 🔗 Related projects

* [ok-script](https://github.com/ok-oldking/ok-script) — the automation framework used here
* [ok-script-app](https://github.com/ok-oldking/ok-script-app) — the project template this repo started from
* [ok-ww](https://github.com/ok-oldking/ok-wuthering-waves) — architecture reference
* [narutomobile](https://github.com/duorua/narutomobile) — task list reference

## 📄 License

Licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** — see [LICENSE](LICENSE) for the full text.

In short: you are free to use, modify and redistribute this project, but **if you distribute a modified
version, you must release it under AGPL-3.0 as well**, including the complete source code.

> Note: the license governs the **code** only. It does not change the account-risk disclaimer above.

