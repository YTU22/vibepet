#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VibePet 果冻史莱姆资产程序化渲染器
====================================
用 numpy + PIL 以 4 倍超采样渲染 6 种状态的高品质 GIF 动画与静态 PNG：
  - 渐变半透明果冻身体（superellipse 软边遮罩 + 垂直渐变 + 径向高光）
  - 每状态独立表情、配色与 24 帧循环动效
  - 同时输出 pet_*.png 静态图、icon.png / icon.ico，以及各状态本体 bbox 比例
    （用于 ui/pet_window.py 中 gif_paddings / png_paddings 的布局锚定）

用法:  python tools/generate_pet_assets.py
输出:  assets/{idle,work,happy,tired,sleep,angry}.gif
        assets/pet_*.png, assets/icon.png, assets/icon.ico
        tools/preview_sheet.png （QA 预览图）
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ---------------------------------------------------------------- 基础参数
SIZE = 256                 # 最终输出边长
SS = 4                     # 超采样倍数
CV = SIZE * SS             # 工作画布边长
N_FRAMES = 24              # 每状态帧数
FRAME_MS = 70              # 每帧时长 (ms)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ASSETS = os.path.join(BASE_DIR, "assets", "skins", "slime")

# 调色板: (顶部高光色, 中间色, 底部深色)
PALETTES = {
    "idle":  ((174, 227, 255), (95, 184, 255), (47, 127, 224)),
    "work":  ((165, 221, 255), (87, 176, 245), (43, 116, 212)),
    "happy": ((192, 236, 255), (110, 198, 255), (52, 144, 234)),
    "tired": ((185, 210, 232), (127, 168, 204), (74, 111, 150)),
    "sleep": ((159, 192, 240), (106, 147, 216), (58, 90, 168)),
    "angry": ((255, 192, 184), (255, 138, 122), (224, 72, 62)),
}

DARK = (28, 43, 74)        # 眼睛/嘴巴深色
BLUSH = (255, 140, 150)    # 腮红


# ---------------------------------------------------------------- 身体渲染
def render_body(cx, base_y, rx, ry, squash, colors, flat=0.80, tilt_x=0.0):
    """ 渲染果冻身体层，返回 RGBA Image (CV x CV)。
    cx, base_y: 身体中心 x 与底部 y（工作画布坐标）
    rx, ry: 基准半径；squash>1 变高变窄，<1 变扁变宽（体积近似守恒）
    flat: 底部压扁系数；tilt_x: 顶部随高度轻微水平偏移（果冻倾斜感）
    """
    top_c, mid_c, bot_c = [np.array(c, dtype=np.float64) for c in colors]
    rx_s = rx / math.sqrt(squash)
    ry_s = ry * squash
    cy = base_y - ry_s

    y, x = np.mgrid[0:CV, 0:CV].astype(np.float64)
    nx = (x - cx - tilt_x * (cy - y)) / rx_s
    ny = (y - cy) / ry_s
    ny = np.where(ny > 0, ny * flat, ny)          # 底部压平

    p = 2.6                                        # superellipse 指数
    d = np.abs(nx) ** p + np.abs(ny) ** p

    # 软边 alpha
    alpha = np.clip((1.015 - d) / 0.06, 0.0, 1.0)

    # 垂直渐变
    t = np.clip((y - (cy - ry_s)) / (2 * ry_s), 0.0, 1.0)
    col = np.zeros((CV, CV, 3))
    upper = t <= 0.5
    tu = (t / 0.5)[..., None]
    tl = ((t - 0.5) / 0.5)[..., None]
    col[upper] = top_c * (1 - tu[upper]) + mid_c * tu[upper]
    col[~upper] = mid_c * (1 - tl[~upper]) + bot_c * tl[~upper]

    # 径向高光（光源在左上方）
    lx, ly = cx - rx_s * 0.38, cy - ry_s * 0.48
    lr = np.sqrt((x - lx) ** 2 + (y - ly) ** 2) / (rx_s * 1.05)
    glow = np.clip(1.0 - lr, 0.0, 1.0) ** 2 * 0.38
    col += glow[..., None] * 255.0 * np.array([1.0, 1.0, 1.0])

    # 底部内阴影，增加体积感
    shade = np.clip((t - 0.62) / 0.38, 0.0, 1.0) * 0.20
    col *= (1.0 - shade[..., None])

    col = np.clip(col, 0, 255).astype(np.uint8)
    a = (alpha * 255).astype(np.uint8)
    rgba = np.dstack([col, a])
    return Image.fromarray(rgba, "RGBA"), cy, rx_s, ry_s


