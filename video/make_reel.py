"""大嵓埜 北新地 Instagram リール用 PR 動画 (1080x1920 / 30fps / 30秒) を生成する。

使い方:  THEME=settai python3 video/make_reel.py [出力パス]
      THEME: settai (接待・大事な会食) / seats (幅広いお席)
必要: Python3 + Pillow + numpy, ffmpeg
"""
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "images", "src")
FONTS = os.path.join(ROOT, "video", "fonts")
THEME = os.environ.get("THEME", "settai")  # settai | seats
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "video", f"okurano_reel_{THEME}.mp4")

W, H, FPS, DURATION = 1080, 1920, 30, 30.0
GOLD = (201, 168, 106)
WHITE = (250, 246, 238)

MINCHO = os.path.join(FONTS, "ShipporiMincho-500.ttf")
MINCHO_B = os.path.join(FONTS, "ShipporiMincho-700.ttf")
SERIF_EN = os.path.join(FONTS, "Cormorant-500.ttf")


def font(path, size):
    return ImageFont.truetype(path, size)


# ---------------------------------------------------------------- easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_io_cubic(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


# ---------------------------------------------------------------- text layers
def shadowed(layer, radius=10, strength=0.75):
    """RGBA レイヤーに柔らかい影を付ける"""
    a = layer.split()[3]
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(v * strength)))
    return Image.alpha_composite(sh, layer)


ROTATE_IN_VERTICAL = set("ー〜～—…｜")
PUNCT_UPPER_RIGHT = set("、。")


def glyph_tile(ch, fnt, color, cell):
    """縦書き用 1 文字タイル (RGBA, cell x cell + 余白)"""
    pad = 24
    size = cell + pad * 2
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    bbox = d.textbbox((0, 0), ch, font=fnt)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = pad + (cell - gw) / 2 - bbox[0]
    y = pad + (cell - gh) / 2 - bbox[1]
    if ch in PUNCT_UPPER_RIGHT:
        x += cell * 0.32
        y -= cell * 0.32
    d.text((x, y), ch, font=fnt, fill=color + (255,))
    if ch in ROTATE_IN_VERTICAL:
        tile = tile.rotate(-90)
    return shadowed(tile, radius=8, strength=0.85), pad


class VerticalCopy:
    """右上に縦書きのキャッチコピー。1文字ずつふわっと現れる。"""

    def __init__(self, columns, size=78, right=905, top=230, col_gap=1.45, step=1.12):
        fnt = font(MINCHO, size)
        self.chars = []  # (tile, x, y, order)
        order = 0
        for ci, col in enumerate(columns):
            cx = right - ci * size * col_gap
            for ri, ch in enumerate(col):
                if ch == " ":
                    order += 1
                    continue
                tile, pad = glyph_tile(ch, fnt, WHITE, size)
                self.chars.append((tile, int(cx - size / 2 - pad), int(top + ri * size * step - pad), order))
                order += 1
        # 縦の金のヘアライン (コピーの右側)
        self.line_x = int(right + size * 0.85)
        self.line_top = top + 6
        self.line_len = int(max(len(c) for c in columns) * size * step * 0.55)

    def draw(self, frame, t, t_in, t_out, stagger=0.065, fade=0.55):
        """t: シーン内時間, t_in: 表示開始, t_out: 消え始め"""
        out_a = 1 - smooth((t - t_out) / 0.35)
        if out_a <= 0 or t < t_in:
            return
        # 金のライン
        la = smooth((t - t_in) / 0.9) * out_a
        if la > 0:
            d = ImageDraw.Draw(frame, "RGBA")
            d.line([(self.line_x, self.line_top),
                    (self.line_x, self.line_top + int(self.line_len * ease_out((t - t_in) / 1.1)))],
                   fill=GOLD + (int(220 * la),), width=2)
        for tile, x, y, order in self.chars:
            p = (t - t_in - order * stagger) / fade
            if p <= 0:
                continue
            a = smooth(p) * out_a
            dy = int((1 - ease_out(p)) * -18)
            paste_alpha(frame, tile, (x, y + dy), a)


