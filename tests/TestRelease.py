"""发布质量门禁测试。

CI（.github/workflows/build.yml 的 "Run tests" 步骤）会在打包前跑 tests/ 下所有
用例，**任何失败都会中断发布**。所以这里的用例刻意做到：

  * 不依赖模拟器 / 游戏窗口（CI 上没有模拟器）；
  * 快、确定、可重复；
  * 覆盖真正容易写错、而且一写错就在用户手里才炸的地方：
      - 模板名写错（会抛 FeatureSet: xxx not found in featureDict）
      - 一键日常引用了没注册的任务
      - 战斗布局档案缺按钮 / 半径范围写反
      - 配置文件里的坐标字符串解析不了

这些坑前面都真实踩过，所以固化成用例。
"""

import ast
import glob
import json
import os
import re
import unittest

try:
    import yaml
except ImportError:  # pyyaml 只是打包配置检查用，缺了不该让整个门禁挂掉
    yaml = None

import src.config as app_config
from src.tasks.combat_ui import (
    CORE_BUTTONS,
    DEFAULT_LAYOUT,
    LAYOUT_PROFILES,
    layout_to_config,
    parse_layout,
)
from src.tasks.daily_task import DAILY_TASKS, DailyTask
from src.tasks.coinorgin_task import CoinOrginTask
from src.tasks.guide_nav import (
    GUIDE_LISTBOTTOM,
    GUIDE_LISTTOP,
    GUIDE_SCROLL_AFTER,
    GUIDE_SCROLL_DOWN_FROM_Y,
    GUIDE_SCROLL_DOWN_TO_Y,
    GUIDE_SCROLL_MAX,
    GUIDE_SCROLL_UP_FROM_Y,
    GUIDE_SCROLL_UP_TO_Y,
    GUIDE_SCROLL_X,
    GUIDE_STUCK_TOLERANCE,
    GuideNavTask,
)
from src.tasks.mission_task import ACCEPT_ATTEMPTS, MissionTask
from src.tasks.page_nav import (
    CANCEL_FEATURES,
    CLICK_ANYWHERE_PATTERNS,
    MAIN_PAGE_FEATURE,
    PageNavTask,
)
from src.tasks.pointrace_task import CHALLENGE_RETRY, ENTRY_RETRY, PointRaceTask
from src.tasks.qiandao_task import QianDaoTask
from src.tasks.team_praytask import COINPRAY_ATTEMPTS, COINPRAY_INTERVAL
from src.tasks.teamfight_task import TeamFightTask

COCO_PATH = os.path.join('assets', 'coco_annotations.json')

# 「回到主页面」和日常任务入口依赖的关键模板，缺一个就会在运行时才炸
REQUIRED_FEATURES = [
    MAIN_PAGE_FEATURE,      # main_adventure
    'main_coinorign',       # 丰饶之间入口
    'main_coin_icon',       # 铜币
    'coin_freetoget',
    'coin_cancel',
    'popu_cancel',
    # 每日签到（src/tasks/qiandao_task.py）
    'main_activity',           # 主界面右上角活动入口
    'activity_qiandao',        # 每月签到面板里的签到按钮
    'activity_qiandaocancel',  # 签到面板的关闭按钮
    # 积分赛（src/tasks/pointrace_task.py）：本队战力靠这个图标定位，
    # 读不到它就取不到数值，整个挑战流程都走不下去
    'pointrace_personalpower',
    # 「指南」入口（src/tasks/guide_nav.py）：
    # 任务集会所 / 排行榜 / 积分赛 / 小队突袭 / 丰饶之间 全靠它进入，
    # 缺任何一个都会让对应任务直接进不去（原来是在主页找 main_* 图标，
    # 每个玩家主页背景不同会匹配不到，所以统一改走指南）
    'main_guide', 'guide_cancel',
    'guide_mission', 'guide_missiongo',
    'guide_ranklist', 'guide_ranklistgo',
    'guide_pointrace', 'guide_pointracego',
    'guide_teamfight', 'guide_teamfightgo',
    'guide_coinorign', 'guide_coinorigngo',
    # 指南列表的两端标志物：判断还能不能往某个方向滑
    'guide_listtop', 'guide_listbottom',
    # 组织祈福的新入口（主页面 main_reward -> 每日任务 -> reward_teampray）
    'main_reward', 'reward_teampray',
]


def load_feature_names():
    with open(COCO_PATH, encoding='utf-8') as f:
        coco = json.load(f)
    return {c['name'] for c in coco['categories']}


class TestFeatureNames(unittest.TestCase):
    """模板名必须真实存在。

    踩过的坑：写了 'coinorign_challenge'，运行时才抛
    ValueError: FeatureSet: coinorign_challenge not found in featureDict。
    """

    @classmethod
    def setUpClass(cls):
        cls.names = load_feature_names()

    def test_coco_file_valid(self):
        self.assertTrue(os.path.isfile(COCO_PATH), f'找不到 {COCO_PATH}')
        self.assertTrue(self.names, 'coco_annotations.json 里没有任何分类')

    def test_page_nav_features_exist(self):
        missing = [n for n in CANCEL_FEATURES if n not in self.names]
        self.assertEqual([], missing, f'page_nav 引用了不存在的模板: {missing}')

    def test_required_features_exist(self):
        missing = [n for n in REQUIRED_FEATURES if n not in self.names]
        self.assertEqual([], missing, f'任务依赖的模板不存在: {missing}')


