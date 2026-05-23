"""
主启动脚本
"""

import os
import sys
import subprocess
import time
import signal
import threading
import atexit
from remote_encryptor import remote_encryptor
from flask import Flask, request, jsonify
import socket


def check_dependencies():
    """检查依赖"""
    required = ['flask', 'pandas', 'openpyxl', 'pyyaml']

    try:
        import flask
        import pandas
        import openpyxl
        import yaml
        print("✓ 所有依赖已安装")
        return True
    except ImportError as e:
        print(f"✗ 缺少依赖: {e}")
        print("正在安装依赖...")

        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
            print("✓ 依赖安装成功")
            return True
        except:
            print("✗ 依赖安装失败")
            return False


def clean_null_bytes(file_path):
    """清理文件中的 null 字节"""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        cleaned_content = content.replace(b'\x00', b'')
        
        if len(cleaned_content) != len(content):
            with open(file_path, 'wb') as f:
                f.write(cleaned_content)
            print(f"  - 已清理 {len(content) - len(cleaned_content)} 个 null 字节")
        return True
    except Exception as e:
        print(f"  - 清理 null 字节失败: {e}")
        return False

def decrypt_core_files():
    """解密核心文件"""
    print("正在解密核心文件...")
    
    if os.path.exists('app.py.ljrk'):
        result = remote_encryptor.decrypt_file_remote('app.py.ljrk', 'app.py')
        if result['success']:
            print("✓ app.py 解密成功")
            clean_null_bytes('app.py')
        else:
            print(f"✗ app.py 远程解密失败: {result['error']}")
            return False
    else:
        print("⚠ app.py 加密文件不存在，跳过解密")
    
    if os.path.exists('config_manager.py.ljrk'):
        result = remote_encryptor.decrypt_file_remote('config_manager.py.ljrk', 'config_manager.py')
        if result['success']:
            print("✓ config_manager.py 解密成功")
            clean_null_bytes('config_manager.py')
        else:
            print(f"✗ config_manager.py 远程解密失败: {result['error']}")
            return False
    else:
        print("⚠ config_manager.py 加密文件不存在，跳过解密")
    
    if os.path.exists('templates') and os.path.isdir('templates'):
        for filename in os.listdir('templates'):
            if filename.endswith('.html.ljrk'):
                encrypted_path = os.path.join('templates', filename)
                decrypted_path = os.path.join('templates', filename[:-5])
                result = remote_encryptor.decrypt_file_remote(encrypted_path, decrypted_path)
                if result['success']:
                    print(f"✓ {decrypted_path} 解密成功")
                    clean_null_bytes(decrypted_path)
                else:
                    print(f"✗ {decrypted_path} 远程解密失败: {result['error']}")
                    return False
    
    return True


def cleanup_decrypted_files():
    """清理解密的文件"""
    print("正在清理解密的文件...")
    
    if os.path.exists('app.py'):
        os.remove('app.py')
        print("✓ app.py 已清理")
    
    if os.path.exists('config_manager.py'):
        os.remove('config_manager.py')
        print("✓ config_manager.py 已清理")
    
    if os.path.exists('templates') and os.path.isdir('templates'):
        for filename in os.listdir('templates'):
            if filename.endswith('.html') and not filename.endswith('.html.ljrk'):
                decrypted_path = os.path.join('templates', filename)
                if os.path.exists(decrypted_path):
                    os.remove(decrypted_path)
                    print(f"✓ {decrypted_path} 已清理")

def signal_handler(sig, frame):
    """信号处理器，用于捕获关闭信号"""
    print('\n接收到关闭信号，正在清理解密的文件...')
    cleanup_decrypted_files()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def setup_directories():
    """设置目录"""
    from config_manager import config_manager
    print("✓ 目录结构已检查")
    return True

control_app = Flask(__name__)
control_app.secret_key = os.urandom(24)

@control_app.route('/api/control/shutdown', methods=['POST'])
def api_shutdown():
    """关闭服务器"""
    print("收到关闭请求，正在清理文件...")
    cleanup_decrypted_files()
    def delayed_exit():
        time.sleep(1)
        os._exit(0)
    thread = threading.Thread(target=delayed_exit)
    thread.daemon = True
    thread.start()
    return jsonify({'success': True, 'message': '服务器正在关闭'})

@control_app.route('/api/control/restart', methods=['POST'])
def api_restart():
    """重启服务器"""
    print("收到重启请求，正在清理文件...")
    cleanup_decrypted_files()
    def delayed_restart():
        time.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    thread = threading.Thread(target=delayed_restart)
    thread.daemon = True
    thread.start()
    return jsonify({'success': True, 'message': '服务器正在重启'})

def start_control_server():
    """启动控制服务器"""
    try:
        from werkzeug.serving import make_server
        server = make_server('127.0.0.1', 5001, control_app, threaded=True)
        server.serve_forever()
    except Exception as e:
        print(f"控制服务器启动失败: {e}")

def main():
    """主函数"""
    print("=" * 60)
    print("中国中学场馆预约系统——算法穹顶社")
    print("=" * 60)

    control_thread = threading.Thread(target=start_control_server, daemon=True)
    control_thread.start()

    if not check_dependencies():
        return 1

    if not decrypt_core_files():
        print("核心文件解密失败，无法启动")
        return 1

    setup_directories()

    try:
        from app import start_server
        return start_server()
    except KeyboardInterrupt:
        print("\n服务器已停止")
        return 0
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
