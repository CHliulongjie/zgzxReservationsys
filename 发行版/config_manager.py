import os
import json
import yaml
from datetime import datetime
from typing import Dict, Any, Optional


class ConfigManager:
    """配置管理器，负责系统配置的加载、保存和验证"""

    def __init__(self, base_dir: str = None):
        """初始化配置管理器"""
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        self.base_dir = base_dir
        self.data_dir = os.path.join(base_dir, 'data')
        self.config_dir = os.path.join(self.data_dir, 'config')
        self.config_file = os.path.join(self.config_dir, 'system_config.yaml')

        # 确保目录存在
        self._ensure_directories()

        # 默认配置
        self.default_config = {
            'server': {
                'host': '0.0.0.0',
                'port': 5000,
                'debug': False,
                'network_mode': 'lan',  # 'lan' 或 'public'
                'allowed_ips': [],  # 允许访问的IP地址列表，空表示允许所有
            },
            'systems': {
                'badminton': {
                    'enabled': False,
                    'name': '羽毛球场',
                    'fields': 6,
                    'weekdays': {'周一': True, '周二': True, '周三': True, '周四': True, '周五': False, '周六': False,
                                 '周日': False},
                    'start_time': '08:00',
                    'end_time': '20:00',
                    'daily_limit_per_user': 1,
                    'only_today': False,  # 仅可预约当日场地
                },
                'pingpong': {
                    'enabled': False,
                    'name': '乒乓球场',
                    'fields': 8,
                    'weekdays': {'周一': True, '周二': True, '周三': True, '周四': True, '周五': False, '周六': False,
                                 '周日': False},
                    'start_time': '09:00',
                    'end_time': '21:00',
                    'daily_limit_per_user': 1,
                    'only_today': False,  # 仅可预约当日场地
                },
                'basketball': {
                    'enabled': False,
                    'name': '篮球场',
                    'fields': 4,
                    'weekdays': {'周一': True, '周二': True, '周三': True, '周四': True, '周五': False, '周六': False,
                                 '周日': False},
                    'start_time': '10:00',
                    'end_time': '22:00',
                    'daily_limit_per_user': 1,
                    'only_today': False,  # 仅可预约当日场地
                },
                'football': {
                    'enabled': False,
                    'name': '足球场',
                    'fields': 2,
                    'weekdays': {'周一': True, '周二': True, '周三': True, '周四': True, '周五': False, '周六': False,
                                 '周日': False},
                    'start_time': '14:00',
                    'end_time': '20:00',
                    'daily_limit_per_user': 1,
                    'only_today': False,  # 仅可预约当日场地
                },
                'movie': {
                    'enabled': False,
                    'name': '尔雅轩电影',
                    'sessions': [],
                },
                'other': {
                    'enabled': False,
                    'name': '其他预约',
                    'items': [],
                }
            },
            'security': {
                'login_server_url': 'https://longjieruankong.xyz/login1',
                'session_timeout_minutes': 30,
                'max_login_attempts': 5,
                'require_https': False,
                'control_panel_password': 'admin123',  # 控制面板默认密码
            },
            'login': {
                'xlsx_path': os.path.join(base_dir, 'users.xlsx'),  # XLSX登录文件路径
                'server_url': 'https://longjieruankong.xyz/login1',
            },
            'data': {
                'backup_auto': True,
                'backup_interval_hours': 24,
                'backup_keep_days': 7,
                'cleanup_old_data_days': 30,
            },
            'ui': {
                'theme': 'default',
                'language': 'zh-CN',
                'show_weekend': False,
            }
        }

        # 加载配置
        self.config = self.load_config()

    def _ensure_directories(self):
        """确保所有必要的目录都存在"""
        directories = [
            self.data_dir,
            self.config_dir,
            os.path.join(self.data_dir, 'badminton'),
            os.path.join(self.data_dir, 'pingpong'),
            os.path.join(self.data_dir, 'basketball'),
            os.path.join(self.data_dir, 'football'),
            os.path.join(self.data_dir, 'movie'),
            os.path.join(self.data_dir, 'other'),
            os.path.join(self.base_dir, 'static', 'css'),
            os.path.join(self.base_dir, 'static', 'js'),
            os.path.join(self.base_dir, 'static', 'images'),
            os.path.join(self.base_dir, 'templates'),
            os.path.join(self.base_dir, 'logs'),
            os.path.join(self.base_dir, 'backups'),
        ]

        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"创建目录: {directory}")

    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = yaml.safe_load(f)

                # 深度合并配置，确保默认值存在
                config = self._deep_merge(self.default_config, loaded_config)
                return config
            except Exception as e:
                print(f"读取配置文件失败: {e}，使用默认配置")
                return self.default_config.copy()
        else:
            print("配置文件不存在，创建默认配置")
            self.save_config(self.default_config)
            return self.default_config.copy()

    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """保存配置文件"""
        if config is None:
            config = self.config

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, sort_keys=False)

            self.config = config
            print(f"配置已保存: {self.config_file}")
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def update_config(self, section: str, key: str, value: Any) -> bool:
        """更新配置的某个部分"""
        if section in self.config and key in self.config[section]:
            self.config[section][key] = value
            return self.save_config()
        else:
            print(f"配置项不存在: {section}.{key}")
            return False

    def get_system_config(self, system_name: str) -> Dict[str, Any]:
        """获取特定系统的配置"""
        if system_name in self.config['systems']:
            return self.config['systems'][system_name].copy()
        else:
            print(f"系统配置不存在: {system_name}")
            return {}

    def update_system_config(self, system_name: str, config: Dict[str, Any]) -> bool:
        """更新特定系统的配置"""
        if system_name in self.config['systems']:
            self.config['systems'][system_name].update(config)
            return self.save_config()
        else:
            print(f"系统配置不存在: {system_name}")
            return False

    def get_server_config(self) -> Dict[str, Any]:
        """获取服务器配置"""
        return self.config['server'].copy()

    def update_server_config(self, config: Dict[str, Any]) -> bool:
        """更新服务器配置"""
        self.config['server'].update(config)
        return self.save_config()

    def get_network_mode(self) -> str:
        """获取网络模式"""
        return self.config['server'].get('network_mode', 'lan')

    def get_allowed_ips(self) -> list:
        """获取允许访问的IP列表"""
        return self.config['server'].get('allowed_ips', [])

    def is_ip_allowed(self, ip: str) -> bool:
        """检查IP是否被允许访问"""
        allowed_ips = self.get_allowed_ips()
        if not allowed_ips:  # 空列表表示允许所有
            return True

        return ip in allowed_ips

    def _deep_merge(self, default: Dict, override: Dict) -> Dict:
        """深度合并两个字典"""
        result = default.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def get_system_status(self, system_name: str) -> bool:
        """获取系统启用状态"""
        system_config = self.get_system_config(system_name)
        return system_config.get('enabled', False)

    def set_system_status(self, system_name: str, enabled: bool) -> bool:
        """设置系统启用状态"""
        return self.update_system_config(system_name, {'enabled': enabled})

    def get_all_systems(self) -> Dict[str, Dict]:
        """获取所有系统配置"""
        return self.config['systems'].copy()

    def generate_backup_path(self) -> str:
        """生成备份文件路径"""
        backup_dir = os.path.join(self.base_dir, 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return os.path.join(backup_dir, f'backup_{timestamp}.zip')

    def get_log_path(self) -> str:
        """获取日志文件路径"""
        log_dir = os.path.join(self.base_dir, 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        date_str = datetime.now().strftime('%Y%m%d')
        return os.path.join(log_dir, f'app_{date_str}.log')

    def verify_control_panel_password(self, password: str) -> bool:
        """验证控制面板密码"""
        control_password = self.config.get('security', {}).get('control_panel_password', 'admin123')
        return password == control_password

    def get_login_config(self) -> Dict[str, Any]:
        """获取登录配置"""
        return self.config.get('login', {}).copy()


# 全局配置管理器实例
config_manager = ConfigManager()

if __name__ == '__main__':
    # 测试配置管理器
    cm = ConfigManager()
    print("当前配置:")
    print(json.dumps(cm.config, ensure_ascii=False, indent=2))

    # 测试更新配置
    cm.update_server_config({'port': 8080, 'host': '127.0.0.1'})
    print("\n更新后的配置:")
    print(f"服务器端口: {cm.config['server']['port']}")
    print(f"服务器地址: {cm.config['server']['host']}")