# -*- coding: UTF-8 -*-
"""
__Author__ = "WECENG"
__Version__ = "1.0.0"
__Description__ = "大麦抢票脚本"
__Created__ = 2023/10/10 17:12
"""
import json
import os
import sys
import time

from concert import Concert
from config import Config


CONFIG_FILE_NAME = 'config.json'


def _candidate_config_paths():
    """返回可能的配置文件路径（按优先级）。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    cwd = os.getcwd()

    candidates = [
        os.path.join(cwd, CONFIG_FILE_NAME),
        os.path.join(script_dir, CONFIG_FILE_NAME),
        os.path.join(project_root, CONFIG_FILE_NAME),
    ]

    unique_candidates = []
    for path in candidates:
        normalized = os.path.normpath(path)
        if normalized not in unique_candidates:
            unique_candidates.append(normalized)

    return unique_candidates


def resolve_config_file():
    """自动定位配置文件。"""
    for path in _candidate_config_paths():
        if os.path.exists(path):
            return path
    return None


def check_config_file():
    """检查配置文件是否存在和有效"""
    config_file = resolve_config_file()

    if not config_file:
        print("=" * 50)
        print("✗ 错误: 未找到配置文件 config.json")
        print("=" * 50)
        print("\n请在以下任一路径创建 config.json（推荐 damai/config.json）:")
        for path in _candidate_config_paths():
            print(f"  - {path}")
        print("\n配置示例:")
        print("""
{
    "index_url": "https://www.damai.cn/",
    "login_url": "https://passport.damai.cn/login",
    "target_url": "目标演出页面URL",
    "users": ["观众1姓名", "观众2姓名"],
    "city": "城市名称（可选）",
    "dates": ["场次日期1", "场次日期2"],
    "prices": ["票面价格1", "票面价格2"],
    "if_listen": true,
    "if_commit_order": true,
    "max_retries": 1000
}
        """)
        print("=" * 50)
        sys.exit(1)

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        required_fields = ['index_url', 'login_url', 'target_url', 'users']
        missing_fields = [field for field in required_fields if field not in config]

        if missing_fields:
            print(f"✗ 配置文件缺少必需字段: {', '.join(missing_fields)}")
            sys.exit(1)

        if not config['users']:
            print("✗ 配置文件中 users 字段不能为空")
            sys.exit(1)

        print(f"✓ 配置文件加载成功")
        print(f"  - 配置路径: {config_file}")
        print(f"  - 目标URL: {config['target_url']}")
        print(f"  - 观众人数: {len(config['users'])} 人")
        print(f"  - 最大重试次数: {config.get('max_retries', 1000)} 次")
        print()
        return config_file

    except json.JSONDecodeError as e:
        print(f"✗ 配置文件格式错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ 读取配置文件失败: {e}")
        sys.exit(1)


def load_config(config_file):
    with open(config_file, 'r', encoding='utf-8') as config_file_obj:
        config = json.load(config_file_obj)
    return Config(
        config['index_url'],
        config['login_url'],
        config['target_url'],
        config['users'],
        config.get('city'),
        config.get('dates'),
        config.get('prices'),
        config['if_listen'],
        config['if_commit_order'],
        config.get('max_retries', 1000),
        config.get('fast_mode', True),  # 默认启用快速模式
        config.get('page_load_delay', 2)  # 默认2秒
    )


def grab():
    print("\n" + "=" * 50)
    print("大麦网抢票脚本启动")
    print("=" * 50)
    print()

    # 检查配置文件
    config_file = check_config_file()

    # 加载配置文件
    config = load_config(config_file)

    # 初始化（会自动检查 Chrome 环境）
    con = Concert(config)
    try:
        # 进入页面
        con.enter_concert()
        # 抢票
        con.choose_ticket()
        # 页面停留5分钟
        print("\n✓ 抢票流程完成，页面将保持5分钟...")
        time.sleep(300)
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断程序")
        con.finish()
    except Exception as e:
        print(f"\n✗ 运行出错: {e}")
        import traceback
        traceback.print_exc()
        con.finish()


# exec
if __name__ == "__main__":
    grab()
