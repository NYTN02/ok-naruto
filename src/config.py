import os

import numpy as np
from ok import ConfigOption

version = "dev"
#不需要修改version, Github Action打包会自动修改

app_profile = os.environ.get("PYAPPIFY_APP_PROFILE", "")
gui_config = {
    'type': 'web' if app_profile.casefold() == 'web' else 'qt',
    'window_size': {
        'width': 1200,
        'height': 800,
        'min_width': 600,
        'min_height': 450,
    },
}
if gui_config['type'] == 'web':
    gui_config['launch_mode'] = 'pywebview'

key_config_option = ConfigOption('Game Hotkey Config', { #全局配置示例
    'Echo Key': 'q',
    'Liberation Key': 'r',
    'Resonance Key': 'e',
    'Tool Key': 't',
}, description='In Game Hotkey for Skills')

combat_keys_config = ConfigOption(
    '火影忍者手游键位',
    {
        '一技能': 'j',        # 一技能
        '二技能': 'k',        # 二技能
        '大招': 'l',       # 大招
        '普攻': 'u',  # 普攻
        '替身': 'h',   # 替身
        '密卷': 'i',  # 密卷
        '通灵': 'o',         # 通灵
        '上': 'w',        # 上
        '下': 's',      # 下
        '左': 'a',      # 左
        '右': 'd',     # 右
    },
    description='火影忍者战斗键位（需与 MuMu 键鼠映射一致）填单个字母或数字。特殊键请用英文单词：空格=space，回车=enter，Esc=esc，Shift=shift，Tab=tab'
)

combat_layout_config = ConfigOption(
    '火影忍者战斗布局',
    {
        '玩法': '自动',
        '普攻': '0.878,0.752',
        '一技能': '0.733,0.558',
        '二技能': '0.714,0.851',
        '大招': '0.891,0.424',
        '替身': '0.672,0.878',
        '密卷': '0.940,0.233',
        '通灵': '0.941,0.380',
        '方向键': '0.175,0.767',
    },
    description='战斗按钮布局。'
                '「玩法」填 自动/副本/练习场 —— 自动时会用圆形识别判断当前是哪种 HUD；'
                '不同玩法布局不同，填错会导致点击落在背景上、游戏没反应。'
                '其余键是按钮中心的相对坐标，格式 "x,y"，取值 0~1（相对屏幕宽高），'
                '默认值实测自 1600x900 丰饶之间（副本）。'
                '需要校准时先跑「战斗按钮校准」任务，看 debug_output/combat_layout_calib.png 再微调这里。'
)

def make_bottom_right_black(frame): #可选. 某些游戏截图时遮挡UID使用
    """
    Changes a portion of the frame's pixels at the bottom right to black.

    Args:
        frame: The input frame (NumPy array) from OpenCV.

    Returns:
        The modified frame with the bottom-right corner blackened.  Returns the original frame
        if there's an error (e.g., invalid frame).
    """
    try:
        height, width = frame.shape[:2]  # Get height and width

        # Calculate the size of the black rectangle
        black_width = int(0.13 * width)
        black_height = int(0.025 * height)

        # Calculate the starting coordinates of the rectangle
        start_x = width - black_width
        start_y = height - black_height

        # Create a black rectangle (NumPy array of zeros)
        black_rect = np.zeros((black_height, black_width, frame.shape[2]), dtype=frame.dtype)  # Ensure same dtype

        # Replace the bottom-right portion of the frame with the black rectangle
        frame[start_y:height, start_x:width] = black_rect

        return frame
    except Exception as e:
        print(f"Error processing frame: {e}")
        return frame

