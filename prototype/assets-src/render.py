#!/usr/bin/env python3
"""辉光管时钟素材渲染器（纯 numpy + PIL，无外部服务）。

产物（写到 ../assets/）：
  plate4.png / plate6.png   整钟未点亮的底图：木底座、黄铜管座、旋钮、玻璃后壁、管内结构
  glow4.png  / glow6.png    辉光打在底座和铜件上的光照图（叠加用）
  tube-front.png            单支管的前层：阳极蜂窝网 + 玻璃前壁反光（盖在发光数字之上）
  nameplate.png             黄铜铭牌（时区文字由页面叠加）
  layout.js                 页面定位用的几何数据（单位：100% 大小下的 CSS 像素）

做法：不透明物体（木、铜）用 SDF 光线步进 + 程序化材质；玻璃是回转体，按解析法线算
反射；管内的细丝/网用 2D 矢量画在超采样画布上。全部长度以「玻璃管半径 R」为单位。

用法： python3 render.py [--scale 3] [--ss 2] [--only 4]
"""
import argparse
import json
import math
import os
import time

import numpy as np
from PIL import Image, ImageDraw

f32 = np.float32
ELEV = math.radians(6.0)            # 相机俯角
SE, CE = math.sin(ELEV), math.cos(ELEV)
R_CSS = 22.0                        # 100% 大小时，R 对应的 CSS 像素
VIEW = np.array([0.0, SE, CE], f32)  # 表面 → 相机

# 管子几何（R 为单位，y 从管座顶面算起）
G_R, G_HB, G_HD, G_TIP, G_TIPR = 1.0, 4.85, 0.98, 0.45, 0.20
CAGE = dict(x0=-0.58, x1=0.58, y0=1.05, y1=4.20)
DIGIT = dict(cx=0.0, cy=2.62, sx=0.96 / 44.0, sy=2.72 / 88.0)   # 笔画坐标(60x100) → R
STACK_ORDER = [1, 6, 2, 7, 5, 0, 4, 9, 8, 3]                    # 阴极叠放顺序：前 → 后
# 氖泡（冒号）
B_R, B_HB, B_HD, B_TIP, B_TIPR = 0.17, 0.80, 0.17, 0.13, 0.045
FERRULE_H = 0.18
COLLAR_H = 0.80

DIGITS = [
    'M30 6 C15 6 8 26 8 50 C8 74 15 94 30 94 C45 94 52 74 52 50 C52 26 45 6 30 6 Z',
    'M20 22 L34 6 L34 94',
    'M9 28 C9 14 18 6 30 6 C42 6 51 14 51 27 C51 40 42 49 31 60 L8 94 L52 94',
    'M10 7 L50 7 L29 41 C43 41 52 52 52 66 C52 82 42 94 29 94 C19 94 12 88 8 80',
    'M41 94 L41 6 L7 68 L54 68',
    'M49 7 L17 7 L12 45 C18 40 24 37 31 37 C44 37 52 49 52 65 C52 82 42 94 29 94 C19 94 12 88 8 80',
    'M45 6 C28 18 9 42 9 66 C9 82 18 94 30 94 C42 94 51 83 51 68 C51 54 43 44 31 44 C20 44 12 52 9 64',
    'M8 7 L52 7 L25 94',
    'M30 46 C20 46 13 37 13 26 C13 14 20 6 30 6 C40 6 47 14 47 26 C47 37 40 46 30 46 C18 46 9 56 9 70 C9 84 18 94 30 94 C42 94 51 84 51 70 C51 56 42 46 30 46 Z',
    None,  # 9 = 6 旋转 180°
]


# ───────────────────────── 基础工具 ─────────────────────────
def sstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def norm3(v):
    return v / np.maximum(np.sqrt((v * v).sum(-1, keepdims=True)), 1e-8)


def dot(a, b):
    return (a * b).sum(-1)


def _hash(ix, iy, iz, seed):
    M = np.uint64(0xffffffff)
    h = (ix.astype(np.uint64) * np.uint64(374761393) + iy.astype(np.uint64) * np.uint64(668265263)
         + iz.astype(np.uint64) * np.uint64(2246822519) + np.uint64((seed * 3266489917) % 2 ** 32)) & M
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & M
    h = h ^ (h >> np.uint64(16))
    return (h.astype(np.float64) / 4294967296.0).astype(f32)


def vnoise(x, y, z, seed=0):
    xf, yf, zf = np.floor(x), np.floor(y), np.floor(z)
    ix, iy, iz = xf.astype(np.int64), yf.astype(np.int64), zf.astype(np.int64)
    fx, fy, fz = x - xf, y - yf, z - zf
    ux, uy, uz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)

    def H(dx, dy, dz):
        return _hash(ix + dx, iy + dy, iz + dz, seed)
    c00 = H(0, 0, 0) * (1 - ux) + H(1, 0, 0) * ux
    c10 = H(0, 1, 0) * (1 - ux) + H(1, 1, 0) * ux
    c01 = H(0, 0, 1) * (1 - ux) + H(1, 0, 1) * ux
    c11 = H(0, 1, 1) * (1 - ux) + H(1, 1, 1) * ux
    c0 = c00 * (1 - uy) + c10 * uy
    c1 = c01 * (1 - uy) + c11 * uy
    return (c0 * (1 - uz) + c1 * uz).astype(f32)


def fbm(x, y, z, octaves=4, seed=0, gain=0.5, lac=2.0):
    a, s, n = 1.0, 0.0, 0.0
    for o in range(octaves):
        s = s + a * vnoise(x, y, z, seed + o * 17)
        n += a
        x, y, z = x * lac, y * lac, z * lac
        a *= gain
    return (s / n).astype(f32)


