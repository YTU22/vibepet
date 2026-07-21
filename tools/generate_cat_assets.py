#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibePet 「墨团小猫」皮肤程序化渲染器
=====================================
参考形象：深蓝灰色羊毛毡质感小猫 + 翠绿色大眼。
用 numpy + PIL 以 4 倍超采样渲染 6 种状态的 24 帧循环 GIF 与静态 PNG：
  - 噪声扰动边缘的绒毛剪影（双层：外层绒毛光晕 + 本体）
  - 翠绿色大眼（径向渐变 + 深色瞳孔 + 双高光）、猫耳、胡须、尾巴
  - 每状态独立表情/耳姿/尾巴动作/特效

用法:  python tools/generate_cat_assets.py
输出:  assets/skins/cat/{idle,work,happy,tired,sleep,angry}.gif + pet_*.png + icon.png
        assets/icon.png, assets/icon.ico （默认皮肤图标）
        tools/preview_cat.png （QA 预览图）
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 256
SS = 4
CV = SIZE * SS
N_FRAMES = 24
FRAME_MS = 70

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS = os.path.join(BASE_DIR, "assets", "skins", "cat")
ROOT_ASSETS = os.path.join(BASE_DIR, "assets")

# 毛色（深石板蓝灰）
FUR_TOP = (82, 96, 120)
FUR_MID = (58, 70, 92)
FUR_BOT = (36, 44, 62)
FUR_DARK = (28, 34, 48)
INNER_EAR = (96, 76, 88)
EYE_TEAL = (66, 205, 178)
EYE_DEEP = (22, 110, 96)
PUPIL = (13, 24, 22)
NOSE = (207, 143, 146)
DARK = (22, 28, 40)


def S(v):
    return v * SS


def layer():
    return Image.new("RGBA", (CV, CV), (0, 0, 0, 0))


# ---------------------------------------------------------------- 绒毛身体
def fur_silhouette(cx, cy, rx, ry, seed, fluff=1.0, squash=1.0, tilt=0.0):
    """ 噪声扰动边界的绒毛剪影遮罩，返回 numpy alpha (0-1) 与形状参数 """
    rx_s = rx / math.sqrt(squash)
    ry_s = ry * squash
    rng = np.random.default_rng(seed)
    n_harm = 7
    phases = rng.uniform(0, 2 * np.pi, n_harm)
    amps = np.array([0.045, 0.032, 0.026, 0.020, 0.016, 0.012, 0.010]) * fluff

    y, x = np.mgrid[0:CV, 0:CV].astype(np.float64)
    dx = (x - cx - tilt * (cy - y)) / rx_s
    dy = (y - cy) / ry_s
    dist = np.sqrt(dx ** 2 + dy ** 2)
    ang = np.arctan2(dy, dx)
    rmod = np.ones_like(ang)
    for i in range(n_harm):
        rmod += amps[i] * np.sin((i + 3) * ang + phases[i])
    d = dist / rmod
    alpha = np.clip((1.02 - d) / 0.05, 0.0, 1.0)
    return alpha, rx_s, ry_s


