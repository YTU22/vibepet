import os
import sys
import time
import subprocess
import urllib.request
import urllib.error

UPDATE_API_URL = "https://vibeharbor.art/api/github/vibepet/latest"
DOWNLOAD_API_URL = "https://vibeharbor.art/api/github/vibepet/download-latest"


def check_for_update(current_version):
    """检查是否有新版本，返回 (has_update, latest_version, download_url)"""
    try:
        req = urllib.request.Request(
            UPDATE_API_URL,
            headers={"User-Agent": "VibePet-UpdateChecker"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        latest = data.get("tag_name", "").lstrip("v")
        if not latest:
            return False, None, None
        
        def parse_ver(v):
            try:
                return tuple(int(x) for x in v.split(".")[:3])
            except Exception:
                return (0, 0, 0)
        
        if parse_ver(latest) > parse_ver(current_version):
            return True, latest, DOWNLOAD_API_URL
        return False, latest, None
    except Exception as e:
        print(f"Check update failed: {e}")
        return False, None, None


def download_update(download_url, save_path, progress_callback=None):
    """下载更新文件，返回是否成功"""
    try:
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "VibePet-Updater"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            total_size = int(resp.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(save_path, 'wb') as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False


def create_update_bat(old_exe_path, new_exe_path):
    """创建批处理脚本用于替换 exe 并启动新版本"""
    bat_content = f'''@echo off
chcp 65001 >nul
echo 正在等待 VibePet 关闭...

:wait_loop
tasklist | findstr "VibePet.exe" >nul
if %errorlevel% == 0 (
    timeout /t 1 /nobreak >nul
    goto wait_loop
)

echo 正在更新...
timeout /t 1 /nobreak >nul

copy /Y "{new_exe_path}" "{old_exe_path}"
if %errorlevel% neq 0 (
    echo 更新失败，请手动复制文件
    pause
    exit /b 1
)

echo 更新完成，正在启动新版本...
start "" "{old_exe_path}"

del "{new_exe_path}"
del "%~f0"
'''
    bat_path = os.path.join(os.path.dirname(new_exe_path), "vibepet_update.bat")
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat_content)
    return bat_path


def run_updater(old_exe_path, new_exe_path):
    """启动更新器（批处理），然后退出当前程序"""
    bat_path = create_update_bat(old_exe_path, new_exe_path)
    # 使用 cmd /c start 让批处理独立运行
    subprocess.Popen(
        ['cmd', '/c', 'start', '', bat_path],
        shell=False,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