config = {
    'custom_tasks':True, # enable creating and editing custom tasks
    'debug': False,  # Optional, default: False
    'gui': gui_config,
    'config_folder': 'configs', #最好不要修改
    'global_configs': [key_config_option, combat_keys_config, combat_layout_config],
    # 'screenshot_processor': make_bottom_right_black, # 在截图的时候对frame进行修改, 可选
    'gui_icon': 'icons/icon.png', #窗口图标, 最好不需要修改文件名
    'wait_until_before_delay': 0,
    'wait_until_check_delay': 0,
    'wait_until_settle_time': 0, #调用 wait_until时候, 在第一次满足条件的时候, 会等待再次检测, 以避免某些滑动动画没到预定位置就在动画路径中被检测到
    'ocr': { #可选, 使用的OCR库
        'lib': 'onnxocr',
        'auto_simplify': True, #自动繁体转简体, 需要ppocrv5等可以识别繁体的库
        'params': {
            'use_openvino': True,
        }
    },
    'windows': {
    'interaction': ['PyDirect', 'Genshin', 'Pynput', 'PostMessage', 'ForegroundPostMessage'],
    'capture_method': ['WGC', 'BitBlt_RenderFull', 'BitBlt'],
    'check_hdr': False,
    'force_no_hdr': False,
    'require_bg': True
    },
    'adb': {  # 模拟器或Android设备请填写此设置, mumu模拟器使用原生截图和input,速度极快. 其他模拟器和真机使用adb,截图速度较慢
        # optional, if set, will start the pacakge and ensure installed
        'packages': ['com.tencent.KiHan']
    },
    # 'browser': {  # 浏览器游戏请填写此设置；windows、adb、browser 至少配置一个，也可以同时配置多个
    #     'url': 'https://example.com/game',
    #     'nick': 'Browser',
    #     'resolution': (1280, 720),
    # },
    'start_timeout': 120,  # default 60
    'supported_resolution': {
        'ratio': '16:9', #支持的游戏分辨率
        'min_size': (1280, 720), #支持的最低游戏分辨率
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)], #可选, 如果非16:9自动缩放为 resize_to
    },
    'links': { # 关于里显示的链接, 可选
            'default': {
                'github': 'https://github.com/NYTN02/ok-naruto',
                'share': 'Download from https://github.com/NYTN02/ok-naruto/releases',
                'qq_group':'https://qm.qq.com/q/3Gq4VLvQe',
                'qq_channel': 'https://pd.qq.com/s/djmm6l44y',
                'faq': 'https://github.com/NYTN02/ok-naruto/blob/master/README.md'
                # 上面 qq_group / qq_channel 是 ok-script-app 模板自带的社区链接，
                # 本项目用不上可以删掉，或者换成自己的群/频道地址。'discord' 同理。
            }
        },
    'screenshots_folder': "screenshots", #截图存放目录, 每次重新启动会清空目录
    'gui_title': 'ok-naruto',  #窗口名
    'template_matching': { # 可选, 如使用OpenCV的模板匹配
        'coco_feature_json': os.path.join('assets', 'coco_annotations.json'), #coco格式标记, 需要png图片, 在debug模式运行后, 会对进行切图仅保留被标记部分以减少图片大小
        'default_horizontal_variance': 0.002, #默认x偏移, 查找不传box的时候, 会根据coco坐标, match偏移box内的
        'default_vertical_variance': 0.002, #默认y偏移
        'default_threshold': 0.8, #默认threshold
    },
    'version': version, #版本
    'my_app': ['src.globals', 'Globals'], #可选. 全局单例对象, 可以存放加载的模型, 使用og.my_app调用
    'onetime_tasks': [  # 用户点击触发的任务
        ["src.tasks.daily_task", "DailyTask"],              # 一键日常（推荐入口）
        ["src.tasks.qiandao_task", "QianDaoTask"],          # 每日签到
        ["src.tasks.coin_task", "CoinTask"],                # 领取铜币
        ["src.tasks.mission_task", "MissionTask"],          # 任务集会所
        ["src.tasks.pointrace_task", "PointRaceTask"],      # 积分赛
        ["src.tasks.friend_task", "FriendTask"],            # 好友体力赠送与收取
        ["src.tasks.ranklist_task", "RankListTask"],        # 排行榜点赞
        ["src.tasks.team_praytask", "TeamPrayTask"],        # 组织祈福
        ["src.tasks.teamfight_task", "TeamFightTask"],      # 小队突袭
        ["src.tasks.noodle_task", "NoodleTask"],            # 领取一乐拉面
        ["src.tasks.jingying_task", "JingYingTask"],        # 精英副本
        ["src.tasks.gacha_task", "GachaTask"],              # 招募
        ["src.tasks.coinorgin_task", "CoinOrginTask"],      # 丰饶之间
        ["src.tasks.share_task", "ShareTask"],              # 每日分享
        ["src.tasks.reward_task", "RewardTask"],            # 每日活跃奖励

        # ---- 以下为调试 / 校准用，正式发布可整体注释掉 ----
        ["src.tasks.back_to_main_task", "BackToMainTask"],  # 回到主页面
        ["src.tasks.debug_circle", "DebugCircleTask"],      # 战斗按钮校准
        ["src.tasks.debug_combat_click", "DebugCombatClickTask"],  # 战斗点击验证
        ["ok", "DiagnosisTask"],                            # ok-script 自带诊断

        # ---- 用户用不到的开发示例 / 键位诊断，已按发布需求注释 ----
        # ["src.tasks.test_task", "TestTask"],              # 模板匹配测试
        # ["src.tasks.debug_sendkey", "DebugSendKeyTask"],  # 键盘发送测试
        # ["src.tasks.debug_key", "DebugKeyTask"],          # 键位API诊断
        # ["src.tasks.MyOneTimeTask", "MyOneTimeTask"],     # 配置演示任务
    ],
}