def fur_body(cx, cy, rx, ry, seed, squash=1.0, tilt=0.0, tint=None):
    """ 渲染绒毛身体（光晕层 + 本体渐变层 + 内部纹理），返回 Image, rx_s, ry_s """
    img = layer()

    # 外层绒毛光晕
    halo_a, _, _ = fur_silhouette(cx, cy, rx * 1.03, ry * 1.03, seed + 1,
                                  fluff=2.2, squash=squash, tilt=tilt)
    halo = np.zeros((CV, CV, 4), dtype=np.uint8)
    halo[..., 0], halo[..., 1], halo[..., 2] = FUR_MID
    halo[..., 3] = (halo_a * 90).astype(np.uint8)
    img.alpha_composite(Image.fromarray(halo, "RGBA").filter(ImageFilter.GaussianBlur(S(1.2))))

    # 本体
    alpha, rx_s, ry_s = fur_silhouette(cx, cy, rx, ry, seed, fluff=1.0,
                                       squash=squash, tilt=tilt)
    top_c, mid_c, bot_c = [np.array(c, dtype=np.float64) for c in (FUR_TOP, FUR_MID, FUR_BOT)]
    if tint is not None:
        tint_c = np.array(tint, dtype=np.float64)
        top_c = top_c * 0.75 + tint_c * 0.25
        mid_c = mid_c * 0.75 + tint_c * 0.25
        bot_c = bot_c * 0.75 + tint_c * 0.25

    y, x = np.mgrid[0:CV, 0:CV].astype(np.float64)
    t = np.clip((y - (cy - ry_s)) / (2 * ry_s), 0.0, 1.0)
    col = np.zeros((CV, CV, 3))
    upper = t <= 0.5
    tu = (t / 0.5)[..., None]
    tl = ((t - 0.5) / 0.5)[..., None]
    col[upper] = top_c * (1 - tu[upper]) + mid_c * tu[upper]
    col[~upper] = mid_c * (1 - tl[~upper]) + bot_c * tl[~upper]

    # 顶部受光
    lx, ly = cx - rx_s * 0.25, cy - ry_s * 0.55
    lr = np.sqrt((x - lx) ** 2 + (y - ly) ** 2) / (rx_s * 1.1)
    col += (np.clip(1.0 - lr, 0.0, 1.0) ** 2 * 22.0)[..., None]

    # 绒毛噪点纹理
    rng = np.random.default_rng(seed + 2)
    noise = rng.normal(0, 6.0, (CV, CV, 1))
    col += noise

    col = np.clip(col, 0, 255).astype(np.uint8)
    rgba = np.dstack([col, (alpha * 255).astype(np.uint8)])
    img.alpha_composite(Image.fromarray(rgba, "RGBA"))
    return img, rx_s, ry_s


def fur_blob(dr, cx, cy, r, seed, color, alpha=255, fluff=0.18, n=28):
    """ 小绒毛球（尾巴节、爪子），PIL 抖动多边形 """
    rng = np.random.default_rng(seed)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = r * (1 + fluff * (rng.uniform(-1, 1)))
        pts.append((S(cx + rr * math.cos(a)), S(cy + rr * math.sin(a))))
    dr.polygon(pts, fill=color + (alpha,))


# ---------------------------------------------------------------- 五官部件
def draw_ear(dr, cx, cy, w, h, rot_deg, seed, droop=0.0):
    """ 绒毛三角耳：外耳 + 内耳。rot_deg>0 向右倒，droop 加大下垂 """
    rng = np.random.default_rng(seed)
    rad = math.radians(rot_deg)
    ca, sa = math.cos(rad), math.sin(rad)

    def rot(px, py):
        return (cx + (px - cx) * ca - (py - cy) * sa,
                cy + (px - cx) * sa + (py - cy) * ca)

    base_l = (cx - w / 2, cy + droop)
    base_r = (cx + w / 2, cy + droop)
    tip = (cx, cy - h + droop)
    # 抖动边缘
    pts = []
    for (x0, y0), (x1, y1) in [(base_l, tip), (tip, base_r), (base_r, base_l)]:
        for i in range(8):
            t = i / 8
            jx = rng.uniform(-2.2, 2.2)
            jy = rng.uniform(-2.2, 2.2)
            pts.append(rot(x0 + (x1 - x0) * t + jx, y0 + (y1 - y0) * t + jy))
    dr.polygon([(S(px), S(py)) for px, py in pts], fill=FUR_MID + (255,))

    # 内耳（平滑小三角）
    shrink = 0.45
    il = (cx - w / 2 * shrink, cy + droop - h * 0.08)
    ir = (cx + w / 2 * shrink, cy + droop - h * 0.08)
    it = (cx, cy - h * (1 - shrink) - h * 0.08 + droop)
    dr.polygon([(S(rot(*p)[0]), S(rot(*p)[1])) for p in (il, it, ir)],
               fill=INNER_EAR + (220,))


