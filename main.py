#!/usr/bin/env python3
"""
主启动脚本

功能：
1. 通过项目目录下的虚拟环境(.venv)直接运行 app.py，方便功能测试
2. 提供控制服务器(端口5001)，支持从管理界面远程关闭/重启整个服务器进程
3. 检测虚拟环境是否存在，若不存在则询问是否自动创建

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


# 全局状态：app.py 子进程对象和重启标志
# 控制服务器通过这些全局变量与主循环交互
_app_process = None        # 当前 app.py 子进程
_restart_flag = False      # 是否需要重启（True=重启 app.py，False=正常退出）


def start_control_server():
    """启动控制服务器，提供关闭/重启主进程的接口

    控制服务器运行在 127.0.0.1:5001，仅本机可访问。
    - POST /api/control/shutdown  关闭整个进程
    - POST /api/control/restart   重启 app.py（终止子进程后由主循环重新启动）
    - GET  /api/control/ping      健康检查

    使用标准库 http.server 实现，无需 Flask 依赖。
    """
    global _app_process, _restart_flag

    class ControlHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code, payload):
            body = json.dumps(payload).encode('utf-8')
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith('/api/control/ping'):
                self._send_json(200, {'success': True, 'status': 'running'})
            else:
                self._send_json(404, {'success': False, 'error': 'Not Found'})

        def do_POST(self):
            global _restart_flag
            if self.path.startswith('/api/control/shutdown'):
                print("[控制服务器] 收到关闭请求，正在关闭服务器...")

                def delayed_exit():
                    time.sleep(1)
                    os._exit(0)

                thread = threading.Thread(target=delayed_exit, daemon=True)
                thread.start()
                self._send_json(200, {'success': True, 'message': '服务器正在关闭'})

            elif self.path.startswith('/api/control/restart'):
                print("[控制服务器] 收到重启请求，正在重启 app.py...")
                # 设置重启标志，主循环检测到后会重新启动 app.py
                _restart_flag = True
                # 终止当前 app.py 子进程，使其退出
                if _app_process is not None:
                    try:
                        _app_process.terminate()
                    except Exception as e:
                        print(f"[控制服务器] 终止子进程失败: {e}")
                self._send_json(200, {'success': True, 'message': '服务器正在重启'})

            else:
                self._send_json(404, {'success': False, 'error': 'Not Found'})

        def log_message(self, format, *args):
            pass

    try:
        server = ThreadingHTTPServer(('127.0.0.1', 5001), ControlHandler)
        print("[控制服务器] 已启动于 http://127.0.0.1:5001")
        server.serve_forever()
    except OSError as e:
        print(f"[控制服务器] 启动失败: {e}")
        print("[控制服务器] 管理界面的关闭/重启服务器功能将不可用，但不影响 app.py 运行")
    except Exception as e:
        print(f"[控制服务器] 运行异常: {e}")


def get_venv_python():
    """获取虚拟环境中的 Python 可执行文件路径

    如果虚拟环境不存在，返回 None。
    """
    if os.name == 'nt':
        python_exe = os.path.join('.venv', 'Scripts', 'python.exe')
    else:
        python_exe = os.path.join('.venv', 'bin', 'python')

    if os.path.exists(python_exe):
        return python_exe
    return None


def create_virtualenv():
    """自动创建虚拟环境并安装依赖

    流程：
    1. python -m venv .venv 创建虚拟环境
    2. .venv\\Scripts\\python.exe -m pip install --upgrade pip 升级 pip
    3. .venv\\Scripts\\python.exe -m pip install -r requirements.txt 安装依赖

    显示实时进度，出错后按空格键关闭。
    """
    print()
    print("=" * 60)
    print("检测到未找到虚拟环境 .venv")
    print("是否自动创建虚拟环境并安装依赖？")
    print("  y - 自动创建虚拟环境并安装依赖")
    print("  n - 取消并退出")
    print("=" * 60)

    try:
        choice = input("请输入选择 (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return False

    if choice != 'y':
        print("已取消创建虚拟环境")
        return False

    print()
    print("=" * 60)
    print("开始创建虚拟环境...")
    print("=" * 60)

    # 步骤 1：创建虚拟环境
    print("\n[步骤 1/3] 正在创建虚拟环境 (.venv)...")
    print(f"  命令: {sys.executable} -m venv .venv")

    try:
        process = subprocess.Popen(
            [sys.executable, '-m', 'venv', '.venv'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        # 实时显示输出
        for line in process.stdout:
            print(f"  {line.rstrip()}")

        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, 'venv')
    except subprocess.CalledProcessError as e:
        print(f"\n✗ 创建虚拟环境失败 (退出码: {e.returncode})")
        _pause_on_error()
        return False
    except Exception as e:
        print(f"\n✗ 创建虚拟环境失败: {e}")
        _pause_on_error()
        return False

    print("✓ 虚拟环境创建成功")

    # 获取虚拟环境中的 Python 路径
    python_exe = get_venv_python()
    if not python_exe:
        print("\n✗ 虚拟环境创建后仍未找到 Python 可执行文件")
        _pause_on_error()
        return False

    # 步骤 2：升级 pip
    print("\n[步骤 2/3] 正在升级 pip...")
    print(f"  命令: {python_exe} -m pip install --upgrade pip")

    try:
        process = subprocess.Popen(
            [python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        for line in process.stdout:
            print(f"  {line.rstrip()}")

        process.wait()
        if process.returncode != 0:
            print(f"  ! pip 升级失败 (退出码: {process.returncode})，继续安装依赖...")
    except Exception as e:
        print(f"  ! pip 升级失败: {e}，继续安装依赖...")

    print("✓ pip 已就绪")

    # 步骤 3：安装依赖
    print("\n[步骤 3/3] 正在安装依赖 (requirements.txt)...")
    requirements_path = os.path.join(os.getcwd(), 'requirements.txt')
    if not os.path.exists(requirements_path):
        print(f"  ! 未找到 requirements.txt ({requirements_path})")
        print("  跳过依赖安装，请在虚拟环境创建后手动安装依赖")
        print("  命令: .venv\\Scripts\\python.exe -m pip install -r requirements.txt")
    else:
        print(f"  命令: {python_exe} -m pip install -r requirements.txt")
        print("  正在安装（这可能需要几分钟，请耐心等待）...")
        print()

        try:
            process = subprocess.Popen(
                [python_exe, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

            for line in process.stdout:
                print(f"  {line.rstrip()}")

            process.wait()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, 'pip install')
        except subprocess.CalledProcessError as e:
            print(f"\n✗ 依赖安装失败 (退出码: {e.returncode})")
            print("  请检查网络连接或 requirements.txt 内容")
            _pause_on_error()
            return False
        except Exception as e:
            print(f"\n✗ 依赖安装失败: {e}")
            _pause_on_error()
            return False

        print("✓ 依赖安装完成")

    print()
    print("=" * 60)
    print("✓ 虚拟环境配置完成！")
    print(f"  Python: {python_exe}")
    print("=" * 60)
    print()

    return python_exe


def _pause_on_error():
    """出错后提示按空格键关闭，防止窗口直接关闭看不到错误"""
    print()
    print("=" * 60)
    print("配置过程中出现错误，请查看上方日志")
    print("按回车键退出...")
    print("=" * 60)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def main():
    """主函数：启动控制服务器 + 通过虚拟环境运行 app.py（支持重启循环）

    如果虚拟环境不存在，询问是否自动创建。
    """
    global _app_process, _restart_flag

    # 切换到脚本所在目录，确保相对路径可用
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 检查虚拟环境是否存在，不存在则询问是否创建
    python_exe = get_venv_python()
    if not python_exe:
        python_exe = create_virtualenv()
        if not python_exe:
            return 1

    app_py = os.path.join(script_dir, 'app.py')
    if not os.path.exists(app_py):
        print(f"✗ 未找到 app.py：{app_py}")
        return 1

    # 启动控制服务器作为后台线程
    control_thread = threading.Thread(target=start_control_server, daemon=True)
    control_thread.start()

    print("=" * 60)
    print("中国中学场馆预约系统——算法穹顶社")
    print(f"使用虚拟环境：{python_exe}")
    print(f"启动应用：{app_py}")
    print(f"控制服务器：http://127.0.0.1:5001 (用于远程关闭/重启)")
    print("=" * 60)

    # 主循环：支持重启
    # - 正常退出（子进程结束且 _restart_flag=False）：跳出循环，main.py 退出
    # - 重启（_restart_flag=True）：重新启动 app.py
    while True:
        try:
            _app_process = subprocess.Popen([python_exe, app_py] + sys.argv[1:])
            exit_code = _app_process.wait()
            print(f"[main] app.py 退出，退出码: {exit_code}")
        except KeyboardInterrupt:
            print("\n[main] 收到 Ctrl+C，正在停止...")
            _restart_flag = False
            if _app_process is not None:
                try:
                    _app_process.terminate()
                    _app_process.wait(timeout=5)
                except Exception:
                    pass
            return 0
        except Exception as e:
            print(f"[main] 启动失败: {e}")
            return 1

        # 检查是否需要重启
        if _restart_flag:
            _restart_flag = False
            print("[main] 检测到重启标志，3 秒后重新启动 app.py...")
            time.sleep(3)
            print("=" * 60)
            print("[main] 正在重启 app.py...")
            print("=" * 60)
            continue
        else:
            print("[main] 正常退出")
            return exit_code


if __name__ == '__main__':
    sys.exit(main())