def paste_alpha(frame, tile, pos, a):
    if a <= 0:
        return
    if a < 1:
        tile = tile.copy()
        tile.putalpha(tile.split()[3].point(lambda v: int(v * a)))
    frame.alpha_composite(tile, pos)


def spaced_text_layer(text, fnt, color, tracking=0, shadow=True):
    """字間を空けた横書きテキストのレイヤー"""
    tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [tmp.textlength(c, font=fnt) for c in text]
    tw = int(sum(widths) + tracking * (len(text) - 1))
    asc, desc = fnt.getmetrics()
    pad = 30
    layer = Image.new("RGBA", (tw + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = pad
    for c, w in zip(text, widths):
        d.text((x, pad), c, font=fnt, fill=color + (255,))
        x += w + tracking
    return shadowed(layer, 7, 0.8) if shadow else layer


class Caption:
    """下部の横書きキャプション: 英字ラベル (金) + 金ライン + 日本語"""

    def __init__(self, en, ja, y=1330, ja_size=46):
        self.en = spaced_text_layer(en, font(SERIF_EN, 34), GOLD, tracking=9) if en else None
        self.ja = [spaced_text_layer(line, font(MINCHO, ja_size), WHITE, tracking=4) for line in ja]
        self.y = y
        self.ja_size = ja_size

    def draw(self, frame, t, t_in, t_out):
        out_a = 1 - smooth((t - t_out) / 0.35)
        if out_a <= 0 or t < t_in:
            return
        y = self.y
        if self.en:
            a = smooth((t - t_in) / 0.6) * out_a
            paste_alpha(frame, self.en, ((W - self.en.width) // 2, y - 30), a)
            y += 58
        # 中央から伸びる金ライン
        g = ease_out((t - t_in - 0.15) / 0.9)
        half = int(150 * g)
        if half > 0:
            ImageDraw.Draw(frame, "RGBA").line([(W // 2 - half, y + 16), (W // 2 + half, y + 16)],
                                               fill=GOLD + (int(210 * out_a),), width=2)
        y += 34
        for i, layer in enumerate(self.ja):
            p = (t - t_in - 0.35 - i * 0.18) / 0.6
            if p > 0:
                dy = int((1 - ease_out(p)) * 14)
                paste_alpha(frame, layer, ((W - layer.width) // 2, y - 30 + dy), smooth(p) * out_a)
            y += int(self.ja_size * 1.55)


# ---------------------------------------------------------------- image scenes
VIGNETTE = None


def vignette():
    global VIGNETTE
    if VIGNETTE is None:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
        v = 1 - 0.55 * np.clip(r - 0.45, 0, 1) ** 1.6
        # 上下に薄い暗幕 (テロップの可読性)
        top = 1 - 0.35 * np.clip(1 - yy / 700, 0, 1) ** 2
        bot = 1 - 0.6 * np.clip((yy - 1000) / 520, 0, 1) ** 1.2
        # 右側 (縦書きコピーの位置) を少し落とす
        side = 1 - 0.38 * np.clip((xx - 560) / 520, 0, 1) * np.clip(1 - (yy - 1150) / 300, 0, 1)
        VIGNETTE = (v * top * bot * side)[..., None]
    return VIGNETTE


class Scene:
    def __init__(self, fname, start, end, fx=(0.5, 0.5), fy=0.5, zoom=(1.0, 1.07),
                 copy=None, caption=None, darken=0.0):
        im = Image.open(os.path.join(SRC, fname)).convert("RGB")
        # 縦画面を覆う高さにリサイズ (最大ズーム分の余裕込み)
        scale = H * 1.12 / im.height
        if im.width * scale < W * 1.3:
            scale = W * 1.3 / im.width
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
        self.img = im
        self.start, self.end = start, end
        self.fx, self.fy, self.zoom = fx, fy, zoom
        self.copy, self.caption = copy, caption
        self.darken = darken

    @property
    def dur(self):
        return self.end - self.start

    def base(self, t):
        """パン＆ズーム済みの写真 (PIL RGB)"""
        p = clamp(t / self.dur)
        z = self.zoom[0] + (self.zoom[1] - self.zoom[0]) * p
        fx = self.fx[0] + (self.fx[1] - self.fx[0]) * smooth(p * 0.9 + 0.05)
        iw, ih = self.img.size
        f = max(W / iw, H / ih) * z  # 出力1pxあたりの画像倍率
        cw, ch = W / f, H / f
        cx = clamp(fx * iw, cw / 2, iw - cw / 2)
        cy = clamp(self.fy * ih, ch / 2, ih - ch / 2)
        sx, sy = cw / W, ch / H
        return self.img.transform((W, H), Image.AFFINE,
                                  (sx, 0, cx - cw / 2, 0, sy, cy - ch / 2), resample=Image.BILINEAR)

    def frame(self, t):
        arr = np.asarray(self.base(t), dtype=np.float32)
        arr = arr * vignette() * (1 - self.darken)
        # ほんのり温かみのあるグレーディング
        arr[..., 0] *= 1.03
        arr[..., 2] *= 0.95
        fr = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")
        self.overlay(fr, t)
        return fr

    def overlay(self, fr, t):
        t_out = self.dur - 0.95
        if self.copy:
            self.copy.draw(fr, t, 0.55, t_out)
        if self.caption:
            self.caption.draw(fr, t, 1.1, t_out)


class OpeningScene(Scene):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.l_small = spaced_text_layer("北新地 ・ 懐石料理", font(MINCHO, 40), WHITE, tracking=10)
        self.l_logo = spaced_text_layer("大嵓埜", font(MINCHO_B, 150), WHITE, tracking=40)
        self.l_en = spaced_text_layer("OKURANO", font(SERIF_EN, 40), GOLD, tracking=18)

    def frame(self, t):
        fr = super().frame(t)
        # 黒からフェードイン
        fade = smooth(t / 0.9)
        if fade < 1:
            black = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - fade))))
            fr = Image.alpha_composite(fr, black)
        return fr

    def overlay(self, fr, t):
        out_a = 1 - smooth((t - (self.dur - 0.95)) / 0.35)
        if out_a <= 0:
            return
        cy = 860
        a1 = smooth((t - 0.5) / 0.7) * out_a
        paste_alpha(fr, self.l_small, ((W - self.l_small.width) // 2, cy - 185), a1)
        # 大嵓埜: 字間が広がりながら現れる
        p = (t - 0.8) / 1.1
        if p > 0:
            a = smooth(p) * out_a
            layer = self.l_logo
            s = 1.08 - 0.08 * ease_out(p)
            lw, lh = int(layer.width * s), int(layer.height * s)
            paste_alpha(fr, layer.resize((lw, lh), Image.LANCZOS), ((W - lw) // 2, cy - lh // 2), a)
        g = ease_out((t - 1.2) / 1.0)
        half = int(170 * g)
        if half > 0:
            ImageDraw.Draw(fr, "RGBA").line([(W // 2 - half, cy + 110), (W // 2 + half, cy + 110)],
                                            fill=GOLD + (int(220 * out_a),), width=2)
        a3 = smooth((t - 1.5) / 0.7) * out_a
        paste_alpha(fr, self.l_en, ((W - self.l_en.width) // 2, cy + 130), a3)


class EndingScene(Scene):
    END_AT = 3.0  # シーン内でエンドカードが出始める時間

    def __init__(self, *a, lead=("おふたり様から八名様まで", "カウンター ・ 個室五室 ・ 全三十六席"), **k):
        super().__init__(*a, **k)
        mk = spaced_text_layer
        self.items = [  # (layer, y, delay)
            (mk("ミシュランガイド 2024–2026 掲載", font(MINCHO, 34), GOLD, tracking=4), 470, 0.0),
            (mk("北新地 ・ 懐石料理", font(MINCHO, 40), WHITE, tracking=10), 610, 0.15),
            (mk("大嵓埜", font(MINCHO_B, 140), WHITE, tracking=36), 730, 0.3),
            (mk("OKURANO", font(SERIF_EN, 38), GOLD, tracking=18), 870, 0.45),
            (mk(lead[0], font(MINCHO, 46), WHITE, tracking=4), 1010, 0.7),
            (mk(lead[1], font(MINCHO, 38), WHITE, tracking=3), 1080, 0.85),
            (mk("ご予約  06-6341-3535", font(MINCHO, 40), WHITE, tracking=3), 1230, 1.1),
            (mk("Web予約 24時間受付", font(MINCHO, 34), WHITE, tracking=3), 1295, 1.2),
            (mk("JR北新地駅 徒歩2分", font(MINCHO, 34), GOLD, tracking=3), 1355, 1.3),
        ]

    def overlay(self, fr, t):
        te = t - self.END_AT
        if te < 0:
            # 前半: 通常の縦書きコピー
            if self.copy:
                self.copy.draw(fr, t, 0.55, self.END_AT - 0.45)
            return
        d = smooth(te / 0.8)
        fr.alpha_composite(Image.new("RGBA", (W, H), (12, 9, 6, int(175 * d))))
        dr = ImageDraw.Draw(fr, "RGBA")
        # 上下の金の細枠
        g = ease_out((te - 0.2) / 1.2)
        if g > 0:
            m = 90
            dr.rectangle([m, 380, W - m, 1470], outline=GOLD + (int(150 * g),), width=1)
            dr.rectangle([m + 10, 390, W - m - 10, 1460], outline=GOLD + (int(90 * g),), width=1)
        lg = ease_out((te - 0.6) / 0.8)
        if lg > 0:
            for yy in (955, 1165):
                half = int(120 * lg)
                dr.line([(W // 2 - half, yy), (W // 2 + half, yy)], fill=GOLD + (200,), width=2)
        for layer, y, delay in self.items:
            p = (te - 0.25 - delay) / 0.6
            if p > 0:
                dy = int((1 - ease_out(p)) * 16)
                paste_alpha(fr, layer, ((W - layer.width) // 2, y - layer.height // 2 + dy), smooth(p))


# ---------------------------------------------------------------- transitions
def to_np(im):
    return np.asarray(im.convert("RGB"), dtype=np.float32)


YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)


def mix(a, b, m):
    return a * (1 - m) + b * m


def tr_blur(A, B, p):
    r = math.sin(math.pi * p) * 16
    if r > 0.5:
        A = A.filter(ImageFilter.GaussianBlur(r))
        B = B.filter(ImageFilter.GaussianBlur(r))
    return mix(to_np(A), to_np(B), smooth(p))


def tr_shoji(A, B, p):
    """襖が左右に開いて次の部屋が現れる"""
    e = ease_io_cubic(p)
    b = to_np(B) * (0.75 + 0.25 * e)
    a = to_np(A)
    out = b.copy()
    off = int(e * W / 2)
    half = W // 2
    if off < half:
        out[:, : half - off] = a[:, off:half]
        out[:, half + off:] = a[:, half:W - off]
        # 襖の縁の影と金の縁取り
        for edge, sgn in ((half - off, 1), (half + off, -1)):
            for k in range(28):
                x = edge + sgn * k
                if 0 <= x < W:
                    out[:, x] *= 1 - 0.5 * (1 - k / 28) * (1 - e)
            x = edge - (1 if sgn > 0 else 0)
            if 0 <= x < W:
                out[:, x] = mix(out[:, x], np.array(GOLD, np.float32), 0.8)
    return out


def tr_wipe_down(A, B, p):
    e = ease_io_cubic(p)
    edge = -200 + e * (H + 400)
    m = np.clip((edge - YY) / 200 + 0.5, 0, 1)[..., None]
    out = mix(to_np(A), to_np(B), m)
    line = np.exp(-((YY - edge) / 3.0) ** 2)[..., None] * 0.9
    return mix(out, np.array(GOLD, np.float32), line)


def tr_circle(A, B, p):
    e = ease_io_cubic(p)
    rmax = math.hypot(W, H) / 2 + 100
    r = e * rmax
    dist = np.sqrt((XX - W / 2) ** 2 + (YY - H * 0.48) ** 2)
    m = np.clip((r - dist) / 90 + 0.5, 0, 1)[..., None]
    out = mix(to_np(A), to_np(B), m)
    ring = np.exp(-((dist - r) / 4.0) ** 2)[..., None] * 0.85 * math.sin(math.pi * p)
    return mix(out, np.array(GOLD, np.float32), ring)


def tr_light(A, B, p):
    warm = np.array((255, 236, 205), np.float32)
    if p < 0.5:
        k = smooth(p / 0.5) * 0.88
        return mix(to_np(A), warm, k)
    k = (1 - smooth((p - 0.5) / 0.5)) * 0.88
    return mix(to_np(B), warm, k)


def tr_zoom(A, B, p):
    e = ease_io_cubic(p)
    s = 1 + 0.25 * e
    aw, ah = int(W * s), int(H * s)
    Az = A.resize((aw, ah), Image.BILINEAR).crop(((aw - W) // 2, (ah - H) // 2, (aw - W) // 2 + W, (ah - H) // 2 + H))
    Az = Az.filter(ImageFilter.GaussianBlur(e * 6)) if e > 0.05 else Az
    return mix(to_np(Az), to_np(B), smooth(p))


def tr_diag(A, B, p):
    e = ease_io_cubic(p)
    proj = (XX * 0.7 + YY * 0.4)
    lo, hi = -250, W * 0.7 + H * 0.4 + 250
    edge = lo + e * (hi - lo)
    m = np.clip((edge - proj) / 220 + 0.5, 0, 1)[..., None]
    out = mix(to_np(A), to_np(B), m)
    line = np.exp(-((proj - edge) / 2.5) ** 2)[..., None] * 0.8
    return mix(out, np.array(GOLD, np.float32), line)


# ---------------------------------------------------------------- timeline
def build(theme):
    V, C = VerticalCopy, Caption
    opening = OpeningScene("intro-slide1-min.png", 0.0, 4.0, fx=(0.30, 0.58), fy=0.55, zoom=(1.0, 1.08), darken=0.38)
    if theme == "seats":  # 幅広いお席に対応
        S = [
            opening,
            Scene("concept-thumb1.jpg", 3.3, 7.3, fx=(0.56, 0.64), fy=0.55, zoom=(1.05, 1.0),
                  copy=V(["目の前で、職人の手仕事を"]),
                  caption=C("COUNTER", ["カウンター　8席"])),
            Scene("scene-gallery1-min.jpg", 6.6, 10.6, fx=(0.62, 0.50), zoom=(1.0, 1.06),
                  copy=V(["大切な方と、", "ふたりの時間"]),
                  caption=C("PRIVATE ROOM", ["個室「寂」　2〜4名様"])),
            Scene("scene-gallery3-min.jpg", 9.9, 13.9, fx=(0.38, 0.50), zoom=(1.06, 1.0),
                  copy=V(["ご接待や", "ご会食の席にも"]),
                  caption=C("PRIVATE ROOM", ["個室「清」「啓」「和」　2〜6名様"])),
            Scene("scene-thumb1-min.jpg", 13.2, 17.2, fx=(0.48, 0.60), zoom=(1.0, 1.07),
                  copy=V(["ご両家の、", "晴れの日に"]),
                  caption=C("FOR CELEBRATIONS", ["個室「玄」　6〜8名様", "お顔合わせ ・ ご結納に"])),
            Scene("concept-thumb2-min.jpg", 16.5, 20.5, fx=(0.42, 0.50), fy=0.5, zoom=(1.0, 1.1),
                  copy=V(["心を尽くした、", "おもてなし"]),
                  caption=C("HOSPITALITY", ["記念日 ・ お祝いの席に"])),
            Scene("intro-slide2-min.jpg", 19.8, 23.8, fx=(0.56, 0.42), fy=0.55, zoom=(1.08, 1.0),
                  copy=V(["お昼の会食から、", "特別な夜まで"]),
                  caption=C("KAISEKI", ["ランチ ・ ディナー"])),
            EndingScene("scene-gallery6-min.jpg", 23.1, 30.0, fx=(0.35, 0.55), zoom=(1.0, 1.1),
                        copy=V(["幅広いお席で、", "お待ちしております"])),
        ]
    else:  # settai: 間違いのない接待・大事な会食に
        S = [
            opening,
            Scene("concept-thumb2-min.jpg", 3.3, 7.3, fx=(0.40, 0.50), fy=0.5, zoom=(1.0, 1.1),
                  copy=V(["大切なお客様を、", "心を尽くして"]),
                  caption=C("HOSPITALITY", ["ご接待 ・ ご会食の席に"])),
            Scene("scene-gallery4-min.jpg", 6.6, 10.6, fx=(0.40, 0.52), zoom=(1.06, 1.0),
                  copy=V(["人目を気にせず、", "落ち着いた個室で"]),
                  caption=C("PRIVATE ROOM", ["個室「清」「啓」「和」　2〜6名様"])),
            Scene("concept-thumb1.jpg", 9.9, 13.9, fx=(0.56, 0.64), fy=0.55, zoom=(1.05, 1.0),
                  copy=V(["旬を見極める、", "職人の技"]),
                  caption=C("CRAFTSMANSHIP", ["茶の湯の心を受け継ぐ懐石"])),
            Scene("intro-slide2-min.jpg", 13.2, 17.2, fx=(0.56, 0.42), fy=0.55, zoom=(1.08, 1.0),
                  copy=V(["話題の尽きない、", "季節のひと皿"]),
                  caption=C("KAISEKI", ["月替わりの懐石コース"])),
            Scene("scene-thumb1-min.jpg", 16.5, 20.5, fx=(0.48, 0.60), zoom=(1.0, 1.07),
                  copy=V(["大人数の会食も、", "格式ある席で"]),
                  caption=C("PRIVATE ROOM", ["個室「玄」　6〜8名様"])),
            Scene("scene-gallery6-min.jpg", 19.8, 23.8, fx=(0.35, 0.50), zoom=(1.0, 1.06),
                  copy=V(["間違いのない、", "おもてなしを"]),
                  caption=C("MICHELIN GUIDE", ["ミシュランガイド", "2024–2026 掲載"])),
            EndingScene("scene-gallery3-min.jpg", 23.1, 30.0, fx=(0.38, 0.50), zoom=(1.0, 1.1),
                        copy=V(["大事な会食は、", "大嵓埜で"]),
                        lead=("ご接待 ・ ご会食 ・ 商談の席に", "個室五室 ・ カウンター八席")),
        ]
    T = [tr_blur, tr_shoji, tr_wipe_down, tr_circle, tr_light, tr_zoom, tr_diag]
    return S, T


def render_frame(S, T, t):
    for i, s in enumerate(S):
        nxt = S[i + 1] if i + 1 < len(S) else None
        if nxt and t >= nxt.start:
            if t < s.end:  # 遷移中
                p = (t - nxt.start) / (s.end - nxt.start)
                A = s.frame(t - s.start).convert("RGB")
                B = nxt.frame(t - nxt.start).convert("RGB")
                return np.clip(T[i](A, B, p), 0, 255).astype(np.uint8)
            continue
        if s.start <= t:
            return np.asarray(s.frame(t - s.start).convert("RGB"))
    return np.zeros((H, W, 3), np.uint8)


def main():
    S, T = build(THEME)
    total = int(DURATION * FPS)
    if os.environ.get("PREVIEW"):  # PREVIEW="1.0,5.2" で静止画だけ書き出す
        for ts in os.environ["PREVIEW"].split(","):
            Image.fromarray(render_frame(S, T, float(ts))).save(f"{os.path.splitext(OUT)[0]}_{ts}.jpg", quality=88)
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-map", "0:v", "-map", "1:a", "-shortest",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "128k", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(total):
        proc.stdin.write(render_frame(S, T, n / FPS).tobytes())
        if n % 60 == 0:
            print(f"{n}/{total}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done:", OUT)


if __name__ == "__main__":
    main()