def draw_eye(dr, x, y, w, h, h_scale=1.0):
    """ 翠绿大眼：底色 + 下部深色渐变弧 + 瞳孔 + 双高光 """
    hh = h * h_scale
    draw_ellipse(dr, x, y, w, hh, EYE_DEEP)
    draw_ellipse(dr, x, y - hh * 0.10, w * 0.86, hh * 0.80, EYE_TEAL)
    if h_scale > 0.35:
        draw_ellipse(dr, x, y + hh * 0.02, w * 0.34, hh * 0.52, PUPIL)
        draw_ellipse(dr, x - w * 0.16, y - hh * 0.20, w * 0.20, w * 0.20, (255, 255, 255))
        draw_ellipse(dr, x + w * 0.14, y + hh * 0.16, w * 0.10, w * 0.10, (255, 255, 255, 190))


def draw_ellipse(dr, cx, cy, w, h, fill, outline=None, width=1):
    dr.ellipse([S(cx - w / 2), S(cy - h / 2), S(cx + w / 2), S(cy + h / 2)],
               fill=fill, outline=outline, width=max(1, int(round(S(width)))))


def draw_arc(dr, cx, cy, w, h, a0, a1, fill, width):
    dr.arc([S(cx - w / 2), S(cy - h / 2), S(cx + w / 2), S(cy + h / 2)],
           a0, a1, fill=fill, width=max(1, int(round(S(width)))))


def draw_line(dr, pts, fill, width):
    dr.line([(S(px), S(py)) for px, py in pts], fill=fill,
            width=max(1, int(round(S(width)))), joint="curve")
    r = width / 2.0
    for px, py in (pts[0], pts[-1]):
        draw_ellipse(dr, px, py, r * 2, r * 2, fill)


def eye_happy(dr, x, y, scale=1.0):
    draw_arc(dr, x, y + 3 * scale, 20 * scale, 17 * scale, 180, 360, DARK, 5 * scale)


def eye_closed(dr, x, y, scale=1.0):
    draw_arc(dr, x, y - 2 * scale, 19 * scale, 15 * scale, 0, 180, DARK, 4.5 * scale)


def eye_half(dr, x, y, scale=1.0):
    draw_ellipse(dr, x, y + 3 * scale, 20 * scale, 13 * scale, EYE_DEEP)
    draw_ellipse(dr, x, y + 3.5 * scale, 12 * scale, 8 * scale, PUPIL)
    draw_arc(dr, x, y - 1 * scale, 23 * scale, 17 * scale, 170, 370, FUR_DARK, 6 * scale)


def eye_angry(dr, x, y, mirror=False, scale=1.0):
    s = scale
    if not mirror:
        pts = [(x - 8 * s, y - 8 * s), (x + 5 * s, y), (x - 8 * s, y + 8 * s)]
    else:
        pts = [(x + 8 * s, y - 8 * s), (x - 5 * s, y), (x + 8 * s, y + 8 * s)]
    draw_line(dr, pts, DARK, 5 * s)


def draw_nose_mouth(dr, x, y, style="smile"):
    # 小鼻子
    dr.polygon([(S(x - 4), S(y - 2)), (S(x + 4), S(y - 2)), (S(x), S(y + 3))],
               fill=NOSE + (255,))
    if style == "smile":      # ω 嘴
        draw_arc(dr, x - 4.5, y + 3, 9, 8, 15, 165, DARK, 2.6)
        draw_arc(dr, x + 4.5, y + 3, 9, 8, 15, 165, DARK, 2.6)
    elif style == "big":      # 开心张嘴
        draw_ellipse(dr, x, y + 7, 13, 11, (90, 40, 48))
        draw_ellipse(dr, x, y + 9.5, 7, 5, (255, 143, 155))
    elif style == "flat":
        draw_line(dr, [(x - 5, y + 5), (x + 5, y + 5)], DARK, 2.6)
    elif style == "frown":
        draw_arc(dr, x, y + 8, 13, 10, 205, 335, DARK, 3)
    elif style == "o":
        draw_ellipse(dr, x, y + 6, 7, 8, (90, 40, 48))
    elif style == "zigzag":
        pts = [(x - 8, y + 3), (x - 4, y + 8), (x, y + 3), (x + 4, y + 8), (x + 8, y + 3)]
        draw_line(dr, pts, DARK, 3)


