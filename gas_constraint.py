# -*- coding: utf-8 -*-
"""
gas_constraint.py — 气测解释约束模块

用途
----
把气测（泥浆录井）解释结果用于"校正 / 剔除"测井解释中过于乐观的油气层，
落实用户的经验法则：

    "没有气测异常，基本可以排除是油气层"

设计
----
1. 优先复用用户已有的 Gas.py（C1-5 传统图版法：
   Pixler / Triangle / 3H / Star 四图版多数投票）得到每深度点的
   ITP_traditional（GAS / OIL / DRY / WATER ...）。
   Gas.py 的 TraditionalInterpretationModule 需要一个配置文件，本模块内置一份
   与 Gas.py 文档化阈值一致的默认配置（pixler + 3H 阈值取自 Gas.py 内置知识，
   triangle / star 取合理默认值），从而真正调用 Gas.py 的解释引擎。
2. 若 Gas.py 因环境原因无法导入 / 运行，则回退到本模块内置的、与 Gas.py
   传统图版法同源的轻量实现（pixler + 3H + triangle），保证功能始终可用。
3. apply_gas_constraint()：对"已被测井解释判为油/气层"的深度，若气测解释为
   DRY（无烃类显示）则直接剔除（判为非储层），并记录原因供报告/绘图追溯。

气测文件格式
------------
- Excel：列名可能含换行与单位，如 'Depth\n(m)' / 'C1\n(ppm)' / 'TG\n(ppm)'，
  本模块自动归一化为 MD / C1..C5 / TG / CO2 / H2S。
- CSV / LAS（lasio 读取）同理。
"""
import os
import re
import json
import logging
import numpy as np
import pandas as pd

logger = logging.getLogger("gas_constraint")

# ----------------------------------------------------------------------------
# 气测组分列归一化映射（原始列名(去空格/换行/小写/去单位) -> 标准名）
# ----------------------------------------------------------------------------
_COLUMN_ALIASES = {
    "md": "MD", "depth": "MD", "dep": "MD", "dept": "MD", "tdep": "MD",
    "md(m)": "MD", "depthm": "MD", "mdm": "MD",
    # BET-1 txt深度列 'MDEPTH (ft)'(2026-10-08): _norm_header_key去括号后为
    # 'mdepth(ft)'/去单位尾缀后为'mdepthft', 均需映射
    "mdepth": "MD", "mdepth(ft)": "MD", "mdepthft": "MD", "depthft": "MD",
    "tg": "TG", "tgas": "TG", "totgas": "TG", "totalgas": "TG",
    "total_gas": "TG", "gas_total": "TG", "total": "TG", "totle": "TG",
    "c1": "C1", "methane": "C1", "ch4": "C1",
    "c2": "C2", "ethane": "C2", "c2h6": "C2",
    "c3": "C3", "propane": "C3", "c3h8": "C3",
    "ic4": "IC4", "isobutane": "IC4",
    "nc4": "NC4", "nbutane": "NC4",
    "ic5": "IC5", "isopentane": "IC5",
    "nc5": "NC5", "npentane": "NC5",
    # 注: 裸 'c5'/'c4' 是"总戊烷/总丁烷", 不可当作异构体 (用户2026-09-14)
    "c4": "C4", "c5": "C5",
    "c6": "C6", "c7": "C7", "c8": "C8",
    "co2": "CO2", "h2s": "H2S",
}

# 全烃(TG)碳数加权合成用的权重 (用户2026-09-14 口径)
_TG_WEIGHTS = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5,
               "C6": 6, "C7": 7, "C8": 8, "BZ": 6, "MCH": 7, "TL": 7}

# 气测"无显示"判定：当气测解释结果为以下类别之一时，认为该深度"无烃类显示"
_NO_SHOW_LABELS = {"DRY", "NONE", "NaN", "nan", "", None}
# 测井解释中被气测约束的油气类标签
_HC_LABELS = {"OIL", "GAS", "OIL_POSSIBLE", "GAS_POSSIBLE",
              "CONDENSATE", "OIL_WATER", "GAS_WATER"}


def _norm_header_key(name) -> str:
    """列名归一化key (与 _normalize_columns 同规则): 小写/去空格换行括号/去单位尾缀。"""
    key = (str(name).replace("\n", " ").replace("\r", " ")
           .strip().lower()
           .replace(" ", "")
           .replace("(m)", "").replace("(ppm)", "")
           .replace("(%)", "").replace("(", "").replace(")", ""))
    # 去掉可能的单位尾缀
    for suf in ["ppm", "mg/l", "mg/l)", "%", "(%)", "m", "min/m", "min/m)", "ft", "(ft)"]:
        if key.endswith(suf):
            key = key[: -len(suf)]
    return key


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """将气测原始列名归一化为标准名（MD / C1..C8 / TG / CO2 / H2S）。"""
    rename = {}
    for col in df.columns:
        if not isinstance(col, str):
            continue
        key = _norm_header_key(col)
        if key in _COLUMN_ALIASES and _COLUMN_ALIASES[key] not in rename.values():
            rename[col] = _COLUMN_ALIASES[key]
    if rename:
        df = df.rename(columns=rename)
    # 清理未命名列
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]
    return df


# 气测烃类组分列(用于单位自洽性检测; 不含 CO2/H2S/H2 —— 全烃TG是非烃气体以外的总烃)
_GAS_HC_COLS = ("C1", "C2", "C3", "C4", "IC4", "NC4", "C5", "IC5", "NC5",
                "C6", "C7", "C8", "MCH", "BZ", "TL")