class TestCombatLayout(unittest.TestCase):
    def test_profiles_cover_core_buttons(self):
        for profile, (layout, radii) in LAYOUT_PROFILES.items():
            for btn in CORE_BUTTONS:
                self.assertIn(btn, layout, f'布局档案 {profile} 缺少 {btn} 的先验坐标')
                self.assertIn(btn, radii, f'布局档案 {profile} 缺少 {btn} 的半径范围')

    def test_default_layout_comes_from_a_real_profile(self):
        # 兜底布局必须等于某个真实档案，否则识别失败时会点到别的位置
        profile_layouts = [layout for layout, _ in LAYOUT_PROFILES.values()]
        self.assertTrue(
            any(DEFAULT_LAYOUT == layout for layout in profile_layouts),
            'DEFAULT_LAYOUT 与任何布局档案都不一致',
        )

    def test_parse_layout_accepts_config_strings(self):
        layout = parse_layout({'普攻': '0.88,0.752', '一技能': [0.733, 0.558]})
        self.assertAlmostEqual(0.88, layout['普攻'][0], places=3)
        self.assertAlmostEqual(0.752, layout['普攻'][1], places=3)
        self.assertAlmostEqual(0.733, layout['一技能'][0], places=3)

    def test_parse_layout_ignores_junk(self):
        # 全局配置里混了非坐标的键（例如「玩法」）时不能污染布局
        layout = parse_layout({
            '玩法': '自动',
            '坏值': 'abc',
            '越界': '2.0,0.5',
            '空值': None,
        })
        for key in ('玩法', '坏值', '越界', '空值'):
            self.assertNotIn(key, layout)

    def test_layout_config_round_trip(self):
        back = parse_layout(layout_to_config(DEFAULT_LAYOUT))
        for name, (x, y) in DEFAULT_LAYOUT.items():
            self.assertAlmostEqual(x, back[name][0], places=3)
            self.assertAlmostEqual(y, back[name][1], places=3)

    def test_radius_ranges_are_ordered(self):
        for profile, (_, radii) in LAYOUT_PROFILES.items():
            for btn, (lo, hi) in radii.items():
                self.assertLess(lo, hi, f'{profile}.{btn} 的半径范围写反了')


class TestDailyTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # config 里 onetime_tasks 是 [模块路径, 类名] 的字符串对
        cls.registered = {name for _, name in app_config.config['onetime_tasks']}

    def test_daily_task_registered(self):
        self.assertIn(DailyTask.__name__, self.registered,
                      '一键日常没有注册到 config.onetime_tasks')

    def test_every_sub_task_registered(self):
        missing = [cls.__name__ for cls, _ in DAILY_TASKS
                   if cls.__name__ not in self.registered]
        self.assertEqual([], missing, f'一键日常引用了未注册的任务: {missing}')

    def test_labels_unique(self):
        labels = [label for _, label in DAILY_TASKS]
        self.assertEqual(len(labels), len(set(labels)), '一键日常存在重名任务')

    def test_run_order_is_expected(self):
        """固定执行顺序，改顺序时这条会提醒你同步改文档和说明。"""
        expected = [
            '每日签到', '领取铜币', '任务集会所', '积分赛', '好友体力赠送与收取',
            '排行榜点赞', '组织祈福', '小队突袭', '领取一乐拉面', '精英副本',
            '招募', '丰饶之间', '每日分享', '每日活跃奖励',
        ]
        self.assertEqual(expected, [label for _, label in DAILY_TASKS])

    def test_dev_only_tasks_not_shipped(self):
        """开发 / 演示用任务不应出现在正式包里。

        若确实要把它们放出来，请连同这条用例一起改掉。
        """
        for name in ('TestTask', 'DebugSendKeyTask', 'DebugKeyTask', 'MyOneTimeTask'):
            self.assertNotIn(name, self.registered,
                             f'{name} 是开发/演示用任务，不应注册到发布版 config')


class TestPackagingConfig(unittest.TestCase):
    """打包配置的完整性。

    踩过的坑：pyappify 的 apply_profile_inheritance() 只从 profiles[0] 继承字段：
        if profile.requires_python.is_empty():
            profile.requires_python = first_profile.requires_python.clone()
    后面的 profile 可以省略字段，但**第一条必须写全**。
    当时把带全字段的 China profile 注释掉、只留精简版 Global，
    于是 Global 成了 profiles[0] 且 requires_python 为空，
    GitHub Actions 卡在「安装 Python」失败，白白发了一次版。
    """

    # profiles[0] 必须显式给出的字段（空值就等于没配）
    REQUIRED_FIRST_PROFILE_FIELDS = (
        'name', 'git_url', 'main_script', 'requirements',
        'requires_python', 'pip_args',
    )

    @classmethod
    def setUpClass(cls):
        path = os.path.join('pyappify.yml')
        if yaml is None:
            raise unittest.SkipTest('未安装 pyyaml，跳过打包配置检查')
        with open(path, encoding='utf-8') as f:
            cls.cfg = yaml.safe_load(f)

    def test_first_profile_is_complete(self):
        profiles = self.cfg.get('profiles') or []
        self.assertTrue(profiles, 'pyappify.yml 里没有任何 profile')
        first = profiles[0]
        missing = []
        for field in self.REQUIRED_FIRST_PROFILE_FIELDS:
            value = first.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(field)
        self.assertEqual(
            [], missing,
            f'pyappify.yml 的 profiles[0] 缺少必需字段 {missing}；'
            f'它不会从别的 profile 继承，缺失会导致打包失败',
        )

    def test_every_profile_declares_its_own_git_url(self):
        """每个 profile 必须**显式**写 git_url。

        pyappify 的 apply_profile_inheritance() 对空字段会继承 profiles[0]：
            if profile.git_url.is_empty() { profile.git_url = first_profile.git_url }
        如果 China profile 漏写 git_url，它会静默继承 Global 的
        GitHub 更新库地址 —— 包名还叫 China，更新源却指向 GitHub，
        国内镜像就白做了，而且很难发现。
        """
        for profile in self.cfg.get('profiles') or []:
            name = profile.get('name')
            url = profile.get('git_url')
            self.assertTrue(
                url and str(url).strip(),
                f'profile "{name}" 没有显式写 git_url；'
                f'它会继承 profiles[0] 的地址，可能导致更新源指错',
            )
            self.assertIn('://', str(url), f'profile "{name}" 的 git_url 不像个地址: {url!r}')

    def test_icon_files_exist(self):
        # pyappify-action 要求 icons/ 里同时有 icon.ico 和 icon.png
        for name in ('icons/icon.ico', 'icons/icon.png'):
            self.assertTrue(os.path.isfile(name), f'缺少图标文件 {name}')

    def test_license_file_present_and_is_agpl(self):
        """LICENSE 必须在，且确实是 AGPL-3.0 全文。

        AGPL 要求分发时附带许可证，所以 deploy.txt 里也要同步它。
        """
        self.assertTrue(os.path.isfile('LICENSE'), '缺少 LICENSE 文件')
        with open('LICENSE', encoding='utf-8') as f:
            text = f.read()
        self.assertIn('GNU AFFERO GENERAL PUBLIC LICENSE', text)
        self.assertIn('Version 3', text)
        # AGPL 区别于 GPL 的关键条款（通过网络提供服务也要提供源码）
        self.assertIn('Remote Network Interaction', text)
        # 许可证必须随代码一起分发给用户
        self.assertIn('LICENSE', open('deploy.txt', encoding='utf-8').read().split())

    def test_profile_names_unique(self):
        names = [p.get('name') for p in self.cfg.get('profiles') or []]
        self.assertEqual(len(names), len(set(names)), 'pyappify.yml 有重名 profile')

    def test_app_name_is_ascii(self):
        # pyappify 的 name 会进文件名，README 明确写了 English only
        name = self.cfg.get('name') or ''
        self.assertTrue(name.isascii(), f'pyappify.yml 的 name 必须是纯英文: {name!r}')


