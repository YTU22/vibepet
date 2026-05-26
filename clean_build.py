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
        shutil.rmtree(build_dir)
        removed.append("build/")

    # 2. 删除 dist/ 目录
    dist_dir = os.path.join(base, "dist")
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
        removed.append("dist/")

    # 3. 删除所有 .spec 文件
    for spec in glob.glob(os.path.join(base, "*.spec")):
        os.remove(spec)
        removed.append(os.path.basename(spec))

    # 4. 删除 __pycache__ 和 .pyc
    for root, dirs, files in os.walk(base):
        for d in dirs:
            if d == "__pycache__":
                p = os.path.join(root, d)
                shutil.rmtree(p)
                removed.append(p.replace(base, "."))
        for f in files:
            if f.endswith(".pyc"):
                p = os.path.join(root, f)
                os.remove(p)
                removed.append(p.replace(base, "."))

    print("已清理以下旧构建文件：")
    for item in removed:
        print(f"  - {item}")
    if not removed:
        print("  （无旧文件需要清理）")
    print("清理完成，可以重新打包。")


if __name__ == "__main__":
    clean()