def draw_whiskers(dr, x, y, side):
    """ 一侧胡须（3 根微弯细线） """
    for i, (dy, ln) in enumerate([(-6, 26), (0, 30), (6, 26)]):
        x0 = x + side * 4
        pts = [(x0, y + dy),
               (x0 + side * ln * 0.55, y + dy - 2 + i * 2),
               (x0 + side * ln, y + dy - 3 + i * 3)]
        dr.line([(S(px), S(py)) for px, py in pts],
                fill=(210, 220, 235, 110), width=max(1, S(1)))


def draw_tail(dr, base_x, base_y, wag, seed, lift=0.0):
    """ 尾巴：沿贝塞尔曲线的一串绒毛球，wag 控制摆动，lift 控制翘起 """
    p0 = (base_x, base_y)
    p1 = (base_x - 58, base_y + 6)
    p2 = (base_x - 46 - 14 * wag, base_y - 46 - lift)
    n = 9
    for i in range(n):
        t = i / (n - 1)
        bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0]
        by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]
        r = 15 - 7 * t
        fur_blob(dr, bx, by, r, seed + i, FUR_MID if i < n - 2 else FUR_TOP)


def draw_shadow(dr, cx, base_y, w, alpha):
    sh = layer()
    d = ImageDraw.Draw(sh)
    d.ellipse([S(cx - w / 2), S(base_y - 5), S(cx + w / 2), S(base_y + 5)],
              fill=(10, 14, 26, alpha))
    return sh.filter(ImageFilter.GaussianBlur(S(2.5)))


# ---------------------------------------------------------------- 特效（与史莱姆渲染器同款）
def heart_pts(x, y, s):
    pts = []
    for i in range(40):
        t = math.pi * 2 * i / 40
        hx = 16 * math.sin(t) ** 3
        hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x + hx * s / 16.0, y - hy * s / 16.0))
    return pts


def draw_heart(dr, x, y, s, alpha):
    dr.polygon([(S(px), S(py)) for px, py in heart_pts(x, y, s)], fill=(255, 107, 157, alpha))


def draw_sparkle(dr, x, y, s, alpha, color=(255, 244, 180)):
    k = 0.28
    pts = [(x, y - s), (x + s * k, y - s * k), (x + s, y), (x + s * k, y + s * k),
           (x, y + s), (x - s * k, y + s * k), (x - s, y), (x - s * k, y - s * k)]
    dr.polygon([(S(px), S(py)) for px, py in pts], fill=color + (alpha,))


def draw_sweat(dr, x, y, r, alpha):
    col = (190, 230, 255, alpha)
    dr.polygon([(S(x - r * 0.85), S(y)), (S(x + r * 0.85), S(y)), (S(x), S(y - r * 1.9))], fill=col)
    draw_ellipse(dr, x, y, r * 2, r * 2, col)
    draw_ellipse(dr, x - r * 0.25, y - r * 0.3, r * 0.5, r * 0.5, (255, 255, 255, int(alpha * 0.8)))


def draw_z(dr, x, y, s, alpha, rot_deg=0):
    col = (235, 244, 255, alpha)
    w2, h2 = s * 0.42, s * 0.5
    pts = [(x - w2, y - h2), (x + w2, y - h2), (x - w2, y + h2), (x + w2, y + h2)]
    if rot_deg:
        rad = math.radians(rot_deg)
        ca, sa = math.cos(rad), math.sin(rad)
        pts = [(x + (px - x) * ca - (py - y) * sa, y + (px - x) * sa + (py - y) * ca)
               for px, py in pts]
    draw_line(dr, pts, col, max(2.5, s * 0.16))


def draw_anger_mark(dr, x, y, s, alpha):
    col = (255, 82, 82, alpha)
    out = (180, 30, 30, alpha)
    for ang in (45, 135, 225, 315):
        rad = math.radians(ang)
        ca, sa = math.cos(rad), math.sin(rad)
        p0 = (x + ca * s * 0.25, y + sa * s * 0.25)
        p1 = (x + ca * s * 0.95, y + sa * s * 0.95)
        draw_line(dr, [p0, p1], out, s * 0.34)
        draw_line(dr, [p0, p1], col, s * 0.22)


