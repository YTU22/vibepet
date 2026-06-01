#!/usr/bin/env python3
"""
VibePet 独立更新器
用法: VibePetUpdater.exe <app_dir> <zip_path>
"""
import os
import sys
import time
import shutil
import subprocess
import zipfile


def wait_for_exit(app_dir, timeout=30):
    """等待 VibePet 进程退出"""
    exe_path = os.path.join(app_dir, "VibePet.exe")
    for i in range(timeout):
        # 检查进程是否还在运行
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'exe']):
                try:
                    if proc.info['exe'] and proc.info['exe'].lower() == exe_path.lower():
                        time.sleep(1)
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            else:
                return True
        except ImportError:
            # 没有 psutil，用 tasklist
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq VibePet.exe'],
                capture_output=True, text=True
            )
            if 'VibePet.exe' not in result.stdout:
                return True
            time.sleep(1)
    return False


def force_kill(app_dir):
    """强制结束 VibePet 进程"""
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'VibePet.exe'], 
                      capture_output=True, check=False)
        time.sleep(2)
    except Exception:
        pass


def update(app_dir, zip_path):
    """执行更新：解压 zip 覆盖原文件"""
    temp_dir = os.path.join(app_dir, '_update_temp')
    
    try:
        # 1. 清理临时目录
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)
        
        # 2. 解压 zip
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_dir)
        
        # 3. 找到解压后的主文件夹
        extracted_items = os.listdir(temp_dir)
        if len(extracted_items) == 1 and os.path.isdir(os.path.join(temp_dir, extracted_items[0])):
            source_dir = os.path.join(temp_dir, extracted_items[0])
        else:
            source_dir = temp_dir
        
        # 4. 备份旧文件（除了 VibePet.exe 和运行时数据）
        backup_dir = os.path.join(app_dir, '_backup')
        if os.path.exists(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)
        os.makedirs(backup_dir, exist_ok=True)
        
        for item in os.listdir(app_dir):
            if item in ('VibePet.exe', 'config.json', 'usage.db', 'vibe_pet.log', 
                       '_update_temp', '_backup', 'vibepet_update.ps1'):
                continue
            src = os.path.join(app_dir, item)
            dst = os.path.join(backup_dir, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        
        # 5. 复制新文件（覆盖，但保留用户数据）
        for item in os.listdir(source_dir):
            if item in ('config.json', 'usage.db', 'vibe_pet.log'):
                continue  # 保留用户数据
            
            src = os.path.join(source_dir, item)
            dst = os.path.join(app_dir, item)
            
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        
        # 6. 清理临时文件
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
        os.remove(zip_path)
        
        # 7. 启动新版本
        exe_path = os.path.join(app_dir, "VibePet.exe")
        subprocess.Popen([exe_path], cwd=app_dir)
        
        return True
        
    except Exception as e:
        print(f"Update failed: {e}")
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: VibePetUpdater.exe <app_dir> <zip_path>")
        sys.exit(1)
    
    app_dir = sys.argv[1]
    zip_path = sys.argv[2]
    
    # 等待 VibePet 退出
    if not wait_for_exit(app_dir):
        force_kill(app_dir)
    
    # 执行更新
    if update(app_dir, zip_path):
        print("Update successful!")
    else:
        print("Update failed!")
        input("Press Enter to exit...")


if __name__ == '__main__':
    main()