def normalize_gas_units(df: pd.DataFrame, unit_hints=None) -> pd.DataFrame:
    """气测单位统一为 ppm —— 识别单位并换算 (用户2026-09-30, TITAS-31)。

    用户口径: "气测数据的列名是自带单位的, 应该能识别, 有的单位是单独占一行,
    要智能分析, 因为不是ppm就是%, 绘图单位统一是ppm"。此前 TG(%) 与组分(ppm)
    被当同一单位直接绘图/解释 —— TG 曲线被压在 ppm 对数刻度最左侧成贴边直线,
    异常门槛(TG≥50ppm)对 TG 失真。

    单位识别两级(单位有 ppm / % / unit 三种):
      阶段0(表头显式标注, 权威): 列名自带单位('TG (%)'/'C1 ppm'/'TGAS (unit)')
        或单位单独占一行(表头下一行 '(%)'/'(ppm)'/'unit', 见 'Gas Show' 表)
        —— 由 attach_gas_unit_hints 捕获为 {标准列名: '%'|'ppm'|'unit'}; 本函数
        按 GAS_UNIT_TO_PPM 换算: %×10^4, unit×200(印尼气测仪刻度, 2026-10-08
        BET-1, 已写入logknow), ppm不变;
      阶段1(值域判定, 无标注时兜底; 用户2026-09-30规则; 判定顺序B/C先于A
        —— 2026-10-08 BET-1: TGAS为%但max 395>100, 演绎证据B/C须优先于
        归纳阈值A):
        · 规则B: 组分一般都是ppm, C1最大值>100且TG中位<C1中位 -> TG为非ppm,
          需换算(系数按自洽性在 unit×200 与 %×10000 中选择, 见下);
        · 规则C: ratio=median(TG)/median(Σ组分), 同单位下必有TG>=Σ组分:
          ratio<0.05 -> TG为非ppm需换算; ratio>100且组分均<=100 -> 组分=%(×10000);
        · 规则A: 列内出现>100的值 -> 该列肯定是ppm (%不会超过100);
        · TG换算系数自洽性选择(2026-10-08印尼BET-1): unit×200 与 %×10000 中取
          换算后TG/Σ组分中位比值最接近1者 —— BET-1 TGAS中位8.27 unit×200=1654ppm
          与Σ组分中位约1100ppm比值1.5自洽, %×10000=82700比值75荒谬;
        · TG与全部组分最大值均<=100 -> 全文件疑似% -> 整体×10000(告警);
        · 其余 -> 同为ppm不换算。
      阶段0换算后仍做自洽性校验: 若 ratio 仍在 0.05~100 之外, 告警"表头标注
      可能有误"(只告警不二次换算, 防止双重换算)。
    换算系数 1% = 10^4 ppm。实测 TITAS-31: TG中位0.33(%)/Σ组分中位约3990(ppm)
    -> TG×10000 后中位3292ppm, 与C1(3798ppm)同量级, 自洽。
    幂等护栏: attrs['gas_units_normalized'] 防止重复换算。
    """
    try:
        if df is None or len(df) == 0 or "TG" not in df.columns:
            return df
        try:
            if getattr(df, "attrs", {}).get("gas_units_normalized"):
                return df
        except Exception:
            pass
        comp_cols = [c for c in _GAS_HC_COLS if c in df.columns]

        def _pos_median(s):
            v = pd.to_numeric(s, errors="coerce")
            v = v[v > 0]
            return float(v.median()) if bool(len(v)) else float("nan")

        # ---------- 阶段0: 表头显式单位标注(列名自带/单位行), 权威 ----------
        hints = unit_hints if isinstance(unit_hints, dict) and unit_hints else None
        if not hints:
            try:
                hints = getattr(df, "attrs", {}).get("gas_unit_hints") or None
            except Exception:
                hints = None
        if hints:
            converted = {}
            for col, u in hints.items():
                u_key = str(u)
                factor = GAS_UNIT_TO_PPM.get(u_key, 1.0)
                if (col in df.columns and col != "MD" and factor > 1.0):
                    df[col] = pd.to_numeric(df[col], errors="coerce") * factor
                    converted[col] = f"{u_key}→ppm(×{factor:g})"
            if converted:
                _units = "/".join(sorted({str(hints[c]) for c in converted}))
                logger.warning("气测单位识别(表头标注): %s 原始单位为%s, 已换算为统一单位ppm",
                               "/".join(converted), _units)
                print(f"★ 气测单位: {'/'.join(converted)} 表头标注单位={_units}, "
                      f"已换算为统一单位ppm")
            try:
                df.attrs["gas_unit_converted"] = converted
            except Exception:
                pass
            # 物理自洽性校验(只告警不二次换算 —— 防止对已换算列双重×10000)
            if "TG" in df.columns and comp_cols:
                tg_med = _pos_median(df["TG"])
                comp_sum = None
                for c in comp_cols:
                    v = pd.to_numeric(df[c], errors="coerce").clip(lower=0.0).fillna(0.0)
                    comp_sum = v if comp_sum is None else comp_sum + v
                comp_med = _pos_median(comp_sum)
                if np.isfinite(tg_med) and np.isfinite(comp_med) and tg_med > 0 and comp_med > 0:
                    ratio = tg_med / comp_med
                    if ratio < 0.05 or ratio > 100:
                        logger.warning("气测单位校验: 表头标注换算后 TG/Σ组分=%.3g 仍超出0.05~100, "
                                       "表头单位标注可能有误, 请人工核对", ratio)
            try:
                df.attrs["gas_units_normalized"] = True
            except Exception:
                pass
            return df

        # ---------- 阶段1: 值域判定(无表头标注时兜底; 用户2026-09-30规则) ----------
        # 判定顺序 B/C(演绎) 先于 A(归纳), 见函数docstring(2026-10-08 BET-1)
        # 规则A: 列内出现>100的值 -> 该列肯定是ppm (%不会超过100)
        # 规则B: 组分一般都是ppm; TG(总体)中位 < C1中位(原始值) -> 物理上TG>=C1,
        #        TG反而小 -> TG=%, C1=ppm -> TG×10000
        # 规则C: 同单位自洽 ratio=TG中位/Σ组分中位(同单位下必有TG>=Σ组分):
        #        <0.05 -> TG=%(×10000); >100且组分均<=100 -> 组分=%(×10000)
        # 追加: TG与全部组分最大值都<=100 -> 全文件疑似% -> 整体×10000(告警)
        if not comp_cols:
            return df
        tg_med = _pos_median(df["TG"])
        tg_max = float(pd.to_numeric(df["TG"], errors="coerce").max())
        tg_max = tg_max if np.isfinite(tg_max) else -1.0
        c1_med = c1_max = float("nan")
        if "C1" in df.columns:
            _c1 = pd.to_numeric(df["C1"], errors="coerce")
            c1_med = _pos_median(_c1)
            c1_max = float(_c1.max())
            c1_max = c1_max if np.isfinite(c1_max) else -1.0
        if not (np.isfinite(tg_med) and tg_med > 0):
            return df

        comp_sum = None
        for c in comp_cols:
            v = pd.to_numeric(df[c], errors="coerce").clip(lower=0.0).fillna(0.0)
            comp_sum = v if comp_sum is None else comp_sum + v
        comp_med = _pos_median(comp_sum)
        comp_max = -1.0
        for c in comp_cols:
            _m = float(pd.to_numeric(df[c], errors="coerce").max())
            if np.isfinite(_m):
                comp_max = max(comp_max, _m)
        ratio = (tg_med / comp_med) if (np.isfinite(comp_med) and comp_med > 0) else float("nan")

        # 判定优先级(2026-10-08, BET-1): 规则B/C是演绎物理证据(同单位下必有
        # TG>=C1 且 TG>=Σ组分), 规则A只是归纳阈值 —— BET-1 的 TGAS(%)最大值
        # 395>100 会误触发规则A阻断正确换算, 故 B/C 必须先于 A 判定。
        tg_is_pct = None
        _rule = ""
        # 规则B: 组分一般都是ppm —— C1最大值>100 且 TG中位<C1中位 -> TG=%
        if (np.isfinite(c1_med) and c1_med > 0
                and c1_max > 100 and tg_med < c1_med):
            tg_is_pct = True
            _rule = "规则B(TG中位%.4g<C1中位%.4g, 组分ppm)" % (tg_med, c1_med)
        # 规则C: TG中位远小于组分和中位 -> TG=% (同单位下必有TG>=Σ组分)
        if tg_is_pct is None and np.isfinite(ratio) and ratio < 0.05:
            tg_is_pct = True
            _rule = "规则C(TG中位%.4g远小于Σ组分中位%.4g)" % (tg_med, comp_med)
        # 规则A: TG最大值>100 -> TG肯定是ppm(%不会超过100), 不再换算
        if tg_is_pct is None and tg_max > 100:
            tg_is_pct = False
            _rule = "规则A(TG最大值%.4g>100)" % tg_max

        if tg_is_pct:
            # TG非ppm -> 需换算为ppm。换算系数按自洽性选择(2026-10-08印尼BET-1):
            # 候选 unit(×200, 印尼气测仪刻度单位, 见logknow知识库) 与 %(×10000),
            # 取换算后 TG中位/Σ组分中位 比值最接近1(物理上TG>=Σ组分且同量级)者。
            # BET-1实测: TG中位8.27 unit -> ×200=1654ppm vs Σ组分中位约1100ppm
            # (比值1.5, 自洽); 若误按%×10000=82700ppm(比值75, 荒谬)。
            factor, unit_name = 10000.0, "%"
            if np.isfinite(comp_med) and comp_med > 0:
                def _unit_dev(f):
                    r = (tg_med * f) / comp_med
                    return abs(np.log10(r)) if r > 0 else float("inf")
                if _unit_dev(200.0) < _unit_dev(10000.0):
                    factor, unit_name = 200.0, "unit"
            df["TG"] = pd.to_numeric(df["TG"], errors="coerce") * factor
            try:
                df.attrs["gas_unit_converted"] = {"TG": f"{unit_name}→ppm(×{factor:g})"}
            except Exception:
                pass
            if not _rule:
                _rule = "全部值<=100, 疑似全文件%%单位"
            logger.warning("气测单位识别(值域): TG原始单位=%s [%s]; TG已×%g换算为统一单位ppm",
                           unit_name, _rule, factor)
            print(f"★ 气测单位: TG原始单位={unit_name} [{_rule}] -> TG已×{factor:g}换算为统一单位ppm")
        elif np.isfinite(ratio) and ratio > 100 and tg_max > 100 and 0 < comp_max <= 100:
            # 规则C(组分=%): TG已证为ppm(最大值>100), 组分均<=100且之和远小于TG -> 组分×10000
            for c in comp_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce") * 10000.0
            try:
                df.attrs["gas_unit_converted"] = {c: "%→ppm(×10000)" for c in comp_cols}
            except Exception:
                pass
            logger.warning("气测单位识别(值域): TG中位%.4g vs 组分和中位%.4g (比值%.3g>100) "
                           "-> 组分单位为%%, TG为ppm; 组分%s已×10000换算为统一单位ppm",
                           tg_med, comp_med, ratio, "/".join(comp_cols))
            print("★ 气测单位: 组分原始单位=%, TG单位=ppm -> 组分已×10000换算为统一单位ppm")
        elif tg_max <= 100 and 0 < comp_max <= 100:
            # 追加: TG与全部组分最大值都<=100 -> 全文件疑似% (ppm井全组分<100极罕见)
            _all = ["TG"] + list(comp_cols)
            for c in _all:
                df[c] = pd.to_numeric(df[c], errors="coerce") * 10000.0
            try:
                df.attrs["gas_unit_converted"] = {c: "%→ppm(×10000)" for c in _all}
            except Exception:
                pass
            logger.warning("气测单位识别(值域): TG与全部组分最大值均<=100 -> 全文件疑似%%单位; "
                           "%s已×10000换算为统一单位ppm, 请人工核对", "/".join(_all))
            print("★ 气测单位: TG与全部组分最大值均≤100, 判定为%单位 -> 已整体×10000换算为ppm(请人工核对)")
        else:
            if np.isfinite(ratio) and ratio < 0.05:
                logger.warning("气测单位检查: TG最大值%.4g>100(ppm特征)但TG中位%.4g远小于组分和%.4g, "
                               "数据自相矛盾, 未做换算, 请人工核对", tg_max, tg_med, comp_med)
            else:
                logger.info("气测单位检查: TG与组分同为ppm(TG中位%.4g, 最大%.4g>100), 无需换算",
                            tg_med, tg_max)
        try:
            df.attrs["gas_units_normalized"] = True
        except Exception:
            pass
        return df
    except Exception as e:
        logger.warning(f"气测单位统一失败(按原值继续): {e}")
        return df