# ───────────────────────── 环境光（影棚） ─────────────────────────
def softbox(az, el, a0, a1, e0, e1, s):
    return (sstep(a0 - s, a0 + s, az) * (1 - sstep(a1 - s, a1 + s, az))
            * sstep(e0 - s, e0 + s, el) * (1 - sstep(e1 - s, e1 + s, el)))


def env(d, soft=3.0, bounce=True):
    """方向 d(N,3) 上的入射亮度 RGB。x 右、y 上、z 朝相机。"""
    az = np.degrees(np.arctan2(d[:, 0], d[:, 2]))
    el = np.degrees(np.arcsin(np.clip(d[:, 1], -1, 1)))
    key = softbox(az, el, -128, -84, -8, 62, soft) * 12.0        # 左侧大柔光箱
    strip = softbox(az, el, 99, 110, -28, 66, soft) * 8.0       # 右侧条形灯
    front = softbox(az, el, -38, 22, -12, 52, soft * 2) * 1.5   # 正面补光
    top = sstep(58 - soft, 66 + soft, el) * 2.6                 # 顶光
    amb = 0.16 + 0.26 * np.clip(d[:, 1], 0, 1)
    L = np.zeros((d.shape[0], 3), f32)
    L += (key[:, None] * np.array([1.0, 0.97, 0.92], f32) + strip[:, None] * np.array([0.92, 0.96, 1.0], f32)
          + (front + top + amb)[:, None])
    if bounce:   # 朝下看到的是木头的反光
        dn = np.clip(-d[:, 1], 0, 1)[:, None]
        L = L * (1 - 0.85 * sstep(0.0, 0.25, dn)) + dn * np.array([0.42, 0.17, 0.06], f32) * 1.4
    return L.astype(f32)


# ───────────────────────── 场景 ─────────────────────────
class Scene:
    def __init__(self, n):
        self.n = n
        self.H, self.D = 3.0, 5.0
        pairs = n // 2
        pcs = [(k - (pairs - 1) / 2) * 8.1 for k in range(pairs)]
        self.tubes = np.array([pc + o for pc in pcs for o in (-1.8, 1.8)], f32)
        self.colons = np.array([(pcs[i] + pcs[i + 1]) / 2 for i in range(pairs - 1)], f32)
        self.W = float(self.tubes[-1] - self.tubes[0]) + 2 * 4.2
        self.knobs = np.array([-2.2, 0.0, 2.2], f32)
        self.knob_y = self.H / 2
        # 屏幕窗口（R 单位）
        self.xmin, self.xmax = -self.W / 2 - 0.4, self.W / 2 + 0.4
        self.ymin = -self.D / 2 * SE - 0.3
        self.ymax = (self.H + COLLAR_H + G_HB + G_HD + G_TIP) * CE + 0.3


def nearest(xs, x):
    if len(xs) == 1:
        return np.full(x.shape, xs[0], f32)
    mids = (xs[:-1] + xs[1:]) / 2
    return xs[np.searchsorted(mids, x)]


def sd_cyl(q, y, h, r, rnd=0.0):
    dx = q - (r - rnd)
    dy = np.abs(y) - (h - rnd)
    return np.minimum(np.maximum(dx, dy), 0) + np.sqrt(np.maximum(dx, 0) ** 2 + np.maximum(dy, 0) ** 2) - rnd


def sd_cone(q, y, h, r1, r2):
    k2x, k2y = r2 - r1, 2 * h
    cax = q - np.minimum(q, np.where(y < 0, r1, r2))
    cay = np.abs(y) - h
    t = np.clip(((r2 - q) * k2x + (h - y) * k2y) / (k2x * k2x + k2y * k2y), 0, 1)
    cbx = q - r2 + k2x * t
    cby = y - h + k2y * t
    s = np.where((cbx < 0) & (cay < 0), -1.0, 1.0)
    return (s * np.sqrt(np.minimum(cax * cax + cay * cay, cbx * cbx + cby * cby))).astype(f32)


def sdf(p, sc):
    """返回 (距离, 材质)：0 木头，1 黄铜。"""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    # 底座：平面圆角矩形挤出，上下棱倒圆
    rc, re = 0.85, 0.24
    qx = np.abs(x) - (sc.W / 2 - rc)
    qz = np.abs(z) - (sc.D / 2 - rc)
    d2 = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qz, 0) ** 2) + np.minimum(np.maximum(qx, qz), 0) - rc
    wx = d2 + re
    wy = np.abs(y - sc.H / 2) - sc.H / 2 + re
    d_wood = np.minimum(np.maximum(wx, wy), 0) + np.sqrt(np.maximum(wx, 0) ** 2 + np.maximum(wy, 0) ** 2) - re

    # 管座（取最近的一个）
    cx = nearest(sc.tubes, x)
    q = np.sqrt((x - cx) ** 2 + z * z)
    yy = y - sc.H
    d_b = sd_cyl(q, yy - 0.07, 0.07, 1.34, 0.03)
    d_b = np.minimum(d_b, sd_cone(q, yy - 0.37, 0.24, 1.27, 1.10))
    d_b = np.minimum(d_b, sd_cyl(q, yy - 0.70, 0.10, 1.16, 0.035))
    # 旋钮（正面，轴向 z）
    kx = nearest(sc.knobs, x)
    rr = np.sqrt((x - kx) ** 2 + (y - sc.knob_y) ** 2)
    zz = z - sc.D / 2
    bezel = sd_cyl(rr, zz - 0.03, 0.05, 0.40, 0.03)
    cap = np.maximum(np.sqrt(rr * rr + (zz + 0.13) ** 2) - 0.36, 0.05 - zz)
    d_b = np.minimum(d_b, np.minimum(bezel, cap))
    # 氖泡小铜座
    if len(sc.colons):
        fx = nearest(sc.colons, x)
        fq = np.sqrt((x - fx) ** 2 + z * z)
        d_b = np.minimum(d_b, sd_cyl(fq, yy - FERRULE_H / 2, FERRULE_H / 2, 0.27, 0.03))
    d = np.minimum(d_wood, d_b)
    return d.astype(f32), (d_b < d_wood)


