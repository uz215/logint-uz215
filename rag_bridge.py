# -*- coding: utf-8 -*-
"""
RAG桥接层 - 连接 logInt 和 logKnow，实现知识检索增强解释

功能:
  1. 连接 logKnow 知识库 (内置模式 / API模式)
  2. 为 logInt 提供知识库上下文注入
  3. 基于曲线特征的参数推荐
  4. 相似历史案例检索
  5. LLM 辅助解释问答

用法:
    # 嵌入式模式 (logKnow 在同一进程)
    bridge = RAGBridge(embedded=True)
    bridge.connect()
    context = bridge.retrieve_context(well_name="X-1", formation="砂岩")

    # API模式 (logKnow 以 HTTP 服务运行)
    bridge = RAGBridge(api_url="http://localhost:8000")
    context = bridge.retrieve_context(well_name="X-1")
"""

import os
import re
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("rag_bridge")


# ============================================================
# 区域地质参数权威表 (REGIONAL_PARAMETERS)
# ------------------------------------------------------------
# 解决"参数推荐不遵循地区规律"问题: 知识库文本检索 + 正则抽取
# 无法稳定拿到区域 Rw, 导致始终落到默认 0.05 Ω·m (高矿化度背景),
# 对非洲等中低矿化度地区明显错误。
#
# 本表为人工校核的权威区域参数, 优先于文本抽取与默认值。
# 匹配优先级: 井名 > 区域 > 层位 (子串匹配, 大小写不敏感)。
# 新增区域只需在此追加条目即可。
# ============================================================
REGIONAL_PARAMETERS = {
    # 非洲 / 西非 / 乍得(邦戈尔-多索)盆地 —— 用户提供权威数据
    "africa_bongor": {
        "name": "非洲(乍得邦戈尔/多索盆地)",
        # 井名/区域/层位别名 (子串匹配)
        "aliases": ["ximenia", "ronier", "kedeni", "mimosa",
                     "非洲", "西非", "乍得", "chad", "bongor", "邦戈尔",
                     "doseo", "多索"],
        "a": 0.90, "m": 1.85, "n": 2.0,          # 西非浊积砂岩 (海外区域参数表)
        # 分层地层水电阻率 (Ω·m) —— 依据用户提供实测/经验
        "rw_by_formation": {"Ronier": 6.2, "Kedeni": 3.8,
                             "Mimosa": 3.1, "P": 2.6},
        "rw": 3.9,                                # 区域代表值(各层 2.6~6.2 的均值, 供单值解释)
        "rho_matrix": 2.65, "dt_matrix": 55.5,
        "confidence": 0.9,
        # ---- 流体先验: 区域油气分布经验约束 ----
        # 依据: 邦戈尔盆地已钻井试油结果, 气层极罕见(仅极少数井的部分井段见少量气),
        #       测井电性(高阻+低密度)易将致密层/钙质层/低阻油层误判为气层。
        "fluid_prior": {
            "gas_rarity": "high",        # high=气层极罕见, medium, low/none
            "oil_dominant": True,        # 以油层为主
            "require_gas_evidence": True,  # 判气层必须有气测/试油证据
            "gas_downgrade_to": "OIL_POSSIBLE",  # 无证据时的降级结论
            "note": ("邦戈尔盆地试油证实气层极罕见(如 Ximenia-5 试油无油气层)。"
                     "无气测异常或无试油见气证据时, 不解释为气层, "
                     "降级为可能油层/水层。"),
        },
        "source": "区域测井解释经验库(用户提供, 邦戈尔盆地)",
        "note": ("地层水电阻率随层位变化显著: Ronier 6.2 / Kedeni 3.8 / "
                 "Mimosa 3.1 / P 2.6 Ω·m。单值解释取各层均值 3.9 Ω·m; "
                 "如需分层解释, 应按层位深度段分别赋值对应 Rw。"
                 "流体先验: 本盆地气层极罕见, 判气层需气测/试油证据。"),
    },
    # 非洲 / 西非 / 尼日尔(特纳雷 Tenere 盆地) —— 用户提供 Pickett 交会图计算值
    "niger_treakeske": {
        "name": "尼日尔(特纳雷盆地 TreakesKE-1 井)",
        # 井名/区域别名 (子串匹配, 大小写不敏感)
        "aliases": ["trakeske", "trakes", "trakes ke", "treakeske", "treakes",
                    "尼日尔", "niger", "tenere", "特纳雷"],
        "a": 1.0, "m": 1.7, "n": 1.8,          # Pickett 交会图(用户提供)
        # 分层地层水电阻率 (Ω·m)
        "rw_by_formation": {"E2": 0.2, "E5": 1.0},
        "rw": 0.45,                             # 区域代表值(各层几何均值, 供单值解释)
        # 分层深度窗口: 按 MD 逐段应用各自 m/n/Rw (用户提供顶底深度)
        "formation_windows": [
            {"formation": "E2", "top": 975.0,  "bottom": 1050.0,
             "m": 1.85, "n": 1.8,  "Rw": 0.2},
            {"formation": "E5", "top": 1205.0, "bottom": 1301.0,
             "m": 1.47, "n": 1.59, "Rw": 1.0},
        ],
        "rho_matrix": 2.65, "dt_matrix": 55.5,
        "confidence": 0.9,
        # ---- 流体先验: 特纳雷(Tenere)坳陷气层极少 ----
        # 依据: TrakesKE-1 试油无气层, 整个坳陷气层极少; 该井有气测资料可交叉验证。
        "fluid_prior": {
            "gas_rarity": "high",
            "oil_dominant": True,
            "require_gas_evidence": True,
            "gas_downgrade_to": "OIL_POSSIBLE",
            "note": ("Tenere 坳陷试油证实气层极少(TrakesKE-1 试油无气层)。"
                     "该井有气测资料, 应以气测异常为判气层前置条件; "
                     "无气测异常时不解释为气层。"),
        },
        "source": "Pickett 交会图计算(用户提供, TreakesKE-1)",
        "note": ("分层参数差异显著: E2(975-1050m) m=1.75-1.94, n=1.59-2, Rw=0.2; "
                 "E5(1205-1301m) m=1.47, n=1.59, Rw=1.0 Ω·m。已按深度窗口逐段应用; "
                 "窗外井段用代表值 Rw≈0.45, m=1.7, n=1.8。"
                 "流体先验: 本坳陷气层极少, 判气层需气测异常支撑。"),
    },
    # 委内瑞拉 胡宁4(JUNIN 4)超重油油藏 —— 用户确认: 重油油藏, 无气层
    "venezuela_huin4_heavyoil": {
        "name": "委内瑞拉(胡宁4区块, 超重油油藏)",
        # 井名/区域别名 (子串匹配, 大小写不敏感)
        "aliases": ["izz", "venezuela", "委内瑞拉", "huin4", "huin 4",
                    "胡宁4", "junin4", "junin 4", "重油", "超重油",
                    "heavy oil", "extra heavy", "orimulsion"],
        "a": 1.0, "m": 2.0, "n": 2.0,           # 暂用常规值(待 Pickett 标定)
        "rw": 0.05,                              # 默认(待实测核实; 重油藏地层水多为高矿化度)
        "rho_matrix": 2.65, "dt_matrix": 55.5,
        "confidence": 0.5,
        # ---- 流体先验: 超重油油藏, 无气层 ----
        # 依据: 用户确认"委内瑞拉是明显的重油油藏, 没有气层"(IZZ0232 等井)。
        #       重油/超重油高阻段是高粘度油而非气, 判气层应转为油层。
        #       储层岩性以极粗粒砂岩(砾石)为主。
        "fluid_prior": {
            "gas_rarity": "none",        # none=完全无气层(重油油藏)
            "oil_dominant": True,
            "require_gas_evidence": True,
            "gas_to": "OIL",             # GAS -> OIL (重油高阻非气)
            "gas_possible_to": "OIL_POSSIBLE",  # GAS_POSSIBLE -> OIL_POSSIBLE
            "note": ("委内瑞拉胡宁4区块(IZZ0232/IZZ0042 等)为超重油油藏, 无气层。"
                     "解释中高阻段应判为油层而非气层; "
                     "储层以极粗粒砂岩(砾石)为主。"),
        },
        "source": "用户提供(委内瑞拉胡宁4项目 IZZ0232 井知识入库)",
        "note": ("重油油藏: 无气层, 高阻段为重油。"
                 "Rw 暂用默认 0.05 Ω·m, 待按实测地层水资料核实后再更新。"
                 "流体先验: 禁判气层, GAS->OIL。"),
    },
    # 孟加拉 Titas/Bakhrabad 气田 (BGFCL) —— 用户提供 PDF:
    # 04-Petrophysical_Bakhrabad-1214.pdf (BGP 2020, Titas/Bakhrabad 三维地震
    # 与报告审查之岩石物理分析)。纯气田: 用户确认"本井是气井, 无油层"。
    "bangladesh_titas_gas": {
        "name": "孟加拉(Titas/Bakhrabad 气田)",
        # 井名/区域别名 (子串匹配, 大小写不敏感)
        "aliases": ["titas", "bakhrabad", "bangladesh", "孟加拉",
                    "bgfcl", "bapex", "tijas", "nawab"],
        # 岩石物理参数: PDF 明确 a=1, m=2, n=2 (default parameters)
        "a": 1.0, "m": 2.0, "n": 2.0,
        # PDF 规定 Sw 用泥质砂岩方程 (Indonesia / Simandoux / Modified Simandoux)
        "method": "indonesia",
        # PDF 未提供实测 Rw。占位值仅防 orchestrator 兜底 0.05(高矿化度,
        # 对孟加拉湾三角洲淡水体系明显错误); 程序以水层反算为准(rw_auto)。
        "rw": 0.8,
        "rho_matrix": 2.65, "dt_matrix": 55.5,
        "confidence": 0.5,
        # ---- 流体先验: 纯气田无油层 (2026-09-30 用户口径) ----
        "fluid_prior": {
            "oil_rarity": "none",          # none=纯气田, 无油层
            "oil_dominant": False,
            "gas_dominant": True,
            "oil_to": "GAS",               # OIL -> GAS (气田内含烃即气)
            "oil_possible_to": "GAS_POSSIBLE",
            "note": ("Titas/Bakhrabad 为纯气田(用户确认本井是气井, 无油层)。"
                     "油层结论按气改写: OIL->GAS, OIL_POSSIBLE->GAS_POSSIBLE; "
                     "气测无显示的层段由气测约束先行处理。"),
        },
        # ---- 岩性口径: 孟加拉砂岩细, 与泥岩伽玛差别小 (2026-09-30 用户) ----
        # GR 判别门槛须自适应(程序已实现 reservoir_gate 自适应), 岩性区分
        # 需借助电阻率/密度等多曲线综合对比, 不能单靠伽玛绝对值。
        "lithology_note": ("上新世-中新世三角洲-浊积细砂岩: 岩性变细使伽玛背景整体"
                           "偏高(TITAS-31 GR 中位 268 API), 砂/泥伽玛对比度低; "
                           "泥质与砂岩判别应以 KTH/去铀伽玛相对起伏 + 电阻率/密度"
                           "组合为准, PE 因重晶石泥浆污染不可用(绝对值不可信)。"
                           "GTO 地质设计(Table 10)证实解释段泥浆 SG 1.81-2.08(KCl-PHPA, "
                           "重晶石加重)且全井仅砂岩/泥岩/粉砂岩互层, 无碳酸盐岩/蒸发岩/火成岩; "
                           "主力目标 Bhuban-1(MD 3746-4153)/Barail-1(MD 4153-4406)砂泥互层。"),
        "source": ("04-Petrophysical_Bakhrabad-1214.pdf (BGP 2020, "
                   "Titas/Bakhrabad 气田岩石物理分析) + 用户 2026-09-30 口径"),
        "note": ("PDF 参数: Sw=Indonesia/Simandoux/Modified Simandoux(泥质校正), "
                 "a=1, m=2, n=2; 泥质 GCUR=3.7(Larionov); 孔隙度=声波或密度-中子; "
                 "渗透率=Timur(Swirr=20%); 有效厚度下限 POR>10%, VSH<=40%, "
                 "气层 Sg>=50%(差气层 40-50%, Rt>15 / >10-12)。"
                 "Rw=0.8 为占位值(PDF 无实测), 以程序水层反算为准。"
                 "流体先验: 纯气田无油层, OIL->GAS。"),
    },
    # 示例: 可在下方继续扩展其它区域, 例如
    # "middle_east_carbonate": {
    #     "name": "中东碳酸盐岩",
    #     "aliases": ["中东", "middle east", "arab", "ghawar"],
    #     "a": 0.85, "m": 2.0, "n": 2.0, "rw": 0.04, ...
    # },
}