def _column_unit_hint(name):
    """从列名提取单位提示: 含'ppm'->'ppm', 含'%'->'%', 含'unit'->'unit'。

    2026-10-08(印尼, BET-1): 印尼气测数据(如 'ASCI GAS dan ROP' 文本)全烃
    TGAS 的单位是气测仪刻度单位 'unit', 1 unit = 200 ppm (印尼地区经验,
    已写入 logknow 知识库) —— 不是 % 的 ×10000。
    """
    s = str(name).lower()
    if "ppm" in s:
        return "ppm"
    if "%" in s:
        return "%"
    if "unit" in s:
        return "unit"
    return None


# 气测单位 -> ppm 换算系数 (统一单位为ppm; 用户2026-09-30/2026-10-08)
# %: 1% = 10^4 ppm; unit: 印尼气测仪刻度单位 1 unit = 200 ppm (logknow)
GAS_UNIT_TO_PPM = {"ppm": 1.0, "unit": 200.0, "%": 10000.0}


def attach_gas_unit_hints(df: pd.DataFrame) -> pd.DataFrame:
    """捕获气测表头单位提示并剔除"单位行" (用户2026-09-30)。

    用户口径: "气测数据的列名是自带单位的, 应该能识别, 有的单位是单独占一行,
    要智能分析, 因为不是ppm就是%"。两种形态:
      ① 列名自带单位: 'TG (%)'/'C1 ppm' (TITAS-31 'Gas data' 表表头行);
      ② 单位单独占一行: 表头下一行整行是 '(%)'/'(ppm)'/'m MD' (TITAS-31
         'Gas Show' 表) —— 该行数值化时会被 coerce 成 NaN 自动剔除, 但单位
         信息会丢失, 必须在剔除前捕获。
    提示写入 df.attrs['gas_unit_hints'] = {标准列名: '%'|'ppm'} 供
    normalize_gas_units 消费; 单位行从数据中删除。
    """
    try:
        if df is None or len(df) == 0:
            return df

        def _std(col):
            k = _norm_header_key(col)
            return _COLUMN_ALIASES.get(k, k.upper())

        hints = {}
        # ① 列名自带单位
        for col in df.columns:
            u = _column_unit_hint(col)
            if u:
                hints[_std(col)] = u
        # ② 单位行: 表头之下前5行内, 一行中≥2个非空格是纯单位串 -> 捕获并整行删除
        drop_idx = []
        for i in range(min(5, len(df))):
            row = df.iloc[i]
            unit_cells = []
            for j, v in enumerate(row.values):
                if pd.isna(v):
                    continue
                s = re.sub(r"[^a-z%]", "", str(v).lower())
                if s in ("ppm", "%", "unit"):
                    unit_cells.append((j, s))
            if len(unit_cells) >= 2:
                for j, u in unit_cells:
                    if j < len(df.columns):
                        hints[_std(df.columns[j])] = u
                drop_idx.append(df.index[i])
        if drop_idx:
            logger.info(f"气测表头单位行识别: 数据第{[str(x) for x in drop_idx]}行为单位行, "
                        f"已捕获单位并从数据中剔除")
            df = df.drop(index=drop_idx)
        if hints:
            try:
                df.attrs["gas_unit_hints"] = dict(hints)
            except Exception:
                pass
            logger.info(f"气测表头单位提示: {hints}")
        return df
    except Exception as e:
        logger.warning(f"气测表头单位提示捕获失败(按无提示继续): {e}")
        return df


def _detect_gas_header_row(raw: pd.DataFrame):
    """在无表头 DataFrame 中探测"深度列+气体组分"表头行; 未找到返回 None。

    要求同时命中: 深度关键词(depth/md) **且** ≥2 个气体组分关键词(tg/c1..c5)。
    """
    for i in range(len(raw)):
        cells = [str(x).lower().replace("\n", " ").replace("(", "").replace(")", "")
                 .replace(" ", "") for x in raw.iloc[i].tolist()]
        has_depth = any(("depth" in c) or ("md" in c and len(c) <= 6) for c in cells)
        gas_hits = sum(1 for c in cells
                       for tok in ("tg", "c1", "c2", "c3", "c4", "c5")
                       if tok in c)
        if has_depth and gas_hits >= 2:
            return i
    return None


def _excel_sheet_priority(xls) -> list:
    """按"像气测数据表"的程度给 sheet 名排序(索引序)。

    2026-09-29(TITAS-31): 气测数据常不在第一个 sheet —— 本井气测在 'Gas data' 表,
    第一个表是俄文日报 'Rus.'。优先级: gas data/气测数据 > 含 gas/气测(排除
    show/异常段——那是**区间**异常表, 不是逐点曲线) > 其余。
    """
    names = list(xls.sheet_names)

    def _rank(nm):
        l = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(nm).lower())
        if "gasdata" in l or ("气测" in str(nm) and "异常" not in str(nm)):
            return 0
        if (("gas" in l or "气测" in str(nm)) and "show" not in l
                and "异常" not in str(nm)):
            return 1
        return 2

    return sorted(range(len(names)), key=lambda k: (_rank(names[k]), k))


def _read_table_with_header(path: str) -> pd.DataFrame:
    """读取表格文件并自动探测表头行（兼容单行/双行(标题+列名)表头）。

    Excel 多表(2026-09-29, TITAS-31): 逐 sheet(按 _excel_sheet_priority 排序)
    探测"深度+气体组分"表头行, 命中即用; 全部未命中退回第一个表(旧行为)。
    """
    if not path.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_csv(path, encoding="utf-8", engine="python", header=None)
        # 在前 5 行内寻找"看起来像列名"的行（含 depth/md/c1/c2 之一）
        hdr_row = 0
        for i in range(min(5, len(raw))):
            cells = [str(x).lower().replace("\n", " ").replace("(", "").replace(")", "")
                     .replace(" ", "") for x in raw.iloc[i].tolist()]
            if any(tok in c for c in cells for tok in ("depth", "md", "c1", "c2")):
                hdr_row = i
                break
        df = raw.iloc[hdr_row + 1:].copy()
        df.columns = [str(x).strip() for x in raw.iloc[hdr_row].tolist()]
        return attach_gas_unit_hints(df)

    xls = pd.ExcelFile(path)
    _names = list(xls.sheet_names)
    for k in _excel_sheet_priority(xls):
        nm = _names[k]
        try:
            raw = pd.read_excel(xls, sheet_name=nm, header=None)
        except Exception as e:
            logger.debug(f"气测Excel读取表 '{nm}' 失败: {e}")
            continue
        i = _detect_gas_header_row(raw)
        if i is None:
            continue
        logger.info(f"气测Excel: 在表 '{nm}' 第{i+1}行找到表头")
        df = raw.iloc[i + 1:].copy()
        df.columns = [str(x).strip() for x in raw.iloc[i].tolist()]
        return attach_gas_unit_hints(df)
    # 兜底: 所有表均未命中 -> 第一个表按旧行为(前5行找 depth/md/c1/c2)
    logger.warning(f"气测Excel: 所有表{_names}均未命中气测表头, 退回第一个表")
    raw = pd.read_excel(xls, sheet_name=_names[0], header=None)
    hdr_row = 0
    for i in range(min(5, len(raw))):
        cells = [str(x).lower().replace("\n", " ").replace("(", "").replace(")", "")
                 .replace(" ", "") for x in raw.iloc[i].tolist()]
        if any(tok in c for c in cells for tok in ("depth", "md", "c1", "c2")):
            hdr_row = i
            break
    df = raw.iloc[hdr_row + 1:].copy()
    df.columns = [str(x).strip() for x in raw.iloc[hdr_row].tolist()]
    return attach_gas_unit_hints(df)