def sdf_d(p, sc):
    return sdf(p, sc)[0]


def march(o, dvec, sc, steps=110, tmax=40.0, eps=1.5e-3):
    N = o.shape[0]
    t = np.zeros(N, f32)
    hit = np.zeros(N, bool)
    act = np.arange(N)
    for _ in range(steps):
        d = sdf_d(o[act] + dvec * t[act, None], sc)
        t[act] += d
        h = d < eps
        far = t[act] > tmax
        hit[act[h]] = True
        act = act[~(h | far)]
        if act.size == 0:
            break
    return t, hit


def normal_at(p, sc, h=2e-3):
    k = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], f32)
    n = np.zeros_like(p)
    for ki in k:
        n += ki * sdf_d(p + ki * h, sc)[:, None]
    return norm3(n)


def ambient_occ(p, n, sc):
    occ = np.zeros(p.shape[0], f32)
    w = 1.0
    for h in (0.04, 0.10, 0.22, 0.45, 0.85):
        occ += w * np.clip(h - sdf_d(p + n * h, sc), 0, None) / h
        w *= 0.72
    return np.clip(1.0 - 0.62 * occ, 0, 1)


def soft_shadow(p, n, L, sc, k=7.0, steps=30, tmax=9.0):
    res = np.ones(p.shape[0], f32)
    t = np.full(p.shape[0], 0.05, f32)
    o = p + n * 0.02
    for _ in range(steps):
        d = sdf_d(o + L * t[:, None], sc)
        res = np.minimum(res, k * d / t)
        t += np.clip(d, 0.03, 0.6)
    return np.clip(res, 0, 1)


def wood_albedo(p):
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    warp = fbm(x * 0.09, y * 0.5, z * 0.5, 3, seed=3)
    d = np.sqrt((y + 12.0) ** 2 + (z + 8.0) ** 2) + 2.1 * warp + 0.03 * x
    v = d / 0.52
    ring = v - np.floor(v)
    late = sstep(0.45, 1.0, ring) * (1 - sstep(0.94, 1.0, ring))            # 晚材暗线
    band = fbm(x * 0.05, y * 0.8, z * 0.8, 3, seed=9)                       # 大尺度色带
    fib = fbm(x * 0.8, y * 34, z * 34, 3, seed=21)                          # 纤维
    pores = sstep(0.66, 0.84, vnoise(x * 4.5, y * 90, z * 90, seed=33))     # 导管孔：顺纹的短黑线
    t = np.clip(0.26 * late + 1.25 * (band - 0.5) + 0.40 + 0.34 * (fib - 0.5), 0, 1)
    light = np.array([0.27, 0.075, 0.024], f32)
    dark = np.array([0.075, 0.018, 0.006], f32)
    col = light * (1 - t)[:, None] + dark * t[:, None]
    col = col * (1 - 0.45 * pores)[:, None]
    return col.astype(f32), fib


BRASS = np.array([1.0, 0.71, 0.27], f32)
ORANGE = np.array([1.0, 0.27, 0.035], f32)
KEY_L = norm3(np.array([[-0.48, 0.78, 0.56]], f32))[0]
FILL_L = norm3(np.array([[0.7, 0.25, 0.65]], f32))[0]


def tonemap(c, exposure=1.0):
    c = np.clip(c * exposure, 0, None)
    c = (c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14)
    return np.clip(c, 0, 1) ** (1 / 2.2)


