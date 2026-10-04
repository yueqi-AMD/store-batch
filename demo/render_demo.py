# -*- coding: utf-8 -*-
"""render_demo.py — 程序化渲染 3 分钟脱敏演示视频（1920x1080, 12fps, 180s）。

用真实 card.py 产出的脱敏卡片 + 拟真运行日志，逐帧渲染为 H.264 MP4。
用法:
    python render_demo.py --preview   # 抽样帧到 preview/ 供检查
    python render_demo.py --render    # 完整渲染到 out/
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PREVIEW = ROOT / "preview"
OUT = ROOT / "out"

W, H = 1920, 1080
FPS = 12
DUR = 113.0
FADE = 0.4

F_REG = "C:/Windows/Fonts/msyh.ttc"
F_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
F_LIGHT = "C:/Windows/Fonts/msyhl.ttc"
F_MONO = "C:/Windows/Fonts/consola.ttf"

BG = (11, 15, 20)
PANEL = (22, 27, 34)
PANEL2 = (28, 33, 40)
BORDER = (48, 54, 61)
FG = (230, 237, 243)
MUTED = (139, 148, 158)
DIM = (96, 104, 115)
BLUE = (64, 120, 255)
GREEN = (63, 185, 80)
RED = (248, 81, 73)
YELLOW = (212, 160, 23)
BLACK = (0, 0, 0)

_STORES = [
    ("DM-001", "演示中心店", "王小明"),
    ("DM-002", "演示广场店", "李华"),
    ("DM-003", "演示社区店", "张伟"),
    ("DM-004", "演示新区店", "刘洋"),
    ("DM-005", "演示湖畔店", "陈静"),
    ("DM-006", "演示老街店", "赵磊"),
]
_STORE_NAME = {s[0]: s[1] for s in _STORES}

_fc = {}


def font(size, bold=False, mono=False, light=False):
    key = (size, bold, mono, light)
    if key not in _fc:
        if mono:
            path = F_MONO
        elif bold:
            path = F_BOLD
        elif light:
            path = F_LIGHT
        else:
            path = F_REG
        _fc[key] = ImageFont.truetype(path, size)
    return _fc[key]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def bg_image():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        c = (int(13 - 4 * k), int(18 - 5 * k), int(24 - 6 * k))
        d.line([(0, y), (W, y)], fill=c)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    do = ImageDraw.Draw(ov)
    do.ellipse((-400, -500, 1100, 500), fill=(64, 120, 255, 18))
    do.ellipse((1300, 700, 2400, 1500), fill=(64, 120, 255, 10))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


BGIMG = None


def draw_text(img, xy, s, size, color, bold=False, mono=False, anchor=None,
              alpha=1.0, light=False):
    if alpha >= 1.0:
        ImageDraw.Draw(img).text(xy, s, font=font(size, bold, mono, light),
                                 fill=color, anchor=anchor)
        return
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(ov).text(xy, s, font=font(size, bold, mono, light),
                            fill=color + (int(255 * max(0.0, min(1.0, alpha))),),
                            anchor=anchor)
    img.alpha_composite(ov)


def draw_text_rgba(img, xy, s, fnt, color, alpha=1.0, anchor=None):
    if alpha >= 1.0:
        ImageDraw.Draw(img).text(xy, s, font=fnt, fill=color, anchor=anchor)
    else:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).text(xy, s, font=fnt,
                                fill=color + (int(255 * max(0.0, min(1.0, alpha))),),
                                anchor=anchor)
        img.alpha_composite(ov)


def panel(d, box, r=16, fill=PANEL, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def wrap_cjk(d, s, fnt, max_w):
    lines, cur = [], ""
    for ch in s:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if d.textlength(cur + ch, font=fnt) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def check_mark(d, cx, cy, size, color, width=8):
    d.line([(cx - size * 0.42, cy + size * 0.02),
            (cx - size * 0.10, cy + size * 0.34)], fill=color, width=width)
    d.line([(cx - size * 0.10, cy + size * 0.34),
            (cx + size * 0.44, cy - size * 0.30)], fill=color, width=width)


def scene_title(img, title, accent=BLUE):
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((80, 108, 90, 166), radius=5, fill=accent)
    d.text((116, 106), title, font=font(46, bold=True), fill=FG)


def watermark(img):
    d = ImageDraw.Draw(img)
    txt = "脱敏演示 · 虚构数据"
    w = d.textlength(txt, font=font(20))
    d.text((W - 36 - w, H - 40), txt, font=font(20), fill=(70, 76, 85))


# ---------------------------------------------------------------- scenes
def scene0(t):
    """标题 0-15s"""
    img = BGIMG.copy().convert("RGBA")
    badge_a = ease(t / 0.4)
    bx0, bx1, by0, by1 = W // 2 - 110, W // 2 + 110, 286, 342
    if badge_a > 0:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((bx0, by0, bx1, by1), radius=28,
                             outline=BLUE + (int(255 * badge_a),), width=2)
        img.alpha_composite(ov)
        draw_text(img, (W // 2, by0 + 27), "系 统 演 示", 28, BLUE,
                  alpha=badge_a, anchor="mm")

    a1 = ease((t - 0.4) / 0.5)
    draw_text(img, (W // 2, 452), "门店运营跟进自动化系统", 92, FG,
              bold=True, alpha=a1, anchor="mm")
    a2 = ease((t - 1.1) / 0.5)
    draw_text(img, (W // 2, 552), "飞书多维表格 × 企业微信 · 全流程无人值守", 34,
              MUTED, alpha=a2, anchor="mm")

    chips = [("1 分钟 / 店", BLUE), ("30 家 / 批", GREEN), ("三重校验 · 绝不发错人", YELLOW)]
    wsum = sum(ImageDraw.Draw(img).textlength(s, font=font(28)) + 72 for s, _ in chips)
    x = (W - wsum - 40 * (len(chips) - 1)) / 2
    for i, (s, c) in enumerate(chips):
        a = ease((t - 2.0 - i * 0.35) / 0.4)
        if a <= 0:
            x += ImageDraw.Draw(img).textlength(s, font=font(28)) + 72 + 40
            continue
        wd = ImageDraw.Draw(img).textlength(s, font=font(28)) + 72
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((x, 660, x + wd, 716), radius=28,
                             fill=c + (int(20 * a),), outline=c + (int(160 * a),), width=2)
        img.alpha_composite(ov)
        draw_text(img, (x + wd / 2, 688), s, 28, c, alpha=a, anchor="mm")
        x += wd + 40

    a3 = ease((t - 4.0) / 0.5)
    draw_text(img, (W // 2, 820), "本视频为脱敏演示 · 全部数据为虚构", 24, DIM,
              alpha=a3, anchor="mm")
    return img.convert("RGB")


def scene1(t):
    """痛点 15-40s"""
    img = BGIMG.copy().convert("RGBA")
    scene_title(img, "传统人工流程", RED)
    rows = [
        "逐店查看 20 项经营指标（流量 / 转化 / 交易 / 评价）",
        "手工整理数据、制作每店数据图",
        "企业微信逐层搜索门店 → 定位店长 → 私聊发送",
        "截取会话截图 → 回飞书逐条上传 → 手工登记时间",
    ]
    d0 = ImageDraw.Draw(img)
    for i, s in enumerate(rows):
        a = ease((t - 0.7 - i * 1.4) / 0.5)
        if a <= 0:
            continue
        x0 = 120 - (1 - a) * 50
        y0 = 250 + i * 165
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((x0, y0, x0 + 1680, y0 + 132), radius=18,
                             fill=PANEL2 + (int(255 * a),), outline=BORDER + (int(255 * a),), width=1)
        do.ellipse((x0 + 36, y0 + 32, x0 + 104, y0 + 100),
                   outline=RED + (int(220 * a),), width=3)
        img.alpha_composite(ov)
        draw_text(img, (x0 + 70, y0 + 66), str(i + 1), 36, RED, bold=True,
                  alpha=a, anchor="mm")
        draw_text(img, (x0 + 140, y0 + 66), s, 30, FG, alpha=a, anchor="lm")

    a = ease((t - 6.5) / 0.5)
    if a > 0:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((120, 930, 1800, 1010), radius=18,
                             fill=(46, 22, 24, int(255 * a)), outline=RED + (int(200 * a),), width=2)
        img.alpha_composite(ov)
        draw_text(img, (W // 2, 970), "单店 10+ 步 · 数百家门店反复执行 · 易错发 · 无留痕",
                  30, RED, alpha=a, anchor="mm")
    return img.convert("RGB")


def scene2(t):
    """流程 40-65s"""
    img = BGIMG.copy().convert("RGBA")
    scene_title(img, "系统流程 · 全流程代码化")
    nodes = [
        ("1", "飞书多维表格", "数据源（只读指定表）"),
        ("2", "智能筛选", "四级优先级 T1 → T4"),
        ("3", "卡片生成", "一店一图 · 20 项指标"),
        ("4", "企微触达", "OCR 三重身份校验"),
        ("5", "截图回传", "自动归档 · 全量留痕"),
        ("6", "状态管理", "幂等 · 断点续跑"),
    ]
    nw, gap, y0, nh = 270, 42, 430, 190
    x0 = (W - (len(nodes) * nw + (len(nodes) - 1) * gap)) / 2
    for i, (num, title, sub) in enumerate(nodes):
        a = ease((t - 0.3 - i * 0.85) / 0.4)
        if a <= 0:
            continue
        x = x0 + i * (nw + gap)
        y = y0 + (1 - a) * 26
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((x, y, x + nw, y + nh), radius=18,
                             fill=PANEL2 + (int(255 * a),), outline=BLUE + (int(120 * a),), width=2)
        img.alpha_composite(ov)
        draw_text(img, (x + nw / 2, y + 52), num, 30, BLUE, bold=True,
                  alpha=a, anchor="mm")
        draw_text(img, (x + nw / 2, y + 102), title, 30, FG, bold=True,
                  alpha=a, anchor="mm")
        draw_text(img, (x + nw / 2, y + 148), sub, 20, MUTED, alpha=a, anchor="mm")
        if i < len(nodes) - 1:
            aa = ease((t - 0.75 - i * 0.85) / 0.3)
            if aa > 0:
                draw_text(img, (x + nw + gap / 2, y + nh / 2), "→", 40, BLUE,
                          alpha=aa, anchor="mm")

    a = ease((t - 6.0) / 0.5)
    if a > 0:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        pw = 760
        do.rounded_rectangle((W / 2 - pw / 2, 760, W / 2 + pw / 2, 824), radius=32,
                             fill=(20, 31, 51, int(255 * a)), outline=BLUE + (int(180 * a),), width=2)
        img.alpha_composite(ov)
        draw_text(img, (W // 2, 792), "一批 30 家 · 一批不跨优先级 · 系统吞吐 1 分钟 / 店",
                  28, BLUE, alpha=a, anchor="mm")
    return img.convert("RGB")


LOG = [
    (0.3, "head", "目标字段=跟进截图  本批=30  待处理=214  跳过=87\n当前优先级=T1 直营店·不达标", None),
    (1.5, "fg", "[1/30] 开始: 演示中心店 -> 王小明", "DM-001"),
    (2.2, "fg", "卡片已生成: DM-001.png", None),
    (2.9, "fg", "已打开会话: 王小明 (演示中心店)", None),
    (3.6, "ok", "文字已发送", None),
    (4.4, "ok", "图片已发送", None),
    (5.1, "mut", "会话截图: shots/chat/0930/演示中心店.png", None),
    (5.8, "blue", "已上传到 跟进截图", None),
    (6.4, "mut", "已清理本地图片 4 个（飞书已保留）", None),
    (7.2, "fg", "[2/30] 开始: 演示广场店 -> 李华", "DM-002"),
    (7.9, "fg", "卡片已生成: DM-002.png", None),
    (8.6, "fg", "已打开会话: 李华 (演示广场店)", None),
    (9.3, "ok", "文字已发送", None),
    (10.1, "ok", "图片已发送", None),
    (10.8, "mut", "会话截图: shots/chat/0930/演示广场店.png", None),
    (11.5, "blue", "已上传到 跟进截图", None),
    (12.1, "mut", "已清理本地图片 4 个（飞书已保留）", None),
    (12.9, "fg", "[3/30] 开始: 演示社区店 -> 张伟", "DM-003"),
    (13.6, "fg", "卡片已生成: DM-003.png", None),
    (14.3, "fg", "已打开会话: 张伟 (演示社区店)", None),
    (15.0, "ok", "文字已发送", None),
    (15.8, "ok", "图片已发送", None),
    (16.5, "mut", "会话截图: shots/chat/0930/演示社区店.png", None),
    (17.2, "blue", "已上传到 跟进截图", None),
    (17.8, "mut", "已清理本地图片 4 个（飞书已保留）", None),
    (18.6, "fg", "[4/30] 开始: 演示新区店 -> 刘洋", "DM-004"),
    (19.3, "fg", "卡片已生成: DM-004.png", None),
    (20.0, "fg", "已打开会话: 刘洋 (演示新区店)", None),
    (20.6, "ok", "文字已发送", None),
    (21.0, "warn", "[暂停键] 已暂停（Ctrl+Z 继续）", None),
    (22.5, "warn", "已暂停：演示新区店 未完成，恢复后将重试", None),
    (24.0, "warn", "[暂停键] 已恢复运行（Ctrl+Z 可再次暂停）", None),
    (24.6, "fg", "[4/30] 开始: 演示新区店 -> 刘洋", "DM-004"),
    (25.2, "fg", "卡片已生成: DM-004.png", None),
    (25.8, "fg", "已打开会话: 刘洋 (演示新区店)", None),
    (26.4, "warn", "检测到文字已发送标记，跳过重发文字", None),
    (27.1, "ok", "图片已发送", None),
    (27.7, "mut", "会话截图: shots/chat/0930/演示新区店.png", None),
    (28.3, "blue", "已上传到 跟进截图", None),
    (28.9, "mut", "已清理本地图片 4 个（飞书已保留）", None),
    (29.7, "fg", "[5/30] 开始: 演示湖畔店 -> 陈静", "DM-005"),
    (30.4, "fg", "卡片已生成: DM-005.png", None),
    (31.0, "fg", "已打开会话: 陈静 (演示湖畔店)", None),
    (31.6, "ok", "文字已发送", None),
    (32.3, "ok", "图片已发送", None),
    (32.9, "mut", "会话截图: shots/chat/0930/演示湖畔店.png", None),
    (33.5, "blue", "已上传到 跟进截图", None),
    (34.1, "mut", "已清理本地图片 4 个（飞书已保留）", None),
    (34.9, "fg", "[6/30] 开始: 演示老街店 -> 赵磊", "DM-006"),
    (35.6, "fg", "卡片已生成: DM-006.png", None),
    (36.3, "err", "失败: 演示老街店 -> 通讯录未搜到门店部门 (OCR为空)", None),
    (38.0, "mut", "失败门店已隔离并保留证据，不影响批次继续", None),
    (39.5, "mut", "（演示节选 · 实际将循环执行至本批 30 家完成）", None),
]

LOG_COLOR = {
    "head": FG, "fg": FG, "mut": MUTED, "ok": GREEN,
    "blue": BLUE, "warn": YELLOW, "err": RED,
}


def scene3(t):
    """运行日志 65-115s (50s)"""
    img = BGIMG.copy().convert("RGBA")
    scene_title(img, "运行演示（节选）")

    # 终端面板
    tx0, ty0, tx1, ty1 = 60, 180, 1180, 1020
    d = ImageDraw.Draw(img)
    panel(d, (tx0, ty0, tx1, ty1), r=16, fill=PANEL, outline=BORDER, width=1)
    d.line([(tx0, ty0 + 54), (tx1, ty0 + 54)], fill=BORDER, width=1)
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        d.ellipse((tx0 + 24 + i * 30, ty0 + 20, tx0 + 40 + i * 30, ty0 + 36), fill=c)
    d.text((tx0 + 130, ty0 + 15), "store-batch · 运行日志（演示）",
           font=font(22), fill=MUTED)

    paused = 21.0 <= t < 24.0
    if paused:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((tx1 - 190, ty0 + 12, tx1 - 24, ty0 + 44), radius=16,
                             fill=(60, 48, 10, 220), outline=YELLOW, width=2)
        img.alpha_composite(ov)
        draw_text(img, (tx1 - 107, ty0 + 28), "已暂停", 22, YELLOW, anchor="mm")

    ts_font = font(21, mono=True)
    msg_font = font(25)
    line_h = 38
    inner_x = tx0 + 30
    inner_top = ty0 + 72
    inner_bottom = ty1 - 24
    max_rows = int((inner_bottom - inner_top) / line_h) - 1
    msg_w = tx1 - tx0 - 60 - 130

    rows = []
    for idx, (lt, tag, msg, card) in enumerate(LOG):
        if lt > t:
            break
        lines = wrap_cjk(d, msg, msg_font, msg_w)
        for j, ln in enumerate(lines):
            rows.append((lt, tag, ln, j, card))

    visible = rows[-max_rows:]
    if len(visible) < max_rows:
        y = inner_top + 8
    else:
        y = inner_bottom - line_h * max_rows + 8
    last_y = y
    for (lt, tag, ln, j, card) in visible:
        secs = int(round(lt))
        ts = f"09:{30 + secs // 60:02d}:{secs % 60:02d}"
        color = LOG_COLOR[tag]
        if j == 0:
            draw_text_rgba(img, (inner_x, y), ts, ts_font, DIM, anchor="lm")
        draw_text_rgba(img, (inner_x + 128, y), ln, msg_font, color, anchor="lm")
        last_y = y
        y += line_h
    if visible and (t - visible[-1][0]) < 0.8 and int(t * 2) % 2 == 0:
        last = visible[-1]
        w = d.textlength(last[2], font=msg_font)
        ImageDraw.Draw(img).rectangle((inner_x + 128 + w + 6, last_y - 12,
                                       inner_x + 128 + w + 22, last_y + 12), fill=MUTED)

    # 右侧状态面板
    rx0, ry0, rx1, ry1 = 1220, 180, 1860, 1020
    panel(d, (rx0, ry0, rx1, ry1), r=16, fill=PANEL, outline=BORDER, width=1)
    d.text((rx0 + 30, ry0 + 24), "当前门店", font=font(22), fill=MUTED)

    cur_card = None
    cur_name = None
    for (lt, tag, msg, card) in LOG:
        if lt <= t and card:
            cur_card, cur_name = card, _STORE_NAME[card]

    succ = sum(1 for (lt, tag, msg, c) in LOG if tag == "mut" and msg.startswith("已清理") and lt <= t)
    fail = sum(1 for (lt, tag, msg, c) in LOG if tag == "err" and lt <= t)
    done = succ + fail

    if cur_card:
        d.text((rx0 + 30, ry0 + 62), f"{cur_name}", font=font(32, bold=True), fill=FG)
        d.text((rx0 + 30 + d.textlength(cur_name, font=font(32, bold=True)) + 16,
                ry0 + 70), f"({cur_card})", font=font(22), fill=DIM)
        card_img = _card_cache.get(cur_card)
        if card_img:
            cw, ch = card_img.size
            box_w, box_h = rx1 - rx0 - 60, 480
            sc = min(box_w / cw, box_h / ch)
            cim = card_img.resize((int(cw * sc), int(ch * sc)), Image.LANCZOS)
            cx = rx0 + 30 + (box_w - cim.size[0]) // 2
            cy = ry0 + 116 + (box_h - cim.size[1]) // 2
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            do = ImageDraw.Draw(ov)
            do.rounded_rectangle((cx - 8, cy - 8, cx + cim.size[0] + 8, cy + cim.size[1] + 8),
                                 radius=10, fill=(255, 255, 255, 255))
            img.alpha_composite(ov)
            img.paste(cim, (cx, cy))

    d.text((rx0 + 30, ry0 + 640), "批次进度", font=font(22), fill=MUTED)
    d.text((rx1 - 30 - d.textlength(f"{done} / 30", font=font(24, bold=True)), ry0 + 638),
           f"{done} / 30", font=font(24, bold=True), fill=FG)
    d.rounded_rectangle((rx0 + 30, ry0 + 684, rx1 - 30, ry0 + 712), radius=14, fill=BORDER)
    if done > 0:
        wfill = (rx1 - 60 - 0) * min(1.0, done / 30)
        d.rounded_rectangle((rx0 + 30, ry0 + 684, rx0 + 30 + max(28, wfill), ry0 + 712),
                            radius=14, fill=BLUE)
    d.text((rx0 + 30, ry0 + 748), f"成功 {succ}", font=font(26, bold=True), fill=GREEN)
    d.text((rx0 + 230, ry0 + 748), f"失败 {fail}", font=font(26, bold=True),
           fill=RED if fail else MUTED)
    d.text((rx0 + 30, ry0 + 796), "演示节选：前 6 家", font=font(20), fill=DIM)

    if paused:
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((rx0 + 30, ry0 + 602, rx1 - 30, ry0 + 630), radius=14,
                             fill=(60, 48, 10, 230), outline=YELLOW, width=1)
        img.alpha_composite(ov)
        draw_text(img, ((rx0 + rx1) / 2, ry0 + 616),
                  "Ctrl+Z 暂停中 · 安全点不发送 / 恢复后重跑", 20, YELLOW, anchor="mm")
    return img.convert("RGB")


def scene4(t):
    """核心能力 115-145s"""
    img = BGIMG.copy().convert("RGBA")
    scene_title(img, "核心能力")
    caps = [
        ("三重身份校验", "姓名 · 门店 · 会话标题 三关全过才发送\n绝不发错人"),
        ("发送结果验证", "发送前 OCR 校验输入内容\n粘贴后像素差异检测，不盲发"),
        ("幂等 · 断点续跑", "中断随时恢复，自动跳过已完成动作\n重复执行零风险"),
        ("异常自动隔离", "单店失败不阻塞批次\n保留证据并登记人工核对清单"),
    ]
    tw, th, gx, gy = 836, 300, 48, 40
    for i, (title, desc) in enumerate(caps):
        a = ease((t - 0.5 - i * 2.5) / 0.5)
        if a <= 0:
            continue
        x = 100 + (i % 2) * (tw + gx)
        y = 200 + (i // 2) * (th + gy) + (1 - a) * 24
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((x, y, x + tw, y + th), radius=20,
                             fill=PANEL2 + (int(255 * a),), outline=BORDER + (int(255 * a),), width=1)
        ca = ease((t - 1.1 - i * 2.5) / 0.35)
        do.ellipse((x + 56, y + 108, x + 144, y + 196),
                   fill=(30, 60, 40, int(255 * ca)), outline=GREEN + (int(220 * ca),), width=3)
        if ca > 0.1 and ca < 1.0:
            sc = 0.6 + 0.4 * ca
        else:
            sc = 1.0
        check_mark(do, x + 100, y + 152, 66 * sc, GREEN + (int(255 * ca),), width=9)
        img.alpha_composite(ov)
        draw_text(img, (x + 180, y + 62), title, 38, FG, bold=True, alpha=a)
        ln = wrap_cjk(ImageDraw.Draw(img), desc, font(26), tw - 240)
        for j, s in enumerate(ln):
            draw_text(img, (x + 180, y + 130 + j * 42), s, 26, MUTED, alpha=a)
    return img.convert("RGB")


def scene5(t):
    """效果数据 145-170s"""
    img = BGIMG.copy().convert("RGBA")
    scene_title(img, "效果数据（保守测算）")
    d = ImageDraw.Draw(img)

    def bar(y, label, val_text, minutes, max_min, max_w, color, a):
        if a <= 0:
            return
        draw_text(img, (100, y - 4), label, 24, MUTED, alpha=a)
        wfull = max_w * ease(a)
        w = max(12, int(wfull * minutes / max_min))
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((100, y + 36, 100 + w, y + 92), radius=16, fill=color + (235,))
        img.alpha_composite(ov)
        draw_text(img, (100 + w + 16, y + 64), val_text, 26,
                  color, bold=True, alpha=a, anchor="lm")

    a1 = ease((t - 1.0) / 0.9)
    bar(300, "人工基线 · 单店", "≈ 3.5 分钟", 3.5, 4.0, 620, (168, 82, 82), a1)
    a2 = ease((t - 2.0) / 0.9)
    bar(430, "系统 · 单店（含节流）", "1 分钟", 1.0, 4.0, 620, BLUE, a2)
    a3 = ease((t - 3.6) / 0.9)
    bar(610, "人工 · 单批 30 家", "≈ 2.5 小时", 2.5 * 60, 3.0 * 60, 620, (168, 82, 82), a3)
    a4 = ease((t - 4.8) / 0.9)
    bar(740, "系统 · 单批 30 家（无人值守）", "≈ 30 分钟", 30, 3.0 * 60, 620, BLUE, a4)

    stats = [
        ("1 分钟 / 店", "系统吞吐（含节流等待）", BLUE),
        ("≈ 30 分钟", "单批 30 家 · 无人值守", GREEN),
        ("0 误发", "三重校验 + 发送结果验证", GREEN),
        ("100% 留痕", "截图 + 时间戳自动归档", BLUE),
    ]
    for i, (num, cap, c) in enumerate(stats):
        a = ease((t - 0.4 - i * 0.6) / 0.4)
        if a <= 0:
            continue
        x = 1000 + (i % 2) * 440
        y = 240 + (i // 2) * 280 + (1 - a) * 20
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        do = ImageDraw.Draw(ov)
        do.rounded_rectangle((x, y, x + 420, y + 220), radius=20,
                             fill=PANEL2 + (int(255 * a),), outline=BORDER + (int(255 * a),), width=1)
        img.alpha_composite(ov)
        draw_text(img, (x + 36, y + 48), num, 60, c, bold=True, alpha=a)
        draw_text(img, (x + 36, y + 140), cap, 24, MUTED, alpha=a)

    a5 = ease((t - 7.0) / 0.5)
    draw_text(img, (100, 900),
              "口径：运行参数为实测配置；效率为基于真实操作步骤的保守测算，随门店信息规范程度浮动。",
              22, DIM, alpha=a5)
    return img.convert("RGB")


def scene6(t):
    """结尾 170-180s"""
    img = BGIMG.copy().convert("RGBA")
    a1 = ease((t - 0.3) / 0.5)
    draw_text(img, (W // 2, 470), "飞书多维表格 × 企业微信 · 全流程自动化", 44, FG,
              bold=True, alpha=a1, anchor="mm")
    a2 = ease((t - 0.9) / 0.5)
    draw_text(img, (W // 2, 556), "本视频为脱敏演示 · 全部数据为虚构", 28, MUTED,
              alpha=a2, anchor="mm")
    a3 = ease((t - 1.5) / 0.5)
    draw_text(img, (W // 2, 626), "案例文档：《连锁门店运营自动化（脱敏）》", 24, DIM,
              alpha=a3, anchor="mm")
    return img.convert("RGB")


SCENES = [
    (0, 7, scene0),
    (7, 19, scene1),
    (19, 32, scene2),
    (32, 82, scene3),
    (82, 95, scene4),
    (95, 107, scene5),
    (107, 113, scene6),
]

_card_cache = {}


def load_cards():
    for sid, name, mgr in _STORES:
        p = ASSETS / f"{sid}.png"
        if p.exists():
            _card_cache[sid] = Image.open(p).convert("RGB")


def locate(t):
    for i, (s, e, fn) in enumerate(SCENES):
        if s <= t < e or (i == len(SCENES) - 1 and t >= e):
            return i, t - s
    return len(SCENES) - 1, 0.0


def render_frame(t, prev_ends):
    i, local = locate(t)
    s, e, fn = SCENES[i]
    img = fn(local)
    if i > 0 and local < FADE:
        img = Image.blend(prev_ends[i - 1], img, ease(local / FADE))
    if i == 0 and t < 0.6:
        img = Image.blend(Image.new("RGB", (W, H), BLACK), img, ease(t / 0.6))
    if i == len(SCENES) - 1 and local > (e - s) - FADE:
        img = Image.blend(img, Image.new("RGB", (W, H), BLACK),
                          ease((local - ((e - s) - FADE)) / FADE))
    watermark(img)
    return img


def preview(times):
    PREVIEW.mkdir(exist_ok=True)
    prev_ends = [fn(e - s - 1 / FPS) for (s, e, fn) in SCENES]
    for t in times:
        img = render_frame(t, prev_ends)
        p = PREVIEW / f"t{int(t):03d}.png"
        img.save(p)
        print(f"preview: {p.name}")


def render():
    import imageio
    OUT.mkdir(exist_ok=True)
    out_path = OUT / "门店运营自动化演示（脱敏）_2min.mp4"
    prev_ends = [fn(e - s - 1 / FPS) for (s, e, fn) in SCENES]
    total = int(DUR * FPS)
    writer = imageio.get_writer(
        str(out_path), fps=FPS, codec="libx264",
        ffmpeg_params=["-crf", "20", "-preset", "veryfast", "-pix_fmt", "yuv420p"],
        macro_block_size=8,
    )
    try:
        for i in range(total):
            t = i / FPS
            img = render_frame(t, prev_ends)
            writer.append_data(np.asarray(img))
            if i % 120 == 0:
                print(f"render: {i}/{total} frames ({t:.0f}s)", flush=True)
    finally:
        writer.close()
    print(f"done: {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    global BGIMG
    BGIMG = bg_image()
    load_cards()
    if args.preview:
        preview([3, 14, 28, 40, 62, 78, 88, 92, 100, 104, 110])
    if args.render:
        render()
    if not args.preview and not args.render:
        print("use --preview or --render")


if __name__ == "__main__":
    main()
