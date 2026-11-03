# -*- coding: utf-8 -*-
"""
DlisTool —— DLIS 数据读取 / 偏移 / 导出（LAS / CSV / XLSX / 复制DLIS）。

API（被 dlis converter.py GUI 壳子调用）：
    tool = DlisTool()
    df, info = tool.load_dlis(fp)                 # 加载 DLIS → DataFrame + 井信息
    tool.modify_curve(curve_name, fn)             # 对 df[curve_name] 应用 fn(arr)
    tool.save_dlis(fp)                            # 原文件副本（dlisio 不支持回写曲线数据）
    tool.export_las(fp)                           # 导出 LAS 2.0
    tool.export_csv(fp)
    tool.export_xlsx(fp)
    succ, fail = tool.batch_convert(in_dir, out_dir, fmt, curve, offset)
    tool.config / tool.save_config()              # dlis_config.json 持久化

dlisio 说明（dlisio 1.0.4 + 兼容 0.x）：
    - 1.0.x: pf = dlisio.dlis.load(path)  → PhysicalFile → .logicalfiles()
    - 0.x  : with dlisio.load(path) as fs:  # 直接是 list[LogicalFile]
    - dlisio 不提供写回 DLIS 曲线数据的 API（只有读），save_dlis 只能做 copy。
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Callable, Tuple, List, Dict, Any, Optional

import numpy as np
import pandas as pd


# ────────────── dlisio 加载：兼容 0.x / 1.x ────────────── #
def _load_logical_files(path: str):
    """
    返回 (pf, list[dlisio LogicalFile])。
    dlisio 1.0.x: pf = dlisio.dlis.load() → PhysicalFile（可迭代 yield LogicalFile）
    dlisio 0.x  : dlisio.load() 直接返回 iterator[LogicalFile]，无 PhysicalFile
    返回 pf 是为了调用方在 finally 里 pf.close()（1.0.x 才需要）
    """
    try:
        import dlisio
    except ImportError as e:
        raise ImportError("需要安装 dlisio：pip install dlisio") from e

    ver = getattr(dlisio, "__version__", "0.0.0")
    major = int(ver.split(".")[0])

    if major >= 1:
        pf = dlisio.dlis.load(path)
        lfs = list(pf)          # PhysicalFile 可迭代 → LogicalFile
        return pf, lfs
    else:
        lfs = list(dlisio.load(path))
        return None, lfs


# ────────────── DLIS → DataFrame + 井信息 ────────────── #
def _extract_well_info(logical_files) -> Dict[str, Any]:
    """
    从 LogicalFile 提取井信息（dlisio 1.x/0.x 统一属性访问）。

    返回结构与 logInt._extract_las_info 一致:
        {'well': {...}, 'parameter': {...}}
    well 段: 井名、油田、公司等（扁平字典，值为 str）
    parameter 段: 额外元信息 + 各 Frame/Channel 描述
    """
    well: Dict[str, str] = {}
    parameter: Dict[str, str] = {}
    channel_info: Dict[str, Any] = {}

    for lf in logical_files:
        # fileheader（属性）
        fh = getattr(lf, "fileheader", None)
        if fh is not None:
            try:
                fn = str(getattr(fh, "filename", "") or getattr(fh, "id", "") or "")
                if fn:
                    well.setdefault("filename", fn)
            except Exception:
                pass

        # origins（属性 → list[Origin]）
        for o in getattr(lf, "origins", []) or []:
            try:
                # 井名
                for key, target in (
                    ("well_name", "well_name"),
                    ("name", "well_name"),
                    ("field_name", "field_name"),
                    ("company", "company"),
                    ("producer_name", "producer_name"),
                    ("run_nr", "run_nr"),
                    ("uom", "uom"),
                    ("api_number", "api_number"),
                ):
                    v = getattr(o, key, None)
                    if v is not None and str(v).strip():
                        well.setdefault(target, str(v).strip())
            except Exception:
                pass

        # channels → parameter.channel_info
        for ch in getattr(lf, "channels", []) or []:
            try:
                ch_name = str(getattr(ch, "name", "") or "").strip()
                if not ch_name:
                    continue
                ch_unit = str(getattr(ch, "units", "") or "").strip()
                ch_desc = str(getattr(ch, "long_name", "") or "").strip()
                channel_info[ch_name] = {
                    "unit": ch_unit,
                    "description": ch_desc,
                }
            except Exception:
                continue

        # frames → 索引类型
        for fr in getattr(lf, "frames", []) or []:
            try:
                idx_type = getattr(fr, "index_type", None)
                if idx_type is not None:
                    parameter.setdefault("index_type", str(idx_type).strip())
                    break
            except Exception:
                continue

    if channel_info:
        parameter["channel_info"] = channel_info

    # DLIS 不像 LAS 有显式 parameter 区，把 well 里未归类的杂项透传到 parameter
    for k, v in list(well.items()):
        if k in ("filename", "well_name", "field_name", "company",
                 "producer_name", "run_nr", "uom", "api_number"):
            continue
        parameter.setdefault(k, v)

    return {"well": well, "parameter": parameter}


def _frames_to_dataframe(logical_files) -> pd.DataFrame:
    """
    把所有 Frame 的 curves 合成一个 DataFrame。

    dlisio 1.0.x 重要事实：
    - PhysicalFile 可迭代 yield LogicalFile
    - LogicalFile.frames 是属性 → list[Frame]
    - Frame.channels 是属性 → list[Channel 描述符]（**Channel 不携带数据**）
    - Frame.curves(strict=True/False) 是方法 → **structured numpy ndarray**
      返回值有 .dtype.names，cv[field_name] 取每列
      strict=False 允许 Channel 重名（自动后缀 0,1,2...）
    - **数据唯读入口就是 frame.curves()**
    """
    frames_data: List[pd.DataFrame] = []
    _n_skip_multidim = 0      # 跳过的多维通道数（NMR 回波/直方图等，属正常）
    _n_frame_fail = 0         # 整帧构造失败数（异常，必须留痕）
    for lf in logical_files:
        frames = getattr(lf, "frames", None)
        if callable(frames):
            try:
                frames = frames()
            except Exception:
                frames = []
        frames = list(frames) if frames else []

        for fr in frames:
            cv = None
            try:
                cv = fr.curves(strict=True)
            except Exception:
                try:
                    cv = fr.curves(strict=False)
                except Exception:
                    continue
            if cv is None or not hasattr(cv, "dtype") or not getattr(cv.dtype, "names", None):
                continue
            try:
                curves_dict = {}
                for name in cv.dtype.names:
                    if name == "FRAMENO":
                        continue
                    arr = cv[name]
                    # 【2026-11 修复：SPS-108 全判泥岩根因】跳过多维通道
                    # （NMR 回波列 WF_* dim=8393、直方图 POR_HIST dim=200、
                    # T2_DIST dim=64、扫描波 dim=[1,11,763] 等）。旧逻辑对含
                    # 多维通道的帧直接 pd.DataFrame → 因非 1-D 数组整体抛错，
                    # except 静默 continue → 整帧（含 DTCO 声波、VOL_CALCITE/
                    # VOL_DOLOM/VOL_ILLITE 元素矿物等一维测井曲线）被丢弃 →
                    # 声波与各元素矿物体积全缺席，碳酸盐 must 因缺 DT 整条失败、
                    # 矿物主控因 VOL_* 缺失无法启用。仅保留 1-D 通道。
                    if getattr(arr, "ndim", 0) != 1:
                        # 【R58】多维通道跳过要留痕——此前静默 continue 是
                        # "声波/元素矿物整帧消失"的隐蔽根源之一。计数只记录、
                        # 不阻断（NMR 回波等本就该跳）。
                        _n_skip_multidim += 1
                        continue
                    curves_dict[name] = arr
                if not curves_dict:
                    continue
                df = pd.DataFrame(curves_dict)
            except Exception as _fe:
                # 【R58】帧构造失败必须留痕：此前 except: continue 会让整帧
                # 曲线无声消失（SPS-108 声波帧即如此），故障现场无从追查。
                _n_frame_fail += 1
                if _n_frame_fail <= 3:
                    import traceback as _tb
                    print("[DlisTool] 帧转 DataFrame 失败，该帧曲线被跳过: %s"
                          % _fe)
                    _tb.print_exc(limit=2)
                continue
            if len(df):
                frames_data.append(df)

    if _n_skip_multidim or _n_frame_fail:
        print("[DlisTool] 帧解析统计: 跳过多维通道 %d 个, 整帧失败 %d 个, "
              "成功帧 %d 个" % (_n_skip_multidim, _n_frame_fail,
                                len(frames_data)))

    if not frames_data:
        return pd.DataFrame()

    if len(frames_data) == 1:
        df = frames_data[0]
    else:
        # 多 frame 合并（找出 depth/md 列做对齐主键）
        def _depth_col(d: pd.DataFrame) -> Optional[str]:
            for cand in ("DEPTH", "depth", "MD", "md", "DEPT", "z"):
                if cand in d.columns:
                    return cand
            return None

        depth_cols = [_depth_col(d) for d in frames_data]
        has_depth = all(c is not None for c in depth_cols)
        if has_depth:
            # 【2026-11 修复】基准帧不再取"行数最多"的帧（密集 NMR/声波帧
            # 采样极细、行数远超常规测井帧，会反客为主把输出拉到数十万行、
            # 且常规曲线被稀疏并到该细网格）。改为取"核心测井曲线覆盖最多"
            # 的帧作基准（通常是常规测井主曲线帧：GR/RHOB/NPOR/CAL/RT），
            # 输出保持常规测井深度网格，其余帧（声波/元素/NMR）并回该网格。
            _core = ('GR', 'RHOB', 'DEN', 'CNL', 'NPOR', 'CAL', 'RT', 'PE',
                     'DEPTH', 'MD', 'DEPT')
            def _core_score(d):
                cols = set(str(c).upper() for c in d.columns)
                return sum(1 for c in _core if c in cols)
            base_i = max(range(len(frames_data)),
                         key=lambda i: _core_score(frames_data[i]))
            base = frames_data[base_i].sort_values(depth_cols[base_i]).reset_index(drop=True)
            base_dep = depth_cols[base_i]
            for i, df_i in enumerate(frames_data):
                if i == base_i:
                    continue
                key = depth_cols[i]
                df_s = df_i.rename(columns={key: base_dep}).sort_values(base_dep)
                extra_cols = [c for c in df_s.columns
                              if c != base_dep and c not in base.columns]
                if extra_cols:
                    # 【2026-11 修复】merge_asof 加容差：避免被合并帧（如声波
                    # 帧）深度范围不覆盖基帧时，把所有基帧点外推成端点常数。
                    # 容差取基帧深度步长中位数的 5 倍（留足插值余量），超出
                    # 容差的点得 NaN —— 物理上即"该深度无此曲线"，由下游 NA
                    # 容错处理，而非伪造常数。
                    _step = pd.Series(base[base_dep]).diff().median()
                    _tol = float(_step) * 5.0 if pd.notna(_step) and _step > 0 else None
                    base = pd.merge_asof(
                        base,
                        df_s[[base_dep] + extra_cols].drop_duplicates(base_dep),
                        on=base_dep, direction="nearest", tolerance=_tol)
            df = base
        else:
            df = pd.concat(frames_data, ignore_index=True)

    # 深度列置顶（统一叫 DEPTH）
    for cand in ("DEPTH", "depth", "MD", "md", "DEPT", "z"):
        if cand in df.columns and cand != "DEPTH":
            df = df.rename(columns={cand: "DEPTH"})
            break
    # 深度列转数值、去重复
    if "DEPTH" in df.columns:
        df["DEPTH"] = pd.to_numeric(df["DEPTH"], errors="coerce")
        df = df.sort_values("DEPTH").reset_index(drop=True)
    return df


# ────────────── LAS 构造 ────────────── #
def _dataframe_to_las(df: pd.DataFrame, well_info: Dict[str, Any]):
    """
    pd.DataFrame → lasio.LASFile（LAS 2.0 格式）。
    lasio 0.32 well section 标准 mnemonics:
        WELL, COMP, FLD, LOC, PROV, CNTY, STAT, CTRY, SRVC, DATE, STRT, STOP, STEP, NULL
    不在标准列表里的额外信息用 las.well.add_item() 追加 HeaderItem。
    """
    import lasio

    STANDARD_ITEMS = {
        "well":      ("WELL",  "",    "井名"),
        "company":   ("COMP",  "",    "公司"),
        "field":     ("FLD",   "",    "油田"),
        "country":   ("CTRY",  "",    "国家"),
        "producer":  ("SRVC",  "",    "来源"),
        "run_nr":    ("LOC",   "",    "井/运行编号"),
    }

    las = lasio.LASFile()
    las.well.NULL.value = -9999.25

    for info_key, (mnemonic, unit, desc) in STANDARD_ITEMS.items():
        val = well_info.get(info_key) or ""
        try:
            las.well.set_item_value(mnemonic, val)
        except Exception:
            try:
                las.well[mnemonic].value = val
            except Exception:
                pass

    # lasio 0.32 SectionItems 继承 list，直接 append HeaderItem 加额外项
    try:
        from lasio import HeaderItem
        for k, v in well_info.items():
            if k in STANDARD_ITEMS:
                continue
            try:
                las.well.append(HeaderItem(str(k).upper()[:8], str(v), "", k))
            except Exception:
                pass
    except Exception:
        pass

    # 深度
    if "DEPTH" in df.columns:
        dep = df["DEPTH"].to_numpy(dtype=float)
        las.well.STRT.value = float(dep[0]) if len(dep) else 0.0
        las.well.STOP.value = float(dep[-1]) if len(dep) else 0.0
        if len(dep) > 1:
            step = float(np.median(np.diff(dep)))
            las.well.STEP.value = round(step, 6)
        # 把 DEPTH 塞到 las.index（深度驱动）
        try:
            las.index = dep
        except Exception:
            pass

    # 曲线（lasio 0.32 用 append_curve(mnemonic, unit, array, desc)）
    for col in df.columns:
        if col == "DEPTH":
            continue
        arr = df[col].to_numpy(dtype=float)
        arr = np.where(np.isfinite(arr), arr, np.nan)
        try:
            las.append_curve(col, "", arr)
        except TypeError:
            # 老版 lasio 可能签名不同
            try:
                las.append_curve(col, arr)
            except Exception:
                pass
        except Exception:
            pass

    return las


# ═══════════════════════════════════════════════════════════════════════════ #
class DlisTool:
    """DLIS 文件读取 / 曲线偏移 / 多格式导出。"""

    CONFIG_FILENAME = "dlis_config.json"
    DEFAULT_CONFIG: Dict[str, Any] = {
        "default_format": "las",
        "batch_curve": "",
        "batch_offset": None,
        "last_in_dir": "",
        "last_out_dir": "",
    }

    def __init__(self, config_path: Optional[str] = None):
        self._config_path = Path(config_path) if config_path else (
            Path(__file__).resolve().parent / self.CONFIG_FILENAME)
        self.config: Dict[str, Any] = dict(self.DEFAULT_CONFIG)
        self.load_config()

        self.df: Optional[pd.DataFrame] = None
        self.info: Dict[str, Any] = {}
        self._source_path: Optional[str] = None

    # ──────── 配置 ──────── #
    def load_config(self) -> None:
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.config.update(loaded)
            except Exception:
                pass

    def save_config(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    # ──────── 核心操作 ──────── #
    def load_dlis(self, fp: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        fp = str(fp)
        if not os.path.isfile(fp):
            raise FileNotFoundError(fp)
        pf, logical_files = _load_logical_files(fp)
        try:
            df = _frames_to_dataframe(logical_files)
            info = _extract_well_info(logical_files)
        finally:
            if pf is not None:
                try:
                    pf.close()
                except Exception:
                    pass
        self.df = df
        self.info = info
        self._source_path = fp
        return df, info

    def modify_curve(self, curve_name: str, fn: Callable[[np.ndarray], np.ndarray]) -> None:
        """对 df[curve_name] 整体应用变换 fn(arr) → new_arr（原地修改）。"""
        if self.df is None:
            raise RuntimeError("请先 load_dlis()")
        if curve_name not in self.df.columns:
            raise KeyError(f"曲线不存在: {curve_name}，可用: {list(self.df.columns)}")
        arr = self.df[curve_name].to_numpy(dtype=float)
        self.df[curve_name] = fn(arr)

    # ──────── 导出 ──────── #
    def save_dlis(self, fp: str) -> None:
        """
        把当前 df（含 modify_curve 的偏移）写回全新 DLIS 文件。
        优先用 dliswriter 真实回写；失败则 fallback 到原文件副本（并提示）。
        """
        if self.df is None:
            raise RuntimeError("请先 load_dlis()")

        # ── 尝试 dliswriter 真实回写 ──
        try:
            self._write_dlis_via_dliswriter(fp)
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"[DlisTool] dliswriter 回写失败({e!s})，fallback 到原文件副本")

        # ── fallback: 原文件副本 ──
        if self._source_path is None:
            raise RuntimeError("无原文件可复制")
        shutil.copy2(self._source_path, fp)
        print(f"[DlisTool] DLIS 副本已写入: {fp}  （注意：这是原文件副本，"
              f"此前 modify_curve 的偏移不会体现在副本中）")

    def _write_dlis_via_dliswriter(self, fp: str) -> None:
        """用 dliswriter 把 self.df 写为全新 DLIS 文件。"""
        import dliswriter

        dlis = dliswriter.DLISFile()
        lf = dlis.add_logical_file()

        # Origin（dliswriter 要求至少一个）
        origin_kw = {}
        well = self.info.get("well") or self.info.get("well_name") or self.info.get("name") or "UNKNOWN"
        field = self.info.get("field") or self.info.get("field_name") or ""
        company = self.info.get("company") or self.info.get("producer") or ""
        try:
            lf.add_origin("ORIGIN", well_name=str(well), field_name=str(field),
                          company=str(company))
        except Exception:
            try:
                lf.add_origin("ORIGIN", well_name=str(well))
            except Exception:
                pass

        # 找深度列（作为 Frame index + spacing）
        dep_col = None
        for cand in ("DEPTH", "DEPT", "MD", "md", "depth", "z", "Z"):
            if cand in self.df.columns:
                dep_col = cand
                break

        # 构造 Channel（所有 df.columns，不含 FRAMENO）
        channels = []
        index_type = "BOREHOLE-DEPTH" if dep_col else None
        for col in self.df.columns:
            if col.upper() == "FRAMENO":
                continue
            arr = self.df[col].to_numpy(dtype=float)
            arr = np.where(np.isfinite(arr), arr, np.nan)
            try:
                ch = lf.add_channel(str(col)[:8], data=arr)
                channels.append(ch)
            except Exception:
                # 可能 mnemonic 太长 → 截断
                try:
                    ch = lf.add_channel(str(col)[:7], data=arr)
                    channels.append(ch)
                except Exception:
                    continue

        if not channels:
            raise RuntimeError("没有可用的曲线写入 DLIS")

        # Frame
        spacing = None
        if dep_col and len(self.df) > 1:
            spacing = float(np.median(np.diff(self.df[dep_col].dropna())))
            if not np.isfinite(spacing) or spacing <= 0:
                spacing = None
        try:
            lf.add_frame("FRAME", channels=channels,
                         index_type=index_type, spacing=spacing)
        except TypeError:
            lf.add_frame("FRAME", channels=channels, index_type=index_type)

        # 写文件
        dlis.write(str(fp))
        print(f"[DlisTool] DLIS 已写回（dliswriter）: {fp}  （{len(channels)} 条曲线）")

    def export_las(self, fp: str) -> None:
        """导出 LAS 文件。lasio 0.32 write 在某些场景有 bug，fallback 到手动 LAS 2.0 文本。"""
        if self.df is None:
            raise RuntimeError("请先 load_dlis()")
        try:
            las = _dataframe_to_las(self.df, self.info)
            try:
                las.write(fp, version=1.2)
            except TypeError:
                las.write(fp)
            return
        except Exception:
            pass
        # ── fallback: 手动拼 LAS 2.0 文本 ──
        self._export_las_text(fp)

    def _export_las_text(self, fp: str) -> None:
        """最简 LAS 2.0 文本（lasio 不可用时的兜底）。"""
        if self.df is None:
            return
        with open(fp, "w", encoding="utf-8") as f:
            f.write("~Version Information\n")
            f.write("VERS                          2.0 : CWLS LOG ASCII STANDARD - VERSION 2.0\n")
            f.write("WRAP                           NO : ONE LINE PER DEPTH STEP\n")
            f.write("~Well Information\n")
            f.write("STRT                           %.6f : START DEPTH\n" % float(self.df["DEPTH"].iloc[0])
                    if "DEPTH" in self.df.columns else 0)
            f.write("STOP                           %.6f : STOP DEPTH\n" % float(self.df["DEPTH"].iloc[-1])
                    if "DEPTH" in self.df.columns else 0)
            if "DEPTH" in self.df.columns and len(self.df) > 1:
                step = float(self.df["DEPTH"].diff().dropna().median())
                f.write("STEP                           %.6f : STEP\n" % step)
            f.write("NULL                         -9999.2500 : NULL VALUE\n")
            f.write("WELL                           %s : WELL NAME\n" % (self.info.get("well") or "UNKNOWN"))
            f.write("COMP                           %s : COMPANY\n" % (self.info.get("company") or ""))
            f.write("FLD                            %s : FIELD\n" % (self.info.get("field") or ""))
            f.write("SRVC                           %s : SERVICE COMPANY\n" % (self.info.get("producer") or ""))
            f.write("~Curve Information\n")
            col_info = []
            if "DEPTH" in self.df.columns:
                col_info.append(("DEPTH", "", "DEPTH"))
            for col in self.df.columns:
                if col != "DEPTH":
                    col_info.append((col, "", col))
            for mn, unit, desc in col_info:
                f.write("%-8s  %-8s  %s\n" % (mn[:8], (unit or "")[:8], desc))
            f.write("~Ascii\n")
            for _, row in self.df.iterrows():
                parts = []
                for col in self.df.columns:
                    v = row[col]
                    if pd.isna(v):
                        parts.append("-9999.25")
                    else:
                        parts.append("%.6f" % float(v))
                f.write(" ".join(parts) + "\n")

    def export_csv(self, fp: str) -> None:
        if self.df is None:
            raise RuntimeError("请先 load_dlis()")
        self.df.to_csv(fp, index=False)

    def export_xlsx(self, fp: str) -> None:
        if self.df is None:
            raise RuntimeError("请先 load_dlis()")
        self.df.to_excel(fp, index=False, engine="openpyxl")

    # ──────── 批量 ──────── #
    def batch_convert(
        self,
        in_dir: str,
        out_dir: str,
        fmt: str = "las",
        curve_name: Optional[str] = None,
        offset: Optional[float] = None,
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        批量转换：遍历 in_dir 下所有 .dlis / .DLIS 文件。
        succ: 成功输出文件的绝对路径列表
        fail: [(源文件, 错误信息)] 列表
        """
        in_dir = Path(in_dir)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        succ: List[str] = []
        fail: List[Tuple[str, str]] = []

        if fmt not in ("las", "csv", "xlsx", "dlis"):
            raise ValueError(f"不支持的输出格式: {fmt}（las / csv / xlsx / dlis）")

        for src in sorted(in_dir.rglob("*")):
            if src.suffix.lower() != ".dlis":
                continue
            try:
                df, info = self.load_dlis(str(src))
                if curve_name and curve_name in df.columns and offset is not None:
                    self.modify_curve(curve_name, lambda arr: arr + float(offset))

                stem = src.stem
                if fmt == "las":
                    out = out_dir / f"{stem}.las"
                    self.export_las(str(out))
                elif fmt == "csv":
                    out = out_dir / f"{stem}.csv"
                    self.export_csv(str(out))
                elif fmt == "xlsx":
                    out = out_dir / f"{stem}.xlsx"
                    self.export_xlsx(str(out))
                else:  # dlis
                    out = out_dir / f"{stem}.dlis"
                    self.save_dlis(str(out))
                succ.append(str(out))
            except Exception as e:
                fail.append((str(src), str(e)))

        return succ, fail
