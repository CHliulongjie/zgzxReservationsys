#!/usr/bin/env python3
"""
主启动脚本

功能：
1. 通过项目目录下的虚拟环境(.venv)直接运行 app.py，方便功能测试
2. 提供控制服务器(端口5001)，支持从管理界面远程关闭整个服务器进程

控制服务器使用 Python 标准库 http.server 实现，不依赖 Flask，
这样即使用系统 Python 运行 main.py 也能正常工作。

使用方法：直接运行 python main.py 即可启动 app.py
"""

import os
import sys
import subprocess
import threading
import time
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_control_server():
    """启动控制服务器，提供关闭主进程的接口

    控制服务器运行在 127.0.0.1:5001，仅本机可访问。
    app.py 中的 /api/system/shutdown 会调用此控制服务器的
    /api/control/shutdown 来关闭整个进程（包括 app.py 和 main.py）。

    使用标准库 http.server 实现，无需 Flask 依赖。
    """
    class ControlHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code, payload):
            body = json.dumps(payload).encode('utf-8')
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            # 健康检查：GET /api/control/ping
            if self.path.startswith('/api/control/ping'):
                self._send_json(200, {'success': True, 'status': 'running'})
            else:
                self._send_json(404, {'success': False, 'error': 'Not Found'})

        def do_POST(self):
            # 关闭服务器：POST /api/control/shutdown
            if self.path.startswith('/api/control/shutdown'):
                print("[控制服务器] 收到关闭请求，正在关闭服务器...")

                def delayed_exit():
                    time.sleep(1)
                    # 强制退出整个进程树（app.py 子进程会随主进程一起退出）
                    os._exit(0)

                thread = threading.Thread(target=delayed_exit, daemon=True)
                thread.start()
                self._send_json(200, {'success': True, 'message': '服务器正在关闭'})
            else:
                self._send_json(404, {'success': False, 'error': 'Not Found'})

        def log_message(self, format, *args):
            # 静默日志输出，避免污染控制台
            pass

    try:
        # 使用独立线程运行控制服务器，绑定到本机 5001 端口
        server = ThreadingHTTPServer(('127.0.0.1', 5001), ControlHandler)
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
    # 使用标准库实现，不依赖 Flask，任何 Python 都能运行
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
