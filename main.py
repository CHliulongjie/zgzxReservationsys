#!/usr/bin/env python3
"""
主启动脚本

功能：通过项目目录下的虚拟环境(.venv)直接运行 app.py，
方便对 app.py 的功能进行测试。

使用方法：直接运行 python main.py 即可启动 app.py
"""

import os
import sys
import subprocess


def get_venv_python():
    """获取虚拟环境中的 Python 可执行文件路径"""
    # 兼容 Windows 和 POSIX 路径
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
    """主函数：通过虚拟环境运行 app.py"""
    # 切换到脚本所在目录，确保相对路径可用
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

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
