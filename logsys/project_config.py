# -*- coding: utf-8 -*-
"""项目配置：井 ↔ 原始资料目录 的绑定关系。

为什么需要这个模块
------------------
项目树（Project → Well → Dataset → Variable）扫描的是**产物目录**
（如 ``D:\\360\\src\\output``），而 QuickLook / 综合解释这类作业需要的是
**原始井目录**（含原始 LAS、地质设计、录井图、气测、甲方格式），例如
``D:\\360\\Indonesia\\BET-1``。

两者的对应关系**无法靠文件名自动推断**：
- 目录名可能不同（井 ``RASHIDPUR_13`` 的资料目录叫 ``RP-13``）；
- 同一口井的资料可能散在多个目录；
- 产物目录里没有原始 LAS（只有 ``*_interpreted.LAS`` 解释成果）。

因此这里采用 Techlog 的做法：把映射关系**显式存下来**，而不是猜。
配置文件为项目根下的 ``project.json``：

```json
{
  "version": 1,
  "source_roots": ["D:\\\\360\\\\Indonesia", "D:\\\\360\\\\Bangladesh"],
  "wells": {
    "BET-1": {"source_dir": "D:\\\\360\\\\Indonesia\\\\BET-1"}
  }
}
```

约定：
- ``source_roots``：候选原始资料根目录，探测时按井名在这些根下找子目录；
- ``wells``：已确认的显式绑定，优先级高于自动探测；
- 写入采用**原子替换**（临时文件 + os.replace），避免半截文件；
- 任何失败都降级为"空配置"，不抛错（与 logsys 约定一致）。

本模块只依赖标准库，不依赖 tkinter，可独立单测。
"""
from __future__ import annotations

import json
import os
import tempfile

#: 项目配置文件名（位于项目根目录）
CONFIG_NAME = 'project.json'

#: 配置格式版本
CONFIG_VERSION = 1


def config_path(root: str) -> str:
    """项目配置文件绝对路径。"""
    return os.path.join(os.path.abspath(root), CONFIG_NAME)


def _empty_config() -> dict:
    return {'version': CONFIG_VERSION, 'source_roots': [], 'wells': {}}


def load_config(root: str) -> dict:
    """读取项目配置。

    返回结构：``{'version': int, 'source_roots': [str], 'wells': {井名: {...}}}``
    文件不存在 / 损坏 → 返回空配置（不抛错）。
    """
    cfg = _empty_config()
    p = config_path(root)
    try:
        with open(p, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return cfg
    if not isinstance(raw, dict):
        return cfg
    try:
        cfg['version'] = int(raw.get('version') or CONFIG_VERSION)
    except Exception:
        cfg['version'] = CONFIG_VERSION
    roots = raw.get('source_roots')
    if isinstance(roots, (list, tuple)):
        cfg['source_roots'] = [str(x) for x in roots if str(x).strip()]
    wells = raw.get('wells')
    if isinstance(wells, dict):
        for name, val in wells.items():
            if isinstance(val, dict):
                cfg['wells'][str(name)] = dict(val)
    return cfg


def save_config(root: str, cfg: dict) -> bool:
    """原子写回项目配置。成功返回 True。"""
    p = config_path(root)
    data = {
        'version': int(cfg.get('version') or CONFIG_VERSION),
        'source_roots': list(cfg.get('source_roots') or []),
        'wells': {str(k): dict(v) for k, v in (cfg.get('wells') or {}).items()
                  if isinstance(v, dict)},
    }
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, p)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- 绑定操作

def bind_well(root: str, well_name: str, source_dir: str,
              extra: dict | None = None) -> bool:
    """绑定一口井的原始资料目录。"""
    cfg = load_config(root)
    entry = {'source_dir': os.path.abspath(source_dir)}
    if extra:
        for k, v in extra.items():
            if v:
                entry[k] = v
    cfg['wells'][str(well_name)] = entry
    return save_config(root, cfg)


def unbind_well(root: str, well_name: str) -> bool:
    """解除一口井的原始资料目录绑定。"""
    cfg = load_config(root)
    if str(well_name) in cfg['wells']:
        del cfg['wells'][str(well_name)]
        return save_config(root, cfg)
    return True


def add_source_root(root: str, source_root: str) -> bool:
    """追加一个候选原始资料根目录。"""
    cfg = load_config(root)
    p = os.path.abspath(source_root)
    if p not in cfg['source_roots']:
        cfg['source_roots'].append(p)
        return save_config(root, cfg)
    return True


def remove_source_root(root: str, source_root: str) -> bool:
    """移除一个候选原始资料根目录。"""
    cfg = load_config(root)
    p = os.path.abspath(source_root)
    if p in cfg['source_roots']:
        cfg['source_roots'].remove(p)
        return save_config(root, cfg)
    return True


# ---------------------------------------------------------------- 解析

def _norm(name: str) -> str:
    """井名归一：去空格/下划线/连字符并大写，用于宽松匹配。

    ``RASHIDPUR_13`` / ``RP-13`` 归一后不同（无法匹配），
    但 ``Trakes KE-1`` / ``TrakesKE-1`` 归一后相同（可匹配）。
    """
    return ''.join(ch for ch in str(name or '').upper() if ch.isalnum())