class TestWorkflowReleaseBody(unittest.TestCase):
    """Release 正文由工作流自动生成，这里守住它的接线不能断。

    背景：正文原来是手写的固定清单，而 pyappify 后来悄悄多产出了
    online-setup.exe 和 win32_sha256.txt —— 手写清单不知道，于是这两个
    文件在 Release 页面上被漏掉了很久。现在改成「枚举实际产物」生成，
    并加这个用例防止有人改回手写、或把接线改错。
    """

    WORKFLOW = os.path.join('.github', 'workflows', 'build.yml')

    @classmethod
    def setUpClass(cls):
        if yaml is None:
            raise unittest.SkipTest('没有 pyyaml，跳过工作流检查')
        with open(cls.WORKFLOW, encoding='utf-8') as f:
            cls.cfg = yaml.safe_load(f)
        cls.steps = cls.cfg['jobs']['build']['steps']
        cls.names = [s.get('name') for s in cls.steps]

    def _step(self, name):
        for s in self.steps:
            if s.get('name') == name:
                return s
        return None

    def test_run_tests_retries_once(self):
        """测试文件失败后必须自动重跑一次，两次都失败才判定失败。

        原因：TestMain 会拉起完整的 ok-script 栈（Qt + OCR），在 CI 上会偶发
        无声崩溃（连 "Ran N tests" 都不打印），重跑即过 —— v0.1.6 因此误拦过一次发布。
        重试一次消除环境偶发，确定性失败重跑仍会失败、照样被拦。
        """
        step = self._step('Run tests')
        self.assertIsNotNone(step, '缺少 Run tests 步骤')
        script = step['run']
        # 只看会执行的代码行：注释里解释了为什么重试，不该算数
        code = '\n'.join(ln for ln in script.splitlines() if not ln.strip().startswith('#'))
        self.assertIn('$maxAttempts', code, '没有重试次数变量')
        self.assertIn('$maxAttempts = 2', code, '重试次数应为 2（首次 + 重试 1 次）')
        self.assertIn('-le $maxAttempts', code, '没有用 $maxAttempts 控制循环')
        self.assertIn('failed, retrying', code, '没有输出重试提示')
        self.assertIn('after $maxAttempts attempts', code, '最终报错应说明尝试了几次')

    def test_run_tests_still_fails_on_persistent_failure(self):
        """重试不能把门禁变成"永远通过"：两次都失败必须 throw。"""
        step = self._step('Run tests')
        code = '\n'.join(ln for ln in step['run'].splitlines()
                         if not ln.strip().startswith('#'))
        self.assertIn('$failed +=', code, '没有累计失败文件')
        self.assertIn('throw "Tests failed in:', code, '两次都失败时没有中断构建')

    def test_generator_step_exists_and_precedes_release(self):
        self.assertIn('Build Release Body', self.names, '缺少生成 Release 正文的步骤')
        self.assertIn('Release', self.names)
        self.assertLess(
            self.names.index('Build Release Body'), self.names.index('Release'),
            '生成正文的步骤必须排在 Release 之前，否则 Release 读不到文件',
        )

    def test_release_uses_body_path_not_inline_body(self):
        rel = self._step('Release')['with']
        self.assertNotIn(
            'body', rel,
            'Release 又用回了手写的 body —— 手写清单会漏掉新产物，'
            '请改回 body_path: release_body.md',
        )
        self.assertEqual('release_body.md', rel.get('body_path'))

    def test_generator_gets_all_needed_env(self):
        gen = self._step('Build Release Body')
        self.assertEqual('pwsh', gen.get('shell'))
        missing = {'TAG', 'REPO', 'START_TAG', 'END_TAG', 'CHANGES'} - set(gen.get('env') or {})
        self.assertEqual(set(), missing, f'生成步骤缺少 env: {sorted(missing)}')

    def test_generator_enumerates_artifacts_instead_of_hardcoding(self):
        """必须枚举产物目录，且对认不出的产物有兜底文案。"""
        script = self._step('Build Release Body')['run']
        self.assertIn('Get-ChildItem', script, '生成脚本没有枚举产物目录')
        self.assertIn('pyappify_dist', script)
        self.assertIn(
            '待补充', script,
            '认不出的产物没有兜底说明，将来新增产物又会被静默漏掉',
        )
        # 写入必须显式无 BOM：PS 5.1 的 Out-File -Encoding utf8 会带 BOM，
        # BOM 混进 markdown 会影响渲染。
        # 只看真正会执行的代码行 —— 脚本注释里解释了为什么不用 Out-File，
        # 那几行不该算数（一开始就是这么误判的）。
        code_lines = [ln for ln in script.splitlines() if not ln.strip().startswith('#')]
        code = '\n'.join(code_lines)
        self.assertIn('UTF8Encoding($false)', code, '写入没有显式指定 UTF-8 无 BOM')
        self.assertNotIn(
            'Out-File', code,
            '又在代码里用了 Out-File -Encoding utf8（PS 5.1 会写 BOM），请用 WriteAllText',
        )