def _read_gas_show_sheet(path: str):
    """读取 Excel 的"气测异常段"表(Gas Show: From/To/峰值 区间数据)。

    用户(2026-09-29, TITAS-31): 该表是**去除单根峰干扰后**的气测异常段,
    比逐点曲线更可靠 —— 每行一个异常段 [From,To](m) + BGG/TG(%)/C1..(ppm) 峰值。
    返回 list[dict] 或 None(无此表/解析失败)。
    """
    if not str(path).lower().endswith((".xlsx", ".xls")):
        return None
    try:
        xls = pd.ExcelFile(path)
    except Exception:
        return None
    nm = next((n for n in xls.sheet_names
               if "show" in str(n).lower() or "异常段" in str(n)), None)
    if nm is None:
        return None
    try:
        raw = pd.read_excel(xls, sheet_name=nm, header=None)
    except Exception as e:
        logger.debug(f"气测异常段表 '{nm}' 读取失败: {e}")
        return None
    hdr = None
    for i in range(len(raw)):
        cells = [str(x).strip().upper() for x in raw.iloc[i].tolist()]
        if any(c.startswith("FROM") for c in cells) and any(c == "TO" for c in cells):
            hdr = i
            break
    if hdr is None:
        return None
    header = [str(x).strip().upper() for x in raw.iloc[hdr].tolist()]

    # 单位行捕获(用户2026-09-30): 表头下一行整行是单位('m MD'/'(%)'/'(ppm)') ——
    # 峰值单位据此换算统一ppm (Gas Show 表 BGG/TG 为 %, C1..nC5 为 ppm)
    unit_by_col = {}
    if hdr + 1 < len(raw):
        _urow = raw.iloc[hdr + 1].tolist()
        _ucells = [v for v in _urow
                   if pd.notna(v)
                   and re.sub(r"[^a-z%]", "", str(v).lower()) in ("ppm", "%")]
        if len(_ucells) >= 2:  # ≥2个纯单位格才认定是单位行
            for j, v in enumerate(_urow):
                if pd.isna(v) or j >= len(header):
                    continue
                s = re.sub(r"[^a-z%]", "", str(v).lower())
                if s in ("ppm", "%"):
                    unit_by_col[header[j]] = "ppm" if s == "ppm" else "%"

    def _num(row, col):
        if col not in header:
            return None
        try:
            v = float(row[header.index(col)])
            return v if np.isfinite(v) else None
        except (ValueError, TypeError, IndexError):
            return None

    def _num_ppm(row, col):
        """取峰值并按单位行换算为ppm: 提示为%的列×10000 (1%=10^4ppm)。"""
        v = _num(row, col)
        if v is None:
            return None
        return v * 10000.0 if unit_by_col.get(col) == "%" else v

    ivs = []
    for i in range(hdr + 1, len(raw)):
        row = raw.iloc[i].tolist()
        top, bot = _num(row, "FROM"), _num(row, "TO")
        if top is None or bot is None or bot <= top:
            continue  # 单位行(m MD)/空行/说明行
        ivs.append({"top": top, "bottom": bot,
                    "BGG": _num_ppm(row, "BGG"), "TG": _num_ppm(row, "TG"),
                    "C1": _num_ppm(row, "C1"), "C2": _num_ppm(row, "C2"),
                    "C3": _num_ppm(row, "C3")})
    if ivs:
        logger.info(f"气测异常段表 '{nm}': 提取 {len(ivs)} 个异常段 "
                    f"({min(v['top'] for v in ivs):.0f}-{max(v['bottom'] for v in ivs):.0f}m)")
        return ivs
    return None