def _match_regional(well_name: str = "", region: str = "",
                    formation: str = "") -> Optional[Dict]:
    """按 井名 > 区域 > 层位 子串匹配区域权威参数表

    Returns:
        匹配到的区域条目 dict, 未命中返回 None
    """
    wn = (well_name or "").lower()
    rg = (region or "").lower()
    fm = (formation or "").lower()
    candidates = []
    for entry in REGIONAL_PARAMETERS.values():
        aliases = [a.lower() for a in entry.get("aliases", [])]
        if any(a in wn for a in aliases):
            candidates.append((3, entry))
        elif any(a in rg for a in aliases):
            candidates.append((2, entry))
        elif any(a in fm for a in aliases):
            candidates.append((1, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]



# ============================================================
# 数据模型
# ============================================================

@dataclass
class InterpretationContext:
    """解释上下文 - 从知识库检索到的信息"""
    well_name: str = ""
    region: str = ""
    formation: str = ""
    profile_type: str = ""           # sand_shale | carbonate | mixed

    # 知识检索结果
    knowledge_snippets: List[Dict] = field(default_factory=list)
    reference_cases: List[Dict] = field(default_factory=list)
    interpretation_templates: List[Dict] = field(default_factory=list)
    test_results: List[Dict] = field(default_factory=list)

    # LLM 生成的建议
    llm_summary: str = ""
    parameter_suggestions: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ParameterRecommendation:
    """参数推荐结果"""
    vsh_method: int = 3              # 泥质含量计算方法
    vsh_cutoff: float = 0.5          # 泥质截止值
    gr_clean: float = 30.0           # 纯砂岩GR
    gr_shale: float = 120.0          # 纯泥岩GR
    a: float = 1.0                   # 阿尔奇系数
    m: float = 2.0                   # 胶结指数
    n: float = 2.0                   # 饱和度指数
    rw: float = 0.05                 # 地层水电阻率
    rho_matrix: float = 2.65         # 骨架密度
    dt_matrix: float = 55.5          # 骨架声波时差
    confidence: float = 0.0          # 置信度
    source: str = ""                 # 推荐来源
    reasoning: str = ""              # 推荐理由
    # ---- 区域匹配扩展字段 ----
    rw_by_formation: Dict = field(default_factory=dict)  # 分层地层水电阻率 {层位: Rw}
    formation_windows: List = field(default_factory=list)  # 分层深度窗口 [{formation,top,bottom,m,n,Rw}]
    region_key: str = ""             # 匹配到的区域键名
    # 流体先验: {gas_rarity, oil_dominant, require_gas_evidence,
    #            gas_downgrade_to, oil_rarity, oil_to, oil_possible_to, note}
    #            —— 用于约束气层过度解释/气田油层误判
    fluid_prior: Dict = field(default_factory=dict)
    method: str = ""                 # 饱和度方程: archie|indonesia|simandoux|modified_simandoux
    region_matched: bool = False     # 是否命中区域权威参数表

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================
# 嵌入模式: 直接导入 logKnow
# ============================================================

class EmbeddedKnowledgeBase:
    """嵌入式知识库连接器 - 直接 import logKnow"""

    def __init__(self, src_dir: str = None):
        if src_dir is None:
            src_dir = str(Path(__file__).parent)
        self.src_dir = src_dir
        self._kb = None
        self._adapter = None
        self._has_vector = False
        self._well_idx = None

    def _get_well_idx(self):
        """懒加载井名索引"""
        if self._well_idx is None:
            try:
                sys.path.insert(0, self.src_dir)
                from well_name_utils import WellNameIndex
                self._well_idx = WellNameIndex()
            except Exception as e:
                logger.warning(f"井名索引加载失败: {e}")
                self._well_idx = False
        return self._well_idx or None

    def _enhance(self, query: str, results: List[Dict], top_n: int = 10) -> List[Dict]:
        """井名精确匹配增强: 查询命中井名时, 将该井知识块置顶 (修复中英/空格/连字符井名检索盲区)"""
        try:
            wi = self._get_well_idx()
            if wi is None:
                return results
            well_files = [f for f, _ in wi.search_by_well(query)]
            if not well_files:
                return results
            well_set = {os.path.normpath(f) for f in well_files}

            def get_src(r):
                if isinstance(r, dict):
                    return os.path.normpath(str(r.get("source") or r.get("source_file") or ""))
                return ""

            # 置顶构造: 井名知识块 (带 content 供 RAG 上下文使用)
            import re as _re
            from collections import OrderedDict
            merged = OrderedDict()
            for f in well_files:
                npf = os.path.normpath(f)
                content = ""
                try:
                    txt = open(f, encoding='utf-8').read()
                    content = _re.sub(r'^---\n.*?\n---\n', '', txt, flags=_re.S).strip()[:1200]
                except Exception:
                    pass
                merged[npf] = {"source": f, "source_file": f, "score": 1e9,
                               "title": os.path.basename(f), "content": content,
                               "well_name": os.path.basename(f).split('_')[0], "method": "well_match"}
            # 合并原有结果 (去重)
            for r in results:
                key = get_src(r)
                if key:
                    merged[key] = r
            return list(merged.values())[:top_n]
        except Exception as e:
            logger.debug(f"井名增强失败, 返回原结果: {e}")
            return results

    def connect(self, enable_vector: bool = True, vector_dir: str = "data/vector_index") -> bool:
        """连接知识库"""
        try:
            sys.path.insert(0, self.src_dir)
            from logKnow import WellLogKnowledgeBase
            # 在创建 KB 前禁用自动更新线程 (默认会爬 baike.baidu.com 等, 国内网络超时 90s+ 噪音)
            _orig_start = WellLogKnowledgeBase.start_auto_update
            WellLogKnowledgeBase.start_auto_update = lambda self, *a, **kw: setattr(self, "running", False)
            try:
                self._kb = WellLogKnowledgeBase(auto_scan=False)
            finally:
                WellLogKnowledgeBase.start_auto_update = _orig_start
            logger.info(f"嵌入式知识库已连接: {self._kb.get_stats()}")

            # 附加向量索引
            if enable_vector:
                try:
                    from vector_indexer import LogKnowVectorAdapter
                    self._adapter = LogKnowVectorAdapter(self._kb, persist_dir=vector_dir)
                    self._adapter.attach()
                    self._has_vector = True
                    logger.info("向量索引已附加")
                except ImportError:
                    logger.warning("vector_indexer 不可用，跳过向量索引")
                    self._has_vector = False

            return True
        except ImportError as e:
            logger.error(f"无法导入 logKnow: {e}")
            return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
            return False

    def search(self, query: str, top_n: int = 10,
               region: str = None, well_name: str = None) -> List[Dict]:
        """搜索知识库 (含井名精确匹配增强)"""
        if not self._kb:
            return []
        res = self._kb.search(query, top_n=top_n, region=region, well_name=well_name)
        return self._enhance(query, res, top_n)

    def vector_search(self, query: str, top_n: int = 10,
                      region: str = None, well_name: str = None) -> List[Dict]:
        """向量语义搜索 (含井名精确匹配增强)"""
        if not self._kb or not hasattr(self._kb, 'vector_search'):
            return []
        results = self._kb.vector_search(query, top_n, region=region, well_name=well_name)
        results = [asdict(r) if hasattr(r, '__dict__') else r for r in results]
        return self._enhance(query, results, top_n)

    def hybrid_search(self, query: str, top_n: int = 10,
                      region: str = None, well_name: str = None) -> List[Dict]:
        """混合检索 (含井名精确匹配增强)"""
        if not self._kb or not hasattr(self._kb, 'hybrid_search'):
            return self.search(query, top_n, region=region, well_name=well_name)
        results = self._kb.hybrid_search(query, top_n, region=region, well_name=well_name)
        results = [asdict(r) if hasattr(r, '__dict__') else r for r in results]
        return self._enhance(query, results, top_n)

    def ask(self, question: str, use_context: bool = True) -> Dict:
        """向 LLM 提问"""
        if not self._kb:
            return {"question": question, "answer": "", "error": "知识库未连接"}
        return self._kb.ask(question, use_context=use_context)

    def ask_with_hybrid(self, question: str) -> Dict:
        """混合检索增强问答"""
        if not self._kb or not hasattr(self._kb, 'ask_with_hybrid'):
            return self.ask(question)
        return self._kb.ask_with_hybrid(question)

    def get_stats(self) -> Dict:
        if not self._kb:
            return {}
        return self._kb.get_stats()

    def detect_region(self, file_path: str) -> Optional[Dict]:
        """从文件检测地区地质特征"""
        if not self._kb:
            return None
        return self._kb.region_detector.detect_from_file(file_path)


# ============================================================
# API模式: 通过 HTTP 调用 logKnow
# ============================================================

class APIKnowledgeBase:
    """API模式知识库连接器 - 调用 logKnow 的 FastAPI"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip('/')
        self._health = False

    def connect(self) -> bool:
        """检查连接"""
        try:
            import requests
            resp = requests.get(f"{self.api_url}/api/health", timeout=5)
            self._health = resp.status_code == 200
            if self._health:
                logger.info(f"知识库API已连接: {self.api_url}")
            return self._health
        except Exception as e:
            logger.warning(f"知识库API不可用 ({self.api_url}): {e}")
            return False

    def search(self, query: str, top_n: int = 10,
               region: str = None, well_name: str = None) -> List[Dict]:
        import requests
        params = {"query": query, "top_n": top_n}
        if region: params["region"] = region
        if well_name: params["well_name"] = well_name

        try:
            resp = requests.get(f"{self.api_url}/api/search", params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except Exception as e:
            logger.warning(f"搜索失败: {e}")
        return []

    def ask(self, question: str, use_context: bool = True) -> Dict:
        import requests
        params = {"question": question, "use_context": use_context}
        try:
            resp = requests.get(f"{self.api_url}/api/ask", params=params, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("result", {})
        except Exception as e:
            logger.warning(f"问答失败: {e}")
        return {"question": question, "answer": "", "error": str(e)}

    def detect_region(self, file_path: str) -> Optional[Dict]:
        import requests
        try:
            resp = requests.post(f"{self.api_url}/api/detect-region",
                               params={"file_path": file_path}, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("detection")
        except Exception as e:
            logger.warning(f"地区检测失败: {e}")
        return None

    def get_stats(self) -> Dict:
        import requests
        try:
            resp = requests.get(f"{self.api_url}/api/stats", timeout=10)
            if resp.status_code == 200:
                return resp.json().get("stats", {})
        except Exception:
            pass
        return {}


# ============================================================
# RAG桥接主类
# ============================================================

class RAGBridge:
    """RAG桥接主类

    充当 logInt 和 logKnow 之间的中介层，提供知识检索增强解释能力
    """

    def __init__(self, embedded: bool = True, api_url: str = None,
                 src_dir: str = None, vector_dir: str = "data/vector_index"):
        self.embedded = embedded
        self.api_url = api_url or "http://localhost:8000"
        self.src_dir = src_dir or str(Path(__file__).parent)
        self.vector_dir = vector_dir

        if embedded:
            self._backend = EmbeddedKnowledgeBase(src_dir=self.src_dir)
        else:
            self._backend = APIKnowledgeBase(api_url=self.api_url)

    def connect(self, enable_vector: bool = True) -> bool:
        """连接到知识库"""
        if self.embedded:
            return self._backend.connect(enable_vector=enable_vector,
                                         vector_dir=self.vector_dir)
        else:
            return self._backend.connect()

    # ---------- 核心检索接口 ----------

    def retrieve_context(self, well_name: str = "", region: str = "",
                         formation: str = "", profile_type: str = "",
                         curve_features: Dict = None,
                         depth_range: str = "") -> InterpretationContext:
        """为解释提供完整的检索上下文

        Args:
            well_name: 井名
            region: 地区/区块
            formation: 层位
            profile_type: 剖面类型 (sand_shale/carbonate/mixed)
            curve_features: 曲线特征 {"GR_avg": 80, "RT_avg": 25, ...}
            depth_range: 深度段

        Returns:
            InterpretationContext 包含所有检索结果
        """
        ctx = InterpretationContext(
            well_name=well_name, region=region,
            formation=formation, profile_type=profile_type
        )

        # 1. 搜索区域解释模板
        template_query = f"{region} {formation} {profile_type} 测井解释模板 参数"
        ctx.interpretation_templates = self._search(template_query, top_n=5,
                                                    region=region)

        # 2. 搜索相似案例
        if well_name and region:
            case_query = f"{region} {formation} 试油 解释结论"
            ctx.reference_cases = self._search(case_query, top_n=5, region=region)

        # 3. 搜索知识片段
        knowledge_queries = [
            f"{profile_type} {formation} 岩性识别 标准",
            f"{region} {formation} 储层参数 图版",
            f"{profile_type} 流体识别 方法",
        ]
        for q in knowledge_queries:
            snippets = self._search(q, top_n=3, region=region)
            ctx.knowledge_snippets.extend(snippets)

        # 4. 参数推荐 (如有曲线特征)
        if curve_features:
            ctx.parameter_suggestions = self._recommend_params(
                region, formation, profile_type, curve_features, well_name=well_name
            )

        # 5. 试油金标准: 相似历史试油层 (油/气/水/干层)
        #    来自结构化试油库(well_test_store), 是测井解释流体判别的"金标准"。
        #    失败时静默降级(不影响主检索链)。
        try:
            from test_gold_standard import search_similar_testzone
            feats = dict(curve_features or {})
            gs = search_similar_testzone(
                well_name=well_name, region=region, formation=formation,
                phi=feats.get("PHI_avg") or feats.get("phi"),
                rt=feats.get("RT_avg") or feats.get("rt"),
                sw=feats.get("SW_avg") or feats.get("sw"),
                limit=5,
            )
            if gs.get("count"):
                ctx.test_results = gs["similar_zones"]
                logger.info(f"[试油金标准] 注入 {gs['count']} 条相似试油层")
        except Exception as e:
            logger.debug(f"试油金标准检索跳过: {e}")

        return ctx

    def search_similar_wells(self, well_name: str, region: str = "",
                             top_n: int = 5) -> List[Dict]:
        """搜索相似井"""
        query = f"{region} {well_name} 测井解释"
        return self._search(query, top_n=top_n, region=region)

    def search_experience(self, topic: str, region: str = "",
                          top_n: int = 5) -> List[Dict]:
        """搜索解释经验"""
        query = f"{region} {topic} 解释经验 注意事项"
        results = self._search(query, top_n=top_n, region=region)
        # 过滤经验类型
        return [r for r in results if "experience" in r.get("source_type", "")]

    def ask_interpretation(self, question: str,
                           context: InterpretationContext = None) -> Dict:
        """向LLM提出解释相关问题

        Args:
            question: 问题
            context: 可选的解释上下文
        """
        # 构建增强提示
        if context:
            enhanced = question
            if context.region:
                enhanced += f"\n（地区: {context.region}, 层位: {context.formation}）"

            # 尝试混合问答
            if self.embedded and hasattr(self._backend, 'ask_with_hybrid'):
                return self._backend.ask_with_hybrid(enhanced)

        return self._backend.ask(question, use_context=True)

    def recommend_parameters(self, well_name: str = "", region: str = "",
                             formation: str = "", profile_type: str = "",
                             curve_features: Dict = None) -> ParameterRecommendation:
        """推荐解释参数

        Args:
            well_name: 井名
            region: 地区
            formation: 层位
            profile_type: 剖面类型
            curve_features: 曲线特征值 {"GR_avg": 80, "RT_avg": 25, "DEN_avg": 2.35, ...}

        Returns:
            ParameterRecommendation
        """
        params = self._recommend_params(region, formation, profile_type,
                                        curve_features, well_name=well_name)
        return params

    # ---------- 内部方法 ----------

    def _search(self, query: str, top_n: int = 10,
                region: str = None, well_name: str = None) -> List[Dict]:
        """统一的搜索方法，优先混合检索

        区域过滤说明: 文档入库时 region 元数据多为中文标签(如"乍得")/井名,
        而调用方传入的 region 可能是区域键(如 africa_bongor), 精确过滤会 0 命中.
        因此命中区域权威表时, 将区域别名展开进查询文本并放弃精确 region 过滤,
        交给语义/关键词相关性排序 (查询已含区域词, 目标区域自然靠前).
        """
        q = query
        filter_region = region
        aliases = self._region_aliases(region)
        if aliases:
            q = f"{query} {' '.join(aliases)}"
            filter_region = None

        if self.embedded and hasattr(self._backend, 'hybrid_search'):
            return self._backend.hybrid_search(q, top_n, filter_region, well_name)
        elif self.embedded and hasattr(self._backend, 'vector_search'):
            return self._backend.vector_search(q, top_n, filter_region, well_name)
        else:
            return self._backend.search(q, top_n, filter_region, well_name)

    def _region_aliases(self, region) -> List[str]:
        """区域键/中文名 -> 区域别名列表 (用于检索扩写; 空表示无需扩写)"""
        if not region:
            return []
        rg = str(region).strip()
        entry = REGIONAL_PARAMETERS.get(rg)
        if entry is None:
            rg_l = rg.lower()
            for k, e in REGIONAL_PARAMETERS.items():
                if rg_l == k.lower():
                    entry = e
                    break
        if entry is None:
            for e in REGIONAL_PARAMETERS.values():
                if any(a.lower() in rg_l for a in e.get("aliases", [])):
                    entry = e
                    break
        if entry is None:
            return []
        return list(entry.get("aliases", []))

    def _recommend_params(self, region: str, formation: str,
                          profile_type: str,
                          curve_features: Dict = None,
                          well_name: str = "") -> Dict:
        """基于知识库和曲线特征推荐参数"""
        rec = ParameterRecommendation()

        # 0. 优先匹配区域权威参数表 (井名 > 区域 > 层位)
        regional = _match_regional(well_name=well_name, region=region,
                                   formation=formation)
        if regional:
            rec.region_key = regional.get("name", "")
            rec.region_matched = True
            if regional.get("rw") is not None:
                rec.rw = regional["rw"]
            if regional.get("rw_by_formation"):
                rec.rw_by_formation = dict(regional["rw_by_formation"])
            if regional.get("formation_windows"):
                rec.formation_windows = list(regional["formation_windows"])
            if regional.get("fluid_prior"):
                rec.fluid_prior = dict(regional["fluid_prior"])
            for _k in ("a", "m", "n", "rho_matrix", "dt_matrix", "method"):
                if regional.get(_k) is not None:
                    setattr(rec, _k, regional[_k])
            rec.confidence = regional.get("confidence", 0.9)
            rec.source = regional.get("source", "regional_table")
            _note = regional.get("note", "")
            rec.reasoning = (f"命中区域参数库: {regional.get('name', '')}; "
                             f"Rw(代表值)={rec.rw} Ω·m, "
                             f"分层Rw={regional.get('rw_by_formation')}. {_note}")
            if rec.fluid_prior:
                rec.reasoning += (f" 流体先验: 气稀有度="
                                  f"{rec.fluid_prior.get('gas_rarity')}, "
                                  f"{rec.fluid_prior.get('note', '')}")
                logger.info(f"区域流体先验生效 [{regional.get('name')}]: "
                            f"gas_rarity={rec.fluid_prior.get('gas_rarity')}, "
                            f"require_gas_evidence="
                            f"{rec.fluid_prior.get('require_gas_evidence')}")
            logger.info(f"区域参数匹配成功 [{regional.get('name')}]: "
                        f"Rw={rec.rw}, a/m/n={rec.a}/{rec.m}/{rec.n}")
            return rec.to_dict()

        # 1. 搜索区域标准参数
        param_query = f"{region} {formation} {profile_type} 阿尔奇参数 骨架值 解释参数"
        results = self._search(param_query, top_n=5, region=region)

        # 2. 从内置知识获取默认参数
        # 关键: EmbeddedKnowledgeBase.__init__ 将 self._kb 预置为 None (占位),
        # hasattr(..., '_kb') 始终 True, 但 _kb 可能是 None (connect 失败/未连接)。
        # 必须显式判断 _kb is not None, 否则会触发 'NoneType' has no 'builtin_knowledge'。
        # 行为策略: 有就用, 没有就跳过 (后续用 default 参数, 不报错)。
        if (self.embedded
                and hasattr(self._backend, '_kb')
                and self._backend._kb is not None):
            kb = self._backend._kb
            builtin = kb.builtin_knowledge

            # 查询特定知识
            for area_results in [builtin.search_knowledge(f"{region} 参数"),
                                 builtin.search_knowledge(f"{profile_type} 解释参数")]:
                for r in area_results[:2]:
                    content = r.get("content", "")
                    # 尝试提取参数（简化版，实际可用正则+LLM）
                    extracted = self._extract_params_from_text(content)
                    for k, v in extracted.items():
                        if hasattr(rec, k) and not getattr(rec, k):
                            setattr(rec, k, v)

        # 3. 根据曲线特征微调
        if curve_features:
            rec = self._refine_by_features(rec, curve_features, profile_type)

        rec.confidence = 0.6  # 基础置信度
        rec.source = f"logKnow + BuiltInKnowledge (region={region})"
        rec.reasoning = f"基于 {region} 地区 {formation} 层位 {profile_type} 剖面历史经验"
        # 未命中区域权威表且 Rw 仍为默认 0.05 (高矿化度背景值),
        # 对中低矿化度地区会偏大, 提示人工复核
        if rec.rw == 0.05 and not rec.region_matched:
            rec.confidence = 0.3
            rec.reasoning += ("; 注意: 未识别到区域地层水电阻率, Rw 使用默认 0.05 Ω·m "
                              "(高矿化度/深水背景), 若工区为中低矿化度请人工复核或补充区域参数")
            logger.warning(f"Rw 使用默认 0.05 Ω·m (region={region} 未匹配区域参数表, 建议复核)")

        return rec.to_dict()

    def _extract_params_from_text(self, text: str) -> Dict:
        """从文本中提取参数（简化版）"""
        import re
        params = {}

        patterns = {
            'a': r'a\s*[=＝]\s*([\d.]+)',
            'm': r'm\s*[=＝]\s*([\d.]+)',
            'n': r'n\s*[=＝]\s*([\d.]+)',
            'rw': r'Rw?\s*[=＝]\s*([\d.]+)',
            'rho_matrix': r'骨架[密]*度\s*[=＝:：]?\s*([\d.]+)',
            'dt_matrix': r'骨架[声时]*差\s*[=＝:：]?\s*([\d.]+)',
            'vsh_cutoff': r'泥质[截]*止[值]*\s*[=＝:：]?\s*([\d.]+)',
        }

        for param, pattern in patterns.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    params[param] = float(m.group(1))
                except ValueError:
                    pass

        return params

    def _refine_by_features(self, rec: ParameterRecommendation,
                            features: Dict, profile_type: str) -> ParameterRecommendation:
        """根据曲线特征微调参数"""
        gr_avg = features.get('GR_avg', features.get('GR_mean', 60))

        # GR 高 → 泥质多，可能需要调整泥质截止
        if gr_avg > 100:
            rec.vsh_cutoff = max(rec.vsh_cutoff, 0.5)
        elif gr_avg < 40:
            rec.vsh_cutoff = min(rec.vsh_cutoff, 0.4)

        # 碳酸盐岩：骨架值需要调整
        if profile_type == 'carbonate':
            den_avg = features.get('DEN_avg', 2.71)
            if den_avg > 2.75:
                rec.rho_matrix = 2.71  # 石灰岩
            elif den_avg < 2.6:
                rec.rho_matrix = 2.87  # 白云岩

        # 电阻率高 → 可能含油气，需注意饱和度模型
        rt_avg = features.get('RT_avg', 20)
        if rt_avg > 100:
            rec.m = max(rec.m, 2.0)  # 碳酸盐岩胶结指数通常更高

        return rec


# ============================================================
# logInt 集成适配器
# ============================================================

def inject_into_logint(bridge: RAGBridge = None, src_dir: str = None):
    """将 RAG桥接层注入 logInt 的 MineralAnalyzer

    替换 MineralAnalyzer.query_knowledge_base()，
    使其不再读本地MD文件，而是通过RAGBridge获取实时知识

    Args:
        bridge: 已连接的 RAGBridge 实例
        src_dir: logInt 所在的源码目录

    Returns:
        bridge: RAGBridge 实例
    """
    if bridge is None:
        bridge = RAGBridge(embedded=True, src_dir=src_dir)
        bridge.connect()

    try:
        sys.path.insert(0, src_dir or str(Path(__file__).parent))
        from logInt import MineralAnalyzer

        # 保存原始方法
        original_query = MineralAnalyzer.query_knowledge_base

        def enhanced_query_knowledge_base(self, profile_type, well_name='Unknown'):
            """增强版知识库查询 - 通过RAG桥接层获取"""

            logger.info(f"[{well_name}] RAG增强查询: profile_type={profile_type}")

            # 1. 通过 RAG 获取上下文
            ctx = bridge.retrieve_context(
                well_name=well_name, profile_type=profile_type
            )

            # 2. 收集知识片段
            knowledge = {}

            # 从 RAG 结果提取
            for snippet in ctx.knowledge_snippets[:5]:
                topic = snippet.get('source', 'knowledge')
                text = snippet.get('content', '')[:1000]  # 限制长度
                if topic not in knowledge:
                    knowledge[topic] = text
                else:
                    knowledge[topic] += "\n" + text

            # 从模板提取
            for tmpl in ctx.interpretation_templates[:3]:
                topic = f"template_{tmpl.get('source', '')[:20]}"
                text = tmpl.get('content', '')[:800]
                knowledge[topic] = text

            # 3. 添加参数建议
            if ctx.parameter_suggestions:
                params_text = json.dumps(ctx.parameter_suggestions, ensure_ascii=False, indent=2)
                knowledge['parameter_recommendations'] = params_text

            # 4. 如果 RAG 没拿到足够内容，回退到原始方法
            if len(knowledge) < 2:
                logger.info(f"[{well_name}] RAG结果不足，回退到本地知识库")
                fallback = original_query(self, profile_type, well_name)
                knowledge.update(fallback)

            logger.info(f"[{well_name}] RAG查询完成: {len(knowledge)} topics loaded")
            return knowledge

        # 注入
        MineralAnalyzer.query_knowledge_base = enhanced_query_knowledge_base
        logger.info("RAG桥接层已注入 logInt.MineralAnalyzer")

    except ImportError as e:
        logger.error(f"注入失败 (logInt 未导入): {e}")
    except Exception as e:
        logger.error(f"注入失败: {e}")

    return bridge


# ============================================================
# 命令行入口
# ============================================================

# ============================================================
# 本地岩石物理资料自动入库
# ------------------------------------------------------------
# 问题: 用户电脑上有各地区岩石物理资料(pdf/docx/xlsx/las等),
# 但知识库只加载 data/local 下的 .md, 且 rag_bridge 连接时
# auto_scan=False(为避免启动爬网/长时间扫描), 导致这些资料从未入库,
# 解释时用不上 -> 符合率低。
# 机制: 显式一键入库 = 文档转换(→data/local) + 增量建索引 + 向量化。
# ============================================================

# 默认扫描目录: 可用环境变量 LOGKNOW_MATERIAL_DIRS 指定(分号或逗号分隔)
DEFAULT_MATERIAL_DIRS = ["data/materials", "data/rockphysics", "data/local"]


def _resolve_material_dirs(source_dirs=None) -> List[str]:
    if source_dirs:
        if isinstance(source_dirs, str):
            source_dirs = [d for d in re.split(r"[;,]", source_dirs) if d.strip()]
        return [str(d).strip() for d in source_dirs if str(d).strip()]
    env = os.environ.get("LOGKNOW_MATERIAL_DIRS", "")
    if env:
        return [d.strip() for d in re.split(r"[;,]", env) if d.strip()]
    return list(DEFAULT_MATERIAL_DIRS)


def ingest_local_materials(source_dirs=None, kb=None,
                           rebuild_index: bool = True,
                           recursive: bool = True) -> Dict:
    """把本地岩石物理资料转换并入库(形成可检索的知识库知识)

    Args:
        source_dirs: 资料目录列表/分隔字符串; 缺省用 LOGKNOW_MATERIAL_DIRS 或默认目录
        kb: 已连接的 WellLogKnowledgeBase / RAGBridge; 为 None 时自行创建
        rebuild_index: 转换后是否增量重建索引(Whoosh + 向量)
        recursive: 是否递归子目录

    Returns:
        {'dirs': [...], 'converted': n, 'skipped': n, 'indexed': bool,
         'local_docs': 'data/local', 'stats': {...}}
    """
    dirs = _resolve_material_dirs(source_dirs)
    out = {"dirs": dirs, "converted": 0, "skipped": 0,
           "indexed": False, "local_docs": "data/local", "stats": {}}

    # ---- 解析知识库实例 ----
    _kb = kb
    if hasattr(_kb, "_backend"):                      # 传入 RAGBridge
        _kb = getattr(_kb._backend, "_kb", None)
    if _kb is None:
        try:
            bridge = RAGBridge(embedded=True)
            if not bridge.connect():
                logger.error("知识库连接失败, 无法入库")
                return out
            _kb = bridge._backend._kb
        except Exception as e:
            logger.error(f"知识库初始化失败: {e}")
            return out
    if _kb is None:
        logger.error("未获得知识库实例, 无法入库")
        return out

    local_docs = "data/local"
    try:
        local_docs = _kb.config["paths"]["local_docs"]
    except Exception:
        pass
    out["local_docs"] = local_docs

    # ---- 1) 文档转换: pdf/docx/xlsx/pptx/las... -> markdown ----
    converter = getattr(_kb, "converter", None)
    if converter is None:
        try:
            from logKnow import DocumentConverter
            converter = DocumentConverter()
        except Exception as e:
            logger.error(f"文档转换器不可用: {e}")
            return out

    for d in dirs:
        if not os.path.isdir(d):
            logger.info(f"资料目录不存在, 跳过: {d}")
            continue
        if os.path.abspath(d) == os.path.abspath(local_docs):
            continue  # data/local 本身无需再转换
        try:
            c, s = converter.batch_convert(d, local_docs, recursive=recursive)
            out["converted"] += int(c or 0)
            out["skipped"] += int(s or 0)
            logger.info(f"资料入库 [{d}]: 转换 {c} 个, 跳过 {s} 个")
        except Exception as e:
            logger.warning(f"资料目录转换失败 [{d}]: {e}")

    # ---- 2) 增量建索引(Whoosh) + 向量化 ----
    if rebuild_index:
        try:
            _kb.build_index(incremental=True)
            out["indexed"] = True
            logger.info("知识库索引已增量更新")
        except Exception as e:
            logger.warning(f"索引更新失败: {e}")
        try:
            from logKnow import MarkdownLoader
            docs = MarkdownLoader(local_docs).load_all(use_cache=False)
            if docs and hasattr(_kb, "add_documents"):
                _kb.add_documents(docs)
                logger.info(f"向量索引已更新: {len(docs)} 篇")
        except Exception as e:
            logger.debug(f"向量索引更新跳过: {e}")

    try:
        out["stats"] = _kb.get_stats()
    except Exception:
        pass
    logger.info(f"本地资料入库完成: 新增 {out['converted']} 篇 -> {local_docs}")
    return out


def main():
    import argparse

    parser = argparse.ArgumentParser(description="RAG桥接层 - 查询工具")
    sub = parser.add_subparsers(dest="cmd")

    # ingest - 本地资料入库
    ingest_p = sub.add_parser("ingest", help="把本地岩石物理资料转换并入库")
    ingest_p.add_argument("--dirs", "-d", default=None,
                          help="资料目录(多个用逗号/分号分隔); 缺省用 "
                               "LOGKNOW_MATERIAL_DIRS 或 data/materials")
    ingest_p.add_argument("--no-index", action="store_true", help="只转换不建索引")
    ingest_p.add_argument("--no-recursive", action="store_true", help="不递归子目录")

    # search
    search_p = sub.add_parser("search", help="搜索知识库")
    search_p.add_argument("--query", "-q", required=True, help="查询")
    search_p.add_argument("--top-n", "-n", type=int, default=5, help="返回数量")
    search_p.add_argument("--region", "-r", help="地区过滤")
    search_p.add_argument("--api", help="API模式URL (如 http://localhost:8000)")

    # context
    context_p = sub.add_parser("context", help="获取解释上下文")
    context_p.add_argument("--well", "-w", required=True, help="井名")
    context_p.add_argument("--region", "-r", help="地区")
    context_p.add_argument("--formation", "-f", help="层位")
    context_p.add_argument("--profile", "-p", default="sand_shale", help="剖面类型")
    context_p.add_argument("--api", help="API模式URL")

    # ask
    ask_p = sub.add_parser("ask", help="提问")
    ask_p.add_argument("--question", "-q", required=True, help="问题")
    ask_p.add_argument("--api", help="API模式URL")

    args = parser.parse_args()

    # frontmatter 兼容 shim: 环境中装的是同名异包(3.0.8), 不含 load/Post/dumps,
    # 导致本地 Markdown 入库/读取失败 (DocumentConverter.convert 静默 SKIP).
    try:
        import frontmatter_shim
        frontmatter_shim.install()
    except Exception as _e:
        logging.warning("frontmatter shim install failed: %s", _e)

    # ingest 不需要 API 模式
    if args.cmd == "ingest":
        res = ingest_local_materials(
            source_dirs=args.dirs,
            rebuild_index=not args.no_index,
            recursive=not args.no_recursive,
        )
        print(f"扫描目录: {res['dirs']}")
        print(f"新增入库: {res['converted']} 篇 (跳过 {res['skipped']} 篇)")
        print(f"落盘目录: {res['local_docs']}, 索引更新: {res['indexed']}")
        if res.get('stats'):
            print(f"知识库统计: {json.dumps(res['stats'], ensure_ascii=False, default=str)}")
        return

    if args.api:
        bridge = RAGBridge(embedded=False, api_url=args.api)
    else:
        bridge = RAGBridge(embedded=True)
    bridge.connect()

    if args.cmd == "search":
        results = bridge._search(args.query, top_n=args.top_n, region=args.region)
        for i, r in enumerate(results, 1):
            content = r.get('content', '')[:200]
            score = r.get('score', 'N/A')
            source = r.get('source_file', r.get('source', 'unknown'))
            method = r.get('method', 'search')
            print(f"\n[{i}] {method} score={score} | {source}")
            print(f"    {content}...")

    elif args.cmd == "context":
        ctx = bridge.retrieve_context(
            well_name=args.well, region=args.region or "",
            formation=args.formation or "", profile_type=args.profile
        )
        print(f"井: {ctx.well_name}")
        print(f"地区: {ctx.region}, 层位: {ctx.formation}, 剖面: {ctx.profile_type}")
        print(f"知识片段: {len(ctx.knowledge_snippets)}")
        print(f"参考案例: {len(ctx.reference_cases)}")
        print(f"解释模板: {len(ctx.interpretation_templates)}")
        if ctx.parameter_suggestions:
            print(f"参数建议: {json.dumps(ctx.parameter_suggestions, ensure_ascii=False, indent=2)}")

    elif args.cmd == "ask":
        result = bridge.ask_interpretation(args.question)
        print(f"问题: {result.get('question', args.question)}")
        print(f"回答:\n{result.get('answer', '')}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                       format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    main()