def render_opaque(sc, P):
    """返回 (rgb 线性 HxWx3, alpha HxW, glow 线性 HxWx3)，分辨率为超采样分辨率。"""
    Wp = int(math.ceil((sc.xmax - sc.xmin) * P))
    Hp = int(math.ceil((sc.ymax - sc.ymin) * P))
    rgb = np.zeros((Hp, Wp, 3), f32)
    glow = np.zeros((Hp, Wp, 3), f32)
    alpha = np.zeros((Hp, Wp), f32)
    # 不透明物最高到管座沿的后缘
    top = (sc.H + COLLAR_H) * CE + 1.4 * SE + 0.1
    j0 = max(int((sc.ymax - top) * P), 0)
    sx = sc.xmin + (np.arange(Wp, dtype=f32) + 0.5) / P
    T0 = 14.0
    fwd = np.array([0.0, -SE, -CE], f32)
    BAND = max(64, int(2_400_000 / Wp))
    for ja in range(j0, Hp, BAND):
        jb = min(ja + BAND, Hp)
        sy = sc.ymax - (np.arange(ja, jb, dtype=f32) + 0.5) / P
        SX, SY = np.meshgrid(sx, sy)
        o = np.stack([SX.ravel(), SY.ravel() * CE + SE * T0, -SY.ravel() * SE + CE * T0], 1).astype(f32)
        t, hit = march(o, fwd, sc)
        if not hit.any():
            continue
        p = o[hit] + fwd * t[hit, None]
        _, mat = sdf(p, sc)
        n = normal_at(p, sc)
        ao = ambient_occ(p, n, sc)
        sh = soft_shadow(p, n, KEY_L, sc)
        ndv = np.clip(dot(n, VIEW), 0, 1)
        col = np.zeros_like(p)
        alb = np.zeros_like(p)

        w = ~mat
        if w.any():
            a, fib = wood_albedo(p[w])
            nw = norm3(n[w] + np.stack([np.zeros_like(fib), (fib - 0.5) * 0.10, np.zeros_like(fib)], 1))
            ndl = np.clip(dot(nw, KEY_L), 0, 1)
            ndf = np.clip(dot(nw, FILL_L), 0, 1)
            ground = 0.70 + 0.30 * sstep(0.0, 1.8, p[w][:, 1])          # 贴近桌面的一段压暗
            diff = a * ((1.9 * ndl * sh[w] + 0.36 * ndf + 0.36 * ao[w]) * ground)[:, None]
            r = 2 * dot(nw, VIEW)[:, None] * nw - VIEW
            fr = 0.04 + 0.96 * (1 - ndv[w]) ** 5
            hv = norm3(KEY_L + VIEW)
            spec = np.clip(dot(nw, hv), 0, 1) ** 70 * 1.6 * sh[w]
            coat = env(r, soft=11.0, bounce=False) * (fr * 0.55 * ao[w] * ground)[:, None] + spec[:, None]
            col[w] = diff + coat
            alb[w] = a
        b = mat
        if b.any():
            pb, nb = p[b], n[b]
            # 车削纹：沿各自轴向的细槽
            g = 0.045 * np.sin(pb[:, 1] * 150.0) + 0.03 * (vnoise(pb[:, 0] * 2, pb[:, 1] * 60, pb[:, 2] * 2, 5) - 0.5)
            onfront = pb[:, 2] > sc.D / 2 - 0.05          # 旋钮不加车削纹
            g = np.where(onfront, 0.0, g)
            nb = norm3(nb + np.stack([np.zeros_like(g), g, np.zeros_like(g)], 1))
            r = 2 * dot(nb, VIEW)[:, None] * nb - VIEW
            fr = (BRASS + (1 - BRASS) * ((1 - np.clip(dot(nb, VIEW), 0, 1)) ** 5)[:, None])
            e = env(r, soft=13.0)
            ndl = np.clip(dot(nb, KEY_L), 0, 1)
            hv = norm3(KEY_L + VIEW)
            spec = np.clip(dot(nb, hv), 0, 1) ** 120 * 5.0 * sh[b]
            col[b] = fr * (e ** 1.15 * (0.30 + 0.70 * ao[b])[:, None] * 0.66 + (0.30 * ndl * sh[b] + spec)[:, None])
            alb[b] = BRASS * 0.55

        # 辉光对不透明物的照明（每支管 3 个采样点近似一条竖直光源）
        gl = np.zeros_like(p)
        for cx in sc.tubes:
            rho = np.sqrt((p[:, 0] - cx) ** 2 + p[:, 2] ** 2)
            near_top = p[:, 1] < sc.H + 0.06
            for hy, wgt in ((1.5, 0.34), (2.6, 0.36), (3.7, 0.30)):
                Lp = np.array([cx, sc.H + COLLAR_H + hy, 0.0], f32)
                l = Lp - p
                d2 = dot(l, l)
                l = l / np.sqrt(d2)[:, None]
                ndl = np.clip(dot(n, l), 0, 1)
                clear = (hy + COLLAR_H) * (1 - 1.16 / np.maximum(rho, 1.17)) / COLLAR_H
                vis = np.where(near_top & (rho > 1.16), sstep(0.8, 1.25, clear), 1.0)
                hv = norm3(l + VIEW)
                spec = np.where(mat, np.clip(dot(n, hv), 0, 1) ** 90 * 1.3, np.clip(dot(n, hv), 0, 1) ** 40 * 0.12)
                gl += (wgt * vis / (d2 + 0.7))[:, None] * (alb * ndl[:, None] + spec[:, None] * np.where(mat[:, None], BRASS, 1.0))
        gl = gl * ORANGE * 3.0

        idx = np.flatnonzero(hit)
        jj = ja + idx // Wp
        ii = idx % Wp
        rgb[jj, ii] = col
        glow[jj, ii] = gl
        alpha[jj, ii] = 1.0
    return rgb, alpha, glow


