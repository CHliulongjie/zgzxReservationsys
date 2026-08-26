#!/usr/bin/env python3
"""
发行版主启动脚本

功能：
1. 通过虚拟环境(.venv)运行解密后的 app.py
2. 启动时计算加密文件(.ljrk)哈希，发送到 top 服务器验证
3. 服务器验证通过后返回密码，本地解密文件运行
4. 程序退出时自动删除解密文件
5. 哈希不匹配时提示更新，从服务器下载新加密文件

通信服务器: https://longjieruankong.top
"""

import os
import sys
import subprocess
import threading
import time
import json
import hashlib
import shutil
import atexit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
import urllib.error


# ==================== 配置 ====================
# top 服务器地址
TOP_SERVER_URL = "https://longjieruankong.top"

# 加密文件目录（相对于脚本目录）
ENCRYPTED_DIR = 'encrypted'

# 解密文件目录（临时，运行后删除）
DECRYPTED_DIR = '.'  # 解密到根目录，方便 app.py 访问 data/ 和 static/

# 加密文件到原始路径的映射
ENCRYPTED_FILE_MAP = {
    'app.py.ljrk': 'app.py',
    'index.html.ljrk': os.path.join('templates', 'index.html'),
    'reservation.html.ljrk': os.path.join('templates', 'reservation.html'),
    'control_panel.html.ljrk': os.path.join('templates', 'control_panel.html'),
    'reservation.js.ljrk': os.path.join('static', 'js', 'reservation.js'),
}

# 全局状态
_app_process = None
_restart_flag = False
_decrypted_files = []  # 记录解密的文件路径，退出时删除