def draw_steam(dr, x, y, r, alpha):
    draw_ellipse(dr, x, y, r * 2, r * 1.7, (245, 248, 255, alpha))


# ---------------------------------------------------------------- 帧渲染
BODY_RX, BODY_RY = 84, 64
BASE_Y = 224
CX = 132                      # 身体略偏右，给左侧尾巴留空间
EYE_W, EYE_H = 25, 29


def render_frame(state, f):
    t = f / N_FRAMES
    img = layer()

    cx, base_y = CX, BASE_Y
    squash, tilt = 1.0, 0.0
    eye_style, mouth_style = "open", "smile"
    eye_hs = 1.0
    ear_rot_l, ear_rot_r = -12, 12        # 耳朵外张角
    ear_droop = 0.0
    tail_wag = math.sin(2 * math.pi * t)
    tail_lift = 0.0
    tint = None

    if state == "idle":
        squash = 1.0 + 0.03 * math.sin(2 * math.pi * t)
        bt = min(abs(f - 8), abs(f - 8 + N_FRAMES), abs(f - 8 - N_FRAMES))
        if bt <= 1:
            eye_hs = {0: 0.10, 1: 0.35}[bt]

    elif state == "work":
        base_y = BASE_Y - 3 * abs(math.sin(4 * math.pi * t))
        squash = 1.0 + 0.015 * math.sin(4 * math.pi * t)
        eye_style, mouth_style = "open", "flat"
        eye_hs = 0.78                       # 专注微眯

    elif state == "happy":
        jump = abs(math.sin(3 * math.pi * t))
        base_y = BASE_Y - 24 * jump
        squash = 0.92 + 0.12 * jump
        eye_style, mouth_style = "happy", "big"
        tail_lift = 22.0

    elif state == "tired":
        cx = CX + 3 * math.sin(2 * math.pi * t)
        squash = 0.95 + 0.015 * math.sin(2 * math.pi * t)
        eye_style, mouth_style = "half", "frown"
        ear_droop = 9.0
        ear_rot_l, ear_rot_r = -24, 24

    elif state == "sleep":
        squash = 0.82 + 0.04 * math.sin(2 * math.pi * t)
        eye_style, mouth_style = "closed", "o"
        ear_droop = 5.0

    elif state == "angry":
        cx = CX + 2.2 * math.sin(16 * math.pi * t)
        squash = 1.02 + 0.025 * math.sin(8 * math.pi * t)
        eye_style, mouth_style = "angry", "zigzag"
        ear_rot_l, ear_rot_r = -68, 68      # 飞机耳
        tint = (120, 60, 66)

    seed = hash(state) % 1000 + 7

    # ---- 阴影 ----
    sh_w = BODY_RX * 2 * (0.80 if state != "sleep" else 0.88)
    if state == "happy":
        sh_w *= 1.0 - 0.22 * abs(math.sin(3 * math.pi * t))
    img.alpha_composite(draw_shadow(None, cx - 6, BASE_Y + 4, sh_w, 70))

    # ---- 尾巴（身体后面）----
    tail = layer()
    td = ImageDraw.Draw(tail)
    draw_tail(td, cx - BODY_RX * 0.70, base_y - 8, tail_wag, seed + 50, lift=tail_lift)
    tail = tail.filter(ImageFilter.GaussianBlur(S(0.6)))
    img.alpha_composite(tail)

    # ---- 身体 ----
    cy_canvas = S(base_y) - S(BODY_RY) * squash   # 身体中心（底部贴 base_y）
    body, rx_s, ry_s = fur_body(S(cx), cy_canvas, S(BODY_RX), S(BODY_RY), seed,
                                squash=squash, tilt=tilt, tint=tint)
    img.alpha_composite(body)

    # ---- 耳朵（头顶两侧，画布坐标换算回最终像素绘制）----
    cy_f = base_y - BODY_RY * squash
    top_y = cy_f - BODY_RY * squash * 0.72
    ears = layer()
    ed = ImageDraw.Draw(ears)
    ear_y = top_y + 14
    draw_ear(ed, cx - 44, ear_y, 34, 38, ear_rot_l, seed + 11, droop=ear_droop)
    draw_ear(ed, cx + 44, ear_y, 34, 38, ear_rot_r, seed + 23, droop=ear_droop)
    img.alpha_composite(ears)

    # ---- 五官 ----
    face = layer()
    fd = ImageDraw.Draw(face)
    ex, ey = 30, cy_f - 6
    ny = cy_f + 16                          # 鼻子 y

    if eye_style == "open":
        draw_eye(fd, cx - ex, ey, EYE_W, EYE_H, h_scale=eye_hs)
        draw_eye(fd, cx + ex, ey, EYE_W, EYE_H, h_scale=eye_hs)
    elif eye_style == "happy":
        eye_happy(fd, cx - ex, ey)
        eye_happy(fd, cx + ex, ey)
    elif eye_style == "closed":
        eye_closed(fd, cx - ex, ey)
        eye_closed(fd, cx + ex, ey)
    elif eye_style == "half":
        eye_half(fd, cx - ex, ey)
        eye_half(fd, cx + ex, ey)
    elif eye_style == "angry":
        eye_angry(fd, cx - ex, ey, mirror=False)
        eye_angry(fd, cx + ex, ey, mirror=True)

    draw_nose_mouth(fd, cx, ny, style=mouth_style)
    if eye_style in ("open", "half", "angry"):
        draw_whiskers(fd, cx - 34, ny - 2, side=-1)
        draw_whiskers(fd, cx + 34, ny - 2, side=1)
    img.alpha_composite(face)

    # ---- 特效 ----
    fx = layer()
    xd = ImageDraw.Draw(fx)
    if state == "happy":
        for k, (hx, phase) in enumerate([(CX - 62, 0.0), (CX + 64, 0.5)]):
            lt = (t + phase) % 1.0
            hy = BASE_Y - 108 - lt * 44
            hxo = hx + 6 * math.sin(2 * math.pi * lt * 2 + k)
            alpha = int(255 * max(0.0, 1.0 - lt) ** 0.8)
            if alpha > 8:
                draw_heart(xd, hxo, hy, 10 + 3 * lt, alpha)
    elif state == "sleep":
        for k in range(3):
            lt = (t + k / 3.0) % 1.0
            zx = CX + 56 + lt * 42
            zy = BASE_Y - 122 - lt * 58
            alpha = int(235 * (1.0 - abs(lt - 0.5) * 2) ** 0.7)
            if alpha > 8:
                draw_z(xd, zx, zy, 14 + 15 * lt, alpha, rot_deg=8)
    elif state == "work":
        for k in range(4):
            ang = 2 * math.pi * (k / 4.0) + 0.6
            sx = CX + 98 * math.cos(ang)
            sy = BASE_Y - 72 + 62 * math.sin(ang)
            tw = (math.sin(2 * math.pi * (t * 2 + k / 4.0)) + 1) / 2
            draw_sparkle(xd, sx, sy, 5 + 4 * tw, int(60 + 190 * tw))
    elif state == "tired":
        for k, (side, phase) in enumerate([(1, 0.0), (-1, 0.55)]):
            lt = (t + phase) % 1.0
            sxp = CX + side * (BODY_RX * 0.74)
            syp = BASE_Y - 92 + lt * 52
            alpha = int(230 * (1.0 - lt ** 2))
            if alpha > 8:
                draw_sweat(xd, sxp, syp, 5.5 - 1.5 * lt, alpha)
    elif state == "angry":
        pulse = 1.0 + 0.18 * math.sin(2 * math.pi * t * 2)
        draw_anger_mark(xd, CX + 64, BASE_Y - 138, 15 * pulse, 245)
        for k in range(2):
            lt = (t * 1.5 + k / 2.0) % 1.0
            sx = CX - 32 + k * 26 + 5 * math.sin(2 * math.pi * lt * 3)
            sy = BASE_Y - 118 - lt * 38
            alpha = int(160 * (1.0 - lt))
            if alpha > 8:
                draw_steam(xd, sx, sy, 7 + 7 * lt, alpha)
    img.alpha_composite(fx)

    # ---- 本体 bbox（身体+耳朵+五官，不含尾巴/特效/阴影）----
    core = layer()
    core.alpha_composite(body)
    core.alpha_composite(ears)
    core.alpha_composite(face)
    return img, core.getbbox()