# ───────────────────────── 玻璃（回转体，解析） ─────────────────────────
def glass_sprite(P, Rg, hb, hd, tip, tipr, pad=0.08):
    """返回 dict(back, front, x0, y1, w, h)。back/front 为预乘 RGBA float(H,W,4)。"""
    Htot = hb + hd + tip
    x0, x1 = -Rg - pad, Rg + pad
    y0, y1 = -Rg * SE - pad, Htot + pad
    W = int(math.ceil((x1 - x0) * P))
    H = int(math.ceil((y1 - y0) * P))
    X = x0 + (np.arange(W, dtype=f32) + 0.5) / P
    Yr = y1 - (np.arange(H, dtype=f32) + 0.5) / P
    # 轮廓 r(h)
    h = Yr
    dome = Rg * np.sqrt(np.clip(1 - (np.clip(h - hb, 0, None) / hd) ** 2, 0, 1))
    h0 = hb + hd - 0.22 * hd
    s = np.clip((h - h0) / (Htot - h0), 0, 1)
    tipp = np.where(h >= h0, tipr * (1 - s) ** 1.25 * (1 + 1.6 * (1 - s) ** 6), 0.0)
    k = 0.10 * Rg
    hh = np.clip(0.5 + 0.5 * (tipp - dome) / k, 0, 1)
    prof = dome * (1 - hh) + tipp * hh + k * hh * (1 - hh)
    prof = np.where(h > Htot, 0.0, prof).astype(f32)
    dr = np.gradient(prof, -1.0 / P).astype(f32)          # dr/dh（行向下 → h 递减）
    dr = np.clip(dr, -6, 6)

    XX, RR = np.meshgrid(X, prof)
    _, DR = np.meshgrid(X, dr)
    _, HH = np.meshgrid(X, h)
    u = np.where(RR > 1e-4, XX / np.maximum(RR, 1e-4), 9.0)
    cov = np.clip((RR - np.abs(XX)) * P + 0.5, 0, 1)
    au = np.clip(np.abs(u), 0, 1)
    nz0 = np.sqrt(1 - au * au)
    # 底部被管座沿切成一段椭圆弧
    cov = cov * np.clip((HH + SE * Rg * nz0) * P + 0.5, 0, 1)
    nrm = np.sqrt(1 + DR * DR)
    us = np.clip(u, -1, 1)

    def layer(nx, ny, nzv, gain, tint):
        n = np.stack([nx.ravel(), ny.ravel(), nzv.ravel()], 1).astype(f32)
        ndv = np.clip(dot(n, VIEW), 0, 1)
        r = 2 * ndv[:, None] * n - VIEW
        L = env(r, soft=1.8, bounce=False)
        F = 0.04 + 0.96 * (1 - ndv) ** 5
        hi = L * (F * gain)[:, None]
        a_hi = np.clip(hi.max(1), 0, 0.92)
        colr = hi / np.maximum(hi.max(1, keepdims=True), 1e-6)
        a_hi = a_hi.reshape(H, W)
        colr = colr.reshape(H, W, 3)
        a_t = tint[0] + tint[1] * (1 - nz0) ** 2.3
        out = np.zeros((H, W, 4), f32)
        out[..., :3] = colr * a_hi[..., None]
        out[..., 3] = a_hi + (1 - a_hi) * a_t
        return out * cov[..., None]

    front = layer(us / nrm, -DR / nrm, nz0 / nrm, 1.0, (0.03, 0.30))
    back = layer(-us / nrm, DR / nrm, nz0 / nrm, 0.36, (0.035, 0.26))
    # 轮廓处一道细亮边
    rim = sstep(0.95, 0.985, au) * (1 - sstep(0.99, 1.0, au)) * 0.20 * cov
    front[..., :3] += rim[..., None] * (1 - front[..., 3:4])
    front[..., 3] += rim * (1 - front[..., 3])
    return dict(back=back, front=front, x0=x0, y1=y1, w=W, h=H)


# ───────────────────────── 管内结构（2D 矢量，画在超采样画布上） ─────────────────────────
def path_points(d, n=28):
    """解析 M/L/C/Z 路径 → 折线列表（每段一个点数组）。"""
    tok = d.replace(',', ' ').split()
    i, cur, start, subs, pts = 0, None, None, [], []
    while i < len(tok):
        c = tok[i]
        if c[0] in 'MLCZ':
            cmd, rest = c[0], c[1:]
            i += 1
            if rest:
                tok.insert(i, rest)
        nums = lambda k: [float(tok[i + j]) for j in range(k)]
        if cmd == 'M':
            if pts:
                subs.append(pts)
            x, y = nums(2); i += 2
            cur = start = (x, y); pts = [cur]
        elif cmd == 'L':
            x, y = nums(2); i += 2
            cur = (x, y); pts.append(cur)
        elif cmd == 'C':
            x1, y1, x2, y2, x, y = nums(6); i += 6
            for k in range(1, n + 1):
                t = k / n
                a, b, c2, dd = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
                pts.append((a * cur[0] + b * x1 + c2 * x2 + dd * x, a * cur[1] + b * y1 + c2 * y2 + dd * y))
            cur = (x, y)
        elif cmd == 'Z':
            pts.append(start); cur = start
    if pts:
        subs.append(pts)
    return subs


def digit_polys(dg):
    if dg == 9:
        return [[(60 - x, 100 - y) for x, y in sub] for sub in path_points(DIGITS[6])]
    return path_points(DIGITS[dg])


class Canvas:
    """以 R 为单位作画的 PIL 画布（y 向上）。"""
    def __init__(self, x0, y1, W, H, P):
        self.x0, self.y1, self.P = x0, y1, P
        self.im = Image.new('RGBA', (W, H), (0, 0, 0, 0))

    def px(self, x, y):
        return ((x - self.x0) * self.P, (self.y1 - y) * self.P)

    def layer(self):
        return Image.new('RGBA', self.im.size, (0, 0, 0, 0))

    def over(self, lay):
        self.im = Image.alpha_composite(self.im, lay)

    def line(self, pts, w, fill, lay=None):
        tgt = lay if lay is not None else self.layer()
        dr = ImageDraw.Draw(tgt)
        wp = max(1, int(round(w * self.P)))
        pp = [self.px(x, y) for x, y in pts]
        dr.line(pp, fill=fill, width=wp, joint='curve')
        if wp > 2:
            rr = wp / 2
            for q in (pp[0], pp[-1]):
                dr.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr], fill=fill)
        if lay is None:
            self.over(tgt)

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, w=0.0):
        lay = self.layer()
        a, b = self.px(cx - rx, cy + ry), self.px(cx + rx, cy - ry)
        ImageDraw.Draw(lay).ellipse([a[0], a[1], b[0], b[1]], fill=fill, outline=outline, width=max(1, int(round(w * self.P))))
        self.over(lay)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w=0.0, rad=0.0):
        lay = self.layer()
        a, b = self.px(x0, y1), self.px(x1, y0)
        ImageDraw.Draw(lay).rounded_rectangle([a[0], a[1], b[0], b[1]], radius=rad * self.P, fill=fill, outline=outline,
                                              width=max(1, int(round(w * self.P))))
        self.over(lay)

    def arr(self):
        a = np.asarray(self.im).astype(f32) / 255.0
        a[..., :3] *= a[..., 3:4]
        return a