# ==================== FileDecryptor（与 top 服务器算法一致） ====================
class FileDecryptor:
    """文件解密器（与 longjieruankong.top 服务器加密算法互逆）"""

    def string_to_hex(self, text):
        """将字符串（支持中文）转换为16进制"""
        try:
            return text.encode('utf-8').hex().upper()
        except Exception:
            try:
                return text.encode('gbk').hex().upper()
            except:
                return text.encode('utf-8', errors='ignore').hex().upper()

    def hex_to_string(self, hex_str):
        """将16进制字符串转换回字符串"""
        try:
            return bytes.fromhex(hex_str).decode('utf-8')
        except UnicodeDecodeError:
            try:
                return bytes.fromhex(hex_str).decode('gbk')
            except:
                return None
        except:
            return None

    def hex_to_file(self, hex_str, output_path):
        """将16进制字符串写回文件"""
        try:
            hex_str = ''.join(c for c in hex_str if c in '0123456789ABCDEFabcdef')
            if len(hex_str) % 2 != 0:
                hex_str = hex_str[:-1]
            content = bytes.fromhex(hex_str)
            with open(output_path, 'wb') as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"  hex_to_file 失败: {e}")
            return False

    def hex_subtraction(self, hex1, hex2):
        """16进制减法（与加密的加法互逆）"""
        max_len = max(len(hex1), len(hex2))
        hex1_padded = hex1.zfill(max_len)
        hex2_padded = hex2.zfill(max_len)
        num1 = int(hex1_padded, 16)
        num2 = int(hex2_padded, 16)
        result = (num1 - num2) % (16 ** max_len)
        result_hex = format(result, f'0{max_len}X')
        return result_hex

    def combine_odd_even(self, odd, even):
        """合并奇偶位"""
        result = []
        min_len = min(len(odd), len(even))
        for i in range(min_len):
            result.append(odd[i])
            result.append(even[i])
        if len(odd) > min_len:
            result.append(odd[min_len])
        if len(even) > min_len:
            result.append(even[min_len])
        return ''.join(result)

    def decrypt_file(self, file_path, password, output_path):
        """解密 .ljrk 文件到指定路径"""
        try:
            # 1. 读取加密文件
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"加密文件不存在: {file_path}")

            with open(file_path, 'r', encoding='utf-8') as f:
                encrypted_content = f.read().strip()

            if '.' not in encrypted_content:
                raise ValueError("无效的加密文件格式")

            odd, even = encrypted_content.split('.', 1)
            full_encrypted_hex = self.combine_odd_even(odd, even)

            # 2. 密码处理
            password_hex = self.string_to_hex(password)
            n = len(password_hex)
            group_size = n + 1

            if n == 0:
                raise ValueError("密码转换后为空")

            if len(full_encrypted_hex) < group_size:
                raise ValueError("加密文件长度不足")

            # 3. 分组处理
            ext_group = full_encrypted_hex[:group_size]
            content_groups_hex = full_encrypted_hex[group_size:]

            content_groups = []
            for i in range(0, len(content_groups_hex), group_size):
                group = content_groups_hex[i:i + group_size]
                if len(group) == group_size:
                    content_groups.append(group)

            # 4. 解密后缀名
            decrypted_ext_hex = self.hex_subtraction(ext_group, password_hex)
            decrypted_ext_hex = decrypted_ext_hex.lstrip('0') or '0'
            file_ext = self.hex_to_string(decrypted_ext_hex)

            if file_ext is None:
                file_ext = "." + decrypted_ext_hex[:10]

            # 5. 解密文件内容
            decrypted_content_hex = ""
            for group in content_groups:
                decrypted_group = self.hex_subtraction(group, password_hex)
                if len(decrypted_group) < n:
                    decrypted_group = '0' * (n - len(decrypted_group)) + decrypted_group
                elif len(decrypted_group) > n:
                    decrypted_group = decrypted_group[-n:]
                decrypted_content_hex += decrypted_group

            # 6. 转换回文件
            # 确保输出目录存在（dirname 为空时跳过）
            out_dir = os.path.dirname(output_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

            success = self.hex_to_file(decrypted_content_hex, output_path)

            if not success:
                # 尝试逐步调整长度
                for i in range(len(decrypted_content_hex), 0, -2):
                    try:
                        test_hex = decrypted_content_hex[:i]
                        if self.hex_to_file(test_hex, output_path):
                            if os.path.getsize(output_path) > 0:
                                success = True
                                break
                    except Exception:
                        continue

            if not success:
                raise ValueError("文件内容转换失败")

            # 清理解密产生的 null 字节
            # 加密时末尾分组补 0 对齐，解密后会还原为多余的 \x00，
            # 对文本文件(.py/.html/.js)必须清除，否则 Python 解析报 SyntaxError
            try:
                with open(output_path, 'rb') as f:
                    raw = f.read()
                if b'\x00' in raw:
                    cleaned = raw.replace(b'\x00', b'')
                    with open(output_path, 'wb') as f:
                        f.write(cleaned)
            except Exception:
                pass

            return {'success': True, 'file_ext': file_ext}

        except Exception as e:
            return {'success': False, 'error': str(e)}


# ==================== 哈希计算 ====================
def compute_file_sha256(file_path):
    """计算文件 SHA256 哈希"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_all_encrypted_hashes():
    """计算 encrypted/ 目录下所有 .ljrk 文件的哈希"""
    hashes = {}
    encrypted_dir = os.path.join(os.getcwd(), ENCRYPTED_DIR)

    if not os.path.exists(encrypted_dir):
        print("[发行版] 加密文件目录不存在")
        return hashes

    for filename in os.listdir(encrypted_dir):
        if filename.endswith('.ljrk'):
            file_path = os.path.join(encrypted_dir, filename)
            file_hash = compute_file_sha256(file_path)
            hashes[filename] = file_hash

    return hashes


# ==================== 服务器通信 ====================
def verify_with_server(hashes):
    """向 top 服务器验证哈希值（使用标准库 urllib，无需 requests 依赖）

    返回:
      - (True, password): 验证通过，返回密码
      - (False, need_update_files): 需要更新，返回需更新的文件列表
      - (None, error_msg): 服务器错误
    """
    try:
        print(f"[发行版] 正在连接 {TOP_SERVER_URL} 验证文件...")
        url = f"{TOP_SERVER_URL}/api/release/verify"
        payload = json.dumps({'files': hashes}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json; charset=utf-8'},
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            return None, f"服务器返回错误: {e.code}"
        except urllib.error.URLError as e:
            if 'timed out' in str(e).lower():
                return None, "连接服务器超时"
            return None, "无法连接到服务器，请检查网络连接"

        result = json.loads(body)
        status = result.get('status')

        if status == 'ok':
            password = result.get('password')
            version = result.get('version', 'unknown')
            print(f"[发行版] 验证通过，版本: {version}")
            return True, password
        elif status == 'update':
            files = result.get('files', [])
            reason = result.get('reason', '核心文件有更新')
            print(f"[发行版] {reason}")
            print(f"[发行版] 需要更新的文件: {', '.join(files)}")
            return False, files
        else:
            msg = result.get('message', '未知错误')
            return None, msg

    except Exception as e:
        return None, str(e)


def download_encrypted_file(filename):
    """从 top 服务器下载加密文件（使用标准库 urllib，无需 requests 依赖）"""
    try:
        print(f"[发行版] 正在下载 {filename}...")
        url = f"{TOP_SERVER_URL}/api/release/download/{filename}"
        req = urllib.request.Request(url, method='GET')

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                content = resp.read()
        except urllib.error.HTTPError as e:
            print(f"[发行版] 下载失败: {e.code}")
            return False
        except urllib.error.URLError as e:
            print(f"[发行版] 下载 {filename} 失败: {e}")
            return False

        encrypted_dir = os.path.join(os.getcwd(), ENCRYPTED_DIR)
        file_path = os.path.join(encrypted_dir, filename)

        with open(file_path, 'wb') as f:
            f.write(content)

        print(f"[发行版] {filename} 下载完成")
        return True

    except Exception as e:
        print(f"[发行版] 下载 {filename} 失败: {e}")
        return False


def update_encrypted_files(file_list):
    """下载并更新加密文件"""
    success = 0
    failed = []

    for filename in file_list:
        if download_encrypted_file(filename):
            success += 1
        else:
            failed.append(filename)

    print(f"[发行版] 更新完成: 成功 {success}/{len(file_list)}")
    if failed:
        print(f"[发行版] 以下文件更新失败: {', '.join(failed)}")
    return len(failed) == 0


# ==================== 解密与清理 ====================
def decrypt_all_files(password):
    """用密码解密所有 .ljrk 文件到根目录"""
    global _decrypted_files

    decryptor = FileDecryptor()
    encrypted_dir = os.path.join(os.getcwd(), ENCRYPTED_DIR)

    print("[发行版] 开始解密文件...")
    success = 0
    failed = []

    for ljrk_name, original_path in ENCRYPTED_FILE_MAP.items():
        ljrk_path = os.path.join(encrypted_dir, ljrk_name)
        output_path = os.path.join(os.getcwd(), original_path)

        if not os.path.exists(ljrk_path):
            print(f"  [!] 加密文件不存在: {ljrk_name}")
            failed.append(ljrk_name)
            continue

        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        result = decryptor.decrypt_file(ljrk_path, password, output_path)

        if result.get('success'):
            _decrypted_files.append(output_path)
            success += 1
            print(f"  [OK] {ljrk_name} -> {original_path}")
        else:
            print(f"  [X] {ljrk_name} 解密失败: {result.get('error')}")
            failed.append(ljrk_name)

    print(f"[发行版] 解密完成: 成功 {success}/{len(ENCRYPTED_FILE_MAP)}")

    if failed:
        print(f"[发行版] 以下文件解密失败: {', '.join(failed)}")
        return False

    return True


def cleanup_decrypted_files():
    """清理所有解密的文件"""
    global _decrypted_files

    if not _decrypted_files:
        return

    print("[发行版] 正在清理解密文件...")

    for file_path in _decrypted_files:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"  [OK] 删除: {file_path}")
        except Exception as e:
            print(f"  [!] 删除失败 {file_path}: {e}")

    # 清理可能为空的目录
    dirs_to_clean = ['templates', os.path.join('static', 'js')]
    for dir_path in dirs_to_clean:
        full_path = os.path.join(os.getcwd(), dir_path)
        if os.path.exists(full_path):
            try:
                if not os.listdir(full_path):
                    os.rmdir(full_path)
            except Exception:
                pass

    _decrypted_files = []
    print("[发行版] 清理完成")


# ==================== 控制服务器 ====================
def start_control_server():
    """启动控制服务器（端口5001），支持远程关闭/重启"""
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
                print("[控制服务器] 收到关闭请求...")
                def delayed_exit():
                    time.sleep(1)
                    # 终止 app.py 子进程，避免成为孤儿进程
                    # （否则第一次关闭只终止 main.py，app.py 仍在 5000 端口运行，
                    #   需点第二次走后备自身退出才真正关闭）
                    try:
                        if _app_process is not None and _app_process.poll() is None:
                            _app_process.terminate()
                            try:
                                _app_process.wait(timeout=3)
                            except Exception:
                                _app_process.kill()
                    except Exception as e:
                        print(f"[控制服务器] 终止 app.py 失败: {e}")
                    # 关闭前清理解密文件（os._exit 不触发 atexit，必须手动清理）
                    try:
                        cleanup_decrypted_files()
                    except Exception as e:
                        print(f"[控制服务器] 清理解密文件失败: {e}")
                    os._exit(0)
                threading.Thread(target=delayed_exit, daemon=True).start()
                self._send_json(200, {'success': True, 'message': '服务器正在关闭'})
            elif self.path.startswith('/api/control/restart'):
                print("[控制服务器] 收到重启请求...")
                _restart_flag = True
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


# ==================== 虚拟环境管理（与原 main.py 一致） ====================
def get_venv_python():
    if os.name == 'nt':
        python_exe = os.path.join('.venv', 'Scripts', 'python.exe')
    else:
        python_exe = os.path.join('.venv', 'bin', 'python')
    if os.path.exists(python_exe):
        return python_exe
    return None


def get_requirements_list():
    req_path = os.path.join(os.getcwd(), 'requirements.txt')
    if not os.path.exists(req_path):
        return []
    packages = []
    with open(req_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            for sep in ['==', '>=', '<=', '>', '<', '!=', '~=', '===']:
                if sep in line:
                    line = line.split(sep)[0].strip()
                    break
            if line:
                packages.append(line)
    return packages


def get_installed_packages(python_exe):
    try:
        result = subprocess.run(
            [python_exe, '-m', 'pip', 'list', '--format=freeze'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', timeout=30
        )
        if result.returncode != 0:
            return set()
        installed = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if '==' in line:
                pkg_name = line.split('==')[0].lower().replace('-', '_')
                installed.add(pkg_name)
        return installed
    except Exception:
        return set()


def check_dependencies(python_exe):
    required = get_requirements_list()
    if not required:
        return []
    installed = get_installed_packages(python_exe)
    missing = []
    for pkg in required:
        pkg_norm = pkg.lower().replace('-', '_')
        if pkg_norm not in installed:
            missing.append(pkg)
    return missing


def install_package(python_exe, package_name, prefer_binary=True):
    cmd = [python_exe, '-m', 'pip', 'install']
    if prefer_binary:
        cmd.append('--prefer-binary')
    cmd.append(package_name)
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        for line in process.stdout:
            print(f"    {line.rstrip()}")
        process.wait()
        return process.returncode == 0
    except Exception as e:
        print(f"    安装异常: {e}")
        return False


def check_and_install_dependencies(python_exe):
    missing = check_dependencies(python_exe)
    if not missing:
        print("[依赖检查] 所有依赖已安装")
        return True
    print(f"[依赖检查] 检测到 {len(missing)} 个缺失的依赖包：")
    for pkg in missing:
        print(f"    - {pkg}")
    print()
    total = len(missing)
    success = 0
    failed = []
    for i, pkg in enumerate(missing, 1):
        print(f"  [{i}/{total}] 正在安装 {pkg}...")
        ok = install_package(python_exe, pkg, prefer_binary=True)
        if ok:
            success += 1
            print(f"  [{i}/{total}] [OK] {pkg} 安装成功")
        else:
            failed.append(pkg)
            print(f"  [{i}/{total}] [X] {pkg} 安装失败，跳过继续")
        print()
    print(f"[依赖检查] 安装完成: 成功 {success}/{total}")
    if failed:
        print(f"[依赖检查] 以下包安装失败: {', '.join(failed)}")
    return len(failed) == 0


def _pause_on_error():
    print()
    print("=" * 60)
    print("配置过程中出现错误，请查看上方日志")
    print("按回车键退出...")
    print("=" * 60)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass


def create_virtualenv():
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

    # 步骤1：创建虚拟环境
    print("\n[步骤 1/3] 正在创建虚拟环境 (.venv)...")
    try:
        process = subprocess.Popen(
            [sys.executable, '-m', 'venv', '.venv'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        for line in process.stdout:
            print(f"  {line.rstrip()}")
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, 'venv')
    except subprocess.CalledProcessError as e:
        print(f"\n[X] 创建虚拟环境失败 (退出码: {e.returncode})")
        _pause_on_error()
        return False
    except Exception as e:
        print(f"\n[X] 创建虚拟环境失败: {e}")
        _pause_on_error()
        return False
    print("[OK] 虚拟环境创建成功")

    python_exe = get_venv_python()
    if not python_exe:
        print("\n[X] 虚拟环境创建后仍未找到 Python 可执行文件")
        _pause_on_error()
        return False

    # 步骤2：升级pip
    print("\n[步骤 2/3] 正在升级 pip...")
    try:
        process = subprocess.Popen(
            [python_exe, '-m', 'pip', 'install', '--upgrade', 'pip'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        for line in process.stdout:
            print(f"  {line.rstrip()}")
        process.wait()
    except Exception:
        pass
    print("[OK] pip 已就绪")

    # 步骤3：安装依赖（逐个安装）
    print("\n[步骤 3/3] 正在安装依赖 (requirements.txt)...")
    packages = get_requirements_list()
    total = len(packages)
    success = 0
    failed = []
    print(f"  共 {total} 个依赖包，逐个安装")
    print()
    for i, pkg in enumerate(packages, 1):
        print(f"  [{i}/{total}] 正在安装 {pkg}...")
        ok = install_package(python_exe, pkg, prefer_binary=True)
        if ok:
            success += 1
            print(f"  [{i}/{total}] [OK] {pkg} 安装成功")
        else:
            failed.append(pkg)
            print(f"  [{i}/{total}] [X] {pkg} 安装失败，跳过继续")
        print()
    print(f"  安装完成: 成功 {success}/{total}")
    if failed:
        print(f"  以下包安装失败: {', '.join(failed)}")

    print()
    print("=" * 60)
    print("[OK] 虚拟环境配置完成！")
    print(f"  Python: {python_exe}")
    print("=" * 60)
    print()
    return python_exe


# ==================== 主函数 ====================
def main():
    """发行版主启动流程：
    1. 检查虚拟环境
    2. 计算加密文件哈希 → 发送到 top 服务器验证
    3. 验证通过 → 获取密码 → 解密文件
    4. 运行解密后的 app.py
    5. 退出时自动清理解密文件
    """
    global _app_process, _restart_flag

    # 切换到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # 注册退出清理
    atexit.register(cleanup_decrypted_files)

    print("=" * 60)
    print("中国中学场馆预约系统 - 发行版")
    print("算法穹顶社")
    print("=" * 60)
    print()

    # 1. 检查虚拟环境
    python_exe = get_venv_python()
    if not python_exe:
        python_exe = create_virtualenv()
        if not python_exe:
            return 1
    else:
        print("[依赖检查] 正在检测虚拟环境中的依赖安装情况...")
        check_and_install_dependencies(python_exe)
        print()

    # 2. 计算加密文件哈希
    print("[发行版] 计算本地加密文件哈希...")
    local_hashes = compute_all_encrypted_hashes()

    if not local_hashes:
        print("[发行版] 未找到加密文件，请检查 encrypted/ 目录")
        _pause_on_error()
        return 1

    print(f"[发行版] 发现 {len(local_hashes)} 个加密文件")
    for name, hash_val in local_hashes.items():
        print(f"  - {name}: {hash_val[:16]}...")
    print()

    # 3. 向服务器验证
    result, data = verify_with_server(local_hashes)

    if result is None:
        # 服务器错误
        print(f"[发行版] 无法验证: {data}")
        print("[发行版] 是否跳过验证直接运行？（需要密码）")
        try:
            choice = input("跳过验证并手动输入密码？(y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 1
        if choice != 'y':
            return 1
        try:
            password = input("请输入密码: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 1
        if not password:
            print("[发行版] 密码为空，无法解密")
            return 1
    elif result is False:
        # 需要更新
        need_update_files = data
        print()
        print("[发行版] 核心文件有更新，是否更新后启动？")
        print(f"  需要更新的文件: {', '.join(need_update_files)}")
        try:
            choice = input("是否下载更新？(y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 1

        if choice != 'y':
            print("[发行版] 用户取消更新，无法启动")
            return 1

        # 下载更新
        if not update_encrypted_files(need_update_files):
            print("[发行版] 部分文件更新失败，是否继续尝试运行？")
            try:
                choice = input("继续运行？(y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return 1
            if choice != 'y':
                return 1

        # 重新计算哈希并验证
        print()
        print("[发行版] 重新计算哈希并验证...")
        local_hashes = compute_all_encrypted_hashes()
        result, data = verify_with_server(local_hashes)

        if result is None:
            print(f"[发行版] 验证失败: {data}")
            return 1
        elif result is False:
            print("[发行版] 更新后仍有文件不匹配，请联系管理员")
            return 1

    # 4. 获取密码，解密文件
    password = data  # data 现在是密码字符串

    if not decrypt_all_files(password):
        print("[发行版] 部分文件解密失败，无法继续")
        _pause_on_error()
        return 1

    # 5. 启动控制服务器
    control_thread = threading.Thread(target=start_control_server, daemon=True)
    control_thread.start()

    # 检查解密后的 app.py 是否存在
    app_py = os.path.join(os.getcwd(), 'app.py')
    if not os.path.exists(app_py):
        print(f"[发行版] 解密后未找到 app.py: {app_py}")
        return 1

    print()
    print("=" * 60)
    print("[发行版] 启动应用...")
    print(f"  Python: {python_exe}")
    print(f"  应用: {app_py}")
    print(f"  控制服务器: http://127.0.0.1:5001")
    print("=" * 60)
    print()

    # 6. 运行 app.py（支持重启）
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
            break
        except Exception as e:
            print(f"[main] 启动失败: {e}")
            break

        # 检查是否需要重启
        if _restart_flag:
            _restart_flag = False
            print("[main] 检测到重启标志，3 秒后重新启动...")
            time.sleep(3)
            print("=" * 60)
            print("[main] 正在重启...")
            print("=" * 60)
            continue
        else:
            break

    # 7. 清理解密文件
    cleanup_decrypted_files()
    print("[main] 程序已退出")
    return 0


if __name__ == '__main__':
    sys.exit(main())