class TestDailyTaskHardening(unittest.TestCase):
    """一键日常里各任务的「重试 / 兜底」行为。

    这些是照着实战反馈加的：
      * 任务集会所接取失败 -> 回主页重跑，重试 2 次后跳过
      * 小队突袭 / 丰饶之间遇到「点击任意位置关闭」-> 点掉并退回主页面
      * 积分赛挑战失败 -> 重试一次
      * 组织祈福点 team_coinpray -> 隔 2 秒重试，最多 3 次
    用例守的是常量和接口约定，避免以后被无声改掉。
    """

    def test_click_anywhere_patterns(self):
        """关键词要能命中常见写法，又不能误命中普通按钮文字。"""
        for text in ('点击任意位置关闭', '任意位置关闭', '点击任意位置继续', '请点击任意位置关闭'):
            self.assertTrue(
                any(p.search(text) for p in CLICK_ANYWHERE_PATTERNS),
                f'「{text}」应该被识别为「任意位置关闭」提示',
            )
        for text in ('点击任意对手', '任意门', '关闭', '确定', '挑战', '确定'):
            self.assertFalse(
                any(p.search(text) for p in CLICK_ANYWHERE_PATTERNS),
                f'「{text}」不该被当成「任意位置关闭」提示（会误点）',
            )

    def test_page_nav_exposes_click_anywhere_helpers(self):
        for name in ('find_click_anywhere', 'dismiss_click_anywhere'):
            self.assertTrue(callable(getattr(PageNavTask, name, None)),
                            f'PageNavTask 缺少 {name}')

    def test_tasks_that_need_page_nav_inherit_it(self):
        """要退回主页面的任务必须继承 PageNavTask（或它的子类）。"""
        for cls in (MissionTask, TeamFightTask, CoinOrginTask, QianDaoTask):
            self.assertTrue(
                issubclass(cls, PageNavTask),
                f'{cls.__name__} 需要 back_to_main / dismiss_click_anywhere，'
                f'必须继承 PageNavTask',
            )

    def test_mission_two_phase_flow(self):
        """任务集会所：先只领奖励，再专门进去接取；接取最多 3 次（首次 + 重试 2 次）。

        用户指定的流程：
            第 1 次进入：只领取奖励，然后回主页面
            第 2 次进入：接取（尝试 1）-> 没接到就回主页重进（尝试 2）（尝试 3）
            3 次都没接到 -> 判定为异常并跳过
        """
        self.assertEqual(3, ACCEPT_ATTEMPTS, '接取应最多尝试 3 次（首次 + 重试 2 次）')
        for name in ('enter_mission_hall', 'exit_mission_hall', 'accept_missions'):
            self.assertTrue(callable(getattr(MissionTask, name, None)),
                            f'缺少 {name}（流程被拆成这几步）')
        with open('src/tasks/mission_task.py', encoding='utf-8') as f:
            src = f.read()
        run_body = src.split('def enter_mission_hall')[0]      # 只看 run()
        # 阶段 1：先只领奖
        self.assertIn('只领取奖励', run_body, '没有"第 1 次进入只领奖"这一步')
        # 阶段 2：接取循环受 ACCEPT_ATTEMPTS 控制
        self.assertIn('range(1, ACCEPT_ATTEMPTS + 1)', run_body,
                      '接取没有按 ACCEPT_ATTEMPTS 重试')
        # 每次失败都要回主页面重新进入
        self.assertIn('back_to_main(', run_body, '失败后没有回主页面')
        self.assertIn('enter_mission_hall()', run_body, '没有重新进入任务集会所')
        # 3 次都不行要判为异常并跳过
        self.assertIn('判定为异常', run_body, '没有"判为异常并跳过"的收尾')
        # 不应该再有旧的一次性 run_once
        self.assertNotIn('def run_once', src, '旧的 run_once 应该已经被拆掉')

    def test_pointrace_entry_retry(self):
        """积分赛：没检测到并点到「挑战」时，回主页面重进，只重试一次。"""
        self.assertEqual(1, ENTRY_RETRY, '积分赛进入失败应只重试 1 次')
        with open('src/tasks/pointrace_task.py', encoding='utf-8') as f:
            src = f.read()
        self.assertIn('ENTRY_RETRY', src)
        self.assertIn('ensure_opponent_screen()', src)
        # 重试循环必须存在并受 ENTRY_RETRY 控制
        self.assertIn('range(ENTRY_RETRY + 1)', src,
                      '没有用 ENTRY_RETRY 控制进入重试')

    def test_pointrace_challenge_retry(self):
        self.assertEqual(1, CHALLENGE_RETRY, '积分赛挑战失败应额外重试 1 次')
        self.assertTrue(callable(getattr(PointRaceTask, 'wait_challenge_result', None)))

    def test_pointrace_returns_to_opponent_screen(self):
        """一场打完后游戏会退回 pointrace_challenge 界面，必须再点一次它
        才能展开对手列表（pointrace_personalpower 才会出现）。

        原来只在「当下恰好匹配到 pointrace_challenge」时才点，画面还在切换时
        两个模板都匹配不到 -> 读战力失败 -> break 掉整个循环，剩下的挑战全丢。
        现在统一走 ensure_opponent_screen()，这里守两件事：
        """
        self.assertTrue(callable(getattr(PointRaceTask, 'ensure_opponent_screen', None)),
                        '缺少 ensure_opponent_screen')
        with open('src/tasks/pointrace_task.py', encoding='utf-8') as f:
            src = f.read()
        self.assertIn('ensure_opponent_screen()', src, 'run() 里没有调用 ensure_opponent_screen()')

    def test_windows_config_has_no_exe_filter(self):
        """windows 段不能出现 exe/title 过滤。

        ok-script 的 DeviceManager.update_capture() 只要看到这些键就会
        reset_selected_hwnd，并把 preferred 改写成 pc_<hwnd> 窗口设备
        （device=windows, capture=windows）—— 后果是每次进设置都要重选设备，
        而且失去 ipc（点击落不到游戏上）。代价远大于「列表好看一点」。
        """
        win = app_config.config.get('windows') or {}
        for key in ('exe', 'title', 'hwnd_class', 'top_hwnd_class', 'selected_hwnd'):
            self.assertNotIn(
                key, win,
                f'windows 段出现了 {key}：会触发 update_capture 重置设备选择，'
                f'导致每次都要重选模拟器设备、并失去 ipc',
            )

    def test_coinpray_retry(self):
        self.assertEqual(3, COINPRAY_ATTEMPTS, 'team_coinpray 应最多点 3 次')
        self.assertEqual(2.0, COINPRAY_INTERVAL, 'team_coinpray 重试间隔应为 2 秒')

    def test_coinorgin_and_teamfight_call_click_anywhere(self):
        """两个任务都要真的调用 dismiss_click_anywhere，不能只是声明。"""
        for rel in ('src/tasks/coinorgin_task.py', 'src/tasks/teamfight_task.py'):
            with open(rel, encoding='utf-8') as f:
                src = f.read()
            self.assertIn('dismiss_click_anywhere()', src,
                          f'{rel} 没有调用 dismiss_click_anywhere()')


