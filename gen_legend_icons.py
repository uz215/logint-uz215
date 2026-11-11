#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""gen_legend_icons.py — 按 legend_format.json 生成油气水图例矩形 PNG 图标

用法:  python gen_legend_icons.py
输出:  symbol/fluid_conclusions/<图标英文名>.png（文件夹与文件名均英文；
       gas/oil/water/gas_water/oil_water/gas_oil/poor_gas/poor_oil/
       oil_bearing_water/gas_bearing_water/probable_*/possible_*）
格式以 symbol/legend_format.json 为准：改格式文件后重跑本脚本即全部重生成。
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
CFG = ROOT / 'symbol' / 'legend_format.json'
OUT = ROOT / 'symbol' / 'fluid_conclusions'


def _hex(c):
    return c if isinstance(c, str) else '#ffffff'


def gen_icon(spec, size, border, background, name):
    w, h = size
    img = Image.new('RGB', (w, h), _hex(background))
    d = ImageDraw.Draw(img)
    bw = int(border.get('width', 3))
    bcol = _hex(border.get('color', '#000000'))
    x0, y0 = bw, bw
    x1, y1 = w - bw, h - bw

    style = spec.get('style', 'frame')
    split = spec.get('split', 'none')
    c1 = _hex(spec.get('color1', spec.get('fill', '#ffffff')))
    c2 = _hex(spec.get('color2', '#ffffff'))
    ratio = float(spec.get('ratio', 0.5))

    if style == 'solid':
        # probable/possible 类：纯色块无外框（参照 symbol 原有 bmp/jpg）
        d.rectangle([0, 0, w - 1, h - 1], fill=c1)
        out = OUT / (name + '.png')
        img.save(str(out))
        return out

    if split == 'none':
        d.rectangle([x0, y0, x1, y1], fill=c1)
    elif split == 'diag':
        # direction: left_down=左上→右下（上半=左上三角 c1，下半=右下三角 c2）
        #            right_up=右上→左下（上半=右上三角 c1，下半=左下三角 c2）
        if spec.get('direction', 'left_down') == 'right_up':
            d.polygon([(x1, y0), (x0, y1), (x1, y1)], fill=c1)   # 右上三角
            d.polygon([(x0, y0), (x0, y1), (x1, y0)], fill=c2)   # 左下三角
        else:
            d.polygon([(x0, y0), (x1, y0), (x0, y1)], fill=c1)   # 左上三角
            d.polygon([(x1, y0), (x0, y1), (x1, y1)], fill=c2)   # 右下三角
    elif split == 'vert_left':
        # 左侧 ratio 有色，右侧空白
        xm = x0 + int((x1 - x0) * ratio)
        d.rectangle([x0, y0, xm, y1], fill=c1)
        d.rectangle([xm + 1, y0, x1, y1], fill=_hex(background))
    elif split == 'vert':
        # 左侧 ratio color1，右侧 color2
        xm = x0 + int((x1 - x0) * ratio)
        d.rectangle([x0, y0, xm, y1], fill=c1)
        d.rectangle([xm + 1, y0, x1, y1], fill=c2)

    # 矩形外框（加粗黑边）
    d.rectangle([x0, y0, x1, y1], outline=bcol, width=bw)
    out = OUT / (name + '.png')
    img.save(str(out))
    return out


def main():
    if not CFG.exists():
        print(f'[gen_legend_icons] 找不到格式文件: {CFG}')
        return 1
    cfg = json.loads(CFG.read_text(encoding='utf-8'))
    size = cfg.get('size', [160, 120])
    border = cfg.get('border', {})
    background = cfg.get('background', '#ffffff')
    OUT.mkdir(parents=True, exist_ok=True)
    icons = cfg.get('icons', {})
    if not icons:
        print('[gen_legend_icons] 格式文件无 icons 定义')
        return 1
    for name, spec in icons.items():
        p = gen_icon(spec, size, border, background, name)
        print(f'  ✓ {name}.png  <- {spec.get("label_cn", "")}'
              f' ({spec.get("label_en", "")})')
    print(f'[gen_legend_icons] 共 {len(icons)} 个图例图标已生成 -> {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