def rod(cv, x, y0, y1, w, base=(168, 164, 158)):
    """竖直金属细杆：暗边 + 高光，带一点圆柱感。"""
    cv.line([(x, y0), (x, y1)], w, (int(base[0] * .42), int(base[1] * .42), int(base[2] * .42), 255))
    cv.line([(x - w * 0.08, y0), (x - w * 0.08, y1)], w * 0.62, base + (255,))
    cv.line([(x - w * 0.2, y0), (x - w * 0.2, y1)], w * 0.2, (245, 243, 238, 230))


def draw_interior(g, P):
    cv = Canvas(g['x0'], g['y1'], g['w'], g['h'], P)
    c = CAGE
    rng = np.random.default_rng(7)
    # 芯柱引脚
    for x in np.linspace(-0.46, 0.46, 9):
        rod(cv, float(x), -0.12, c['y0'] - 0.02, 0.03, (150, 146, 140))
    # 下云母片
    cv.ellipse(0, c['y0'] - 0.07, 0.80, 0.80 * SE + 0.012, fill=(120, 114, 104, 200))
    cv.ellipse(0, c['y0'] - 0.055, 0.80, 0.80 * SE, fill=(168, 160, 146, 190))
    # 两侧支撑杆
    for x in (-0.71, 0.71):
        rod(cv, x, 0.05, c['y1'] + 0.34, 0.045)
    # 阴极罩后板：深色金属，上亮下暗，带细微拉丝
    H = cv.im.size[1]
    a, b = cv.px(c['x0'], c['y1']), cv.px(c['x1'], c['y0'])
    bw, bh = int(b[0] - a[0]), int(b[1] - a[1])
    gy = np.linspace(1, 0, bh)[:, None]
    gx = np.abs(np.linspace(-1, 1, bw))[None, :]
    lum = 21 + 15 * gy ** 1.6 - 7 * gx ** 2
    lum = lum + rng.normal(0, 1.1, (bh, 1)) + rng.normal(0, 0.7, (bh, bw))
    plate = np.clip(np.stack([lum * 1.05, lum * 0.98, lum * 0.93, np.full_like(lum, 255)], -1), 0, 255).astype(np.uint8)
    lay = cv.layer()
    lay.paste(Image.fromarray(plate), (int(a[0]), int(a[1])))
    cv.over(lay)
    # 数字阴极叠层（后 → 前），细金属丝
    for depth, dg in reversed(list(enumerate(STACK_ORDER))):
        off = (depth - 4.5) * 0.010
        shade = 86 - depth * 4
        for sub in digit_polys(dg):
            pts = [(DIGIT['cx'] + (x - 30) * DIGIT['sx'] + off, DIGIT['cy'] - (y - 50) * DIGIT['sy']) for x, y in sub]
            cv.line(pts, 0.036, (int(shade * .40), int(shade * .37), int(shade * .34), 255))
            cv.line([(x - 0.006, y + 0.006) for x, y in pts], 0.015, (shade + 34, shade + 26, shade + 14, 200))
    # 罩框
    cv.rect(c['x0'] - 0.03, c['y0'] - 0.03, c['x1'] + 0.03, c['y1'] + 0.03, outline=(104, 98, 92, 255), w=0.035, rad=0.03)
    cv.line([(c['x0'] - 0.03, c['y1'] + 0.03), (c['x1'] + 0.03, c['y1'] + 0.03)], 0.02, (190, 186, 178, 230))
    # 上云母片
    ym = c['y1'] + 0.26
    cv.ellipse(0, ym - 0.015, 0.82, 0.82 * SE + 0.014, fill=(118, 112, 102, 210))
    cv.ellipse(0, ym, 0.82, 0.82 * SE, fill=(176, 168, 152, 195))
    cv.ellipse(0, ym, 0.82, 0.82 * SE, outline=(226, 220, 206, 200), w=0.010)
    # 顶部吸气环与排气管内的细丝
    rod(cv, -0.20, ym, ym + 0.52, 0.026, (150, 146, 140))
    rod(cv, 0.20, ym, ym + 0.52, 0.026, (150, 146, 140))
    cv.ellipse(0, ym + 0.54, 0.30, 0.30 * SE + 0.02, outline=(74, 70, 66, 255), w=0.05)
    cv.ellipse(0, ym + 0.555, 0.30, 0.30 * SE + 0.02, outline=(196, 192, 184, 240), w=0.022)
    return cv.arr()


def draw_mesh(g, P):
    """前层阳极网：蜂窝状细丝。"""
    cv = Canvas(g['x0'], g['y1'], g['w'], g['h'], P)
    c = CAGE
    a = 0.094                      # 六边形边长
    w, hgt = math.sqrt(3) * a, 1.5 * a
    dark, lite = cv.layer(), cv.layer()
    row = 0
    y = c['y0'] - a
    while y < c['y1'] + a:
        x = c['x0'] - w + (w / 2 if row % 2 else 0)
        while x < c['x1'] + w:
            v = [(x + a * math.cos(math.radians(30 + 60 * k)), y + a * math.sin(math.radians(30 + 60 * k))) for k in range(6)]
            for k in (0, 1, 2):     # 每格只画三条边，避免重复
                seg = [v[k], v[k + 1]]
                cv.line(seg, 0.0125, (30, 24, 20, 205), dark)
                cv.line([(px - 0.003, py + 0.003) for px, py in seg], 0.006, (128, 116, 102, 70), lite)
            x += w
        y += hgt
        row += 1
    # 裁到罩框内
    mask = Image.new('L', cv.im.size, 0)
    p0, p1 = cv.px(c['x0'], c['y1']), cv.px(c['x1'], c['y0'])
    ImageDraw.Draw(mask).rounded_rectangle([p0[0], p0[1], p1[0], p1[1]], radius=0.02 * P, fill=255)
    for lay in (dark, lite):
        lay.putalpha(Image.composite(lay.getchannel('A'), Image.new('L', cv.im.size, 0), mask))
        cv.over(lay)
    cv.rect(c['x0'] - 0.03, c['y0'] - 0.03, c['x1'] + 0.03, c['y1'] + 0.03, outline=(70, 64, 58, 255), w=0.03, rad=0.03)
    return cv.arr()