class TestGuideEntry(unittest.TestCase):
    """「指南」入口重构（src/tasks/guide_nav.py）。

    背景：每个玩家的主页面背景都不同，直接匹配 main_team / main_mission /
    main_pointrace 这些主页图标经常失败。改成统一走「指南」列表：
    点 main_guide -> 在固定锚点滑动找 guide_xxx -> 点它 -> 点 guide_xxxgo。

    这个重构牵动 5 个任务 + 1 个组织祈福新入口，容易漏改，所以固化成用例。
    """

    # 任务 -> (条目模板, 前往按钮模板)，必须和任务文件里的常量一致
    GUIDE_TASKS = {
        'mission_task': ('guide_mission', 'guide_missiongo'),
        'ranklist_task': ('guide_ranklist', 'guide_ranklistgo'),
        'pointrace_task': ('guide_pointrace', 'guide_pointracego'),
        'teamfight_task': ('guide_teamfight', 'guide_teamfightgo'),
        'coinorgin_task': ('guide_coinorign', 'guide_coinorigngo'),
    }

    def test_guide_constants(self):
        """滑动手势是需求里明确规定的两条固定起止线。"""
        from src.tasks.guide_nav import GUIDE_CANCEL, GUIDE_ENTRY
        self.assertEqual('main_guide', GUIDE_ENTRY)
        self.assertEqual('guide_cancel', GUIDE_CANCEL)
        self.assertAlmostEqual(0.100, GUIDE_SCROLL_X, places=3)
        # 往下找：按住 0.777 滑到 0.325
        self.assertAlmostEqual(0.777, GUIDE_SCROLL_DOWN_FROM_Y, places=3)
        self.assertAlmostEqual(0.325, GUIDE_SCROLL_DOWN_TO_Y, places=3)
        # 往上找：按住 0.325 滑到 0.777
        self.assertAlmostEqual(0.325, GUIDE_SCROLL_UP_FROM_Y, places=3)
        self.assertAlmostEqual(0.777, GUIDE_SCROLL_UP_TO_Y, places=3)
        # 两个方向各最多 20 次
        self.assertEqual(20, GUIDE_SCROLL_MAX)
        # 往下找 = 手指往上拖（终点 y 更小）；往上找相反
        self.assertLess(GUIDE_SCROLL_DOWN_TO_Y, GUIDE_SCROLL_DOWN_FROM_Y,
                        '往下找必须是手指往上拖（终点 y 更小）')
        self.assertGreater(GUIDE_SCROLL_UP_TO_Y, GUIDE_SCROLL_UP_FROM_Y,
                           '往上找必须是手指往下拖（终点 y 更大）')

    def test_all_guide_tasks_inherit_and_declare_matching_templates(self):
        import importlib
        for mod_name, (item, go) in self.GUIDE_TASKS.items():
            mod = importlib.import_module(f'src.tasks.{mod_name}')
            self.assertEqual(item, mod.GUIDE_ITEM,
                             f'{mod_name}.GUIDE_ITEM 应为 {item}')
            self.assertEqual(go, mod.GUIDE_GO,
                             f'{mod_name}.GUIDE_GO 应为 {go}')
            # 拿到 enter_guide 才可能走指南入口
            cls = next(
                v for k, v in vars(mod).items()
                if isinstance(v, type) and k.endswith('Task') and k != 'GuideNavTask'
            )
            self.assertTrue(issubclass(cls, GuideNavTask),
                            f'{cls.__name__} 必须继承 GuideNavTask 才能用 enter_guide')
            with open(f'src/tasks/{mod_name}.py', encoding='utf-8') as f:
                src = f.read()
            self.assertIn('enter_guide(', src,
                          f'{mod_name} 没有调用 enter_guide()，入口没真正改过来')
            # 旧的主页图标入口不应该还在用
            self.assertNotIn(f"swipe_find('main_", src,
                             f'{mod_name} 还在用 swipe_find 找 main_* 入口，应改走指南')

    def test_teampray_uses_ocr_entry(self):
        """组织祈福入口：OCR 找「组织祈福」，点它正下方的「立刻前往」。

        原来是找 reward_teampray 模板再点它下方的按钮，改成 OCR 认文字
        （列表条目本身就是文字，比模板稳）；模板保留作兜底。
        """
        import src.tasks.team_praytask as tp
        self.assertEqual('main_reward', tp.REWARD_ENTRY)
        self.assertEqual('组织祈福', tp.TEAMPRAY_TEXT)
        self.assertEqual('立刻前往', tp.GO_TEXT)
        self.assertEqual('reward_teampray', tp.TEAMPRAY_ITEM, '模板应保留作兜底')
        self.assertTrue(issubclass(tp.TeamPrayTask, GuideNavTask))
        with open('src/tasks/team_praytask.py', encoding='utf-8') as f:
            src = f.read()
        self.assertIn('enter_teampray', src)
        self.assertIn('click_below(', src, '没有用 click_below 点条目正下方的按钮')
        # OCR 优先、模板兜底
        finder = src.split('def find_teampray_on_screen')[1]
        self.assertLess(finder.index('self.ocr('), finder.index('_safe_find_one('),
                        'find_teampray_on_screen 应该先 OCR 再退回模板')
        self.assertIn('TEAMPRAY_PATTERN', src)
        self.assertNotIn("swipe_find('main_team'", src, '还在用旧的 main_team 入口')

    def test_share_retries_once(self):
        """每日分享失败后要退回主页面重试一次。

        一键日常跑的就是同一个 ShareTask，所以这里实现了，
        「一键日常里的每日分享」也就一起有了重试。
        """
        from src.tasks.share_task import SHARE_RETRY, ShareTask
        from src.tasks.page_nav import PageNavTask
        self.assertEqual(1, SHARE_RETRY, '每日分享应重试 1 次')
        # 重试需要"退回主页面"的能力
        self.assertTrue(issubclass(ShareTask, PageNavTask),
                        'ShareTask 必须继承 PageNavTask 才能 back_to_main')
        self.assertTrue(callable(getattr(ShareTask, 'run_once', None)))
        self.assertTrue(callable(getattr(ShareTask, 'should_stop', None)))
        with open('src/tasks/share_task.py', encoding='utf-8') as f:
            src = f.read()
        run_body = src.split('def run_once')[0]
        self.assertIn('range(SHARE_RETRY + 1)', run_body, '没有按 SHARE_RETRY 重试')
        self.assertIn('back_to_main(', run_body, '重试前没有退回主页面')
        self.assertIn('should_stop(', run_body, '没有响应停止')

    def test_guide_scroll_stays_inside_list(self):
        """滑动的起止点必须落在列表范围内。

        这是实测踩过的坑：手指滑出列表区域，手势就不生效
        （表现是"按住往下滑没办法正常滚动"）。现在用的是需求里给定的两条固定线，
        这里直接从标注里算出列表范围来校验它们。
        """
        coco = json.load(open(COCO_PATH, encoding='utf-8'))
        cats = {c['id']: c['name'] for c in coco['categories']}
        imgs = {i['id']: i for i in coco['images']}
        centers = {}
        for a in coco['annotations']:
            name = cats[a['category_id']]
            if name in ('guide_listtop', 'guide_listbottom'):
                img = imgs[a['image_id']]
                _, y, _, h = a['bbox']
                centers[name] = (y + h / 2) / img['height']

        self.assertIn('guide_listtop', centers, '缺少 guide_listtop 标注，无法判断列表范围')
        self.assertIn('guide_listbottom', centers, '缺少 guide_listbottom 标注')
        top = centers['guide_listtop']
        bottom = centers['guide_listbottom']
        self.assertLess(top, bottom, 'guide_listtop 应该在 guide_listbottom 上面')

        for label, y in (
            ('往下找起点', GUIDE_SCROLL_DOWN_FROM_Y),
            ('往下找终点', GUIDE_SCROLL_DOWN_TO_Y),
            ('往上找起点', GUIDE_SCROLL_UP_FROM_Y),
            ('往上找终点', GUIDE_SCROLL_UP_TO_Y),
        ):
            self.assertGreaterEqual(y, top, f'{label} {y:.3f} 超出了列表上边缘 {top:.3f}')
            self.assertLessEqual(y, bottom, f'{label} {y:.3f} 超出了列表下边缘 {bottom:.3f}')

    def test_guide_entry_uses_ocr(self):
        """五个任务都要用 OCR 文字进指南，模板只作兜底。

        改用 OCR 的原因：列表条目本身就是文字，OCR 认文字比模板匹配直接，
        也不受标注质量影响。模板保留作 fallback（两条路都有更稳）。
        """
        import importlib
        expected = {
            'mission_task': '任务集会所',
            'ranklist_task': '排行榜',
            'pointrace_task': '积分赛',
            'teamfight_task': '小队突袭',
            'coinorgin_task': '丰饶之间',
        }
        for mod_name, text in expected.items():
            mod = importlib.import_module(f'src.tasks.{mod_name}')
            self.assertEqual(text, getattr(mod, 'GUIDE_TEXT', None),
                             f'{mod_name} 的 OCR 目标文字应为「{text}」')
            with open(f'src/tasks/{mod_name}.py', encoding='utf-8') as f:
                src = f.read()
            self.assertIn('enter_guide(GUIDE_TEXT', src,
                          f'{mod_name} 没有用 OCR 文字调 enter_guide')
            self.assertIn('item_feature=GUIDE_ITEM', src,
                          f'{mod_name} 没有把模板作为兜底传进去')
        # enter_guide 内部要先用 OCR 找条目，找不到才退回模板
        with open('src/tasks/guide_nav.py', encoding='utf-8') as f:
            gsrc = f.read()
        on_screen = gsrc.split('def find_entry_on_screen')[1].split('def _sweep_entry')[0]
        self.assertLess(on_screen.index('self.ocr('), on_screen.index('_safe_find_one('),
                        'find_entry_on_screen 应该先 OCR，再退回模板')
        self.assertIn('GO_TEXT_PATTERN', gsrc, '「前往」没有 OCR 兜底')

    def test_guide_stops_at_list_bounds(self):
        """列表两端的判据用 OCR 认条目文字（用户指定）。

        OCR 到「装备」      => 已在列表顶部
        OCR 到「忍具锻造」  => 已在列表底部
        模板 guide_listtop / guide_listbottom 只作兜底（那两个标记很小，
        滑过头就露不全、匹配不到）。
        """
        from src.tasks.guide_nav import GUIDE_BOTTOM_TEXT, GUIDE_TOP_TEXT
        self.assertEqual('装备', GUIDE_TOP_TEXT)
        self.assertEqual('忍具锻造', GUIDE_BOTTOM_TEXT)
        self.assertEqual('guide_listtop', GUIDE_LISTTOP)
        self.assertEqual('guide_listbottom', GUIDE_LISTBOTTOM)
        with open('src/tasks/guide_nav.py', encoding='utf-8') as f:
            src = f.read()
        # 两个判据都要先 OCR、再退回模板
        top_body = src.split('def at_guide_top')[1].split('def at_guide_bottom')[0]
        self.assertIn('_ocr_has(GUIDE_TOP_PATTERN)', top_body)
        self.assertLess(top_body.index('_ocr_has('), top_body.index('_safe_find_one('),
                        'at_guide_top 应该先 OCR 再退回模板')
        bottom_body = src.split('def at_guide_bottom')[1].split('def _warn_if_bounds')[0]
        self.assertIn('_ocr_has(GUIDE_BOTTOM_PATTERN)', bottom_body)
        self.assertLess(bottom_body.index('_ocr_has('), bottom_body.index('_safe_find_one('),
                        'at_guide_bottom 应该先 OCR 再退回模板')

    def test_stop_is_detected_for_both_stop_buttons(self):
        """两个「停止」入口都要能被检测到。

        ok-script 的停止有两条完全不同的路：
          * 任务卡片：TaskCard.stop_clicked() -> task.disable() + unpause()
                     只置 _enabled=False，不动 exit_event
          * 设备/截图页：executor.stop() -> exit_event.set()
        只查 exit_is_set() 会漏掉任务栏那个 —— 那正是「在一键日常那栏点了停止
        却还在继续操作」的原因。
        """
        from src.tasks.page_nav import _task_disabled
        with open('src/tasks/page_nav.py', encoding='utf-8') as f:
            src = f.read()
        body = src.split('def stop_requested')[1].split('def should_stop')[0]
        self.assertIn('exit_is_set()', body, '没有检查 executor 级别的停止')
        self.assertIn('_task_disabled', body, '没有检查任务被 disable 的情况')

        class _T:
            def __init__(self, enabled):
                self.enabled = enabled

        self.assertFalse(_task_disabled(_T(True)))
        self.assertTrue(_task_disabled(_T(False)))

    def test_subtask_does_not_mistake_its_own_disabled_for_stop(self):
        """子任务不能因为自己 _enabled=False 就被当成"已停止"。

        一键日常是直接调子任务 run() 的，子任务实例通常从未被单独启用过，
        _enabled 一直是 False。无脑把 False 当停止信号的话，
        子任务会一上来就判定"已停止"、什么都不做。
        """
        with open('src/tasks/page_nav.py', encoding='utf-8') as f:
            body = f.read().split('def stop_requested')[1].split('def should_stop')[0]
        self.assertIn('_parent_task', body, '子任务没有走父任务判断')
        self.assertIn('_saw_enabled', body, '缺少 _saw_enabled 兜底')

    def test_daily_checks_stop_and_registers_parent(self):
        """一键日常每轮查停止；并把父任务登记给子任务。"""
        with open('src/tasks/daily_task.py', encoding='utf-8') as f:
            src = f.read()
        run_body = src.split('def run_sub_task')[0]
        self.assertIn('should_stop(', run_body, '一键日常没有检查停止')
        self.assertIn('_parent_task = self', src,
                      '没有把父任务登记给子任务，子任务无法感知停止')
        # 停止后不应该再去做收尾的"回到主页面"（用户已经要停了，别再操作游戏）
        self.assertIn('已停止', run_body)

    def test_long_loops_check_stop(self):
        """耗时最长的几个循环必须查停止，否则点了停止要等很久才停。"""
        for rel, where in (
            ('src/tasks/coinorgin_task.py', '战斗循环'),
            ('src/tasks/guide_nav.py', '指南滑动'),
            ('src/tasks/mission_task.py', '任务集会所接取'),
            ('src/tasks/pointrace_task.py', '积分赛挑战'),
            ('src/tasks/team_praytask.py', '组织祈福领奖'),
        ):
            with open(rel, encoding='utf-8') as f:
                src = f.read()
            self.assertIn(f"should_stop('{where}')", src,
                          f'{rel} 的{where}没有检查停止')

    def test_guide_detects_no_movement(self):
        """「画面没动」的检测在 _sweep_entry 里，两个方向共用；且要配合模板判据。"""
        from src.tasks.guide_nav import GuideNavTask
        self.assertTrue(callable(getattr(GuideNavTask, 'list_thumb', None)))
        self.assertTrue(callable(getattr(GuideNavTask, 'list_moved', None)))
        with open('src/tasks/guide_nav.py', encoding='utf-8') as f:
            src = f.read()
        sweep = src.split('def _sweep_entry')[1].split('def click_below')[0]
        self.assertIn('list_moved(', sweep, '_sweep_entry 里没有"画面没动"的检测')
        self.assertIn('to_bottom', sweep, '_sweep_entry 没有按方向区分')
        find_body = src.split('def find_entry_in_guide')[1].split('def find_entry_on_screen')[0]
        self.assertEqual(2, find_body.count('self._sweep_entry('),
                         'find_entry_in_guide 应该对两个方向各调一次 _sweep_entry')

    def test_guide_scroll_interval_is_one_second(self):
        """每次滑动之间要留足 1 秒。

        列表松手后还会惯性滚一会儿，间隔太短时画面还在动就去做模板匹配，
        会出现「明明画面里已经有要找的模板，却判定成没找到」的假失败
        （实测 0.6 秒时偶发）。这个值同时也是两次滑动之间的间隔。
        """
        from src.tasks.guide_nav import GUIDE_SCROLL_AFTER, GUIDE_SCROLL_SETTLE
        self.assertGreaterEqual(GUIDE_SCROLL_AFTER, 1.0,
                                f'松手后只等 {GUIDE_SCROLL_AFTER}s，太短会漏匹配')
        self.assertGreater(GUIDE_SCROLL_SETTLE, 0, '终点按住时间应为正')
        # gesture() 必须把 after 传下去，不能只写在常量里没人用
        with open('src/tasks/guide_nav.py', encoding='utf-8') as f:
            src = f.read()
        gesture_body = src.split('def gesture')[1].split('def at_guide_top')[0]
        self.assertIn('after_sleep=after', gesture_body,
                      'gesture() 没有把间隔传给 swipe，常量等于没用')

    def test_guide_boundary_only_uses_templates(self):
        """边界只能由 guide_listtop / guide_listbottom 判定。

        「画面没动」**不算**到达边界 —— 它只说明这一下手势没生效
        （滑到列表外面 / 被动画吃掉）。如果把它当成"到头了"，
        会把明明还能滚的列表判死、漏掉目标。
        正确做法：画面没动又没有边界标志时，判为"滑动出问题"，
        记 error 并重试；连续多次才放弃这个方向。
        """
        from src.tasks.guide_nav import GUIDE_STUCK_TOLERANCE
        self.assertGreaterEqual(GUIDE_STUCK_TOLERANCE, 1)
        with open('src/tasks/guide_nav.py', encoding='utf-8') as f:
            src = f.read()
        sweep = src.split('def _sweep_entry')[1].split('def click_below')[0]
        # 判定边界时必须看模板
        self.assertIn('at_guide_bottom()', sweep)
        self.assertIn('at_guide_top()', sweep)
        # 画面没动但没边界标志 -> 判为滑动出问题（error），而不是边界
        self.assertIn('滑动出问题', sweep)
        self.assertIn('log_error', sweep)
        # 不能出现"没动就直接 return/break 说已到头"的写法
        self.assertNotIn('画面没有变化（已到', sweep,
                         '不能把"画面没动"直接当成已到边界')
        # 找遍全程：两个方向都要扫
        find_body = src.split('def find_entry_in_guide')[1].split('def find_entry_on_screen')[0]
        self.assertEqual(2, find_body.count('_sweep_entry('),
                         'find_entry_in_guide 应该对两个方向各调一次 _sweep_entry')

    def test_combat_click_verify_covers_all_buttons(self):
        """战斗点击验证：间隔 6 秒，且包含通灵/密卷。"""
        from src.tasks.debug_combat_click import CLICK_INTERVAL, CLICK_ORDER
        self.assertEqual(6.0, CLICK_INTERVAL)
        for name in ('普攻', '一技能', '二技能', '大招', '替身', '密卷', '通灵'):
            self.assertIn(name, CLICK_ORDER, f'战斗点击验证缺少 {name}')

    def test_share_waits_longer_for_personal_share(self):
        """每日分享等 personal_share 的时间放宽到 15 秒。"""
        import src.tasks.share_task as st
        self.assertEqual(15, st.PERSONAL_SHARE_TIMEOUT)
        self.assertGreater(st.PERSONAL_SHARE_TIMEOUT, 5, '应比原来的 5 秒更长')