# ---------------------------------------------------------------- 绘制助手
def S(v):
    """ 最终像素坐标 -> 工作画布坐标 """
    return v * SS


def layer():
    return Image.new("RGBA", (CV, CV), (0, 0, 0, 0))


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
    for px, py in (pts[0], pts[-1]):                     # 圆头
        draw_ellipse(dr, px, py, r * 2, r * 2, fill)


def draw_poly(dr, pts, fill):
    dr.polygon([(S(px), S(py)) for px, py in pts], fill=fill)


# ---------------------------------------------------------------- 五官
def eye_open(dr, x, y, scale=1.0, h_scale=1.0):
    w, h = 15 * scale, 19 * scale * h_scale
    draw_ellipse(dr, x, y, w, h, DARK)
    if h_scale > 0.4:
        draw_ellipse(dr, x - w * 0.20, y - h * 0.22, 5 * scale, 5 * scale, (255, 255, 255))
        draw_ellipse(dr, x + w * 0.18, y + h * 0.24, 2.4 * scale, 2.4 * scale, (255, 255, 255, 190))


def eye_happy(dr, x, y, scale=1.0):
    draw_arc(dr, x, y + 3 * scale, 17 * scale, 15 * scale, 180, 360, DARK, 4.5 * scale)


def eye_closed(dr, x, y, scale=1.0):
    draw_arc(dr, x, y - 3 * scale, 16 * scale, 13 * scale, 0, 180, DARK, 4 * scale)


def eye_half(dr, x, y, scale=1.0):
    # 厚重的下垂眼皮 + 只露出下半截的眼睛，一眼可读"疲惫"
    draw_ellipse(dr, x, y + 3.5 * scale, 14 * scale, 9 * scale, DARK)
    draw_ellipse(dr, x - 2 * scale, y + 5 * scale, 3 * scale, 3 * scale, (255, 255, 255, 200))
    draw_arc(dr, x, y - 0.5 * scale, 18 * scale, 14 * scale, 175, 365, DARK, 5 * scale)


def eye_angry(dr, x, y, mirror=False, scale=1.0):
    s = scale
    if not mirror:   # 左眼 ">"
        pts = [(x - 6 * s, y - 7 * s), (x + 4 * s, y), (x - 6 * s, y + 7 * s)]
    else:            # 右眼 "<"
        pts = [(x + 6 * s, y - 7 * s), (x - 4 * s, y), (x + 6 * s, y + 7 * s)]
    draw_line(dr, pts, DARK, 4.2 * s)


def mouth_smile(dr, x, y, scale=1.0):
    draw_arc(dr, x, y - 3 * scale, 15 * scale, 12 * scale, 25, 155, DARK, 3.2 * scale)


def mouth_big(dr, x, y, scale=1.0):
    w, h = 18 * scale, 14 * scale
    dr.pieslice([S(x - w / 2), S(y - h * 0.55), S(x + w / 2), S(y + h * 0.9)],
                0, 180, fill=(122, 46, 58))
    draw_ellipse(dr, x, y + h * 0.30, w * 0.55, h * 0.35, (255, 143, 155))


def mouth_flat(dr, x, y, scale=1.0):
    draw_line(dr, [(x - 6 * scale, y), (x + 6 * scale, y)], DARK, 3 * scale)


def mouth_frown(dr, x, y, scale=1.0):
    draw_arc(dr, x, y, 16 * scale, 13 * scale, 205, 335, DARK, 3.8 * scale)


def mouth_o(dr, x, y, scale=1.0):
    draw_ellipse(dr, x, y, 7 * scale, 8.5 * scale, (122, 46, 58))


def mouth_zigzag(dr, x, y, scale=1.0):
    s = scale
    pts = [(x - 8 * s, y - 2 * s), (x - 4 * s, y + 3 * s), (x, y - 2 * s),
           (x + 4 * s, y + 3 * s), (x + 8 * s, y - 2 * s)]
    draw_line(dr, pts, DARK, 3 * s)


def blush(dr_layer, x, y, scale=1.0):
    bl = Image.new("RGBA", (CV, CV), (0, 0, 0, 0))
    d = ImageDraw.Draw(bl)
    for sx in (-1, 1):
        d.ellipse([S(x + sx * 30 * scale - 9 * scale), S(y - 4.5 * scale),
                   S(x + sx * 30 * scale + 9 * scale), S(y + 4.5 * scale)],
                  fill=BLUSH + (110,))
    bl = bl.filter(ImageFilter.GaussianBlur(S(2.2)))
    dr_layer.alpha_composite(bl)


