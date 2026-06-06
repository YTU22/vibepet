#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibePet Automated Build & Data Protection Script
Automatically backs up user configuration/database before compilation,
runs PyInstaller directory mode build, restores user configurations,
and packages the final release zip file.
"""

import os
import shutil
import subprocess
import zipfile

def run_build():
    base = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(base, "dist")
    vp_dir = os.path.join(dist_dir, "VibePet")
    backup_dir = os.path.join(base, "build", "user_backup")
    
    # 1. Back up user config and database from dist/VibePet/ if they exist
    os.makedirs(backup_dir, exist_ok=True)
    backed_up = []
    user_files = ["config.json", "usage.db", "vibe_pet.log", "vibe_pet.lock"]
    
    for f in user_files:
        src = os.path.join(vp_dir, f)
        if os.path.exists(src):
            try:
                shutil.copy2(src, os.path.join(backup_dir, f))
                backed_up.append(f)
            except Exception as e:
                print(f"警告: 备份 {f} 失败: {e}")
                
    if backed_up:
        print(f"[数据保护] 已成功备份用户数据文件: {', '.join(backed_up)}")
    else:
        print("[数据保护] 没有检测到已有的用户数据文件，将使用项目根目录下的备份。")

    # 2. Run clean_build.py
    clean_script = os.path.join(base, "clean_build.py")
    if os.path.exists(clean_script):
        print("[1/4] 清理旧构建目录...")
        subprocess.run(["python", clean_script], check=True)

    # 3. Run PyInstaller
    spec_file = os.path.join(base, "VibePet_onedir.spec")
    print(f"[2/4] 运行 PyInstaller 打包 (onedir 模式)...")
    subprocess.run(["pyinstaller", "--clean", "--noconfirm", spec_file], check=True)

    # 4. Restore user configs and database
    restored = []
    for f in user_files:
        dst = os.path.join(vp_dir, f)
        # Try restoring from backup first
        src_backup = os.path.join(backup_dir, f)
        src_root = os.path.join(base, f)
        
        if os.path.exists(src_backup):
            try:
                shutil.copy2(src_backup, dst)
                restored.append(f"{f} (从临时备份恢复)")
            except Exception as e:
                print(f"错误: 还原备份 {f} 失败: {e}")
        elif os.path.exists(src_root):
            try:
                shutil.copy2(src_root, dst)
                restored.append(f"{f} (从根目录备份恢复)")
            except Exception as e:
                print(f"错误: 还原根目录 {f} 失败: {e}")
                
    if restored:
        print(f"[数据保护] 已成功还原用户配置/数据文件: {', '.join(restored)}")

    # 5. Clean backup folder
    try:
        shutil.rmtree(backup_dir)
    except Exception:
        pass

    # 6. Create Release Zip
    print("[3/4] 正在打包归档 Release Zip 文件...")
    zip_path = os.path.join(dist_dir, "VibePet-v1.2.8.zip")
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass
            
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(vp_dir):
                for file in files:
                    # Skip user config and private database files in release zip
                    if file in user_files:
                        continue
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, dist_dir)
                    zf.write(file_path, rel_path)
        print(f"[4/4] 打包发布程序归档成功! 归档路径: {zip_path}")
    except Exception as e:
        print(f"错误: 创建归档 zip 失败: {e}")

if __name__ == "__main__":
    run_build()