class TestNoUndefinedConstants(unittest.TestCase):
    """静态找出「用了但没定义」的全大写常量。

    踩过的坑：team_praytask 里函数体用了 REWARD_GO_TIMEOUT，常量块里却只有
    REWARD_ITEM_TIMEOUT —— import 不报错、编译不报错，**只在一键日常跑到那一步
    才抛 NameError**（用户实测才发现的）。这类错误用 ast 就能查出来。

    做法：把每个任务模块里所有形如 XXX_YYY 的大写名字收集起来，
    凡是在函数体里被读取、但模块全局里没有定义、也不是参数/局部变量的，就报出来。
    """

    UPPER_RE = re.compile(r'^[A-Z][A-Z0-9_]{2,}$')

    def _module_level_names(self, tree):
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    # 注意要用 walk：像 `A, B = 0.05, 0.30` 这种元组赋值，
                    # 目标是 ast.Tuple 而不是 ast.Name，只看 Name 会漏掉
                    # （一开始就是这么误报了 GUIDE_LIST_SIG_* ）
                    for sub in ast.walk(t):
                        if isinstance(sub, ast.Name):
                            names.add(sub.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.asname or a.name.split('.')[0])
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names.add(node.name)
        return names

    def _local_names(self, func):
        names = set()
        for a in list(func.args.args) + list(func.args.kwonlyargs) + list(func.args.posonlyargs):
            names.add(a.arg)
        if func.args.vararg:
            names.add(func.args.vararg.arg)
        if func.args.kwarg:
            names.add(func.args.kwarg.arg)
        for node in ast.walk(func):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                names.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.asname or a.name.split('.')[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                names.add(node.name)
            elif isinstance(node, (ast.comprehension,)):
                for t in ast.walk(node.target):
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
        return names

    def test_task_modules_have_no_undefined_constants(self):
        import builtins
        problems = []
        modules = sorted(glob.glob(os.path.join('src', '**', '*.py'), recursive=True))
        self.assertTrue(modules, '没找到任何 src 下的模块')
        for path in modules:
            with open(path, encoding='utf-8') as f:
                src = f.read()
            tree = ast.parse(src, filename=path)
            global_names = self._module_level_names(tree) | set(dir(builtins))
            for func in [n for n in ast.walk(tree)
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                known = global_names | self._local_names(func)
                for node in ast.walk(func):
                    if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
                        continue
                    if not self.UPPER_RE.match(node.id):
                        continue          # 只查全大写的常量名
                    if node.id not in known:
                        problems.append(f'{path}:{node.lineno} {func.name}() 用了未定义的常量 {node.id}')
        self.assertEqual([], problems,
                         '有常量被使用但没有定义（运行时才会抛 NameError）:\n  '
                         + '\n  '.join(problems))


if __name__ == '__main__':
    unittest.main()
