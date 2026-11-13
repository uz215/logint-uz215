"""
dlis_tool.py  (standalone 转换器)
功能：读取 DLIS、修改曲线、导出 DLIS / LAS / CSV / XLSX；支持单文件 + 批量文件夹处理；json 配置持久化。

【2026-11-03 修复 · 与 SPS-108 全判泥岩同源的根因】
原实现 load_dlis 只取第一个 LogicalFile 的第一帧（frames[0]），且直接
pd.DataFrame(curves_data) 不做多维通道（NMR 回波 / 直方图 / T2 分布）跳过处理。
SPS-108 这类多 LogicalFile / 多帧 / 含多维通道的井，声波(DTCO)、元素矿物
(VOL_CALCITE 等) 会整段静默丢失 —— 与 logInt 主流程此前"全判泥岩"是同一类缺陷。

现改为继承 logint.dlis_tool.DlisTool（已修复、已验证的健壮实现），复用其：
  - 多 LogicalFile / 多帧遍历
  - 多维通道跳过（ndim != 1）
  - 核心曲线覆盖优选基准帧 + 其余帧按深度 merge
  - 曲线名标准化（DTCO→DT、NPOR→CNL …）
  - dliswriter 真实回写 + 兜底副本
本文件仅保留独立的 config 路径与向后兼容属性（well_info / depth_col）。
"""
from pathlib import Path
from logint.dlis_tool import DlisTool as _BaseDlisTool


class DlisTool(_BaseDlisTool):
    def __init__(self, config_path=None):
        if config_path is None:
            # 独立运行时的配置位置：<src 父目录>/config/dlis_config.json
            config_path = Path(__file__).resolve().parent.parent / "config" / "dlis_config.json"
        super().__init__(config_path=str(config_path))
        # 向后兼容：旧调用可能直接读 self.well_info / self.depth_col
        self.well_info = self.info
        self.depth_col = self._depth_col_name(self.df) if self.df is not None else ""

    def load_dlis(self, filepath):
        """读取 DLIS（委托给已修复的基类实现），并更新向后兼容属性。"""
        df, info = super().load_dlis(filepath)
        self.well_info = info
        self.depth_col = self._depth_col_name(df)
        return df, info

    @staticmethod
    def _depth_col_name(df):
        if df is None:
            return ""
        for c in ("MD", "DEPT", "DEPTH", "DEPTH_M"):
            if c in df.columns:
                return c
        for c in df.columns:
            cl = c.lower()
            if "depth" in cl or cl in ("md", "dept"):
                return c
        return df.index.name or ""


if __name__ == "__main__":
    t = DlisTool()
    print(t.config)
