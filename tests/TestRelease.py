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

import json
import os
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
from src.tasks.mission_task import MAX_ACCEPT_RETRY, MissionTask
from src.tasks.page_nav import (
    CANCEL_FEATURES,
    CLICK_ANYWHERE_PATTERNS,
    MAIN_PAGE_FEATURE,
    PageNavTask,
)
from src.tasks.pointrace_task import CHALLENGE_RETRY, PointRaceTask
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

    def test_mission_accept_retry(self):
        self.assertEqual(2, MAX_ACCEPT_RETRY, '任务集会所接取失败应重试 2 次')
        for name in ('run_once', 'accept_one_mission'):
            self.assertTrue(callable(getattr(MissionTask, name, None)), f'缺少 {name}')

    def test_pointrace_challenge_retry(self):
        self.assertEqual(1, CHALLENGE_RETRY, '积分赛挑战失败应额外重试 1 次')
        self.assertTrue(callable(getattr(PointRaceTask, 'wait_challenge_result', None)))

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


if __name__ == '__main__':
    unittest.main()