def draw_bulb_interior(g, P):
    cv = Canvas(g['x0'], g['y1'], g['w'], g['h'], P)
    for x in (-0.055, 0.055):
        rod(cv, x, -0.03, 0.62, 0.032, (176, 170, 160))
    cv.ellipse(0, 0.10, 0.11, 0.11 * SE + 0.012, fill=(60, 56, 52, 230))
    return cv.arr()


# ───────────────────────── 合成 ─────────────────────────
def over(dst, src, x, y):
    """预乘 RGBA：把 src 盖到 dst 的 (x,y)。"""
    h, w = src.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, dst.shape[1]), min(y + h, dst.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    s = src[y0 - y:y1 - y, x0 - x:x1 - x]
    d = dst[y0:y1, x0:x1]
    dst[y0:y1, x0:x1] = s + d * (1 - s[..., 3:4])


def down(a, ss):
    if ss == 1:
        return a
    h, w = a.shape[0] // ss * ss, a.shape[1] // ss * ss
    a = a[:h, :w]
    return a.reshape(h // ss, ss, w // ss, ss, -1).mean((1, 3)).squeeze()


def save_rgba(premult, path):
    a = premult[..., 3:4]
    rgb = np.where(a > 1e-5, premult[..., :3] / np.maximum(a, 1e-5), 0)
    out = np.concatenate([np.clip(rgb, 0, 1), np.clip(a, 0, 1)], -1)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(path, optimize=True)


def nameplate(P_css_scale, path):
    """拉丝黄铜铭牌：纯 2D 着色。尺寸 3.6R x 0.84R。"""
    wR, hR = 3.6, 0.84
    S = 3                                   # 内部超采样
    P = R_CSS * P_css_scale * S
    W, H = int(wR * P), int(hR * P)
    yy, xx = np.mgrid[0:H, 0:W].astype(f32)
    u, v = xx / P, yy / P                    # R 单位，v 向下
    rad = 0.07
    qx = np.abs(u - wR / 2) - (wR / 2 - rad)
    qy = np.abs(v - hR / 2) - (hR / 2 - rad)
    d = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2) + np.minimum(np.maximum(qx, qy), 0) - rad
    cov = np.clip(-d * P + 0.5, 0, 1)
    streak = fbm(u * 1.2, v * 70, np.zeros_like(u), 3, seed=41)
    grad = 0.78 - 0.30 * (v / hR) + 0.10 * np.exp(-((v / hR - 0.30) / 0.16) ** 2)
    lum = grad * (0.86 + 0.28 * (streak - 0.5))
    bev = sstep(0.0, 0.05, -d)               # 倒角：外缘一圈
    edge_hi = (1 - bev) * np.clip(1 - v / hR * 1.3, 0, 1) * 0.55
    edge_lo = (1 - bev) * np.clip(v / hR * 1.3 - 0.4, 0, 1) * 0.55
    lum = lum + edge_hi - edge_lo
    col = lum[..., None] * np.array([1.0, 0.80, 0.42], f32) * 0.92 + 0.06
    # 两颗小螺丝
    for cx in (0.22, wR - 0.22):
        rr = np.sqrt((u - cx) ** 2 + (v - hR / 2) ** 2)
        head = np.clip((0.085 - rr) * P + 0.5, 0, 1)
        dome = np.clip(1 - (rr / 0.085) ** 2, 0, 1)
        hc = (0.45 + 0.5 * dome * np.clip(1 - (v - hR / 2 + 0.03) / 0.09, 0, 1.4))[..., None] * np.array([1.0, 0.82, 0.46], f32)
        slot = (np.abs((u - cx) * 0.6 + (v - hR / 2) * 0.8) < 0.012) & (rr < 0.075)
        hc = np.where(slot[..., None], hc * 0.25, hc)
        col = col * (1 - 0.45 * (1 - sstep(0.085, 0.115, rr)) * (1 - head))[..., None]
        col = col * (1 - head[..., None]) + hc * head[..., None]
    col = np.clip(col, 0, 1) ** (1 / 1.25)
    out = np.concatenate([col * cov[..., None], cov[..., None]], -1)
    out = down(out, S)
    save_rgba(out, path)
    return out.shape[1], out.shape[0]


def build(n, scale, ss, outdir, shared):
    t0 = time.time()
    sc = Scene(n)
    P = R_CSS * scale * ss
    rgb, alpha, glow = render_opaque(sc, P)
    Hs, Ws = alpha.shape
    plate = np.zeros((Hs, Ws, 4), f32)
    plate[..., :3] = tonemap(rgb, 0.80) * alpha[..., None]
    plate[..., 3] = alpha
    gl = 1 - np.exp(-glow * 1.3)
    ga = gl.max(-1)
    glowimg = np.concatenate([gl, ga[..., None]], -1)       # 预乘：rgb 即加到背景上的量
    print(f'  opaque {n}: {Ws}x{Hs} in {time.time() - t0:.1f}s')

    def to_px(x, y):            # 世界 (x, 高度 y, z=0) → 超采样像素
        return (x - sc.xmin) * P, (sc.ymax - y * CE) * P

    tube = shared['tube']
    bulb = shared['bulb']
    y_axis = sc.H + COLLAR_H
    step = ss                   # 贴到成品像素网格上，保证各管与前层贴图严丝合缝
    tube_pos = []
    for cx in sc.tubes:
        px, py = to_px(float(cx) + tube['x0'], 0)
        _, py = to_px(0, y_axis)
        X = int(round(px / step)) * step
        Y = int(round((py - tube['y1'] * P) / step)) * step
        over(plate, tube['back'], X, Y)
        over(plate, tube['inner'], X, Y)
        tube_pos.append((X // ss, Y // ss))
    bulb_pos = []
    for cx in sc.colons:
        px, _ = to_px(float(cx) + bulb['x0'], 0)
        _, py = to_px(0, sc.H + FERRULE_H)
        X = int(round(px / step)) * step
        Y = int(round((py - bulb['y1'] * P) / step)) * step
        over(plate, bulb['back'], X, Y)
        over(plate, bulb['inner'], X, Y)
        over(plate, bulb['front'], X, Y)
        bulb_pos.append((X // ss, Y // ss))

    save_rgba(down(plate, ss), os.path.join(outdir, f'plate{n}.png'))
    save_rgba(down(glowimg, ss), os.path.join(outdir, f'glow{n}.png'))

    k = 1.0 / scale             # 成品像素 → CSS 像素
    Pa = R_CSS * scale          # 成品像素 / R
    lay = dict(
        w=Ws // ss * k, h=Hs // ss * k,
        tubes=[dict(x=x * k, y=y * k) for x, y in tube_pos],
        bulbs=[dict(x=x * k, y=y * k) for x, y in bulb_pos],
        knobs=[dict(x=(float(kx) - sc.xmin) * R_CSS, y=(sc.ymax - (sc.knob_y * CE - sc.D / 2 * SE)) * R_CSS, r=0.42 * R_CSS) for kx in sc.knobs],
        plate=dict(x=(0 - sc.xmin) * R_CSS, y=(sc.ymax - (1.12 * CE - sc.D / 2 * SE)) * R_CSS),
        topY=(sc.ymax - sc.H * CE) * R_CSS,
    )
    print(f'  plate{n} done in {time.time() - t0:.1f}s')
    return lay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scale', type=float, default=3.0, help='成品像素 / CSS 像素')
    ap.add_argument('--ss', type=int, default=2, help='超采样倍数')
    ap.add_argument('--only', type=int, default=0)
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    P = R_CSS * a.scale * a.ss

    t0 = time.time()
    g = glass_sprite(P, G_R, G_HB, G_HD, G_TIP, G_TIPR)
    crop = lambda arr: arr[:arr.shape[0] // a.ss * a.ss, :arr.shape[1] // a.ss * a.ss]
    tube = dict(x0=g['x0'], y1=g['y1'], back=crop(g['back']), front=crop(g['front']),
                inner=crop(draw_interior(g, P)), mesh=crop(draw_mesh(g, P)))
    front = tube['mesh'].copy()
    over(front, tube['front'], 0, 0)
    save_rgba(down(front, a.ss), os.path.join(a.out, 'tube-front.png'))
    gb = glass_sprite(P, B_R, B_HB, B_HD, B_TIP, B_TIPR, pad=0.05)
    bulb = dict(x0=gb['x0'], y1=gb['y1'], back=crop(gb['back']), front=crop(gb['front']), inner=crop(draw_bulb_interior(gb, P)))
    print(f'glass + interior in {time.time() - t0:.1f}s')

    shared = dict(tube=tube, bulb=bulb)
    layouts = {}
    for n in (4, 6):
        if a.only and a.only != n:
            continue
        layouts[str(n)] = build(n, a.scale, a.ss, a.out, shared)
    pw, ph = nameplate(a.scale, os.path.join(a.out, 'nameplate.png'))

    k = 1.0 / a.scale
    meta = dict(
        R=R_CSS, scale=a.scale,
        tube=dict(w=tube['front'].shape[1] // a.ss * k, h=tube['front'].shape[0] // a.ss * k,
                  ax=-g['x0'] * R_CSS, ay=g['y1'] * R_CSS),      # 管轴线、管座顶面在贴图内的位置
        bulb=dict(w=bulb['front'].shape[1] // a.ss * k, h=bulb['front'].shape[0] // a.ss * k,
                  ax=-gb['x0'] * R_CSS, ay=gb['y1'] * R_CSS, glowY=0.36 * R_CSS),
        cage={k2: v * R_CSS for k2, v in CAGE.items()},
        digit=dict(cx=DIGIT['cx'] * R_CSS, cy=DIGIT['cy'] * R_CSS, sx=DIGIT['sx'] * R_CSS, sy=DIGIT['sy'] * R_CSS),
        stack=STACK_ORDER,
        nameplate=dict(w=pw * k, h=ph * k),
        layouts=layouts,
    )
    path = os.path.join(a.out, 'layout.js')
    if a.only and os.path.exists(path):          # 只渲染一种时保留另一种的布局
        try:
            old = json.loads(open(path).read().split('=', 1)[1].rstrip().rstrip(';'))
            for kk, vv in old.get('layouts', {}).items():
                meta['layouts'].setdefault(kk, vv)
        except Exception:
            pass
    with open(path, 'w') as fh:
        fh.write('window.NIXIE_LAYOUT = ' + json.dumps(meta, indent=1) + ';\n')
    print(f'all done in {time.time() - t0:.1f}s → {os.path.abspath(a.out)}')


if __name__ == '__main__':
    main()
