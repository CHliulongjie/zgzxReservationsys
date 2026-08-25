#!/usr/bin/env python3
"""
主启动脚本

功能：
1. 通过项目目录下的虚拟环境(.venv)直接运行 app.py，方便功能测试
2. 提供控制服务器(端口5001)，支持从管理界面远程关闭整个服务器进程

使用方法：直接运行 python main.py 即可启动 app.py
"""

import os
import sys
import subprocess
import threading
import time


def start_control_server():
    """启动控制服务器，提供关闭主进程的接口

    控制服务器运行在 127.0.0.1:5001，仅本机可访问。
    app.py 中的 /api/system/shutdown 会调用此控制服务器的
    /api/control/shutdown 来关闭整个进程（包括 app.py 和 main.py）。
    """
    try:
        from flask import Flask, jsonify
        from werkzeug.serving import make_server
    except ImportError:
        print("[控制服务器] Flask 未安装，关闭功能不可用。请安装依赖：.venv\\Scripts\\pip install flask")
        return

    control_app = Flask(__name__)
    control_app.secret_key = os.urandom(24)

    @control_app.route('/api/control/shutdown', methods=['POST'])
    def api_shutdown():
        """关闭服务器：终止整个进程（app.py 子进程 + main.py 主进程）"""
        print("[控制服务器] 收到关闭请求，正在关闭服务器...")

        def delayed_exit():
            time.sleep(1)
            # 强制退出整个进程树
            os._exit(0)

        thread = threading.Thread(target=delayed_exit, daemon=True)
        thread.start()
        return jsonify({'success': True, 'message': '服务器正在关闭'})

    @control_app.route('/api/control/ping', methods=['GET'])
    def api_ping():
        """健康检查接口，用于确认控制服务器是否在运行"""
        return jsonify({'success': True, 'status': 'running'})

    try:
        # 使用独立线程运行控制服务器，绑定到本机 5001 端口
        server = make_server('127.0.0.1', 5001, control_app, threaded=True)
        print("[控制服务器] 已启动于 http://127.0.0.1:5001")
        server.serve_forever()
    except OSError as e:
        # 端口被占用等错误不阻塞主流程
        print(f"[控制服务器] 启动失败: {e}")
        print("[控制服务器] 管理界面的关闭服务器功能将不可用，但不影响 app.py 运行")
    except Exception as e:
        print(f"[控制服务器] 运行异常: {e}")


def get_venv_python():
    """获取虚拟环境中的 Python 可执行文件路径"""
    if os.name == 'nt':
        python_exe = os.path.join('.venv', 'Scripts', 'python.exe')
    else:
        python_exe = os.path.join('.venv', 'bin', 'python')

    if not os.path.exists(python_exe):
        print(f"✗ 未找到虚拟环境 Python：{python_exe}")
        print("  请先创建虚拟环境：python -m venv .venv")
        print("  并安装依赖：.venv\\Scripts\\python.exe -m pip install -r requirements.txt")
        return None
    return python_exe


def main():
    """主函数：启动控制服务器 + 通过虚拟环境运行 app.py"""
    # 切换到脚本所在目录，确保相对路径可用
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 启动控制服务器作为后台线程（用于支持管理界面的关闭服务器功能）
    control_thread = threading.Thread(target=start_control_server, daemon=True)
    control_thread.start()

    python_exe = get_venv_python()
    if not python_exe:
        return 1

    app_py = os.path.join(script_dir, 'app.py')
    if not os.path.exists(app_py):
        print(f"✗ 未找到 app.py：{app_py}")
        return 1

    print("=" * 60)
    print("中国中学场馆预约系统——算法穹顶社")
    print(f"使用虚拟环境：{python_exe}")
    print(f"启动应用：{app_py}")
    print(f"控制服务器：http://127.0.0.1:5001 (用于远程关闭)")
    print("=" * 60)

    try:
        # 通过虚拟环境的 Python 直接运行 app.py
        # 使用同一进程的标准 I/O，方便调试和查看日志
        return subprocess.call([python_exe, app_py] + sys.argv[1:])
    except KeyboardInterrupt:
        print("\n服务器已停止")
        return 0
    except Exception as e:
        print(f"启动失败: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
