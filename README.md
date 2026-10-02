<div align="center">
  <h1 align="center">
    <img src="icons/icon.png" width="200" alt="ok-naruto logo"/>
    <br/>
    ok-naruto
  </h1>

  <p>
    一个基于图像识别的《火影忍者》手游日常自动化程序，支持后台运行，基于 <a href="https://ok-script.com">ok-script</a> 开发。
    <br />
    An image-recognition-based daily-task automation tool for Naruto Mobile, with background mode support, developed with <a href="https://ok-script.com">ok-script</a>.
  </p>

  <p><i>通过模拟器 ADB / 原生触控接口模拟手指操作，无内存读取、无文件修改</i></p>
</div>

<div align="center">

![平台](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/NYTN02/ok-naruto)](https://github.com/NYTN02/ok-naruto/releases)
[![总下载量](https://img.shields.io/github/downloads/NYTN02/ok-naruto/total)](https://github.com/NYTN02/ok-naruto/releases)

</div>

### 中文说明 | [English](README_en.md)

---

## ⚠️ 免责声明

本软件为外部辅助工具，仅通过模拟常规用户界面操作来简化《火影忍者》手游中的重复性日常，**不读取游戏内存、不修改任何游戏文件或数据、不修改网络封包**。

本软件开源、免费，仅供个人学习与交流使用，请勿用于任何商业或营利性目的。

**请务必注意**：使用任何第三方自动化工具都可能违反游戏的用户协议，存在账号被警告、限制或封禁的风险。是否使用、以及由此产生的任何后果，由使用者自行承担，与本项目及开发者无关。

**下载并使用本软件即表示您已阅读、理解并同意以上声明。**

## 🚀 快速开始

### 环境要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10 / 11 |
| 模拟器 | **MuMu 模拟器 12**（目前只在 MuMu 上测试过，其它模拟器不保证可用） |
| 分辨率 | 模拟器设为 **16:9**，推荐 **1600x900** |
| ADB | 模拟器需开启 ADB 调试（MuMu 默认端口 16384） |
| 游戏设置 | 游戏内**按键布局保持默认** |

> ⚠️ **关于「默认按键布局」**：脚本是按固定坐标点击游戏画面上的技能 / 普攻 / 大招按钮的。
> 如果你在游戏里自定义拖动过技能按钮的位置、改过按钮大小，点击就会落空。
> 请在游戏设置里把按键布局恢复为默认。

### 使用步骤

1. 启动 MuMu 模拟器，把分辨率设为 1600x900（或其它 16:9 分辨率）。
2. 启动《火影忍者》手游，**登录并进入游戏主页面**（能看见右下角「冒险」图标）。
3. **关掉所有活动弹窗 / 公告 / 签到推送**，确保主页面是干净的。
   （「一键日常」开始时会自动尝试点掉弹窗退回主页面，但手动关掉更稳妥。）
4. 运行 `ok-naruto`，选择任务「**一键日常**」，点击开始。
5. 首次运行会弹出使用前提提示，确认后开始按顺序执行。

程序运行期间可以正常使用电脑（走模拟器原生截图 + 触控注入，不需要窗口保持前台）。

## ✨ 主要功能

### 一键日常

一个入口按固定顺序跑完全部日常，中途某个任务失败会记录下来并继续跑下一个，结束后汇总成功 / 失败清单。

执行顺序：

```
回到主页面
 → 每日签到 → 领取铜币 → 任务集会所 → 积分赛 → 好友体力赠送与收取
 → 排行榜点赞 → 组织祈福 → 小队突袭 → 领取一乐拉面 → 精英副本
 → 招募 → 丰饶之间 → 每日分享 → 每日活跃奖励
```

任务配置里可以**任意勾选**本次想跑的项目（默认全选），也可以关掉「任务间回到主页面」。

### 单独执行的任务

上面的每一项都可以单独运行，方便只想补做某一项的时候用：

| 任务 | 说明 |
|---|---|
| 每日签到 | 活动页上滑找到「每月签到」并领取 |
| 领取铜币 | 主界面铜币入口，领取免费铜币 |
| 任务集会所 | 领取任务集会所奖励 |
| 积分赛 | 积分赛挑战与奖励领取 |
| 好友体力赠送与收取 | 批量赠送 / 收取好友体力 |
| 排行榜点赞 | 排行榜点赞 |
| 组织祈福 | 组织祈福 |
| 小队突袭 | 小队突袭 |
| 领取一乐拉面 | 一乐拉面免费领取 |
| 精英副本 | 精英副本扫荡 / 挑战 |
| 招募 | 免费招募 |
| 丰饶之间 | 丰饶之间经验副本（自动战斗） |
| 每日分享 | 每日分享 |
| 每日活跃奖励 | 每日活跃度宝箱领取 |

### 其它

* **后台运行**：通过 MuMu 原生截图与触控注入，不要求游戏窗口保持前台。
* **自动战斗**：副本类玩法用圆形识别自动定位普攻 / 技能 / 大招按钮并点击，
  不需要键盘映射，也不依赖模拟器键位方案。
* **自动退出弹窗**：内置「回到主页面」能力，会依次尝试
  `popu_cancel` / `reward_cancel` / `gacha_cancel` / `clean_cancel` /
  `activity_cancel` / `activity_qiandaocancel` / `team_cancel` /
  `friend_cancel` / `coin_cancel` 把当前面板逐层关掉。

## 🔧 疑难解答

1. **点了没反应 / 任务卡住**
   确认分辨率是 16:9、游戏内按键布局为默认，并且是从游戏主页面开始运行的。
2. **「找不到丰饶之间入口」**
   主界面是会左右滚动的，脚本会自动左右滑动查找。如果一直找不到，
   可能是活动弹窗遮住了入口，先手动关掉弹窗再跑。
3. **「认不出当前战斗布局」**
   说明当前战斗界面不是已适配的玩法。可以运行调试任务「战斗按钮校准」，
   它会导出一张标注图到 `debug_output/combat_layout_calib.png`，并告诉你
   识别成了哪种玩法、得分多少。
4. **杀毒软件误报**
   把安装目录加入杀毒软件（含 Windows Defender）的信任区 / 白名单。
5. **改了游戏内按键布局之后**
   请恢复默认。脚本不依赖模拟器键位方案，但依赖游戏内按钮处于默认位置。

## 💻 开发者专区

### 从源码运行

推荐 Python 3.12。先创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --no-deps -r requirements.txt

# 正常运行
python main.py

# 调试模式（带开发工具窗口、识别框可视化）
python main_debug.py
```

### 运行测试

```powershell
.\.venv\Scripts\Activate.ps1
.\run_tests.ps1
```

`tests/` 下的用例同时是 GitHub Actions 的发布门禁，不通过就不会打包。

### 命令行参数

```powershell
# 启动后自动执行第 1 个任务（一键日常），完成后退出程序
ok-naruto.exe -t 1 -e
```

* `-t` / `--task`：启动后自动执行第 N 个任务。
* `-e` / `--exit`：任务结束后自动退出程序。

### 打包发布

打包由 GitHub Actions 完成（推 `v*` tag 触发）。
细节见 [RELEASE.md](RELEASE.md)。

## 🔗 相关项目

* [ok-script](https://github.com/ok-oldking/ok-script) —— 本项目使用的自动化框架
* [ok-script-app](https://github.com/ok-oldking/ok-script-app) —— 本项目的初始模板
* [ok-ww](https://github.com/ok-oldking/ok-wuthering-waves) —— 架构参考
* [narutomobile](https://github.com/duorua/narutomobile) —— 任务清单参考

## ❤️ 致谢

* [ok-oldking/ok-script](https://github.com/ok-oldking/ok-script)
* [ok-oldking/OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
* [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)

## 📄 许可证

本项目采用 **GNU Affero General Public License v3.0 (AGPL-3.0)**，完整条款见 [LICENSE](LICENSE)。

简单说：你可以自由使用、修改、分发本项目，但**修改后的版本如果对外分发，也必须以 AGPL-3.0 开源**。
如果你把本项目的代码整合进自己的项目并提供给他人，同样需要开源你的完整源码。

> 注意：许可证只约束**代码**的使用与分发，不改变上面免责声明里关于游戏账号风险的说明。

