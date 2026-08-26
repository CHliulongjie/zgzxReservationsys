import os
import json
import time
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import traceback
import requests
import logging
from logging.handlers import RotatingFileHandler
import socket
from functools import wraps

from config_manager import config_manager

# 配置日志
log_dir = os.path.join(config_manager.base_dir, 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file = os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d")}.log')
log_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

# 初始化Flask应用
app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# 添加日志处理器
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)


# ==================== 工具函数 ====================

def get_week_start(date=None):
    """获取周开始日期"""
    if date is None:
        date = datetime.now()
    return date - timedelta(days=date.weekday())


def get_week_filename(system, date=None):
    """获取周文件名"""
    week_start = get_week_start(date)
    filename = f"{week_start.strftime('%Y-%m-%d')}.xlsx"
    system_dir = os.path.join(config_manager.data_dir, system)
    return os.path.join(system_dir, filename)


def load_week_data(system, date=None):
    """加载周数据"""
    filepath = get_week_filename(system, date)

    if os.path.exists(filepath):
        try:
            # 读取Excel，第一行是日期（列名），后面每行是场次（行索引）
            df = pd.read_excel(filepath, index_col=0, header=0)
            # 确保所有值是字符串
            df = df.astype(str)
            df.replace('nan', '', inplace=True)
            return df
        except Exception as e:
            app.logger.error(f"读取Excel失败: {e}")

    # 创建新文件
    system_config = config_manager.get_system_config(system)
    fields = system_config.get('fields', 0)

    if fields == 0:
        return None

    # 创建一周的日期（作为列名）
    week_start = get_week_start(date)
    dates = [(week_start + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]

    # 创建DataFrame：行是场次，列是日期
    # 第一行是日期（列名），后面每行是场次（行索引）
    rows = [f'场地{i + 1}' for i in range(fields)]
    df = pd.DataFrame('', index=rows, columns=dates)

    # 保存
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    df.to_excel(filepath)

    return df


def save_week_data(system, df, date=None):
    """保存周数据"""
    filepath = get_week_filename(system, date)

    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        df.to_excel(filepath)
        return True
    except Exception as e:
        app.logger.error(f"保存Excel失败: {e}")
        return False


def check_reservation_limit(username, date=None):
    """检查预约限制"""
    if date is None:
        date = datetime.now()

    date_str = date.strftime('%Y-%m-%d')

    # 检查所有球类系统
    for system in ['badminton', 'pingpong', 'basketball', 'football']:
        df = load_week_data(system, date)
        if df is not None and date_str in df.columns:
            # df的行是场次，列是日期
            for field in df.index:
                if df.at[field, date_str] == username:
                    return True
    return False


def check_system_available(system, date=None):
    """检查系统是否可用"""
    if date is None:
        date = datetime.now()

    config = config_manager.get_system_config(system)

    if not config.get('enabled', False):
        return False

    # 检查星期
    weekday = date.weekday()  # 0=周一, 6=周日
    weekdays_chinese = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    current_weekday = weekdays_chinese[weekday]

    # 检查星期是否开放（weekdays是字典，键是星期，值是True/False）
    weekdays = config.get('weekdays', {})
    if isinstance(weekdays, dict):
        if not weekdays.get(current_weekday, False):
            return False
    elif isinstance(weekdays, list):
        if current_weekday not in weekdays:
            return False

    # 检查时间：用当前时间判断是否在场馆开放时间内
    # 注意：date 是用户选择的预约日期（由 %Y-%m-%d 解析，time() 为 00:00），
    #   若用 date.time() 比较，start_time 非 00:00 时会永远判定不在时间内，
    #   且 end_time 判断会失效（00:00 恒 <= end_time）导致超时仍可预约。
    #   故开放时间判断用 now.time()，date 仅用于上方星期判断。
    current_time = datetime.now().time()
    start_time = datetime.strptime(config.get('start_time', '00:00'), '%H:%M').time()
    end_time = datetime.strptime(config.get('end_time', '23:59'), '%H:%M').time()

    return start_time <= current_time <= end_time


def load_session_data(system, session_id):
    """加载会话数据（电影/其他预约）"""
    # 使用xlsx文件存储，第一行是预约项目名称，每列是对应预约的人的账户名
    filepath = os.path.join(config_manager.data_dir, system, f"{session_id}.xlsx")

    if os.path.exists(filepath):
        try:
# 读取Excel，列名是预约人，第一行是项目名称
            df = pd.read_excel(filepath, header=0)
            if df.empty:
                return pd.DataFrame(), None
            # 第一行的值就是项目名称（所有列都是同一个项目名称）
            session_name = None
            if len(df) > 0:
                # 获取第一行的第一个值作为项目名称
                session_name = str(df.iloc[0].values[0]) if len(df.columns) > 0 else None
            return df, session_name
        except Exception as e:
            app.logger.error(f"读取会话数据失败: {e}")
            return pd.DataFrame(), None

    return pd.DataFrame(), None


def save_session_data(system, session_id, session_name, usernames):
    """保存会话数据（电影/其他预约）"""
    filepath = os.path.join(config_manager.data_dir, system, f"{session_id}.xlsx")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # 创建DataFrame：第一行是项目名称，每列是一个预约人的账户名
    # 格式：列名是预约人，第一行（索引0）所有单元格都是项目名称
    if usernames:
        # 创建一个DataFrame，列名是预约人
        # 第一行所有单元格都是项目名称
        data = {}
        for username in usernames:
            data[username] = [session_name]  # 第一行是项目名称

        df = pd.DataFrame(data)
    else:
        # 如果没有预约人，创建一个只包含项目名称的DataFrame
        # 但至少需要一列来保存项目名称
        df = pd.DataFrame({'项目': [session_name]})

    try:
        df.to_excel(filepath, index=False)
        return True
    except Exception as e:
        app.logger.error(f"保存会话数据失败: {e}")
        return False


# ==================== 装饰器 ====================

def login_required(f):
    """登录要求装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


def control_panel_login_required(f):
    """控制面板登录要求装饰器"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'control_panel_logged_in' not in session:
            return jsonify({'error': '请先登录控制面板'}), 401
        return f(*args, **kwargs)

    return decorated_function


# ==================== 路由 ====================

@app.route('/')
def index():
    """首页/登录页"""
    return render_template('index.html')


@app.route('/reservation')
@login_required
def reservation():
    """预约页面"""
    return render_template('reservation.html')


@app.route('/control')
def control_panel():
    """控制面板页面"""
    # 检查是否只允许本地访问（可选，可以配置）
    server_config = config_manager.get_server_config()
    control_panel_local_only = server_config.get('control_panel_local_only', False)
    if control_panel_local_only:
        if request.remote_addr not in ['127.0.0.1', 'localhost']:
            return "控制面板只允许本地访问", 403

    return render_template('control_panel.html')


# ==================== 登录相关API ====================

def get_users_xlsx_path():
    """获取有效的 users.xlsx 路径

    优先使用配置中的 xlsx_path，若该路径不存在（例如配置了 Linux 路径但在
    Windows 上运行），则回退到项目根目录(base_dir)下的 users.xlsx。
    """
    login_config = config_manager.get_login_config()
    configured = login_config.get('xlsx_path', 'users.xlsx')

    # 如果是绝对路径且存在，直接使用
    if os.path.isabs(configured) and os.path.exists(configured):
        return configured

    # 相对路径：相对于项目根目录解析
    candidate = os.path.join(config_manager.base_dir, configured)
    if os.path.exists(candidate):
        return candidate

    # 回退到项目根目录下的 users.xlsx
    return os.path.join(config_manager.base_dir, 'users.xlsx')


def get_server_login_url():
    """获取服务器登录URL（xyz服务器的登录路由为 /login，而非 /login1）"""
    login_config = config_manager.get_login_config()
    url = login_config.get('server_url', 'https://longjieruankong.xyz/login')
    # 修正历史遗留的 /login1 路径为 /login
    if url.endswith('/login1'):
        url = url[:-1]  # 去掉末尾的 1，变成 /login
    return url


def ensure_users_xlsx():
    """确保users.xlsx文件存在，如果不存在则创建并添加测试账号"""
    xlsx_path = get_users_xlsx_path()

    if not os.path.exists(xlsx_path):
        try:
            # 创建包含测试账号的DataFrame
            test_data = {
                '用户名': ['test', 'admin'],
                '密码': ['123456', 'admin123']
            }
            df = pd.DataFrame(test_data)
            df.to_excel(xlsx_path, index=False)
            app.logger.info(f"自动创建users.xlsx文件: {xlsx_path}")
            app.logger.info("测试账号: test/123456, admin/admin123")
        except Exception as e:
            app.logger.error(f"创建users.xlsx文件失败: {e}")


@app.route('/api/login/xlsx', methods=['POST'])
def api_login_xlsx():
    """XLSX登录（用户预约登录）"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400

        # 确保XLSX文件存在
        ensure_users_xlsx()

        # 检查XLSX文件（使用健壮的路径获取函数，避免配置路径不存在导致登录失败）
        xlsx_path = get_users_xlsx_path()

        if os.path.exists(xlsx_path):
            try:
                df = pd.read_excel(xlsx_path)
                # 第一列是用户名，第二列是密码
                for _, row in df.iterrows():
                    if str(row.iloc[0]).strip() == username and str(row.iloc[1]).strip() == password:
                        session['user'] = username
                        session['login_time'] = datetime.now().isoformat()
                        app.logger.info(f"用户登录成功: {username}")
                        return jsonify({'success': True, 'username': username})
            except Exception as e:
                app.logger.error(f"读取XLSX文件失败: {e}")

        return jsonify({'error': '用户名或密码错误'}), 401

    except Exception as e:
        app.logger.error(f"登录失败: {e}")
        return jsonify({'error': '登录失败'}), 500


@app.route('/api/login/server', methods=['POST'])
def api_login_server():
    """服务器登录（用户预约登录）"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400

        # 调用外部服务器（xyz服务器登录路由为 /login）
        server_url = get_server_login_url()

        try:
            response = requests.post(
                server_url,
                json={'username': username, 'password': password},
                timeout=10
            )

            if response.status_code == 200:
                session['user'] = username
                session['login_time'] = datetime.now().isoformat()
                app.logger.info(f"用户通过服务器登录成功: {username}")
                return jsonify({'success': True, 'username': username})
            else:
                return jsonify({'error': '用户名或密码错误'}), 401

        except requests.exceptions.RequestException as e:
            app.logger.error(f"连接登录服务器失败: {e}")
            return jsonify({'error': '登录服务器连接失败'}), 503

    except Exception as e:
        app.logger.error(f"登录失败: {e}")
        return jsonify({'error': '登录失败'}), 500


@app.route('/api/login/control', methods=['POST'])
def api_login_control():
    """控制面板登录（管理员登录）- 只允许服务器登录，且必须是admin角色且权限包含*"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()

        if not username or not password:
            return jsonify({'error': '用户名和密码不能为空'}), 400

        # 控制面板只能通过服务器登录验证
        # 使用 get_server_login_url() 获取正确的 /login 路由（xyz服务器登录路由为 /login）
        admin_login_url = get_server_login_url()

        app.logger.info(f"管理员登录尝试连接到: {admin_login_url}")

        try:
            response = requests.post(
                admin_login_url,
                json={'username': username, 'password': password},
                timeout=10
            )

            if response.status_code == 200:
                response_data = response.json()
                app.logger.info(f"服务器返回数据: {response_data}")

                # 验证管理员身份：只需要account_type为admin即可（身份验证，非权限验证）
                account_type = response_data.get('account_type', '')
                roles = response_data.get('roles', [])

                # 兼容roles为list格式
                if isinstance(roles, str):
                    roles = [r.strip() for r in roles.split(',')]
                if not isinstance(roles, list):
                    roles = []

                # 检查是否是管理员身份
                is_admin = account_type == 'admin' or (roles and 'admin' in [str(r).lower() for r in roles])

                app.logger.info(f"用户身份: account_type={account_type}, roles={roles}, is_admin={is_admin}")

                if is_admin:
                    session['control_panel_logged_in'] = True
                    session['control_panel_username'] = username
                    session['control_panel_login_time'] = datetime.now().isoformat()

                    app.logger.info(f"管理员登录成功: {username}")

                    # 返回用户信息
                    return jsonify({
                        'success': True,
                        'username': username,
                        'message': '登录成功'
                    })
                else:
                    app.logger.warning(f"管理员登录失败: {username} - 身份不足 (account_type: {account_type}, roles: {roles})")
                    return jsonify({'error': '只有管理员身份可以登录管理端'}), 403
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('message', '用户名或密码错误')
                app.logger.warning(f"管理员登录失败: {username} - {error_msg}")
                return jsonify({'error': error_msg}), 401


        except requests.exceptions.RequestException as e:
            app.logger.error(f"连接登录服务器失败: {e}")
            return jsonify({'error': f'登录服务器连接失败: {str(e)}'}), 503
        except Exception as e:
            app.logger.error(f"管理员登录验证失败: {e}")
            import traceback
            app.logger.error(traceback.format_exc())
            return jsonify({'error': f'登录验证失败: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"管理端登录接口异常: {e}")
        return jsonify({'error': f'登录接口异常: {str(e)}'}), 500

@app.route('/api/logout')
def api_logout():
    """退出登录"""
    session.clear()
    return jsonify({'success': True})


# ==================== 系统信息API ====================

@app.route('/api/system/info')
def api_system_info():
    """获取系统信息"""
    try:
        info = {
            'version': '2.0',
            'server_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'systems': {}
        }

        for system_name in ['badminton', 'pingpong', 'basketball', 'football', 'movie', 'other']:
            config = config_manager.get_system_config(system_name)
            info['systems'][system_name] = {
                'enabled': config.get('enabled', False),
                'name': config.get('name', system_name)
            }

        return jsonify(info)
    except Exception as e:
        app.logger.error(f"获取系统信息失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 系统配置API ====================

@app.route('/api/system/config', methods=['GET'])
@control_panel_login_required
def api_get_all_config():
    """获取所有配置"""
    try:
        return jsonify(config_manager.config)
    except Exception as e:
        app.logger.error(f"获取配置失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/server/config', methods=['GET'])
@control_panel_login_required
def api_get_server_config():
    """获取服务器配置"""
    try:
        return jsonify(config_manager.get_server_config())
    except Exception as e:
        app.logger.error(f"获取服务器配置失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/server/config', methods=['POST'])
@control_panel_login_required
def api_update_server_config():
    """更新服务器配置"""
    try:
        data = request.json
        port = data.get('port')
        host = data.get('host')

        if port is not None:
            try:
                port = int(port)
                if port < 1 or port > 65535:
                    return jsonify({'error': '端口号必须在1-65535之间'}), 400
            except ValueError:
                return jsonify({'error': '端口号必须是数字'}), 400

        update_data = {}
        if port is not None:
            update_data['port'] = port
        if host:
            update_data['host'] = host

        if config_manager.update_server_config(update_data):
            return jsonify({'success': True, 'message': '配置已保存，请重启服务器使配置生效'})
        else:
            return jsonify({'error': '保存失败'}), 500

    except Exception as e:
        app.logger.error(f"更新服务器配置失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/<system_name>/config', methods=['GET'])
def api_get_system_config(system_name):
    """获取系统配置"""
    try:
        config = config_manager.get_system_config(system_name)
        if not config:
            return jsonify({'error': '系统不存在'}), 404

        return jsonify(config)
    except Exception as e:
        app.logger.error(f"获取系统配置失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/<system_name>/config', methods=['POST'])
@control_panel_login_required
def api_update_system_config(system_name):
    """更新系统配置"""
    try:
        data = request.json
        if config_manager.update_system_config(system_name, data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': '更新失败'}), 500
    except Exception as e:
        app.logger.error(f"更新系统配置失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/<system_name>/status', methods=['POST'])
@control_panel_login_required
def api_toggle_system_status(system_name):
    """切换系统状态"""
    try:
        data = request.json
        enabled = data.get('enabled', False)

        if config_manager.set_system_status(system_name, enabled):
            return jsonify({'success': True, 'enabled': enabled})
        else:
            return jsonify({'error': '操作失败'}), 500
    except Exception as e:
        app.logger.error(f"切换系统状态失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 球类预约API ====================

@app.route('/api/reservation/sports/<system_name>', methods=['GET'])
@login_required
def api_get_sports_reservations(system_name):
    """获取球类预约数据"""
    try:
        date_str = request.args.get('date')
        date = None

        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
            except:
                pass

        df = load_week_data(system_name, date)

        if df is None:
            return jsonify({'error': '系统不存在或未配置'}), 404

        # 转换为字典格式
        # df的行是场次，列是日期
        result = []
        for date_col in df.columns:
            day_data = {'date': date_col, 'fields': {}}
            for field_row in df.index:
                value = df.at[field_row, date_col]
                if value and str(value).strip() and str(value) != 'nan':
                    day_data['fields'][field_row] = str(value)
            result.append(day_data)

        return jsonify({'reservations': result})
    except Exception as e:
        app.logger.error(f"获取预约数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reservation/sports/<system_name>/book', methods=['POST'])
@login_required
def api_book_sports(system_name):
    """预约球类场地"""
    try:
        data = request.json
        username = session.get('user')
        date_str = data.get('date')
        field = data.get('field')

        if not username:
            return jsonify({'error': '请先登录'}), 401

        if not date_str or not field:
            return jsonify({'error': '缺少必要参数'}), 400

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        except:
            return jsonify({'error': '日期格式错误'}), 400

        # 检查日期不能是过去的日期（将today减一天，确保当天日期可以预约）
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        if date.date() < yesterday:
            return jsonify({'error': '不能预约过去的日期'}), 400

        # 检查系统配置
        config = config_manager.get_system_config(system_name)

        # 检查是否开启了"仅可预约当日场地"选项
        only_today = config.get('only_today', False)
        if only_today:
            # 如果开启了仅可预约当日，检查日期必须是今天或昨天
            # 使用用户建议的and逻辑：如果选择的日期不是今天并且不是昨天，就报错
            if date.date() != today and date.date() != yesterday:
                return jsonify({'error': '该系统仅允许预约当日场地'}), 400

        # 检查系统是否可用
        if not check_system_available(system_name, date):
            return jsonify({'error': '系统在当前时间不可用'}), 400

        # 检查预约限制
        if check_reservation_limit(username, date):
            return jsonify({'error': '您今天已经预约过了'}), 400

        # 加载数据
        df = load_week_data(system_name, date)

        if df is None:
            return jsonify({'error': '系统数据加载失败'}), 500

        # 检查场地是否被占用
        # df的行是场次，列是日期
        if field in df.index and date_str in df.columns:
            current_value = df.at[field, date_str]
            if current_value and str(current_value).strip() and str(current_value) != 'nan':
                return jsonify({'error': '该场地已被预约'}), 400

            # 预约场地
            df.at[field, date_str] = username

            # 保存
            if save_week_data(system_name, df, date):
                app.logger.info(f"用户{username}预约了{system_name}的{field}在{date_str}")
                return jsonify({'success': True})
            else:
                return jsonify({'error': '保存失败'}), 500
        else:
            return jsonify({'error': '场地不存在'}), 400

    except Exception as e:
        app.logger.error(f"预约失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reservation/sports/<system_name>/cancel', methods=['POST'])
@login_required
def api_cancel_sports(system_name):
    """取消球类预约"""
    try:
        data = request.json
        username = session.get('user')
        date_str = data.get('date')
        field = data.get('field')

        if not username:
            return jsonify({'error': '请先登录'}), 401

        if not date_str or not field:
            return jsonify({'error': '缺少必要参数'}), 400

        # 加载数据
        df = load_week_data(system_name)

        if df is None:
            return jsonify({'error': '系统数据加载失败'}), 500

        # 检查预约是否存在
        # df的行是场次，列是日期
        if field in df.index and date_str in df.columns:
            current_value = df.at[field, date_str]
            if not current_value or str(current_value).strip() != username:
                return jsonify({'error': '未找到您的预约'}), 400

            # 取消预约
            df.at[field, date_str] = ''
# 保存
            if save_week_data(system_name, df):
                app.logger.info(f"用户{username}取消了{system_name}的{field}在{date_str}")
                return jsonify({'success': True})
            else:
                return jsonify({'error': '保存失败'}), 500
        else:
            return jsonify({'error': '场地不存在'}), 400

    except Exception as e:
        app.logger.error(f"取消预约失败: {e}")
        return jsonify({'error': str(e)}), 500

# ==================== 电影/其他预约API ====================

@app.route('/api/reservation/session/<system_name>', methods=['GET'])
def api_get_sessions(system_name):
    """获取电影/其他预约项目"""
    try:
        config = config_manager.get_system_config(system_name)

        if system_name == 'movie':
            sessions = config.get('sessions', [])
            # 为每个场次加载预约人数
            for s in sessions:
                session_id = str(s.get('id', ''))
                df, _ = load_session_data(system_name, session_id)
                if not df.empty:
                    # 列名是预约人，统计非空列（排除'项目'列）
                    s['current_count'] = len(
                        [col for col in df.columns if pd.notna(col) and str(col).strip() and str(col) != '项目'])
                else:
                    s['current_count'] = 0
            return jsonify({'sessions': sessions})
        else:
            items = config.get('items', [])
        # 为每个项目加载预约人数
            for item in items:
                item_id = str(item.get('id', ''))
                df, _ = load_session_data(system_name, item_id)
                if not df.empty:
                    # 列名是预约人，统计非空列（排除'项目'列）
                    item['current_count'] = len(
                        [col for col in df.columns if pd.notna(col) and str(col).strip() and str(col) != '项目'])
                else:
                    item['current_count'] = 0
            return jsonify({'items': items})

    except Exception as e:
        app.logger.error(f"获取预约项目失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/reservation/session/<system_name>/book', methods=['POST'])
@login_required
def api_book_session(system_name):
    """预约电影/其他项目"""
    try:
        data = request.json
        username = session.get('user')
        session_id = data.get('session_id')

        if not username:
            return jsonify({'error': '请先登录'}), 401

        if not session_id:
            return jsonify({'error': '缺少必要参数'}), 400

        # 获取项目配置
        config = config_manager.get_system_config(system_name)
        if system_name == 'movie':
            sessions = config.get('sessions', [])
            target_session = None
            for s in sessions:
                if str(s.get('id')) == str(session_id):
                    target_session = s
                    break
        else:
            items = config.get('items', [])
            target_session = None
            for item in items:
                if str(item.get('id')) == str(session_id):
                    target_session = item
                    break

        if not target_session:
            return jsonify({'error': '项目不存在'}), 404

        # 检查系统是否启用
        if not config.get('enabled', False):
            return jsonify({'error': '该系统暂未开放'}), 400

        # 检查时间
        now = datetime.now()
        start_time_str = target_session.get('start_time', '')
        end_time_str = target_session.get('end_time', '')

        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                if now < start_time:
                    return jsonify({'error': '预约尚未开始'}), 400
            except:
                pass

        if end_time_str:
            try:
                end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                if now > end_time:
                    return jsonify({'error': '预约已结束'}), 400
            except:
                pass

        # 加载预约数据
        df, loaded_session_name = load_session_data(system_name, session_id)

        # 获取已预约的用户列表
        usernames = []
        if not df.empty:
            # DataFrame的列名是预约人（第一行是项目名称数据）
            usernames = [str(col) for col in df.columns.tolist() if
                         col and pd.notna(col) and str(col).strip() and str(col) != '项目']

        # 检查是否已预约
        if username in usernames:
            return jsonify({'error': '您已预约该项目'}), 400

        # 检查人数限制
        capacity = target_session.get('capacity', 0)
        if capacity > 0 and len(usernames) >= capacity:
            return jsonify({'error': '预约人数已满'}), 400

        # 添加预约
        usernames.append(username)

        # 保存
        session_name = target_session.get('name', f'项目{session_id}')
        if save_session_data(system_name, session_id, session_name, usernames):
            app.logger.info(f"用户{username}预约了{system_name}项目{session_name}")
            return jsonify({'success': True})
        else:
            return jsonify({'error': '保存失败'}), 500

    except Exception as e:
        app.logger.error(f"预约失败: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/reservation/session/<system_name>/cancel', methods=['POST'])
@login_required
def api_cancel_session(system_name):
    """取消电影/其他预约"""
    try:
        data = request.json
        username = session.get('user')
        session_id = data.get('session_id')

        if not username:
            return jsonify({'error': '请先登录'}), 401

        if not session_id:
            return jsonify({'error': '缺少必要参数'}), 400

        # 仅允许 movie/other 系统
        if system_name not in ['movie', 'other']:
            return jsonify({'error': '系统类型错误'}), 400

        # 加载预约数据
        df, loaded_session_name = load_session_data(system_name, session_id)

        if df.empty:
            return jsonify({'error': '预约记录不存在'}), 404

        # 获取已预约的用户列表（列名是预约人）
        usernames = [str(col) for col in df.columns.tolist()
                     if col and pd.notna(col) and str(col).strip() and str(col) != '项目']

        # 检查是否已预约
        if username not in usernames:
            return jsonify({'error': '您未预约该项目'}), 400

        # 移除当前用户
        usernames.remove(username)

        # 保存（使用已加载的项目名称，如无则回退到 session_id）
        session_name = loaded_session_name if loaded_session_name else f'项目{session_id}'

        if save_session_data(system_name, session_id, session_name, usernames):
            app.logger.info(f"用户{username}取消了{system_name}项目{session_name}的预约")
            return jsonify({'success': True})
        else:
            return jsonify({'error': '保存失败'}), 500

    except Exception as e:
        app.logger.error(f"取消预约失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 场次管理API ====================

@app.route('/api/session/<system_name>/add', methods=['POST'])
@control_panel_login_required
def api_add_session(system_name):
    """添加电影/其他预约场次"""
    try:
        data = request.json

        config = config_manager.get_system_config(system_name)

        if system_name == 'movie':
            sessions = config.get('sessions', [])
            # 生成新ID
            new_id = str(int(time.time() * 1000)) if sessions else '1'
            new_session = {
                'id': new_id,
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'capacity': int(data.get('capacity', 0)),
                'start_time': data.get('start_time', ''),
                'end_time': data.get('end_time', '')
            }
            sessions.append(new_session)
            config['sessions'] = sessions
        else:
            items = config.get('items', [])
            # 生成新ID
            new_id = str(int(time.time() * 1000)) if items else '1'
            new_item = {
                'id': new_id,
                'name': data.get('name', ''),
                'description': data.get('description', ''),
                'capacity': int(data.get('capacity', 0)),
                'start_time': data.get('start_time', ''),
                'end_time': data.get('end_time', '')
            }
            items.append(new_item)
            config['items'] = items

        if config_manager.update_system_config(system_name, config):
            return jsonify({'success': True, 'id': new_id})
        else:
            return jsonify({'error': '保存失败'}), 500

    except Exception as e:
        app.logger.error(f"添加场次失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 系统控制API ====================

@app.route('/api/system/restart', methods=['POST'])
@control_panel_login_required
def api_restart_system():
    """重启系统

    通过 main.py 控制服务器(5001端口)终止 app.py 子进程，
    main.py 主循环检测到重启标志后重新启动 app.py。
    若控制服务器不可用（如直接运行 app.py 测试），则 app.py 自身退出
    （通过 main.py 启动时 Popen.wait 返回，若设置了重启标志会重新启动）。
    """
    try:
        app.logger.info("系统重启请求已接收")

        # 先尝试通过 main.py 控制服务器重启
        try:
            import requests
            response = requests.post('http://127.0.0.1:5001/api/control/restart', timeout=2)
            if response.status_code == 200:
                result = response.json()
                return jsonify(result)
        except Exception as e:
            app.logger.warning(f"控制服务器不可用，改由 app.py 自身退出触发重启: {e}")

        # 后备方案：app.py 自身延迟退出
        # 通过 main.py 启动时，Popen.wait() 返回，主循环检测退出码决定是否重启
        # 这里用退出码 0 退出，main.py 会根据 _restart_flag 决定（直接运行 app.py 时不会重启）
        import threading
        import os
        import time

        def delayed_self_exit():
            time.sleep(1)
            app.logger.info("app.py 自身关闭中（等待 main.py 重启）...")
            os._exit(0)

        thread = threading.Thread(target=delayed_self_exit, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': '服务器正在重启'})

    except Exception as e:
        app.logger.error(f"重启系统失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/shutdown', methods=['POST'])
@control_panel_login_required
def api_shutdown_system():
    """关闭系统

    优先通过 main.py 控制服务器(5001端口)关闭整个进程树；
    若控制服务器不可用（如直接运行 app.py 测试），则 app.py 自身延迟退出，
    这样通过 main.py 启动时 subprocess.call 会返回，main.py 随之退出。
    """
    try:
        app.logger.info("系统关闭请求已接收")

        # 先尝试通过 main.py 控制服务器关闭整个进程树
        try:
            import requests
            response = requests.post('http://127.0.0.1:5001/api/control/shutdown', timeout=2)
            if response.status_code == 200:
                result = response.json()
                return jsonify(result)
        except Exception as e:
            app.logger.warning(f"控制服务器不可用，改由 app.py 自身关闭: {e}")

        # 后备方案：app.py 自身延迟退出
        import threading
        import os
        import time

        def delayed_self_exit():
            time.sleep(1)
            app.logger.info("app.py 自身关闭中...")
            os._exit(0)

        thread = threading.Thread(target=delayed_self_exit, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': '服务器正在关闭'})

    except Exception as e:
        app.logger.error(f"关闭系统失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/session/<system_name>/delete', methods=['POST'])
@control_panel_login_required
def api_delete_session(system_name):
    """删除电影/其他预约场次"""
    try:
        data = request.json
        session_id = str(data.get('session_id', ''))

        if not session_id:
            return jsonify({'error': '缺少必要参数'}), 400

        config = config_manager.get_system_config(system_name)

        if system_name == 'movie':
            sessions = config.get('sessions', [])
            sessions = [s for s in sessions if str(s.get('id')) != session_id]
            config['sessions'] = sessions
        else:
            items = config.get('items', [])
            items = [item for item in items if str(item.get('id')) != session_id]
            config['items'] = items

        if config_manager.update_system_config(system_name, config):
            # 删除对应的数据文件
            filepath = os.path.join(config_manager.data_dir, system_name, f"{session_id}.xlsx")
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass

            return jsonify({'success': True})
        else:
            return jsonify({'error': '保存失败'}), 500

    except Exception as e:
        app.logger.error(f"删除场次失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 数据管理API ====================

@app.route('/api/data/clear', methods=['POST'])
@control_panel_login_required
def api_clear_data():
    """清除数据"""
    try:
        data = request.json
        system = data.get('system', 'all')

        if system == 'all':
            # 清除所有系统数据
            for sys in ['badminton', 'pingpong', 'basketball', 'football', 'movie', 'other']:
                sys_dir = os.path.join(config_manager.data_dir, sys)
                if os.path.exists(sys_dir):
                    for file in os.listdir(sys_dir):
                        file_path = os.path.join(sys_dir, file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
        else:
            # 清除特定系统数据
            sys_dir = os.path.join(config_manager.data_dir, system)
            if os.path.exists(sys_dir):
                for file in os.listdir(sys_dir):
                    file_path = os.path.join(sys_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"清除数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/stats', methods=['GET'])
def api_get_data_stats():
    """获取数据统计"""
    try:
        stats = {}
        total = 0

        for system in ['badminton', 'pingpong', 'basketball', 'football', 'movie', 'other']:
            size = 0
            sys_dir = os.path.join(config_manager.data_dir, system)
            if os.path.exists(sys_dir):
                for file in os.listdir(sys_dir):
                    file_path = os.path.join(sys_dir, file)
                    if os.path.isfile(file_path):
                        size += os.path.getsize(file_path)

            stats[system] = size
            total += size

        stats['total'] = total

        return jsonify(stats)
    except Exception as e:
        app.logger.error(f"获取数据统计失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 用户数据API ====================

@app.route('/api/user/info', methods=['GET'])
@login_required
def api_get_user_info():
    """获取当前用户信息"""
    try:
        username = session.get('user')
        if username:
            return jsonify({'success': True, 'username': username})
        else:
            return jsonify({'error': '未登录'}), 401
    except Exception as e:
        app.logger.error(f"获取用户信息失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/user/reservations', methods=['GET'])
@login_required
def api_get_user_reservations():
    """获取用户的所有预约"""
    try:
        username = session.get('user')
        result = []

        # 检查球类预约
        for system in ['badminton', 'pingpong', 'basketball', 'football']:
            df = load_week_data(system)
            if df is not None:
                # df的行是场次，列是日期
                for field in df.index:
                    for date_col in df.columns:
                        if df.at[field, date_col] == username:
                            result.append({
                                'system': system,
                                'system_name': config_manager.get_system_config(system).get('name', system),
                                'date': date_col,
                                'field': field,
                                'type': 'sports'
                            })

        # 检查电影/其他预约
        for system in ['movie', 'other']:
            sys_dir = os.path.join(config_manager.data_dir, system)
            if os.path.exists(sys_dir):
                for file in os.listdir(sys_dir):
                    if file.endswith('.xlsx'):
                        session_id = file[:-5]
                        df, session_name = load_session_data(system, session_id)
                        if not df.empty and username in df.columns:
                            result.append({
                                'system': system,
                                'system_name': config_manager.get_system_config(system).get('name', system),
                                'session_id': session_id,
                                'session_name': session_name or f'项目{session_id}',
                                'type': 'session'
                            })

        return jsonify({'reservations': result})
    except Exception as e:
        app.logger.error(f"获取用户预约失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 数据查看与导出API ====================

@app.route('/api/data/files/<system_name>', methods=['GET'])
@control_panel_login_required
def api_get_data_files(system_name):
    """获取指定系统的所有数据文件列表"""
    try:
        sys_dir = os.path.join(config_manager.data_dir, system_name)
        if not os.path.exists(sys_dir):
            return jsonify({'files': []})

        files = []
        for file in os.listdir(sys_dir):
            if file.endswith('.xlsx') and not file.startswith('~'):
                file_path = os.path.join(sys_dir, file)
                stat = os.stat(file_path)
                files.append({
                    'name': file,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })

        # 按修改时间倒序排列
        files.sort(key=lambda x: x['modified'], reverse=True)
        return jsonify({'files': files})
    except Exception as e:
        app.logger.error(f"获取文件列表失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/preview/<system_name>/<filename>', methods=['GET'])
@control_panel_login_required
def api_preview_data(system_name, filename):
    """预览xlsx文件数据"""
    try:
        file_path = os.path.join(config_manager.data_dir, system_name, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        df = pd.read_excel(file_path, header=0)
        # 将NaN替换为空字符串
        df = df.fillna('')
        # 转换为可序列化的格式
        data = {
            'columns': df.columns.tolist(),
            'rows': df.values.tolist(),
            'shape': list(df.shape)
        }
        return jsonify(data)
    except Exception as e:
        app.logger.error(f"预览数据失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/export/<system_name>/<filename>', methods=['GET'])
@control_panel_login_required
def api_export_data(system_name, filename):
    """导出xlsx文件"""
    try:
        file_path = os.path.join(config_manager.data_dir, system_name, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        from flask import send_from_directory
        directory = os.path.join(config_manager.data_dir, system_name)
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        app.logger.error(f"导出数据失败: {e}")
        return jsonify({'error': str(e)}), 500


# ==================== 启动函数 ====================

def get_local_ip():
    """获取本地IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'


def start_server():
    """启动服务器"""
    try:
        # 确保users.xlsx文件存在
        ensure_users_xlsx()

        server_config = config_manager.get_server_config()
        host = server_config.get('host', '0.0.0.0')
        port = server_config.get('port', 5000)

        local_ip = get_local_ip()

        print("=" * 60)
        print("中国中学场馆预约系统——算法穹顶社")
        print("=" * 60)
        print(f"数据目录: {config_manager.data_dir}")
        print(f"配置文件: {config_manager.config_file}")
        print(f"监听地址: {host}:{port}")
        print(f"本地访问: http://localhost:{port}")
        print(f"局域网访问: http://{local_ip}:{port}")
        print(f"预约页面: http://{local_ip}:{port}/reservation")
        print(f"控制面板: http://{local_ip}:{port}/control")
        print(f"日志文件: {log_file}")
        print("=" * 60)
        print("按 Ctrl+C 停止服务器")
        print("=" * 60)

        # 自动打开浏览器到控制面板
        import webbrowser
        import threading
        import time
        
        def open_browser():
            time.sleep(2)  # 等待服务器启动
            webbrowser.open(f"http://localhost:{port}/control")
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # 使用waitress启动服务器
        from waitress import serve
        serve(app, host=host, port=port, threads=4, connection_limit=1000)

    except Exception as e:
        print(f"服务器启动失败: {e}")
        traceback.print_exc()
        return False


if __name__ == '__main__':
    start_server()