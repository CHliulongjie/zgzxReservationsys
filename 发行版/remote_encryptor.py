"""
远程加密解密工具
用于与2号服务器进行加密解密操作
"""

import os
import requests
import tempfile


class RemoteEncryptor:
    def __init__(self, server_url="https://longjieruankong.top"):
        self.server_url = server_url
        self.password = "算法穹顶版权所有"
    
    def encrypt_file_remote(self, file_path, output_path):
        """
        通过远程服务器加密文件
        """
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {'password': self.password}
                
                response = requests.post(f"{self.server_url}/api/encrypt",
                                       files=files,
                                       data=data,
                                       timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        download_url = f"{self.server_url}/api/download/{result['file_id']}"
                        download_response = requests.get(download_url)
                        
                        if download_response.status_code == 200:
                            with open(output_path, 'wb') as output_file:
                                output_file.write(download_response.content)
                            return {'success': True}
                        else:
                            return {'success': False, 'error': '下载加密文件失败'}
                    else:
                        return {'success': False, 'error': result.get('error', '加密失败')}
                else:
                    return {'success': False, 'error': f'服务器返回错误: {response.status_code}'}
                    
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def decrypt_file_remote(self, file_path, output_path):
        """
        通过远程服务器解密文件
        """
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                data = {'password': self.password}
                
                response = requests.post(f"{self.server_url}/api/decrypt",
                                       files=files,
                                       data=data,
                                       timeout=60)
                
                if response.status_code == 200:
                    with open(output_path, 'wb') as output_file:
                        output_file.write(response.content)
                    try:
                        with open(output_path, 'rb') as f:
                            content = f.read()
                            if b'\x00' in content:
                                cleaned_content = content.replace(b'\x00', b'')
                                with open(output_path, 'wb') as f_clean:
                                    f_clean.write(cleaned_content)
                                print(f"警告: 检测到并清理了 {content.count(b'\\x00')} 个 null 字节")
                    except:
                        pass
                    return {'success': True}
                else:
                    try:
                        result = response.json()
                        error_msg = result.get('error', f'服务器返回错误: {response.status_code}')
                        if '减法结果为负' in error_msg:
                            error_msg += " (可能是服务器端加密算法与本地不匹配)"
                        return {'success': False, 'error': error_msg}
                    except:
                        return {'success': False, 'error': f'服务器返回错误: {response.status_code}, 响应内容: {response.text[:200]}...'}
                    
        except Exception as e:
            error_msg = str(e)
            if '减法结果为负' in error_msg:
                error_msg += " (服务器端加密算法可能与本地不匹配，建议联系管理员更新服务器算法)"
            return {'success': False, 'error': error_msg}


remote_encryptor = RemoteEncryptor()
