#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibePet 构建清理脚本
删除 PyInstaller 打包残留、Python 缓存文件，确保每次打包都是干净的。

用法:
    python clean_build.py
"""

import os
import shutil
import glob


def clean():
    base = os.path.dirname(os.path.abspath(__file__))
    removed = []

    # 1. 删除 build/ 目录
    build_dir = os.path.join(base, "build")
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
            removed.append("build/")
        except Exception as e:
            print(f"警告：删除 build/ 目录失败，该目录可能正在被杀毒软件（如 360）扫描或被其他进程锁定。请关闭杀软或相关进程后重试。错误: {e}")

    # 2. 清理 dist/ 目录下的打包输出文件，但保留数据库、日志和配置文件等
    dist_dir = os.path.join(base, "dist")
    if os.path.exists(dist_dir):
        # 删除文件夹模式输出
        vp_folder = os.path.join(dist_dir, "VibePet")
        if os.path.exists(vp_folder):
            try:
                shutil.rmtree(vp_folder)
                removed.append("dist/VibePet/")
            except Exception as e:
                print(f"警告：删除 dist/VibePet/ 目录失败。错误: {e}")
                
        # 删除单文件 exe
        vp_exe = os.path.join(dist_dir, "VibePet.exe")
        if os.path.exists(vp_exe):
            try:
                os.remove(vp_exe)
                removed.append("dist/VibePet.exe")
            except Exception as e:
                print(f"警告：删除 dist/VibePet.exe 失败。错误: {e}")
                
        # 删除 zip 归档
        for zip_file in glob.glob(os.path.join(dist_dir, "*.zip")):
            try:
                os.remove(zip_file)
                removed.append(f"dist/{os.path.basename(zip_file)}")
            except Exception as e:
                print(f"警告：删除 zip 文件 {os.path.basename(zip_file)} 失败。错误: {e}")

    # 3. 删除 PyInstaller 生成的临时 .spec（保留项目自带的 spec 配置文件）
    for spec in glob.glob(os.path.join(base, "*.spec")):
        if os.path.basename(spec) not in ("VibePet.spec", "VibePet_onedir.spec"):
            try:
                os.remove(spec)
                removed.append(os.path.basename(spec))
            except Exception as e:
                print(f"警告：删除 spec 临时文件 {os.path.basename(spec)} 失败。错误: {e}")

    # 4. 删除 __pycache__ 和 .pyc
    for root, dirs, files in os.walk(base):
        for d in dirs:
            if d == "__pycache__":
                p = os.path.join(root, d)
                try:
                    shutil.rmtree(p)
                    removed.append(p.replace(base, "."))
                except Exception:
                    pass
        for f in files:
            if f.endswith(".pyc"):
                p = os.path.join(root, f)
                try:
                    os.remove(p)
                    removed.append(p.replace(base, "."))
                except Exception:
                    pass

    print("已清理以下旧构建文件：")
    for item in removed:
        print(f"  - {item}")
    if not removed:
        print("  （无旧文件需要清理）")
    print("清理完成，可以重新打包。")


if __name__ == "__main__":
    clean()
