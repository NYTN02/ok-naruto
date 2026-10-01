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

import src.config as app_config
from src.tasks.combat_ui import (
    CORE_BUTTONS,
    DEFAULT_LAYOUT,
    LAYOUT_PROFILES,
    layout_to_config,
    parse_layout,
)
from src.tasks.daily_task import DAILY_TASKS, DailyTask
from src.tasks.page_nav import CANCEL_FEATURES, MAIN_PAGE_FEATURE

COCO_PATH = os.path.join('assets', 'coco_annotations.json')

# 「回到主页面」和日常任务入口依赖的关键模板，缺一个就会在运行时才炸
REQUIRED_FEATURES = [
    MAIN_PAGE_FEATURE,      # main_adventure
    'main_coinorign',       # 丰饶之间入口
    'main_coin_icon',       # 铜币
    'coin_freetoget',
    'coin_cancel',
    'popu_cancel',
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
            '领取铜币', '任务集会所', '积分赛', '好友体力赠送与收取', '排行榜点赞',
            '组织祈福', '小队突袭', '领取一乐拉面', '精英副本', '招募',
            '丰饶之间', '每日分享', '每日活跃奖励',
        ]
        self.assertEqual(expected, [label for _, label in DAILY_TASKS])

    def test_dev_only_tasks_not_shipped(self):
        """开发 / 演示用任务不应出现在正式包里。

        若确实要把它们放出来，请连同这条用例一起改掉。
        """
        for name in ('TestTask', 'DebugSendKeyTask', 'DebugKeyTask', 'MyOneTimeTask'):
            self.assertNotIn(name, self.registered,
                             f'{name} 是开发/演示用任务，不应注册到发布版 config')


if __name__ == '__main__':
    unittest.main()