# ---------------------------------------------------------------- 特效
def heart_pts(x, y, s):
    pts = []
    for i in range(40):
        t = math.pi * 2 * i / 40
        hx = 16 * math.sin(t) ** 3
        hy = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((x + hx * s / 16.0, y - hy * s / 16.0))
    return pts


def draw_heart(dr, x, y, s, alpha):
    draw_poly(dr, heart_pts(x, y, s), (255, 107, 157, alpha))


def draw_sparkle(dr, x, y, s, alpha, color=(255, 244, 180)):
    k = 0.28
    pts = [(x, y - s), (x + s * k, y - s * k), (x + s, y), (x + s * k, y + s * k),
           (x, y + s), (x - s * k, y + s * k), (x - s, y), (x - s * k, y - s * k)]
    draw_poly(dr, pts, color + (alpha,))


def draw_sweat(dr, x, y, r, alpha):
    col = (190, 230, 255, alpha)
    draw_poly(dr, [(x - r * 0.85, y), (x + r * 0.85, y), (x, y - r * 1.9)], col)
    draw_ellipse(dr, x, y, r * 2, r * 2, col)
    draw_ellipse(dr, x - r * 0.25, y - r * 0.3, r * 0.5, r * 0.5, (255, 255, 255, int(alpha * 0.8)))


def draw_z(dr, x, y, s, alpha, rot_deg=0):
    """ 程序化手绘字母 Z（避免字体依赖） """
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
    """ 💢 怒气符号：中心向外四条圆头短杠 """
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