def finalize(img):
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def quantize_frames(frames):
    strip = Image.new("RGB", (SIZE, SIZE * len(frames)))
    for i, fr in enumerate(frames):
        rgb = Image.new("RGB", (SIZE, SIZE))
        rgb.paste(fr, mask=fr.getchannel("A"))
        strip.paste(rgb, (0, i * SIZE))
    pal = strip.quantize(colors=255, method=Image.MEDIANCUT, dither=Image.Dither.NONE)
    qframes = []
    for fr in frames:
        alpha = fr.getchannel("A")
        rgb = Image.new("RGB", (SIZE, SIZE))
        rgb.paste(fr, mask=alpha)
        q = rgb.quantize(colors=255, palette=pal, dither=Image.Dither.FLOYDSTEINBERG)
        mask = alpha.point(lambda a: 255 if a < 128 else 0)
        q.paste(255, mask=mask)
        q.info["transparency"] = 255
        qframes.append(q)
    return qframes


def main():
    os.makedirs(ASSETS, exist_ok=True)
    states = ["idle", "work", "happy", "tired", "sleep", "angry"]
    static_frame = {"idle": 0, "work": 0, "happy": 4, "tired": 0, "sleep": 0, "angry": 0}
    paddings = {}
    preview_cells = []

    for state in states:
        frames, bboxes = [], []
        for f in range(N_FRAMES):
            img, bbox = render_frame(state, f)
            frames.append(finalize(img))
            bboxes.append(bbox)

        qframes = quantize_frames(frames)
        gif_path = os.path.join(ASSETS, f"{state}.gif")
        qframes[0].save(gif_path, save_all=True, append_images=qframes[1:],
                        duration=FRAME_MS, loop=0, disposal=2, optimize=False)
        frames[static_frame[state]].save(os.path.join(ASSETS, f"pet_{state}.png"))

        valid = [b for b in bboxes if b]
        paddings[state] = (
            round(min(b[0] for b in valid) / CV, 3),
            round(min(b[1] for b in valid) / CV, 3),
            round(max(b[2] for b in valid) / CV, 3),
            round(max(b[3] for b in valid) / CV, 3),
        )
        for f in range(0, N_FRAMES, 4):
            preview_cells.append((state, frames[f]))
        print(f"[{state}] {gif_path}  {os.path.getsize(gif_path)/1024:.0f} KB  bbox={paddings[state]}")

    # ---- 皮肤图标 + 根目录默认图标 ----
    idle_img, bbox = render_frame("idle", 0)
    l, tp, r, bt = bbox
    m = int((r - l) * 0.08)
    crop = idle_img.crop((max(0, l - m), max(0, tp - m), min(CV, r + m), min(CV, bt + m)))
    icon = crop.resize((256, 256), Image.LANCZOS)
    icon.save(os.path.join(ASSETS, "icon.png"))
    icon.save(os.path.join(ROOT_ASSETS, "icon.png"))
    icon.save(os.path.join(ROOT_ASSETS, "icon.ico"),
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("[icon] skins/cat/icon.png + assets/icon.png / icon.ico 已生成")

    # ---- QA 预览图 ----
    sheet = Image.new("RGBA", (SIZE * 6, SIZE * 6), (40, 44, 60, 255))
    for i, (state, cell) in enumerate(preview_cells):
        row = states.index(state)
        sheet.alpha_composite(cell, ((i % 6) * SIZE, row * SIZE))
    sheet_path = os.path.join(BASE_DIR, "tools", "preview_cat.png")
    sheet.convert("RGB").save(sheet_path)
    print(f"[preview] {sheet_path}")

    print("\ncat_paddings = {")
    for s in states:
        v = paddings[s]
        print(f'    "{s}": ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f}, {v[3]:.3f}),')
    print("}")


if __name__ == "__main__":
    main()
