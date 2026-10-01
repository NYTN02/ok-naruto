# 打包与发布说明（ok-naruto）

本项目基于 [ok-script-app](https://github.com/ok-oldking/ok-script-app) 模板，
发布流程和官方文档一致：
[ok-script-app/docs/release.md](https://github.com/ok-oldking/ok-script-app/blob/master/docs/release.md)、
[ok-script 进阶使用指南](https://github.com/ok-oldking/ok-script/blob/master/docs/after_quick_start/README.md)。

## 先理解一件事：打包不是在你电脑上做的

PyPI 上那个 `pyappify` 包只是个占位 stub（里面就一句 `print("PyAppify Hello world")`），
真正的打包器由 `ok-oldking/pyappify-action` 在 **GitHub 的服务器上**提供。

所以「打包」的完整含义是：

```
你推一个 v0.1.0 的 tag
   ↓
GitHub 自动开一台 Windows 机器，跑 .github/workflows/build.yml：
   1. 装依赖 → 把 ok-script 内联进源码
   2. 跑 tests/ 里的用例（有一项失败就中止，不会发布）
   3. 把 deploy.txt 里列的文件同步到「更新库」
   4. 打包出安装包 ok-naruto-win32-Global-setup.exe
   5. 创建 Release 并把安装包挂上去
   ↓
用户在 GitHub Releases 页面下载安装包；装好以后程序自动从「更新库」拉更新
```

你本地不需要装任何打包工具。

---

## 一、只需要做 2 件事（一次性）

> 原本模板还要求改「Workflow permissions」，我已经在 `build.yml` 里显式写了
> `permissions: contents: write`，**正常情况不用再动那个设置**。
> 万一 Release 步骤报 403，再看本章最后的「备用步骤」。

### 第 1 件：建「更新库」

**为什么要建**：安装包里写死的更新地址指向一个**单独的轻量仓库**，只放
`deploy.txt` 里列的文件（`src` / `assets` / `main.py` / `requirements.txt` …）。
用户自动更新时只拉这个小仓库，不用下载整个开发库（含 docs、tests、tools、
`.venv` 之类），又快又小。

**怎么建（网页版，5 次点击，推荐）**

1. 浏览器打开 https://github.com/new
2. **Repository name** 填：`ok-naruto-update`
   （必须一字不差，后面 `pyappify.yml` 和 `build.yml` 里都写死了这个名字）
3. 选 **Public**
4. **不要**勾选 "Add a README file"、`.gitignore`、license，让它保持全空
5. 点 **Create repository**

建完你会看到一个空仓库页面，提示 "Quick setup — if you've done this kind of thing
before"。**这就对了，不用再操作**，CI 会往里推东西。

<details>
<summary>或者用 GitHub Desktop 建（会多一个本地文件夹）</summary>

1. `File` → `New repository...`
2. **Name** 填 `ok-naruto-update`，**Local path** 随便选一个空目录
3. 点 `Create repository`
4. 点顶部的 `Publish repository`
5. **取消勾选** `Keep this code private`
6. 点 `Publish repository`

两种方式效果一样，网页版更干净（不会在你电脑上多留一个文件夹）。
</details>

### 第 2 件：生成访问令牌（PAT）并加进 Secrets

**为什么要做**：GitHub 给每个 workflow 的默认令牌（`GITHUB_TOKEN`）**只能操作当前
仓库**，没有权限往 `ok-naruto-update` 推东西。所以要自己生成一个令牌给它用。

**步骤 A：生成令牌**

1. 打开 https://github.com/settings/tokens?type=beta
   （也可以点右上角头像 → `Settings` → 左侧拉到最下面 → `Developer settings`
   → `Personal access tokens` → `Fine-grained tokens`）
2. 点 **Generate new token**
3. **Token name** 填：`ok-naruto-ci`
4. **Expiration** 选一个期限。建议 1 年；
   ⚠️ 到期后构建会失败，到时候回来重新生成一个换掉即可
5. **Repository access** 选 **Only select repositories**，
   然后在下面勾选 **`ok-naruto-update`**（只勾这一个）
6. 展开 **Permissions** → **Repository permissions**，
   找到 **Contents**，把它设成 **Read and write**（其它保持 No access）
7. 点最下面 **Generate token**
8. **立刻复制**页面上那串 `github_pat_...`
   —— 这个页面关掉之后就再也看不到它了

**步骤 B：把令牌存进仓库 Secrets**

1. 打开 https://github.com/NYTN02/ok-naruto/settings/secrets/actions
   （也可以：仓库页 → `Settings` → 左侧 `Secrets and variables` → `Actions`）
2. 点 **New repository secret**
3. **Name** 填：`OK_GH`
   （必须完全一致，大小写都要一样；`build.yml` 里写的是 `secrets.OK_GH`）
4. **Secret** 粘贴刚才复制的 `github_pat_...`
5. 点 **Add secret**

搞定。列表里应该能看到一个叫 `OK_GH` 的 secret（值看不到，这是正常的）。

---

## 二、发布新版本

以后每发一版只要三步：改代码 → 提交推送 → 打个 `v*` tag。

### 用 GitHub Desktop 打 tag（你熟悉的工具）

1. 正常 `Commit` + `Push origin`
2. 切到 **History** 标签页
3. 在提交列表里**右键最新那条提交** → **`Create Tag...`**
   （参考 [GitHub 官方文档](https://docs.github.com/en/desktop/managing-commits/managing-tags-in-github-desktop)）
4. **Name** 填 `v0.1.0`（必须以 `v` 开头，`build.yml` 只认 `v*`）
5. 点 **Create Tag**
6. 回到主界面点 **`Push origin`**（tag 要单独推一次）

推送后打开 https://github.com/NYTN02/ok-naruto/actions ，能看到一个正在跑的
**Build** 工作流。

<details>
<summary>或者用网页发 Release（效果一样，也能触发构建）</summary>

1. 打开 https://github.com/NYTN02/ok-naruto/releases/new
2. **Choose a tag** 里输入 `v0.1.0`，点 **Create new tag: v0.1.0 on publish**
3. 填个标题，点 **Publish release**

发布 Release 会自动创建并推送这个 tag，所以同样能触发构建。
CI 跑完会把安装包挂到这个 Release 上（并覆盖你自己写的说明）。
</details>

### 版本号怎么涨

- 正式版：`v0.1.0` → `v0.1.1` → `v0.1.2` …
- 预发布版：带 `-`，例如 `v0.1.1-beta.1`。
  `build.yml` 里配了 `prerelease` 判断，带 `-` 的 tag 会自动标成 Pre-release，
  不会显示成正式版。

---

## 三、构建失败怎么办

按报错出现在哪一步对照：

| 报错位置 | 原因 | 处理 |
|---|---|---|
| `Run tests` | 某个测试用例挂了 | 本地跑 `.\run_tests.ps1` 复现并修好；测试是发布门禁，故意不让过 |
| `Sync Repositories` | 更新库不存在 / `OK_GH` 没配或权限不够 / 令牌过期 | 对照上面第 1、2 件逐一检查 |
| `Release` 报 403 | 令牌没有创建 Release 的权限 | 见下面「备用步骤」 |
| `Build with PyAppify Action` | `pyappify.yml` 写错，或 `requirements.txt` 装不上 | 按日志里 PyAppify 的提示改 |

### 备用步骤（只有 Release 报 403 才需要）

1. 打开 https://github.com/NYTN02/ok-naruto/settings/actions
2. 拉到 **Workflow permissions**
3. 选 **Read and write permissions**
4. 点 **Save**

（正常不用做，因为 `build.yml` 顶部已经声明了 `permissions: contents: write`，
它会覆盖仓库默认设置。）

---

## 四、本地自查

发布前建议先本地跑一遍测试，和 CI 里的门禁等价：

```powershell
cd D:\Work\okNARUTO\ok-naruto
.\.venv\Scripts\Activate.ps1     # 必须先激活，脚本里用的是裸 python
.\run_tests.ps1
```

另外确认：

- [ ] `.github/workflows/` 里没有残留 `ok-script-app` / `ok-ww` 的仓库地址
- [ ] `ok-naruto-update` 已建好、`OK_GH` 已配置
- [ ] `icons/icon.png` 和 `icons/icon.ico` 都是最新图标
      （`icon.ico` 必须**含多个尺寸**，否则小图标会发虚。
      换图标后跑 `.venv\Scripts\python.exe tools\make_icon.py` 重新生成）
- [ ] 改了依赖的话重新编译锁定文件：

```powershell
python -m piptools compile --extra qt --strip-extras --no-header --output-file requirements.txt pyproject.toml
```

编译后删掉生成的 `pyside6` / `pyside6-addons` 条目，保留 `pyside6-essentials`。

---

## 五、可选：CNB 国内镜像

国内用户直连 GitHub 下载/更新较慢，模板提供了 CNB（cnb.cool，腾讯云的代码托管）
镜像通道。**不接也能正常发布**，只是国内下载慢一点。

关于费用（社区版是「免费额度 + 超额按量」）：

- 仓库存储 **100 GiB/月 免费**，本项目仓库只有几 MB，永远到不了超额。
- 云原生构建 **160 核时/月 免费**。我们只把它当 git 镜像用，
  推送由 GitHub Actions 完成，**不在 CNB 上跑构建**，所以基本不消耗。
- **不需要自己买服务器**，也不需要为「用户下载」付流量费。
- 不绑定腾讯云付费方式时，额度用尽只会受限，**不会扣费**。

启用步骤：注册 cnb.cool → 建公开仓库 `NYTN02/ok-naruto` → 生成访问令牌 →
GitHub Secrets 加 `CNB_TOKEN` → 取消 `pyappify.yml` 里 China profile 的注释 →
在 `build.yml` 的 `repos` 里加一行 CNB 地址。
（注意：`repos` 是块文本，里面写 `#` 是数据不是注释。）

参考：[CNB 计费说明](https://docs.cnb.cool/zh/pricing.md)

---

## 六、已做的模板定制

| 文件 | 改了什么 |
|---|---|
| `pyappify.yml` | 应用名 → `ok-naruto`；更新源 → `NYTN02/ok-naruto-update`；Global profile 按 ok-ww 的写法保持最小；China / Web profile 注释掉 |
| `.github/workflows/build.yml` | git 用户、同步仓库地址、Release 资产名与下载链接全换成 ok-naruto；删除 MirrorChyan 触发步骤；**新增 `permissions`**；**checkout 加 `fetch-depth: 0`**；**修正测试步骤的退出码判断**；预发布 tag 自动标记 |
| `.github/workflows/mirrorchyan_*.yml` | 按「不接入 Mirror酱」删除 |
| `pyproject.toml` | `name` → `ok-naruto` |
| `mkdocs.yml` | `site_name` / `repo_url` → ok-naruto |
| `src/config.py` | 关于页链接换成本项目仓库；`onetime_tasks` 重排并注释掉开发用任务 |
| `README.md` / `README_en.md` | 重写为 ok-naruto 的项目介绍 |
| `icons/icon.ico` | 用新的 `icon.png` 重新生成，含 16/24/32/48/64/128/256 七个尺寸 |
| `tests/TestRelease.py` | **新增** 14 个发布门禁用例 |
| `tests/TestMain.py` | 删掉 2 个模板占位用例（依赖模板 assets 里的 `this_is_a_place_holder`，本项目没有，原先必然失败卡死 CI） |

### 为什么 build.yml 要加 `fetch-depth: 0`

`partial-sync-repo` 要对比「上次同步的 tag → 当前 tag」来生成更新日志。
`actions/checkout` 默认只拉 1 层历史（浅克隆），拿不到历史 tag，
日志会为空或报错。ok-ww 也显式写了 `fetch-depth: 0`。

### 为什么测试步骤要逐个检查退出码

PowerShell 步骤的最终退出码只看**最后一条原生命令**。模板原来的写法是
`... | ForEach-Object { python -m unittest $_.FullName }`，不检查
`$LASTEXITCODE`，于是只有**最后一个**测试文件的结果算数，
前面的文件全挂了也会判定成功——发布门禁形同虚设。现在每个文件都显式检查。

---

## 七、尚未处理

- `docs/` 目录和 `.github/workflows/docs.yml` 还是模板文档站，
  会以 ok-naruto 的名义发布 ok-script-app 的使用文档。用不到就删掉
  `docs.yml` 和 `docs/`。
- 任务目前只有中文名，没有做 i18n（`i18n/*/LC_MESSAGES/ok.po`）。
  如果要给海外用户用，可以按 [ok-script i18n 文档](https://github.com/ok-oldking/ok-script/blob/master/docs/after_quick_start/README.md) 补。