def draw_shadow(dr, cx, base_y, w, alpha):
    sh = Image.new("RGBA", (CV, CV), (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    d.ellipse([S(cx - w / 2), S(base_y - 5), S(cx + w / 2), S(base_y + 5)],
              fill=(20, 30, 60, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(S(2.5)))
    return sh


# ---------------------------------------------------------------- 各状态帧渲染
BODY_RX, BODY_RY = 86, 66          # 基准身体半径（最终像素）
BASE_Y = 232                       # 身体底部基准 y
CX = 128                           # 身体中心 x


def face_pos(cy, rx_s, ry_s):
    ex = rx_s * 0.38
    ey = cy - ry_s * 0.08
    my = cy + ry_s * 0.30
    return ex, ey, my


def render_frame(state, f):
    """ 渲染某状态第 f 帧（0..N_FRAMES-1），返回 CV 尺寸 RGBA 图与本体 bbox """
    t = f / N_FRAMES
    img = layer()
    colors = PALETTES[state]

    # 默认姿态
    cx, base_y = CX, BASE_Y
    squash, tilt = 1.0, 0.0
    eye_style, mouth_style = "open", "smile"
    eye_hs = 1.0

    if state == "idle":
        squash = 1.0 + 0.035 * math.sin(2 * math.pi * t)
        tilt = 0.012 * math.sin(2 * math.pi * t)
        # 眨眼：第 8 帧全闭、相邻帧半闭
        bt = min(abs(f - 8), abs(f - 8 + N_FRAMES), abs(f - 8 - N_FRAMES))
        if bt <= 1:
            eye_hs = {0: 0.12, 1: 0.35}[bt]

    elif state == "work":
        base_y = BASE_Y - 3.5 * abs(math.sin(4 * math.pi * t))   # 打字式双跳
        squash = 1.0 + 0.02 * math.sin(4 * math.pi * t)
        eye_style, mouth_style = "open", "flat"

    elif state == "happy":
        jump = abs(math.sin(3 * math.pi * t))                    # 每循环 1.5 次弹跳
        base_y = BASE_Y - 26 * jump
        squash = 0.90 + 0.14 * jump
        eye_style, mouth_style = "happy", "big"

    elif state == "tired":
        cx = CX + 3.5 * math.sin(2 * math.pi * t)                # 疲惫摇晃
        squash = 0.94 + 0.02 * math.sin(2 * math.pi * t)
        tilt = 0.03 * math.sin(2 * math.pi * t)
        eye_style, mouth_style = "half", "frown"

    elif state == "sleep":
        squash = 0.80 + 0.045 * math.sin(2 * math.pi * t)        # 趴扁 + 深呼吸
        eye_style, mouth_style = "closed", "o"

    elif state == "angry":
        cx = CX + 2.5 * math.sin(16 * math.pi * t)               # 高频震动
        squash = 1.03 + 0.03 * math.sin(8 * math.pi * t)
        eye_style, mouth_style = "angry", "zigzag"

    # ---- 阴影（先画，垫在身体下）----
    shadow_w = BODY_RX * 2 * (0.86 if state == "sleep" else 0.78)
    if state == "happy":
        shadow_w *= 1.0 - 0.25 * abs(math.sin(3 * math.pi * t))
    img.alpha_composite(draw_shadow(None, cx, BASE_Y + 4, shadow_w, 55))

    # ---- 身体（render_body 使用画布坐标，此处统一换算）----
    cx_c, base_c = S(cx), S(base_y)
    body, cy, rx_s, ry_s = render_body(cx_c, base_c, S(BODY_RX), S(BODY_RY),
                                       squash, colors, tilt_x=tilt)
    img.alpha_composite(body)

    # 高光白斑（左上经典果冻光泽，画布坐标，强模糊柔和过渡）
    gl = layer()
    gd = ImageDraw.Draw(gl)
    gd.ellipse([cx_c - rx_s * 0.52, cy - ry_s * 0.72, cx_c - rx_s * 0.10, cy - ry_s * 0.38],
               fill=(255, 255, 255, 72))
    gl = gl.filter(ImageFilter.GaussianBlur(S(3.2)))
    img.alpha_composite(gl)

    # ---- 五官（换算回最终像素单位，绘制函数内部自行乘 SS）----
    face = layer()
    fd = ImageDraw.Draw(face)
    ex = (rx_s * 0.38) / SS
    ey = (cy - ry_s * 0.08) / SS
    my = (cy + ry_s * 0.30) / SS
    cxu = cx

    if eye_style == "open":
        eye_open(fd, cxu - ex, ey, h_scale=eye_hs)
        eye_open(fd, cxu + ex, ey, h_scale=eye_hs)
    elif eye_style == "happy":
        eye_happy(fd, cxu - ex, ey)
        eye_happy(fd, cxu + ex, ey)
    elif eye_style == "closed":
        eye_closed(fd, cxu - ex, ey)
        eye_closed(fd, cxu + ex, ey)
    elif eye_style == "half":
        eye_half(fd, cxu - ex, ey)
        eye_half(fd, cxu + ex, ey)
    elif eye_style == "angry":
        eye_angry(fd, cxu - ex, ey, mirror=False)
        eye_angry(fd, cxu + ex, ey, mirror=True)

    if mouth_style == "smile":
        mouth_smile(fd, cxu, my)
    elif mouth_style == "big":
        mouth_big(fd, cxu, my)
    elif mouth_style == "flat":
        mouth_flat(fd, cxu, my)
    elif mouth_style == "frown":
        mouth_frown(fd, cxu, my)
    elif mouth_style == "o":
        mouth_o(fd, cxu, my)
    elif mouth_style == "zigzag":
        mouth_zigzag(fd, cxu, my)

    if state in ("idle", "work", "happy"):
        blush(face, cxu, ey + 14)
    img.alpha_composite(face)

    # ---- 状态特效 ----
    fx = layer()
    xd = ImageDraw.Draw(fx)

    if state == "happy":
        # 两颗爱心交替上升
        for k, (hx, phase) in enumerate([(CX - 58, 0.0), (CX + 60, 0.5)]):
            lt = (t + phase) % 1.0
            hy = BASE_Y - 110 - lt * 46
            hxo = hx + 6 * math.sin(2 * math.pi * lt * 2 + k)
            alpha = int(255 * max(0.0, 1.0 - lt) ** 0.8)
            if alpha > 8:
                draw_heart(xd, hxo, hy, 10 + 3 * lt, alpha)

    elif state == "sleep":
        # Zzz 依次飘出
        for k in range(3):
            lt = (t + k / 3.0) % 1.0
            zx = CX + 52 + lt * 44
            zy = BASE_Y - 128 - lt * 62
            alpha = int(235 * (1.0 - abs(lt - 0.5) * 2) ** 0.7)
            if alpha > 8:
                draw_z(xd, zx, zy, 14 + 16 * lt, alpha, rot_deg=8)

    elif state == "work":
        # 四周闪烁的灵感火花
        for k in range(4):
            ang = 2 * math.pi * (k / 4.0) + 0.6
            sx = CX + 96 * math.cos(ang)
            sy = BASE_Y - 78 + 66 * math.sin(ang)
            tw = (math.sin(2 * math.pi * (t * 2 + k / 4.0)) + 1) / 2
            alpha = int(60 + 190 * tw)
            draw_sparkle(xd, sx, sy, 5 + 4.5 * tw, alpha)

    elif state == "tired":
        # 两滴汗交替滑落
        for k, (side, phase) in enumerate([(1, 0.0), (-1, 0.55)]):
            lt = (t + phase) % 1.0
            sxp = CX + side * (BODY_RX * 0.72)
            syp = BASE_Y - 96 + lt * 56
            alpha = int(230 * (1.0 - lt ** 2))
            if alpha > 8:
                draw_sweat(xd, sxp, syp, 5.5 - 1.5 * lt, alpha)

    elif state == "angry":
        # 怒气符号脉冲
        pulse = 1.0 + 0.18 * math.sin(2 * math.pi * t * 2)
        draw_anger_mark(xd, CX + 62, BASE_Y - 148, 16 * pulse, 245)
        # 蒸汽上升
        for k in range(2):
            lt = (t * 1.5 + k / 2.0) % 1.0
            sx = CX - 30 + k * 26 + 5 * math.sin(2 * math.pi * lt * 3)
            sy = BASE_Y - 128 - lt * 40
            alpha = int(160 * (1.0 - lt))
            if alpha > 8:
                draw_steam(xd, sx, sy, 7 + 8 * lt, alpha)

    img.alpha_composite(fx)

    # ---- 本体 bbox（仅身体+五官，不含特效与阴影，供布局锚定）----
    core = layer()
    core.alpha_composite(body)
    core.alpha_composite(face)
    bbox = core.getbbox()
    return img, bbox


def finalize(img):
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def quantize_frames(frames):
    """ 全局共享调色板 + Floyd-Steinberg 抖动量化：
    消除果冻渐变的色带，并避免逐帧独立调色板导致的颜色闪烁 """
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
        mask = alpha.point(lambda a: 255 if a < 128 else 0)   # 透明像素写入保留索引 255
        q.paste(255, mask=mask)
        q.info["transparency"] = 255
        qframes.append(q)
    return qframes


# ---------------------------------------------------------------- 主流程
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

        gif_path = os.path.join(ASSETS, f"{state}.gif")
        qframes = quantize_frames(frames)
        qframes[0].save(gif_path, save_all=True, append_images=qframes[1:],
                        duration=FRAME_MS, loop=0, disposal=2, optimize=False)

        # 静态 PNG（代表帧）
        sf = static_frame[state]
        png_path = os.path.join(ASSETS, f"pet_{state}.png")
        frames[sf].save(png_path)

        # 本体 bbox 取所有帧并集（身体最大活动范围），换算成比例
        valid = [b for b in bboxes if b]
        l = min(b[0] for b in valid) / CV
        tp = min(b[1] for b in valid) / CV
        r = max(b[2] for b in valid) / CV
        bt = max(b[3] for b in valid) / CV
        paddings[state] = (round(l, 3), round(tp, 3), round(r, 3), round(bt, 3))

        # 预览采样 6 帧
        for f in range(0, N_FRAMES, 4):
            preview_cells.append((state, frames[f]))

        kb = os.path.getsize(gif_path) / 1024
        print(f"[{state}] {gif_path}  {kb:.0f} KB  bbox={paddings[state]}")

    # ---- 皮肤图标（根目录 icon 由默认皮肤渲染器生成，此处仅写入皮肤目录备份）----
    idle_img, bbox = render_frame("idle", 0)
    l, tp, r, bt = bbox
    m = int((r - l) * 0.10)
    crop = idle_img.crop((max(0, l - m), max(0, tp - m), min(CV, r + m), min(CV, bt + m)))
    icon = crop.resize((256, 256), Image.LANCZOS)
    icon.save(os.path.join(ASSETS, "icon.png"))
    print("[icon] skins/slime/icon.png 已生成")

    # ---- QA 预览图：6 状态 x 6 帧 ----
    sheet = Image.new("RGBA", (SIZE * 6, SIZE * 6), (40, 44, 60, 255))
    for i, (state, cell) in enumerate(preview_cells):
        row = ["idle", "work", "happy", "tired", "sleep", "angry"].index(state)
        col = i % 6
        sheet.alpha_composite(cell, (col * SIZE, row * SIZE))
    sheet_path = os.path.join(BASE_DIR, "tools", "preview_sheet.png")
    sheet.convert("RGB").save(sheet_path)
    print(f"[preview] {sheet_path}")

    print("\n# 粘贴到 ui/pet_window.py 的 paddings：")
    print("gif_paddings = {")
    for s in states:
        v = paddings[s]
        print(f'    "{s}": ({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f}, {v[3]:.3f}),')
    print("}")


if __name__ == "__main__":
    main()