def read_gas_text_table(path: str) -> pd.DataFrame:
    """读取 txt/dat 气测文本文件（制表符/逗号/空白分隔），自动定位表头行。

    示例(BET-1, 2026-10-08): Tab分隔, 首行即表头
      'MDEPTH (ft)\tROP (ft/hrs)\tWOB\tTRPM\tTGAS\tC1\tC2\tC3\tiC4\tnC4\tiC5\tnC5'
    表头行识别标准: 同时包含深度关键词(MD/DEPTH/DEPT/TDEP)与
    >=2 个气体组分关键词(TG/TGAS/C1..C5)。
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.readlines()
    hdr = None
    for i, line in enumerate(lines[:200]):
        fields = [x.strip().upper() for x in re.split(r"[\t,;]+", line.strip()) if x.strip()]
        if not fields:
            continue
        has_depth = any(any(k in fld for k in ("MD", "DEPTH", "DEPT", "TDEP"))
                        for fld in fields)
        n_gas = sum(1 for fld in fields
                    for k in ("TG", "TGAS", "TOTGAS", "C1", "C2", "C3", "C4", "C5")
                    if k in fld)
        if has_depth and n_gas >= 2:
            hdr = i
            break
    if hdr is None:
        hdr = 0
        logger.warning(f"气测文本文件未定位到表头行, 默认首行为表头: {path}")
    sep = "\t" if "\t" in lines[hdr] else ("," if "," in lines[hdr] else r"\s+")
    df = pd.read_csv(path, sep=sep, skiprows=hdr, engine="python",
                     encoding="utf-8-sig", header=0)
    logger.info(f"气测文本文件: 表头在第{hdr + 1}行(分隔符={'Tab' if sep == chr(9) else sep}), "
                f"{len(df.columns)}列, {len(df)}行")
    return df


def load_gas_file(path: str) -> pd.DataFrame:
    """读取气测文件（xls/xlsx/csv/txt/dat/las），返回归一化后的 DataFrame（含 MD 与 C1..C5）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls", ".csv"):
        df = _read_table_with_header(path)
    elif ext in (".txt", ".dat"):
        df = read_gas_text_table(path)
    elif ext == ".las":
        try:
            import lasio
            las = lasio.read(path)
            df = las.df().reset_index()
        except Exception as e:
            raise RuntimeError(f"读取 LAS 气测文件失败: {e}")
    else:
        raise ValueError(f"不支持的气测文件格式: {ext}")
    # 表头单位提示必须在列名归一化前取出(rename可能丢attrs), 换算时显式传入
    try:
        _gas_uhints = dict(df.attrs.get("gas_unit_hints") or {})
    except Exception:
        _gas_uhints = {}
    df = _normalize_columns(df)
    # 统一深度列名
    for dcol in ("MD", "DEPTH", "DEPT", "DEP", "TDEP"):
        if dcol in df.columns:
            if dcol != "MD":
                df = df.rename(columns={dcol: "MD"})
            break
    # 【2026-10-20 RASHIDPUR_13】重复列名防御：xls 尾部无名空列被读成重复
    # 'nan' 列（本例 14 列中 2 个 'nan'），取 df[c] 得到 DataFrame 而非
    # Series → pd.to_numeric 抛 "arg must be a list, tuple, 1-d array, or
    # Series" → 自动发现加载失败回退对话框（CLI 后台运行卡死）。
    # 去重（保留首列）后再数值化。
    if df.columns.duplicated().any():
        _dupcols = df.columns[df.columns.duplicated()].unique().tolist()
        logger.warning(f"气测数据存在重复列名，保留首列去重: {_dupcols}")
        df = df.loc[:, ~df.columns.duplicated()]
    # 关键修复(2026-09-14, 3-SPS-111D): lasio 对含非数值记号的行会把整列保留为字符串
    # (该井气测 LAS 85 列中 82 列为 str), 导致后续比值运算 TypeError("str"/"str")、
    # 气测解释整体失败被静默跳过。气测各道均为数值测量, 这里统一强制数值化(非数值置 NaN)。
    _n_coerced = 0
    for c in list(df.columns):
        if str(c).startswith("Unnamed"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = pd.to_numeric(df[c], errors="coerce")
            _n_coerced += 1
    if _n_coerced:
        logger.info(f"气测数据数值化: {_n_coerced}列 由字符串/混合类型转为数值")
    if "MD" in df.columns:
        df = df.dropna(subset=["MD"])
    # 丁烷/戊烷总量合成: iC4+nC4 才是 C4, iC5+nC5 才是 C5 (用户2026-09-14)
    # 2026-09-29(3-SPS-111D): 两个组分**都缺测**时总量须为 NaN, 不能 fillna(0) 相加
    #   得 0.0 —— 假"有值"会让下游 TG 合成的"全组分缺测"掩膜永不触发(共 0 点),
    #   断测语义又退化为 TG=0。
    for _tot, _parts in (("C4", ("IC4", "NC4")), ("C5", ("IC5", "NC5"))):
        if _tot not in df.columns and all(p in df.columns for p in _parts):
            _p0 = pd.to_numeric(df[_parts[0]], errors="coerce")
            _p1 = pd.to_numeric(df[_parts[1]], errors="coerce")
            _tot_s = _p0.fillna(0.0) + _p1.fillna(0.0)
            df[_tot] = _tot_s.where(_p0.notna() | _p1.notna())
            logger.info("气测组分合成: %s = %s + %s (两者均缺测 -> NaN)", _tot, _parts[0], _parts[1])

    # 全烃(TG)合成: 无可信全烃测量列(且绝不可取 TMPGAS 类泥浆温度)时按碳数加权合成
    # 2026-09-29(3-SPS-111D): 与 logInt.load_gas_data 同口径 —— 全部组分均缺测
    #   (断测/停钻)的行 TG=NaN, 保留"无数据"语义; compute_gas_anomaly 据此把
    #   ratio 置 NaN, 排除断测点对"相对异常占比"分母的污染。部分缺测行其余
    #   组分照常加权(缺项计 0)。
    if "TG" not in df.columns:
        _avail = {k: w for k, w in _TG_WEIGHTS.items() if k in df.columns}
        if _avail:
            _tg = pd.Series(0.0, index=df.index)
            _any = pd.Series(False, index=df.index)
            for _k, _w in _avail.items():
                _kv = pd.to_numeric(df[_k], errors="coerce")
                _tg = _tg + _w * _kv.fillna(0.0)
                _any = _any | _kv.notna()
            df["TG"] = _tg.where(_any)
            logger.info("气测全烃(TG)按碳数加权合成: %s (全组分缺测点 TG=NaN, 共 %d 点)",
                        "+".join(f"{w}*{k}" for k, w in _avail.items()),
                        int((~_any).sum()))

    # 单位统一为ppm (用户2026-09-30, TITAS-31): 阶段0按表头显式单位(列名自带/
    # 单位行)换算, 阶段1值域自洽性兜底 —— 必须在 T15/异常检测之前, 使异常门槛
    # (TG≥50ppm等)生效
    df = normalize_gas_units(df, unit_hints=_gas_uhints)

    # 计算总烃 T15（C1..C5 之和），缺失组分按 0 处理；异构体缺失时用总量列兜底
    comp = [c for c in ("C1", "C2", "C3", "IC4", "NC4", "IC5", "NC5") if c in df.columns]
    if "IC4" not in df.columns and "NC4" not in df.columns and "C4" in df.columns:
        comp.append("C4")
    if "IC5" not in df.columns and "NC5" not in df.columns and "C5" in df.columns:
        comp.append("C5")
    if comp:
        df["T15"] = df[comp].fillna(0).sum(axis=1)
    else:
        df["T15"] = 0.0
        logger.warning(f"气测文件缺少 C1..C5 组分列: {path}")
    # 关键修复(2026-09-22, TrakesKE-1): 归一化索引为 0..n-1。
    # _read_table_with_header 用 raw.iloc[hdr+1:] 取数据, 索引残留 Excel 行号
    # (本井为 2..1360)。而 Gas.py 的 star_interpretation 用 range(len(df)) 作
    # **位置**下标、却用 df.at[idx, ...] 按**标签**写入 —— 标签 0/1 不存在,
    # pandas 会**凭空追加 2 行**(1359->1361), 且 2..1360 号行的结果整体**错位 2 行**。
    # 后果: run_gas_constraint_for_well 里 df["ITP_traditional"]=itp.values 长度不符
    # 抛异常 -> **整个气测约束(含气测异常约束)被静默跳过**。
    df = df.reset_index(drop=True)
    return df


# ----------------------------------------------------------------------------
# 默认气测解释配置（与 Gas.py 传统图版法文档化阈值同源）
# ----------------------------------------------------------------------------
def _default_gas_config() -> dict:
    return {
        "pixler": {
            "oil":  {"C1C2": [1.5, 15], "C1C3": [1.5, 25], "C1C4": [1.5, 50]},
            "gas":  {"C1C2": [8.0, 40], "C1C3": [15.0, 90], "C1C4": [30.0, 250]},
        },
        "triangle": {
            "lr_offset": 0.0,
            "lr_factor": 1.0,
            "t14_threshold": 50.0,            # T14(=C1+C2+C3+iC4+nC4) 下限 ppm
            "heavy_hydrocarbon_threshold": 0.05,
            "c1t14_range": {"min": 0.0, "max": 1.0},
        },
        "three_h": {
            "oil": {"WH": [0.05, 25.0], "CH_min": 0.05, "BH_max_ratio": 2.0},
            "gas": {"WH": [0.05, 25.0]},
        },
        "star": {
            "rolling_window": 30,
            "quantile": 0.25,
            "similarity_threshold": 0.1,
            "core_params": ["C1T15", "C2T15", "C3T15", "C4T15", "C2_C3", "C1_C2"],
            "templates": {
                "OIL":  [0.60, 0.10, 0.05, 0.05, 2.0, 3.0],
                "GAS":  [0.90, 0.05, 0.02, 0.01, 1.0, 15.0],
                "WATER":[0.30, 0.20, 0.20, 0.20, 1.0, 1.5],
                "DRY":  [0.10, 0.10, 0.10, 0.10, 1.0, 1.0],
            },
        },
    }


def _compute_show(df: pd.DataFrame, window: int = 31) -> np.ndarray:
    """基于总烃(TG/T15)的滚动基线识别'气测异常(烃类显示)'。

    返回与 df 等长的 bool 数组：True 表示该深度存在明显烃类显示。
    方法：以 TG（或 T15）为中心滚动中位数作为背景基线，显示 = TG 超过基线 2 倍
    且绝对量 > 100 ppm。这正是'气测异常'的量化定义，也是约束要用的核心信号。
    """
    n = len(df)
    if "TG" in df.columns:
        raw = df["TG"].fillna(0).values.astype(float)
    elif "T15" in df.columns:
        raw = df["T15"].fillna(0).values.astype(float)
    else:
        return np.zeros(n, dtype=bool)
    s = pd.Series(raw)
    baseline = s.rolling(window, center=True, min_periods=3).median()
    base_med = float(s.median()) if s.median() == s.median() else 0.0
    baseline = baseline.fillna(base_med)
    baseline = np.where(baseline <= 0, max(base_med, 1.0), baseline)
    show = (raw > 2.0 * baseline) & (raw > 100.0)
    return show


def compute_gas_anomaly(df: pd.DataFrame,
                        baseline_window_m: float = 150.0,
                        rel_threshold: float = 1.5,
                        min_abs: float = 50.0) -> tuple:
    """同井**相对**气测异常度（用户 2026-09-14 口径）。

    问题背景
    --------
    原 `_compute_show` 用"TG > 2×局部滚动中位 且 TG > 100"判烃类显示，对
    气测背景高的井会普遍成立：3-SPS-111D 全井 6300-6980m 的 TG 中位在
    500~4900 ppm 间波动，Gas.py 图版法把 9829 点中的 6099 点(62%) 判成 OIL，
    于是"无气测异常→不是油气层"的约束全井只剔除了 1 段，形同虚设。

    用户经验："本井有气测数据，没有气测异常段应该是油层的可能性不大"。
    这里把"异常"定义为 **同井相对异常**——某深度的 TG 相对其上下围岩基线
    （慢变滚动中位）的抬升倍数，而非绝对量级：

        anom_ratio = TG / baseline(TG, 以深度为轴的 ±baseline_window_m/2 中位)
        异常       = anom_ratio >= rel_threshold 且 TG >= min_abs

    全井高背景会被基线吸收，只有"明显比围岩出气"的层才判异常。

    Args:
        df: 气测 DataFrame（需含 MD，以及 TG 或 T15）
        baseline_window_m: 基线窗口（深度，米），默认 150m（约一个储层段尺度）
        rel_threshold: 相对抬升倍数阈值，默认 1.5
        min_abs: 绝对量级下限（ppm），低于此为噪声，默认 50

    Returns:
        (anom_ratio: ndarray[float], is_anomaly: ndarray[bool])，与 df 等长
    """
    n = len(df)
    if n == 0:
        return np.zeros(0), np.zeros(0, dtype=bool)
    col = "TG" if "TG" in df.columns else ("T15" if "T15" in df.columns else None)
    if col is None:
        return np.zeros(n), np.zeros(n, dtype=bool)

    tg = pd.to_numeric(df[col], errors="coerce").values.astype(float)
    # 2026-09-29(3-SPS-111D): 断测/停钻段的 TG 是 NaN(源 LAS 的 NULL), 原实现
    #   fillna(0) 把"没有测量"冒充成"测量了且为 0" -> ratio=0 与真实无异常无法区分,
    #   下游占比的分母被断测点污染(6540-6590m 断测 63%, 有值中位 380 是背景 58 的
    #   6.5 倍, 却因占比被判"无异常"降级)。现保留 NaN 语义: ratio=NaN 表示无数据,
    #   is_anom=False(不强判异常); 下游占比用 notna() 排除断测点。
    if "MD" in df.columns:
        md = pd.to_numeric(df["MD"], errors="coerce").values.astype(float)
        _ok = np.isfinite(md)
        if not _ok.all():
            md = np.where(_ok, md, np.nan)
    else:
        md = np.arange(n, dtype=float)

    # 采样步长 -> 换算点数窗口（气测采样间隔不等，用中位步长近似）
    _d = np.diff(md)
    _d = _d[np.isfinite(_d) & (_d > 0)]
    step = float(np.median(_d)) if len(_d) else 0.25
    if not np.isfinite(step) or step <= 0:
        step = 0.25
    win = max(5, int(round(baseline_window_m / step)))

    s = pd.Series(tg)
    base = s.rolling(win, center=True, min_periods=max(3, win // 10)).median()
    _pos = tg[tg > 0]
    base = base.fillna(float(np.median(_pos)) if len(_pos) else 0.0)
    base_v = base.values.astype(float)
    base_v = np.where(base_v <= 0, np.nan, base_v)
    with np.errstate(invalid="ignore", divide="ignore"):
        anom_ratio = np.where(np.isfinite(base_v), tg / base_v, 0.0)
    # 断测点(tg=NaN)保持 NaN —— 不参与"有无异常"占比的分母(2026-09-29, 见函数头注释)
    anom_ratio = np.where(np.isfinite(tg), anom_ratio, np.nan)
    anom_ratio = np.nan_to_num(anom_ratio, nan=np.nan, posinf=0.0, neginf=0.0)
    is_anom = (anom_ratio >= float(rel_threshold)) & (tg >= float(min_abs))
    return anom_ratio, is_anom


def _builtin_interpret(df, show):
    """内置轻量气测解释（与 Gas.py 传统图版法同源）。

    逻辑：
      1) 无烃类显示(show=False) -> DRY（约束将据此剔除测井油气层）；
      2) 有显示 -> 用 C1-C5 比值(Pixler/3H)细分 GAS / OIL，甲烷主导判 GAS，
         含较多重烃判 OIL；仅当比值法无法判断时按甲烷占比默认 GAS/OIL。
    """
    n = len(df)
    itp = np.array(["DRY"] * n, dtype=object)
    if not show.any():
        return pd.Series(itp, index=df.index)

    c1 = df["C1"].fillna(0).values if "C1" in df.columns else np.zeros(n)
    c2 = df["C2"].fillna(0).values if "C2" in df.columns else np.zeros(n)
    c3 = df["C3"].fillna(0).values if "C3" in df.columns else np.zeros(n)
    ic4 = df["IC4"].fillna(0).values if "IC4" in df.columns else np.zeros(n)
    nc4 = df["NC4"].fillna(0).values if "NC4" in df.columns else np.zeros(n)
    ic5 = df["IC5"].fillna(0).values if "IC5" in df.columns else np.zeros(n)
    nc5 = df["NC5"].fillna(0).values if "NC5" in df.columns else np.zeros(n)

    def ratio(a, b):
        return np.where(b == 0, 0.0, a / np.where(b == 0, 1e-9, b))

    c1c2 = ratio(c1, c2)
    c1c3 = ratio(c1, c3)
    c1c4 = ratio(c1, ic4 + nc4)
    heav = c2 + c3 + ic4 + nc4 + ic5 + nc5
    tot5 = c1 + c2 + c3 + ic4 + nc4 + ic5 + nc5
    wh = np.where(tot5 == 0, 0.0, heav / np.where(tot5 == 0, 1e-9, tot5))
    t15 = df["T15"].fillna(0).values if "T15" in df.columns else tot5
    denom = np.where(t15 > 0, t15, 1.0)
    c1share = np.where(t15 > 0, c1 / denom, 0.0)

    # 比值法细分（仅对 show 点有效）
    is_oil = ((c1c2 >= 1.5) & (c1c2 <= 15) & (c1c3 >= 1.5) & (c1c3 <= 25) &
              (c1c4 >= 1.5) & (c1c4 <= 50) & (wh >= 0.05) & (wh <= 25))
    is_gas = ((c1c2 >= 8) & (c1c2 <= 40) & (c1c3 >= 15) & (c1c3 <= 90) &
              (c1c4 >= 30) & (c1c4 <= 250) & (wh >= 0.05) & (wh <= 25))
    label = np.where(c1share > 0.85, "GAS", "OIL")  # 甲烷主导默认气
    label = np.where(is_oil, "OIL", label)
    label = np.where(is_gas, "GAS", label)
    itp[show] = label[show]
    return pd.Series(itp, index=df.index)


def _try_gaspy_interpret(df: pd.DataFrame, well_name: str, tmp_dir: str):
    """尝试使用 Gas.py 的 TraditionalInterpretationModule 进行解释。成功返回 Series，失败返回 None。"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import Gas  # 延迟导入，避免拖慢主流程
        # Gas.py 的图版法用 np.where 预计算除法分支，若全局 np.seterr 设为 raise
        # 会触发 "division by zero"。此处临时放宽，避免误伤。
        old_err = np.seterr(all="ignore")
        cfg = _default_gas_config()
        cfg_path = os.path.join(tmp_dir, f"_gaspy_cfg_{well_name}.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        mod = Gas.TraditionalInterpretationModule(df.copy(), "REGULAR", tmp_dir, cfg_path)
        ok = mod.run_interpretation(well_name)
        np.seterr(**old_err)
        # 校验图版法是否真正生效（至少 pixler/triangle/3h 之一成功写入列）
        chart_cols = [c for c in ("ITP_pixler", "ITP_triangle", "ITP_3h")
                      if c in mod.data.columns]
        if ok and "ITP_traditional" in mod.data.columns and chart_cols:
            return mod.data["ITP_traditional"].copy(), True
        logger.warning(f"Gas.py 图版法未生效(仅STAR或无有效列)，回退内置实现")
        return None, False
    except Exception as e:
        logger.warning(f"Gas.py 气测解释失败，回退内置实现: {e}")
        return None, False


def interpret_gas_df(df: pd.DataFrame, well_name: str = "Unknown",
                     tmp_dir: str = ".") -> pd.Series:
    """对气测 DataFrame 逐点给出 ITP（GAS/OIL/DRY/...），DRY 等价于'无烃类显示'。

    优先级：
      1) 若 Gas.py 传统图版法能给出合理(非全 DRY)且自洽的结果，优先采用；
      2) 否则采用内置的、与 Gas.py 同源的轻量解释（以 TG 基线显示检测为门控）。
    """
    show = _compute_show(df)
    itp_builtin = _builtin_interpret(df, show)

    gp, used = _try_gaspy_interpret(df, well_name, tmp_dir)
    if gp is not None and (gp.astype(str).str.upper() != "DRY").any():
        logger.info("气测解释采用 Gas.py 传统图版法结果")
        return gp
    logger.info("气测解释采用内置轻量图版法（与 Gas.py 同源，TG 基线显示检测）")
    return itp_builtin


def find_gas_file(well_name: str, search_dirs=None) -> str:
    """按井名在常见目录中查找气测文件。匹配 gas_*.las / *Gas*.xls(x) / *gas*.csv / *GAS*.txt。

    2026-09-29(TITAS-31): 文件名无 'gas' 但含 'dgr'(检测气测读数, 如
    '147 Titas-31 (Deep) DGR 20260913.xlsx')同样收录; search_dirs 可传入
    主数据(LAS)所在目录 —— 气测文件常与 LAS 放同一目录。
    2026-10-08(BET-1): ①匹配数字前导零剥离 —— 井名'BET-1'也能匹配文件名
    'BET-001'(bet-001 与 bet-1 归一化后同为 bet1); ②search_dirs 递归搜索
    子目录(气测文件常放 supportdata/ 等子目录); ③支持 .txt/.dat 文本格式。
    """
    if not well_name:
        return None
    def _norm(s):
        s = re.sub(r"[^a-z0-9]", "", str(s).lower())
        # 前导零剥离: 'bet001'->'bet1' (井号/日期等数字段前导零无语义)
        s = re.sub(r"0+(\d)", r"\1", s)
        return s

    wn = _norm(well_name)
    if search_dirs is None:
        base = os.path.dirname(os.path.abspath(__file__))
        search_dirs = [
            os.path.join(base, "data", "uploads"),
            os.path.join(os.getcwd(), "data", "uploads"),
            os.getcwd(),
        ]
    import glob
    cands = []
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        # 递归搜索子目录 (BET-1 气测文件在 supportdata/ 下)
        for root, _dirs, _files in os.walk(d):
            for pat in ("*.xlsx", "*.xls", "*.csv", "*.las", "*.txt", "*.dat"):
                for p in glob.glob(os.path.join(root, pat)):
                    base_n = _norm(os.path.basename(p))
                    if (("gas" in base_n or "flair" in base_n or "dgr" in base_n)
                            and (wn in base_n or wn == "")):
                        cands.append(p)
    if not cands:
        return None
    # 优先文件名中包含完整井名的, 其次路径更短/更浅的(浅目录优先于深层子目录)
    cands.sort(key=lambda p: (wn not in _norm(os.path.basename(p)),
                              p.count(os.sep), len(p)))
    return cands[0]


def run_gas_constraint_for_well(well_name: str, gas_path: str,
                                main_md: pd.Series) -> dict:
    """对单井运行气测约束，返回对齐到主深度网格的气测解释结果。

    返回:
        {
          'itp': Series(与主 main_md 等长, 每点 ITP 标签, 无气测则为 None),
          'used_gaspy': bool,
          'file': str,
          'raw': DataFrame(气测原始+解释),
        }
    """
    df = load_gas_file(gas_path)
    if "MD" not in df.columns:
        logger.warning("气测数据缺少深度列，跳过气测约束")
        return {"itp": None, "used_gaspy": False, "file": gas_path, "raw": df}
    # 图版法解释(ITP)与"同井相对异常度"是两条**独立**证据, 前者失败不得连累后者。
    # 教训(2026-09-22, TrakesKE-1): Gas.py STAR 因索引非 0 基多出 2 行 -> 长度不符抛
    # 异常 -> 整个气测约束(含异常约束)被静默跳过, 表现为"传了气测文件但结论毫无变化"。
    itp = None
    try:
        itp = interpret_gas_df(df, well_name=str(well_name),
                               tmp_dir=os.path.dirname(os.path.abspath(gas_path)) or ".")
    except Exception as _e_itp:
        logger.warning(f"气测图版解释失败(仍在计算气测相对异常): {_e_itp}")
    if itp is not None:
        _vals = np.asarray(itp.values if hasattr(itp, "values") else list(itp), dtype=object)
        if len(_vals) != len(df):
            logger.warning(f"气测解释结果长度({len(_vals)})与气测数据({len(df)})不符, "
                           f"已对齐(多余截断/缺失补 DRY)")
            if len(_vals) > len(df):
                _vals = _vals[:len(df)]
            else:
                _vals = np.concatenate(
                    [_vals, np.full(len(df) - len(_vals), "DRY", dtype=object)])
        df["ITP_traditional"] = _vals
    else:
        df["ITP_traditional"] = "DRY"

    # 同井相对气测异常度(用户2026-09-14): 用"相对围岩抬升倍数"判异常, 替代
    # 绝对量级判据——高背景井(如 3-SPS-111D)用绝对判据会处处显示, 约束失效。
    _ar, _ia = compute_gas_anomaly(df)
    # ---- 气测异常段权威证据 (2026-09-29, TITAS-31) ----
    # Excel 的 'Gas Show' 表是**去除单根峰干扰后**的异常段(用户: "更好用")。
    # 段内点(±1m容差)强制标记异常: GAS_ANOM=1, RATIO 抬到门槛(1.5)之上 ——
    # 这是解释人员确认过的真实异常, 优先级高于逐点曲线自动计算。
    try:
        _ivs = _read_gas_show_sheet(gas_path)
    except Exception as _e_iv:
        _ivs = None
        logger.debug(f"气测异常段解析失败(忽略): {_e_iv}")
    if _ivs:
        _mdg = pd.to_numeric(df["MD"], errors="coerce").to_numpy(dtype=float)
        _in_iv = np.zeros(len(df), dtype=bool)
        for _iv in _ivs:
            _in_iv |= ((_mdg >= _iv["top"] - 1.0) & (_mdg <= _iv["bottom"] + 1.0))
        _n_boost = int(_in_iv.sum())
        if _n_boost:
            _ar = np.asarray(_ar, dtype=float)
            _ar[_in_iv] = np.where(np.isfinite(_ar[_in_iv]),
                                   np.maximum(_ar[_in_iv], 1.6), 1.6)
            _ia = np.asarray(_ia, dtype=float)
            _ia[_in_iv] = 1.0
            logger.info(f"气测异常段权威证据: {len(_ivs)} 段, 段内 {_n_boost}/{len(df)} 点"
                        f"强制标记为异常(GAS_ANOM=1)")
    df["GAS_ANOM_RATIO"] = _ar
    # 2026-09-29(3-SPS-111D): 断测点(ratio=NaN)的 flag 也保留 NaN —— bool→int 会把
    #   "没有测量"冒充成"测量了且无异常(0)", 污染 apply_gas_anomaly_constraint
    #   的占比分母(6540-6590m 断测 63%, 被整段判"无相对异常"而降级)。
    _ia_f = _ia.astype(float)
    _ia_f[~np.isfinite(np.asarray(_ar, dtype=float))] = np.nan
    df["GAS_ANOM"] = _ia_f

    main = pd.DataFrame({"MD": main_md.astype(float).values})
    main["_ord"] = np.arange(len(main))
    gas_sorted = df[["MD", "ITP_traditional", "GAS_ANOM_RATIO", "GAS_ANOM"]].copy()
    gas_sorted["MD"] = gas_sorted["MD"].astype(float)
    gas_sorted = gas_sorted.sort_values("MD")
    main = main.sort_values("MD").reset_index(drop=True)
    merged = pd.merge_asof(main, gas_sorted, on="MD", direction="nearest", tolerance=2.0)
    # 恢复调用方(主深度网格)的原始顺序, 避免主网格未排序时错位赋值
    merged = merged.sort_values("_ord").reset_index(drop=True)
    itp_aligned = merged["ITP_traditional"].reset_index(drop=True)
    return {"itp": itp_aligned if itp is not None else None,
            "anom": merged["GAS_ANOM"].reset_index(drop=True),
            "anom_ratio": merged["GAS_ANOM_RATIO"].reset_index(drop=True),
            "used_gaspy": bool(itp is not None),
            "file": gas_path, "raw": df}


def apply_gas_constraint(interpretation: pd.Series,
                         gas_itp: pd.Series = None,
                         show_fraction_min: float = 0.2,
                         anom_ratio: pd.Series = None,
                         anom_threshold: float = 1.5) -> (pd.Series, list):
    """气测约束：对测井解释为油/气层、但气测无明显烃类显示的层段，直接剔除（非储层）。

    以"连续油气层段"为单位判定：某层段内有气测显示的深度占比低于
    show_fraction_min 时，整段剔除（避免单点碎片化）。无气测数据的深度不参与判定。

    "有显示"的判定（2026-09-29 双通道, 3-SPS-111D）：
      ITP 标签非 DRY（图版法显示） **或** 同井相对异常 anom_ratio ≥ anom_threshold。
      背景：ITP 图版在气测绝对值偏低/断测多的井会整段判 DRY，而同井相对异常
      明显（6470-6510m ITP 98% DRY 但 ratio≥1.5 占比 45%）——只认 ITP 会把
      真油层误杀成非储层（用户: "厚层盐岩/硬石膏下孔隙合适+气测异常的段
      一般都是好的油气层"）。两通道任一命中即算"有显示"。

    参数:
        interpretation: 测井解释结论 Series（OIL/GAS/...）
        gas_itp:       对齐到同深度的气测解释结论 Series（GAS/OIL/DRY/...）；
                        None 表示无气测数据，不做约束。
        show_fraction_min: 层段内"有显示"深度最低占比阈值（默认 0.2）。
        anom_ratio:    对齐到同深度的同井相对异常倍数 Series（可 NaN=断测）。
        anom_threshold: 相对异常判异常的倍数阈值（默认 1.5，与
                        compute_gas_anomaly 的 rel_threshold 同口径）。

    返回:
        (new_interpretation, reasons)
        reasons: [(段起点index, 原结论, 原因说明)]
    """
    new = interpretation.copy()
    reasons = []
    if gas_itp is None:
        return new, reasons
    interp = interpretation.astype(str).str.upper().reset_index(drop=True)
    gi = gas_itp.astype(str).str.upper().reset_index(drop=True) if hasattr(gas_itp, "astype") else pd.Series([str(x).upper() for x in gas_itp]).reset_index(drop=True)
    ar = None
    if anom_ratio is not None and hasattr(anom_ratio, "notna"):
        ar = pd.to_numeric(anom_ratio, errors="coerce").reset_index(drop=True)
    n = len(interp)
    i = 0
    while i < n:
        lab = interp.iloc[i]
        if lab not in _HC_LABELS:
            i += 1
            continue
        j = i
        while j < n and interp.iloc[j] in _HC_LABELS:
            j += 1
        seg_idx = list(range(i, j))
        seg_itp = gi.iloc[seg_idx]
        present = seg_itp.notna() & (seg_itp != "NAN")
        if ar is not None:
            # 相对异常有测量(非 NaN)的点也计入"有数据"分母(断测点不算证据也不算反证)
            present = present | (ar.iloc[seg_idx].notna() & seg_itp.isna())
        if present.any():
            shown = present & (seg_itp != "DRY")
            if ar is not None:
                shown = shown | (ar.iloc[seg_idx] >= float(anom_threshold))
            frac = shown.sum() / present.sum()
            if frac < show_fraction_min:
                for k in seg_idx:
                    new.iloc[k] = "NonReservoir"
                reasons.append((i, lab, f"气测烃类显示占比{frac:.0%}<{show_fraction_min:.0%}->非储层"))
        i = j
    return new, reasons


_HC_POSSIBLE_MAP = {
    "OIL": "OIL_POSSIBLE", "GAS": "GAS_POSSIBLE", "CONDENSATE": "GAS_POSSIBLE",
    "OIL_POSSIBLE": "OIL_POSSIBLE", "GAS_POSSIBLE": "GAS_POSSIBLE",
    "OIL_WATER": "OIL_WATER", "GAS_WATER": "GAS_WATER",
}


def apply_gas_anomaly_constraint(interpretation: pd.Series,
                                 anom: pd.Series = None,
                                 sw: pd.Series = None,
                                 anom_fraction_min: float = 0.05,
                                 sw_water_min: float = 0.60,
                                 min_points: int = 8) -> (pd.Series, list):
    """气测**异常**约束：油气层段若同井相对气测无异常 -> 降级。

    用户经验(2026-09-14): "本井有气测数据，没有气测异常段应该是油层的可能性不大，
    比如 6668-6726m"。这是对原 `apply_gas_constraint`(以 ITP 标签是否 DRY 判定)
    的加强：原判据依赖绝对量级，高背景井会处处"有显示"，约束失效。

    降级分级（避免一刀切成非储层而丢失含烃信息）：
      - 段内含水特征明显(Sw 中位 >= sw_water_min) 或无含烃证据 -> WATER
      - 仍有含烃证据(Sw < sw_water_min) -> *_POSSIBLE（保留"可能含烃"，但不再
        报定为油气层——即用户所说"是油层的可能性不大"）

    以"连续油气层段"为单位判定；段内**有气测数据**的点中异常点占比 <
    anom_fraction_min 才降级，录井缺失段不参与判定（避免数据缺失误伤）。

    Args:
        interpretation: 测井解释结论
        anom: 对齐到同深度的气测异常标志(0/1)，无数据为 NaN
        sw: 对齐到同深度的含水饱和度(可选，用于决定降级到 WATER 还是 *_POSSIBLE)
        anom_fraction_min: 段内有数据点中"异常点"最低占比，默认 0.20
        sw_water_min: 判为水层的 Sw 门槛，默认 0.60
        min_points: 段最小点数（约 1m），过薄不判，默认 8

    Returns:
        (new_interpretation, reasons)；reasons: [(段起点index, 原结论, 新结论, 说明)]
    """
    new = interpretation.copy()
    reasons = []
    if anom is None:
        return new, reasons
    interp = interpretation.astype(str).str.upper().reset_index(drop=True)
    try:
        ai = pd.to_numeric(pd.Series(np.asarray(anom)).reset_index(drop=True),
                           errors="coerce")
    except Exception:
        return new, reasons
    n = len(interp)
    if len(ai) < n:
        return new, reasons
    sws = None
    if sw is not None:
        try:
            _s = pd.to_numeric(pd.Series(np.asarray(sw)).reset_index(drop=True),
                               errors="coerce")
            if len(_s) >= n:
                sws = _s
        except Exception:
            sws = None

    i = 0
    while i < n:
        lab = interp.iloc[i]
        if lab not in _HC_LABELS:
            i += 1
            continue
        j = i
        while j < n and interp.iloc[j] in _HC_LABELS:
            j += 1
        seg = list(range(i, j))
        if len(seg) >= int(min_points):
            seg_an = ai.iloc[seg]
            present = seg_an.notna()
            if present.any():
                frac = float(seg_an[present].mean())
                if frac < float(anom_fraction_min):
                    # 决定降级目标: 有含水特征 -> WATER; 否则保留"可能"
                    _tgt = _HC_POSSIBLE_MAP.get(lab, lab)
                    _swm = None
                    if sws is not None:
                        _sv = sws.iloc[seg]
                        _sv = _sv[_sv.notna()]
                        if len(_sv):
                            _swm = float(_sv.median())
                    if _swm is not None and _swm >= float(sw_water_min):
                        _tgt = "WATER"
                    for k in seg:
                        new.iloc[k] = _tgt
                    reasons.append((i, lab, _tgt,
                                    f"气测无相对异常(异常占比{frac:.0%}<"
                                    f"{float(anom_fraction_min):.0%}"
                                    + (f", Sw中位{_swm:.2f}" if _swm is not None else "")
                                    + ")"))
        i = j
    return new, reasons


# ============================================================
# 区域流体先验约束 (气层极罕见区域)
# ============================================================

_GAS_LABELS = {"GAS", "GAS_POSSIBLE", "CONDENSATE", "GAS_WATER"}
# 气测认可的"明确见气"标签
_GAS_EVIDENCE_LABELS = {"GAS", "CONDENSATE", "GAS_POSSIBLE"}
# 油层结论标签 (气田无油层政策的改写对象, 2026-09-30)
_OIL_LABELS = {"OIL", "OIL_POSSIBLE"}


def _apply_oil_field_prior(new: pd.Series, interp: pd.Series,
                           fluid_prior: dict, reasons: list) -> None:
    """纯气田流体先验 (2026-09-30, 孟加拉 Titas/Bakhrabad 气田)。

    用户口径: "本井是气井, 无油层"。与 gas_rarity=none(重油区禁判气层)严格对称:
    纯气田内油层结论不可信, 无条件改写:
        OIL          -> oil_to            (默认 GAS)
        OIL_POSSIBLE -> oil_possible_to   (默认 GAS_POSSIBLE)

    气测有/无显示的区分已由 apply_gas_constraint / apply_gas_anomaly_constraint
    在上游完成(无显示的油气层段已先被剔为非储层/降级), 本函数做区域级兜底;
    对无气测资料的井, 这是油层结论的唯一拦截手段。
    """
    oil_to = (fluid_prior.get("oil_to")
              or fluid_prior.get("oil_downgrade_to") or "GAS")
    oil_possible_to = (fluid_prior.get("oil_possible_to")
                       or fluid_prior.get("oil_downgrade_to") or "GAS_POSSIBLE")
    n = len(interp)
    i = 0
    while i < n:
        if interp.iloc[i] not in _OIL_LABELS:
            i += 1
            continue
        j = i
        while j < n and interp.iloc[j] in _OIL_LABELS:
            j += 1
        lab = interp.iloc[i]
        for k in range(i, j):
            cur = interp.iloc[k]
            new.iloc[k] = oil_to if cur == "OIL" else oil_possible_to
        reasons.append((i, lab, oil_to, "区域为纯气田(无油层), 油层结论按气改写"))
        i = j


def apply_fluid_prior(interpretation: pd.Series,
                      fluid_prior: dict = None,
                      gas_itp: pd.Series = None,
                      evidence_fraction_min: float = 0.2) -> (pd.Series, list):
    """区域流体先验约束: 在"气层极罕见"的区域, 无气测见气证据时不解释为气层。

    适用场景 (用户经验):
      - 乍得邦戈尔盆地 (Ximenia-5 等): 试油证实基本无油气层, 气层极罕见,
        且该井 LAS 无气测曲线 -> 全部气层结论降级。
      - 尼日尔特纳雷坳陷 (TrakesKE-1 等): 整坳陷气层极少, 有气测资料 ->
        仅在气测明确见气的层段保留气层结论。
      - 孟加拉 Titas/Bakhrabad 气田 (TITAS-31 等, 2026-09-30): 纯气田无油层,
        oil_rarity=none -> OIL→GAS / OIL_POSSIBLE→GAS_POSSIBLE。

    参数:
        interpretation: 测井解释结论 Series
        fluid_prior:    区域流体先验 dict (来自 rag_bridge.REGIONAL_PARAMETERS)
                        {gas_rarity, require_gas_evidence, gas_downgrade_to, note,
                         oil_rarity, oil_to, oil_possible_to, oil_downgrade_to}
        gas_itp:        对齐后的气测解释 Series; None 表示该井无气测资料
        evidence_fraction_min: 层段内"明确见气"深度最低占比 (默认 0.2)

    返回:
        (new_interpretation, reasons)
        reasons: [(段起点index, 原结论, 新结论, 原因)]
    """
    new = interpretation.copy()
    reasons = []
    if not fluid_prior:
        return new, reasons
    # 气层先验与油层先验相互独立, 各自生效 (2026-09-30 重构:
    # 原实现在 gas_rarity 缺失时整体早退, 导致纯气田油层政策无法单独启用)
    gas_rarity = str(fluid_prior.get("gas_rarity", "")).lower()
    has_gas_prior = (gas_rarity in ("high", "medium", "none")
                     and bool(fluid_prior.get("require_gas_evidence", True)))
    has_oil_prior = str(fluid_prior.get("oil_rarity", "")).lower() in ("none",)
    if not has_gas_prior and not has_oil_prior:
        return new, reasons

    downgrade_to = fluid_prior.get("gas_downgrade_to") or "OIL_POSSIBLE"
    rarity = gas_rarity
    interp = interpretation.astype(str).str.upper().reset_index(drop=True)
    if gas_itp is not None:
        gi = (gas_itp.astype(str).str.upper().reset_index(drop=True)
              if hasattr(gas_itp, "astype")
              else pd.Series([str(x).upper() for x in gas_itp]))
    else:
        gi = None

    n = len(interp)
    # 气层先验未启用时把游标置到末尾跳过气层循环(油层先验仍独立生效)
    i = n if not has_gas_prior else 0
    while i < n:
        if interp.iloc[i] not in _GAS_LABELS:
            i += 1
            continue
        j = i
        while j < n and interp.iloc[j] in _GAS_LABELS:
            j += 1
        seg_idx = list(range(i, j))
        lab = interp.iloc[i]

        if rarity == "none":
            # 无气层区域 (如委内瑞拉胡宁4超重油油藏): 重油高阻段是油不是气,
            # 无论有无气测证据, 一律禁止气层结论。GAS->OIL, GAS_POSSIBLE->OIL_POSSIBLE。
            gas_to = fluid_prior.get("gas_to", "OIL")
            gas_possible_to = fluid_prior.get("gas_possible_to", "OIL_POSSIBLE")
            seg_target = {}
            for k in seg_idx:
                cur = interp.iloc[k]
                seg_target[k] = gas_to if cur == "GAS" else gas_possible_to
                new.iloc[k] = seg_target[k]
            reasons.append((i, lab, seg_target.get(i, gas_to),
                            "区域为无气层重油油藏(高阻段为重油非气), 禁判气层"))
            i = j
            continue

        if rarity == "high":
            # 高稀有度区域 (如邦戈尔盆地/特纳雷坳陷): 实测气层极罕见、试油常无气。
            # 即便井上有气测显示, 气层结论也整体降级为 oil-possible,
            # 符合"用气测识别不出气层"的经验 (剩少量见气段作为 oil-possible 待证)。
            for k in seg_idx:
                new.iloc[k] = downgrade_to
            reasons.append((i, lab, downgrade_to,
                            "区域气层极罕见(高稀有度), 气层结论整体降级"))
            i = j
            continue

        if gi is None:
            # 无气测资料: 区域气层极罕见 -> 一律降级 (Ximenia-5 情形)
            for k in seg_idx:
                new.iloc[k] = downgrade_to
            reasons.append((i, lab, downgrade_to,
                            "区域气层极罕见且本井无气测资料, 无见气证据->降级"))
        else:
            seg = gi.iloc[seg_idx]
            present = seg.notna() & (seg != "NAN") & (seg != "NONE")
            if not present.any():
                # 该层段无气测覆盖 -> 同样按无证据处理
                for k in seg_idx:
                    new.iloc[k] = downgrade_to
                reasons.append((i, lab, downgrade_to,
                                "区域气层极罕见且该段无气测覆盖->降级"))
            else:
                evid = present & seg.isin(_GAS_EVIDENCE_LABELS)
                frac = evid.sum() / present.sum()
                if frac < evidence_fraction_min:
                    for k in seg_idx:
                        new.iloc[k] = downgrade_to
                    reasons.append((i, lab, downgrade_to,
                                    f"区域气层极罕见, 气测见气占比{frac:.0%}"
                                    f"<{evidence_fraction_min:.0%}->降级"))
        i = j

    if has_oil_prior:
        # 纯气田无油层政策 (2026-09-30, 孟加拉 Titas/Bakhrabad)
        _apply_oil_field_prior(new, interp, fluid_prior, reasons)
    return new, reasons
