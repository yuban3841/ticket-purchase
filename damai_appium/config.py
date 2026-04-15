# -*- coding: UTF-8 -*-
"""
__Author__ = "WECENG"
__Version__ = "1.0.0"
__Description__ = "配置类"
__Created__ = 2023/10/27 09:54
"""
import json
from pathlib import Path


class Config:
    def __init__(self, server_url, keyword, users, city, date, price, price_index, if_commit_order, device_name=""):
        self.server_url = server_url
        self.device_name = device_name
        self.keyword = keyword
        self.users = users
        self.city = city
        self.date = date
        self.price = price
        self.price_index = price_index
        self.if_commit_order = if_commit_order

    @staticmethod
    def _candidate_config_paths():
        base_dir = Path(__file__).resolve().parent
        cwd = Path.cwd()
        return [
            cwd / 'config.jsonc',
            cwd / 'config.json',
            base_dir / 'config.jsonc',
            base_dir / 'config.json',
        ]

    @staticmethod
    def load_config():
        config = None
        for config_path in Config._candidate_config_paths():
            if config_path.exists():
                with config_path.open('r', encoding='utf-8') as config_file:
                    config = json.load(config_file)
                break

        if config is None:
            raise FileNotFoundError('未找到配置文件: 请提供 config.jsonc 或 config.json')

        users = config.get('users')
        if not isinstance(users, list):
            users = []

        return Config(
            config.get('server_url', 'http://127.0.0.1:4723'),
            config.get('keyword', ''),
            users,
            config.get('city', ''),
            config.get('date', ''),
            config.get('price', ''),
            config.get('price_index', 0),
            bool(config.get('if_commit_order', False)),
            config.get('device_name', ''),
        )