def _match_dir(dirname: str, well_name: str) -> bool:
    """目录名是否可视为该井的资料目录。

    归一化后完全相等，或一方为另一方的前缀。
    较短一方须 **≥4 个字符**，否则短名井（如 ``3``、``1``）会误匹配到
    ``3-SPS-111D`` 这类目录上。
    """
    d = _norm(dirname)
    w = _norm(well_name)
    if not d or not w:
        return False
    if d == w:
        return True
    short, long_ = (d, w) if len(d) < len(w) else (w, d)
    if len(short) < 4:
        return False
    return long_.startswith(short)


def detect_source_dir(well_name: str, source_roots: list[str],
                      extra_roots: list[str] | None = None) -> str:
    """在候选源根中探测某口井的原始资料目录。

    策略（按优先级）：
      1. 源根下**同名子目录**；
      2. 源根下**归一化后宽松匹配**的子目录（RASHIDPUR_13 → RP-13 这类
         明显不同的命名不会被匹配上，属预期——那需要显式绑定；
         ``Trakes KE-1`` ↔ ``TrakesKE-1`` 则可匹配）；
      3. 源根下**包含井名 LAS 文件**的子目录；
      4. **源根本身**直接含该井的 LAS（资料以散文件形式放在源根里的情形，
         如 TITAS-31 的 LAS 就在 Bangladesh/ 根部）。

    找不到返回 ''。
    """
    roots = [r for r in (list(source_roots or []) + list(extra_roots or [])) if r]
    for root in roots:
        if not os.path.isdir(root):
            continue
        # 1) 同名子目录
        direct = os.path.join(root, well_name)
        if os.path.isdir(direct):
            return os.path.abspath(direct)
        # 2) 宽松匹配的子目录
        try:
            entries = sorted(os.listdir(root))
        except Exception:
            entries = []
        for e in entries:
            d = os.path.join(root, e)
            if os.path.isdir(d) and _match_dir(e, well_name):
                return os.path.abspath(d)
        # 3) 含该井名 LAS 文件的子目录
        for e in entries:
            d = os.path.join(root, e)
            if not os.path.isdir(d):
                continue
            try:
                files = os.listdir(d)
            except Exception:
                continue
            for fn in files:
                if _is_well_las(fn, well_name):
                    return os.path.abspath(d)
        # 4) 源根本身直接含该井 LAS
        for fn in entries:
            if _is_well_las(fn, well_name):
                return os.path.abspath(root)
    return ''


def _is_well_las(filename: str, well_name: str) -> bool:
    """文件名是否为该井的 LAS 文件。

    归一化后完全相等，或一方为另一方前缀（短者须 ≥4 字符，避免
    ``3`` 井误匹配 ``3-SPS-111D`` 的 LAS）。
    """
    low = filename.lower()
    if not low.endswith('.las'):
        return False
    w = _norm(well_name)
    if not w:
        return False
    stem = _norm(os.path.splitext(filename)[0])
    if not stem:
        return False
    if stem == w:
        return True
    short, long_ = (stem, w) if len(stem) < len(w) else (w, stem)
    if len(short) < 4:
        return False
    return long_.startswith(short)


def resolve_source_dir(root: str, well_name: str,
                       extra_roots: list[str] | None = None) -> str:
    """解析一口井的原始资料目录。

    优先级：**显式绑定** > **自动探测** > 空。
    """
    cfg = load_config(root)
    entry = (cfg.get('wells') or {}).get(str(well_name)) or {}
    bound = str(entry.get('source_dir') or '').strip()
    if bound and os.path.isdir(bound):
        return os.path.abspath(bound)
    detected = detect_source_dir(well_name, cfg.get('source_roots') or [], extra_roots)
    return detected


def source_map(root: str, well_names: list[str],
               extra_roots: list[str] | None = None) -> dict:
    """批量解析井 → 原始资料目录 的映射（供 scan_project 使用）。"""
    cfg = load_config(root)
    roots = cfg.get('source_roots') or []
    out: dict[str, str] = {}
    for name in well_names:
        entry = (cfg.get('wells') or {}).get(str(name)) or {}
        bound = str(entry.get('source_dir') or '').strip()
        if bound and os.path.isdir(bound):
            out[str(name)] = os.path.abspath(bound)
            continue
        det = detect_source_dir(name, roots, extra_roots)
        if det:
            out[str(name)] = det
    return out


def source_roots(root: str) -> list[str]:
    """已登记的候选源根列表。"""
    return list(load_config(root).get('source_roots') or [])


if __name__ == '__main__':
    import sys
    r = sys.argv[1] if len(sys.argv) > 1 else '.'
    cfg = load_config(r)
    print('配置文件:', config_path(r))
    print('候选源根:')
    for x in cfg['source_roots']:
        print('   ', x)
    print('显式绑定:')
    for k, v in cfg['wells'].items():
        print('   %-24s %s' % (k, v.get('source_dir', '')))
