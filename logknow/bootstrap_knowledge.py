import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE = Path(__file__).parent
GRAPH_FILE = BASE / "data" / "graph_store.json"

# ===================== 校验规则配置（与存量体系严格对齐）=====================
VALIDATION_RULES = {
    "formation_required_fields": [
        "geologic_age", "lithology", "porosity_range",
        "permeability_range", "reservoir_type",
        "rock_electric_a", "rock_electric_m", "rock_electric_n",
        "formation_water_salinity"
    ],
    "test_interval_required_fields": [
        "name", "top", "bottom", "conclusion",
        "oil_production", "gas_production", "water_production"
    ],
    "valid_reservoir_types": ["孔隙型", "孔洞型", "裂缝型", "孔隙-裂缝型", "孔洞-裂缝型", "裂缝-孔洞型", "页岩-致密型"],
    "porosity_pattern": r"^\d+%~\d+%$",
    "permeability_pattern": r"^[\d.]+~[\d.]+ mD$",
    "salinity_pattern": r"^\d+~\d+ mg/L$",
}


class GraphStore:
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if GRAPH_FILE.exists():
            with open(GRAPH_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.nodes = raw.get("nodes", {})
                self.edges = raw.get("edges", [])

    def _save(self):
        GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GRAPH_FILE, "w", encoding="utf-8") as f:
            json.dump({"nodes": self.nodes, "edges": self.edges}, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _key(etype: str, name: str) -> str:
        return f"{etype}||{name.strip()}"

    def add_node(self, etype: str, name: str, props: Dict[str, Any]):
        key = self._key(etype, name)
        if key not in self.nodes:
            self.nodes[key] = {"type": etype, "name": name, "props": props}
        else:
            self.nodes[key]["props"].update(props)
        self._save()

    def add_edge(self, from_type: str, from_name: str, rel: str, to_type: str, to_name: str):
        e = {
            "from": self._key(from_type, from_name),
            "rel": rel,
            "to": self._key(to_type, to_name)
        }
        if e not in self.edges:
            self.edges.append(e)
            self._save()

    def lookup(self, etype: str, name: str) -> Optional[Dict[str, Any]]:
        key = self._key(etype, name)
        if key in self.nodes:
            return self.nodes[key]
        target = name.strip()
        for nd in self.nodes.values():
            if nd["type"] != etype:
                continue
            nd_name = nd["name"]
            aliases = nd["props"].get("aliases", [])
            if target == nd_name or target in aliases or target in nd_name:
                return nd
        return None

    def get_children(self, etype: str, name: str, child_type: str = None) -> List[Dict[str, Any]]:
        nd = self.lookup(etype, name)
        if not nd:
            return []
        key = self._key(etype, nd["name"])
        res = []
        for ed in self.edges:
            if ed["from"] != key:
                continue
            child = self.nodes.get(ed["to"])
            if child and (child_type is None or child["type"] == child_type):
                res.append(child)
        return res

    def match_methods(self, region: str, formation: str) -> List[Dict[str, Any]]:
        hits = []
        seen = set()
        for nd in self.nodes.values():
            if nd["type"] != "interpretation_method":
                continue
            p = nd["props"]
            mname = p.get("method_name", "")
            if mname in seen:
                continue
            reg_list = p.get("applicable_regions", [])
            fm_list = p.get("applicable_formations", [])
            reg_ok = not reg_list or any(region in r for r in reg_list)
            fm_ok = not fm_list or any(formation in f for f in fm_list)
            if reg_ok and fm_ok:
                seen.add(mname)
                hits.append({
                    "method_name": mname,
                    "applicable_regions": reg_list,
                    "applicable_formations": fm_list,
                    "input_curves": p.get("input_curves", []),
                    "formula": p.get("formula", ""),
                    "threshold": p.get("threshold", {}),
                    "limitation": p.get("limitation", ""),
                    "reference_case": p.get("reference_case", ""),
                    "quad_in_one": {
                        "code_path": p.get("code_path", ""),
                        "config_path": p.get("config_path", ""),
                        "test_path": p.get("test_path", ""),
                        "doc_path": p.get("doc_path", "")
                    }
                })
        return hits


# ===================== 一致性校验器 =====================
class KnowledgeValidator:
    def __init__(self, benchmark_data: Dict[str, Any]):
        self.data = benchmark_data
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.all_formation_names: Set[str] = set()

    def _collect_all_formations(self):
        for country in self.data["countries"]:
            for basin in country["basins"]:
                for oilfield in basin["oilfields"]:
                    for fm in oilfield["formations"]:
                        self.all_formation_names.add(fm["name"])
                        for alias in fm.get("aliases", []):
                            self.all_formation_names.add(alias)

    def validate(self) -> bool:
        print("🔍 开始知识库一致性校验...")
        self._collect_all_formations()

        country_idx = 0
        for country in self.data["countries"]:
            country_idx += 1
            cname = country["name"]
            if not country.get("basins"):
                self.warnings.append(f"[国家 {cname}] 未配置盆地")
                continue

            for basin in country["basins"]:
                bname = basin["name"]
                if not basin.get("oilfields"):
                    self.warnings.append(f"[盆地 {cname}>{bname}] 未配置油气田")
                    continue

                for oilfield in basin["oilfields"]:
                    oname = oilfield["name"]
                    if not oilfield.get("formations"):
                        self.errors.append(f"[油气田 {cname}>{bname}>{oname}] 缺少地层配置")
                        continue

                    # 校验地层
                    for fm in oilfield["formations"]:
                        self._validate_formation(cname, bname, oname, fm)

                    # 校验井与试油
                    for well in oilfield.get("wells", []):
                        self._validate_well(cname, bname, oname, well)

        # 校验解释方法绑定
        self._validate_methods()

        # 输出结果
        print(f"✅ 校验完成：错误 {len(self.errors)} 个，警告 {len(self.warnings)} 个")
        if self.warnings:
            print("\n⚠️  警告列表：")
            for w in self.warnings:
                print(f"  - {w}")
        if self.errors:
            print("\n❌ 错误列表（必须修复）：")
            for e in self.errors:
                print(f"  - {e}")
            return False
        return True

    def _validate_formation(self, cname: str, bname: str, oname: str, fm: Dict[str, Any]):
        fm_name = fm["name"]
        path = f"{cname}>{bname}>{oname}>{fm_name}"
        props = fm.get("props", {})

        # 必填字段检查
        for field in VALIDATION_RULES["formation_required_fields"]:
            if field not in props:
                self.errors.append(f"[地层 {path}] 缺少必填字段：{field}")

        # 储集类型合法性
        rt = props.get("reservoir_type", "")
        if rt and rt not in VALIDATION_RULES["valid_reservoir_types"]:
            self.errors.append(f"[地层 {path}] 储集类型不规范：{rt}")

        # 格式检查：孔隙度
        por = props.get("porosity_range", "")
        if por and not self._match_pattern(por, VALIDATION_RULES["porosity_pattern"]):
            self.errors.append(f"[地层 {path}] 孔隙度格式不规范：{por}（应为 x%~y%）")

        # 格式检查：渗透率
        perm = props.get("permeability_range", "")
        if perm and not self._match_pattern(perm, VALIDATION_RULES["permeability_pattern"]):
            self.errors.append(f"[地层 {path}] 渗透率格式不规范：{perm}（应为 x~y mD）")

        # 格式检查：矿化度
        sal = props.get("formation_water_salinity", "")
        if sal and not self._match_pattern(sal, VALIDATION_RULES["salinity_pattern"]):
            self.errors.append(f"[地层 {path}] 矿化度格式不规范：{sal}（应为 x~y mg/L）")

        # 岩电参数数值类型
        for param in ["rock_electric_a", "rock_electric_m", "rock_electric_n"]:
            val = props.get(param)
            if val is not None and not isinstance(val, (int, float)):
                self.errors.append(f"[地层 {path}] {param} 必须为数值类型，当前：{type(val).__name__}")

    def _validate_well(self, cname: str, bname: str, oname: str, well: Dict[str, Any]):
        wname = well["name"]
        path = f"{cname}>{bname}>{oname}>{wname}"
        for ti in well.get("test_intervals", []):
            for field in VALIDATION_RULES["test_interval_required_fields"]:
                if field not in ti:
                    self.errors.append(f"[试油 {path}] 缺少必填字段：{field}")
            if isinstance(ti.get("top"), (int, float)) and isinstance(ti.get("bottom"), (int, float)):
                if ti["top"] >= ti["bottom"]:
                    self.errors.append(f"[试油 {path}] 顶深 >= 底深：{ti['top']} >= {ti['bottom']}")

    def _validate_methods(self):
        for m in self.data["methods"]:
            mname = m["method_name"]
            for fm in m.get("applicable_formations", []):
                if fm and fm not in self.all_formation_names:
                    self.warnings.append(f"[方法 {mname}] 绑定的地层不存在于知识库：{fm}")

    @staticmethod
    def _match_pattern(text: str, pattern: str) -> bool:
        import re
        return bool(re.match(pattern, text.strip()))


# ===================== 全量标杆知识（30国完整版）=====================
BENCHMARK_DATA = {
    "countries": [
        # 南亚
        {"name": "孟加拉国", "aliases": ["孟加拉"], "basins": [
            {"name": "孟加拉盆地", "oilfields": [
                {"name": "Titas气田", "formations": [
                    {"name": "Bokabil组", "aliases": ["Bokabil"], "props": {
                        "geologic_age": "中新世",
                        "lithology": "三角洲前缘细砂岩、粉砂岩，砂泥互层，泥质含量偏高",
                        "porosity_range": "12%~32%",
                        "permeability_range": "0.1~120 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.1,
                        "rock_electric_m": 2.15,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "8000~15000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Titas-1", "test_intervals": [
                        {"name": "Bokabil组试油", "top": 2360, "bottom": 2520, "conclusion": "气层",
                         "gas_production": "72万方/天", "oil_production": "微量凝析油", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 南美
        {"name": "巴西", "aliases": [], "basins": [
            {"name": "桑托斯盆地", "oilfields": [
                {"name": "Libra油田", "formations": [
                    {"name": "Barra Velha组", "aliases": ["Barra Velha"], "props": {
                        "geologic_age": "晚阿普特期",
                        "lithology": "微生物碳酸盐岩，叠层石、球粒灰岩，溶蚀孔洞+晶间孔",
                        "porosity_range": "5%~22%",
                        "permeability_range": "0.01~500 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.0,
                        "rock_electric_n": 1.9,
                        "formation_water_salinity": "20000~35000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Libra-1", "test_intervals": [
                        {"name": "Barra Velha组试油", "top": 4920, "bottom": 5100, "conclusion": "油层",
                         "oil_production": "285 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "阿根廷", "aliases": [], "basins": [
            {"name": "内乌肯盆地", "oilfields": [
                {"name": "Loma La Lata油田", "formations": [
                    {"name": "Vaca Muerta组", "aliases": ["Vaca Muerta"], "props": {
                        "geologic_age": "晚侏罗世-早白垩世",
                        "lithology": "海相页岩，夹致密灰岩、粉砂岩，水平井体积压裂改造",
                        "porosity_range": "2%~10%",
                        "permeability_range": "0.0001~1 mD",
                        "reservoir_type": "页岩-致密型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.15,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "20000~40000 mg/L"
                    }}
                ], "wells": [
                    {"name": "LLL-1", "test_intervals": [
                        {"name": "Vaca Muerta组试油", "top": 2800, "bottom": 3100, "conclusion": "油层",
                         "oil_production": "120 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "哥伦比亚", "aliases": [], "basins": [
            {"name": "洛斯亚诺斯盆地", "oilfields": [
                {"name": "Rubiales油田", "formations": [
                    {"name": "Carbonera组", "aliases": ["Carbonera"], "props": {
                        "geologic_age": "渐新世-中新世",
                        "lithology": "河流三角洲砂岩，分选中等，泥岩夹层发育",
                        "porosity_range": "14%~33%",
                        "permeability_range": "1~500 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.03,
                        "rock_electric_m": 1.98,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "5000~15000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Rubiales-1", "test_intervals": [
                        {"name": "Carbonera组试油", "top": 1280, "bottom": 1420, "conclusion": "油层",
                         "oil_production": "180 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 北美
        {"name": "墨西哥", "aliases": [], "basins": [
            {"name": "坎佩切湾盆地", "oilfields": [
                {"name": "Cantarell油田", "formations": [
                    {"name": "Ek-Balam组", "aliases": ["Ek Balam"], "props": {
                        "geologic_age": "晚白垩世",
                        "lithology": "礁滩碳酸盐岩，溶蚀孔洞、裂缝发育",
                        "porosity_range": "5%~24%",
                        "permeability_range": "0.1~600 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.02,
                        "rock_electric_n": 1.96,
                        "formation_water_salinity": "18000~32000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Cantarell-1", "test_intervals": [
                        {"name": "Ek-Balam组试油", "top": 3200, "bottom": 3450, "conclusion": "油层",
                         "oil_production": "280 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 欧洲
        {"name": "挪威", "aliases": [], "basins": [
            {"name": "北海中央地堑", "oilfields": [
                {"name": "Troll油田", "formations": [
                    {"name": "Brent组", "aliases": ["Brent"], "props": {
                        "geologic_age": "中侏罗世",
                        "lithology": "三角洲砂岩，分选良好，夹页岩",
                        "porosity_range": "15%~32%",
                        "permeability_range": "10~1500 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 1.95,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "10000~25000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Troll-1", "test_intervals": [
                        {"name": "Brent组试油", "top": 1500, "bottom": 1680, "conclusion": "油层（带气顶）",
                         "oil_production": "220 m³/d", "gas_production": "气顶气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "英国", "aliases": [], "basins": [
            {"name": "北海中央地堑", "oilfields": [
                {"name": "Forties油田", "formations": [
                    {"name": "Paleocene浊积砂", "aliases": ["古新统浊积砂岩"], "props": {
                        "geologic_age": "古新世",
                        "lithology": "深水浊积扇砂岩，分选良好，砂体孤立分布",
                        "porosity_range": "16%~34%",
                        "permeability_range": "5~1200 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.02,
                        "rock_electric_m": 1.96,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "12000~28000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Forties-1", "test_intervals": [
                        {"name": "古新统试油", "top": 1800, "bottom": 1960, "conclusion": "油层",
                         "oil_production": "260 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 非洲
        {"name": "乍得", "aliases": [], "basins": [
            {"name": "多巴盆地", "oilfields": [
                {"name": "Kome油田", "formations": [
                    {"name": "Kome组", "aliases": ["Kome"], "props": {
                        "geologic_age": "早白垩世",
                        "lithology": "陆相三角洲分流河道、河口坝细-中砂岩，夹煤层、炭质泥岩",
                        "porosity_range": "16%~36%",
                        "permeability_range": "1~800 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.05,
                        "rock_electric_m": 1.95,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "5000~12000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Kome-1", "test_intervals": [
                        {"name": "Kome组试油", "top": 860, "bottom": 970, "conclusion": "油层",
                         "oil_production": "158 m³/d", "gas_production": "微量伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "尼日尔", "aliases": [], "basins": [
            {"name": "阿加德兹盆地", "oilfields": [
                {"name": "Goulbi油田", "formations": [
                    {"name": "Goulbi砂岩", "aliases": ["Goulbi"], "props": {
                        "geologic_age": "早白垩世",
                        "lithology": "河流三角洲砂岩，分选中等，泥岩夹层发育，局部钙质胶结",
                        "porosity_range": "15%~34%",
                        "permeability_range": "0.5~500 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.02,
                        "rock_electric_m": 2.0,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "6000~13000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Goulbi-1", "test_intervals": [
                        {"name": "Goulbi砂岩试油", "top": 1140, "bottom": 1260, "conclusion": "油层",
                         "oil_production": "144 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "苏丹", "aliases": [], "basins": [
            {"name": "穆格莱德盆地", "oilfields": [
                {"name": "Fula油田", "formations": [
                    {"name": "Abu Gabra组", "aliases": ["Abu Gabra"], "props": {
                        "geologic_age": "早白垩世",
                        "lithology": "辫状河三角洲砂岩，厚层块状砂，分选中等，湖相泥岩为盖层",
                        "porosity_range": "14%~33%",
                        "permeability_range": "1~650 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.03,
                        "rock_electric_m": 1.98,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "7000~15000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Fula-1", "test_intervals": [
                        {"name": "Abu Gabra组试油", "top": 1280, "bottom": 1410, "conclusion": "油层",
                         "oil_production": "105 m³/d", "gas_production": "微量伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "阿尔及利亚", "aliases": [], "basins": [
            {"name": "伊利济盆地", "oilfields": [
                {"name": "Hassi R'Mel气田", "formations": [
                    {"name": "Tadrart组", "aliases": ["Tadrart"], "props": {
                        "geologic_age": "晚泥盆世",
                        "lithology": "高成熟石英砂岩，胶结致密，裂缝对渗透率贡献大",
                        "porosity_range": "3%~18%",
                        "permeability_range": "0.01~100 mD",
                        "reservoir_type": "孔隙-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.1,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "15000~25000 mg/L"
                    }}
                ], "wells": [
                    {"name": "HR-1", "test_intervals": [
                        {"name": "Tadrart组试气", "top": 2820, "bottom": 3010, "conclusion": "凝析气层",
                         "gas_production": "110万方/天", "oil_production": "凝析油", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "利比亚", "aliases": [], "basins": [
            {"name": "锡尔特盆地", "oilfields": [
                {"name": "Sarir油田", "formations": [
                    {"name": "Sarir砂岩", "aliases": ["Sarir"], "props": {
                        "geologic_age": "晚白垩世",
                        "lithology": "河流-三角洲厚层石英砂岩，分选好，胶结弱，高孔高渗",
                        "porosity_range": "18%~34%",
                        "permeability_range": "10~2000 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 1.9,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "8000~18000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Sarir-1", "test_intervals": [
                        {"name": "Sarir砂岩试油", "top": 1440, "bottom": 1560, "conclusion": "油层",
                         "oil_production": "210 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "埃及", "aliases": [], "basins": [
            {"name": "苏伊士湾盆地", "oilfields": [
                {"name": "Belayim油田", "formations": [
                    {"name": "Belayim组", "aliases": ["Belayim"], "props": {
                        "geologic_age": "中新世",
                        "lithology": "滨岸砂岩、礁灰岩、泥岩互层，断块分割强烈，相变快",
                        "porosity_range": "10%~30%",
                        "permeability_range": "0.1~300 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.05,
                        "rock_electric_m": 2.0,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "20000~35000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Belayim-1", "test_intervals": [
                        {"name": "Belayim组试油", "top": 1420, "bottom": 1550, "conclusion": "油层",
                         "oil_production": "165 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 中亚
        {"name": "乌兹别克斯坦", "aliases": ["乌兹别克"], "basins": [
            {"name": "阿姆河盆地", "oilfields": [
                {"name": "Gazli气田", "formations": [
                    {"name": "Kugitang组", "aliases": ["Kugitang"], "props": {
                        "geologic_age": "中侏罗世",
                        "lithology": "礁滩相灰岩、白云岩，孔洞+裂缝复合储层，膏盐夹层",
                        "porosity_range": "4%~20%",
                        "permeability_range": "0.05~200 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.05,
                        "rock_electric_n": 1.95,
                        "formation_water_salinity": "10000~22000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Gazli-1", "test_intervals": [
                        {"name": "Kugitang组试气", "top": 1960, "bottom": 2120, "conclusion": "凝析气层",
                         "gas_production": "95万方/天", "oil_production": "凝析油", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "土库曼斯坦", "aliases": ["土库曼"], "basins": [
            {"name": "阿姆河盆地", "oilfields": [
                {"name": "Galkynysh气田", "formations": [
                    {"name": "牛津阶礁滩组", "aliases": ["牛津阶", "牛津阶组", "Callovian-Oxfordian"], "props": {
                        "geologic_age": "晚侏罗世牛津期",
                        "lithology": "礁灰岩、颗粒灰岩、白云岩，孔洞-裂缝型储层，上覆膏盐盖层",
                        "porosity_range": "4%~24%",
                        "permeability_range": "0.05~350 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.08,
                        "rock_electric_n": 1.96,
                        "formation_water_salinity": "12000~25000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Galkynysh-1", "test_intervals": [
                        {"name": "牛津阶试气", "top": 2960, "bottom": 3120, "conclusion": "气层",
                         "gas_production": "156万方/天", "oil_production": "凝析油", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "哈萨克斯坦", "aliases": ["哈萨克"], "basins": [
            {"name": "滨里海盆地", "oilfields": [
                {"name": "Kashagan油田", "formations": [
                    {"name": "Asselian组", "aliases": ["Asselian"], "props": {
                        "geologic_age": "早二叠世",
                        "lithology": "孤立生物礁碳酸盐岩，礁核孔洞裂缝发育，礁间泥灰岩",
                        "porosity_range": "5%~24%",
                        "permeability_range": "0.1~800 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.0,
                        "rock_electric_n": 1.9,
                        "formation_water_salinity": "25000~40000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Kashagan-1", "test_intervals": [
                        {"name": "Asselian组试油", "top": 4020, "bottom": 4230, "conclusion": "油层（带凝析气顶）",
                         "oil_production": "420 m³/d", "gas_production": "大量伴生凝析气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 中东
        {"name": "伊朗", "aliases": [], "basins": [
            {"name": "扎格罗斯盆地", "oilfields": [
                {"name": "Ahwaz油田", "formations": [
                    {"name": "Asmari组", "aliases": ["Asmari"], "props": {
                        "geologic_age": "渐新世-中新世",
                        "lithology": "礁滩相灰岩、白云岩，溶蚀孔洞发育，膏盐盖层",
                        "porosity_range": "6%~26%",
                        "permeability_range": "0.1~400 mD",
                        "reservoir_type": "孔洞型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.02,
                        "rock_electric_n": 1.98,
                        "formation_water_salinity": "15000~28000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Ahwaz-1", "test_intervals": [
                        {"name": "Asmari组试油", "top": 1860, "bottom": 2020, "conclusion": "油层",
                         "oil_production": "280 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "叙利亚", "aliases": [], "basins": [
            {"name": "扎格罗斯盆地北部", "oilfields": [
                {"name": "Omar油田", "formations": [
                    {"name": "Jeribe组", "aliases": ["Jeribe"], "props": {
                        "geologic_age": "中新世",
                        "lithology": "颗粒灰岩、泥粒灰岩，局部白云岩化，孔洞发育",
                        "porosity_range": "5%~22%",
                        "permeability_range": "0.1~250 mD",
                        "reservoir_type": "孔洞型",
                        "rock_electric_a": 1.02,
                        "rock_electric_m": 2.04,
                        "rock_electric_n": 1.96,
                        "formation_water_salinity": "18000~30000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Omar-1", "test_intervals": [
                        {"name": "Jeribe组试油", "top": 1620, "bottom": 1780, "conclusion": "油层",
                         "oil_production": "185 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "也门", "aliases": [], "basins": [
            {"name": "马里卜-沙布瓦盆地", "oilfields": [
                {"name": "Marib油田", "formations": [
                    {"name": "Naifa组", "aliases": ["Naifa"], "props": {
                        "geologic_age": "晚白垩世",
                        "lithology": "礁滩相颗粒灰岩、白云岩，孔洞-裂缝复合储层",
                        "porosity_range": "4%~20%",
                        "permeability_range": "0.05~180 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.03,
                        "rock_electric_m": 2.06,
                        "rock_electric_n": 1.95,
                        "formation_water_salinity": "12000~24000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Marib-1", "test_intervals": [
                        {"name": "Naifa组试油", "top": 2240, "bottom": 2410, "conclusion": "油层",
                         "oil_production": "128 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "卡塔尔", "aliases": [], "basins": [
            {"name": "卡塔尔盆地", "oilfields": [
                {"name": "北方气田", "formations": [
                    {"name": "Khuff组", "aliases": ["Khuff"], "props": {
                        "geologic_age": "二叠纪",
                        "lithology": "厚层颗粒灰岩、泥粒灰岩，夹硬石膏与盐岩隔层，孔洞晶间孔裂缝复合",
                        "porosity_range": "2%~18%",
                        "permeability_range": "0.01~150 mD",
                        "reservoir_type": "孔洞-裂缝型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.1,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "20000~32000 mg/L"
                    }}
                ], "wells": [
                    {"name": "North-1", "test_intervals": [
                        {"name": "Khuff组试气", "top": 2620, "bottom": 2840, "conclusion": "气层",
                         "gas_production": "220万方/天", "oil_production": "少量凝析油", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "科威特", "aliases": [], "basins": [
            {"name": "阿拉伯盆地", "oilfields": [
                {"name": "Burgan油田", "formations": [
                    {"name": "Wara组", "aliases": ["Wara"], "props": {
                        "geologic_age": "早白垩世",
                        "lithology": "生物碎屑灰岩、颗粒灰岩，局部砂质灰岩，泥质条带发育",
                        "porosity_range": "6%~24%",
                        "permeability_range": "0.1~300 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.02,
                        "rock_electric_m": 2.0,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "18000~30000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Burgan-1", "test_intervals": [
                        {"name": "Wara组试油", "top": 1120, "bottom": 1210, "conclusion": "油层",
                         "oil_production": "320 m³/d", "gas_production": "少量伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "伊拉克", "aliases": [], "basins": [
            {"name": "美索不达米亚盆地", "oilfields": [
                {"name": "Rumaila油田", "formations": [
                    {"name": "Zubair组", "aliases": ["Zubair"], "props": {
                        "geologic_age": "早白垩世",
                        "lithology": "滨海-三角洲石英砂岩，夹页岩，砂体连续性好",
                        "porosity_range": "14%~32%",
                        "permeability_range": "1~600 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 1.95,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "12000~25000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Rumaila-1", "test_intervals": [
                        {"name": "Zubair组试油", "top": 2740, "bottom": 2860, "conclusion": "油层",
                         "oil_production": "260 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "阿曼", "aliases": [], "basins": [
            {"name": "阿曼盆地", "oilfields": [
                {"name": "Yibal油田", "formations": [
                    {"name": "Athel组", "aliases": ["Athel"], "props": {
                        "geologic_age": "寒武纪",
                        "lithology": "薄层硅质碎屑岩、粉细砂岩，热成熟度高，古岩溶改造",
                        "porosity_range": "4%~22%",
                        "permeability_range": "0.05~100 mD",
                        "reservoir_type": "孔隙-裂缝型",
                        "rock_electric_a": 1.05,
                        "rock_electric_m": 2.1,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "10000~20000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Yibal-1", "test_intervals": [
                        {"name": "Athel组试油", "top": 1360, "bottom": 1480, "conclusion": "凝析油层",
                         "oil_production": "142 m³/d", "gas_production": "凝析气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "阿联酋", "aliases": [], "basins": [
            {"name": "阿拉伯盆地", "oilfields": [
                {"name": "Zakum油田", "formations": [
                    {"name": "Shuaiba组", "aliases": ["Shuaiba"], "props": {
                        "geologic_age": "早白垩世",
                        "lithology": "厚层生物礁灰岩、泥粒灰岩，礁核礁后差异大，溶蚀孔洞发育",
                        "porosity_range": "6%~28%",
                        "permeability_range": "0.1~500 mD",
                        "reservoir_type": "孔洞型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.0,
                        "rock_electric_n": 1.95,
                        "formation_water_salinity": "15000~28000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Zakum-1", "test_intervals": [
                        {"name": "Shuaiba组试油", "top": 2140, "bottom": 2300, "conclusion": "油层",
                         "oil_production": "310 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "沙特阿拉伯", "aliases": ["沙特"], "basins": [
            {"name": "阿拉伯盆地", "oilfields": [
                {"name": "Ghawar油田", "formations": [
                    {"name": "Arab-D组", "aliases": ["Arab-D"], "props": {
                        "geologic_age": "晚侏罗世",
                        "lithology": "颗粒灰岩、鲕粒灰岩，溶蚀孔洞发育，上部硬石膏盖层",
                        "porosity_range": "8%~26%",
                        "permeability_range": "1~800 mD",
                        "reservoir_type": "孔洞型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 1.95,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "20000~35000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Ghawar-1", "test_intervals": [
                        {"name": "Arab-D组试油", "top": 1700, "bottom": 1830, "conclusion": "油层",
                         "oil_production": "360 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 东南亚
        {"name": "印度尼西亚", "aliases": ["印尼"], "basins": [
            {"name": "库泰盆地", "oilfields": [
                {"name": "Attaka油田", "formations": [
                    {"name": "Balikpapan组", "aliases": ["Balikpapan"], "props": {
                        "geologic_age": "中新世",
                        "lithology": "三角洲前缘细中砂岩，砂泥互层频繁，煤层、炭质泥岩普遍",
                        "porosity_range": "16%~36%",
                        "permeability_range": "0.5~600 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.05,
                        "rock_electric_m": 1.95,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "4000~12000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Attaka-1", "test_intervals": [
                        {"name": "Balikpapan组试油", "top": 1780, "bottom": 1920, "conclusion": "油层",
                         "oil_production": "176 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "缅甸", "aliases": [], "basins": [
            {"name": "伊洛瓦底盆地", "oilfields": [
                {"name": "Yadana气田", "formations": [
                    {"name": "上新统三角洲砂岩", "aliases": ["上新统", "Pliocene"], "props": {
                        "geologic_age": "上新世",
                        "lithology": "近海三角洲砂岩、泥岩互层，河道砂、滩砂为储层，成岩弱孔隙保存好",
                        "porosity_range": "20%~38%",
                        "permeability_range": "2~800 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.08,
                        "rock_electric_m": 1.92,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "6000~14000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Yadana-1", "test_intervals": [
                        {"name": "上新统试气", "top": 2160, "bottom": 2320, "conclusion": "气层",
                         "gas_production": "108万方/天", "oil_production": "微量凝析油", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "越南", "aliases": [], "basins": [
            {"name": "九龙盆地", "oilfields": [
                {"name": "白虎油田", "formations": [
                    {"name": "渐新统砂岩", "aliases": ["渐新统"], "props": {
                        "geologic_age": "渐新世",
                        "lithology": "三角洲分流河道砂岩，分选中等，泥岩夹层发育，断块控制强",
                        "porosity_range": "15%~33%",
                        "permeability_range": "1~550 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.04,
                        "rock_electric_m": 1.96,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "8000~18000 mg/L"
                    }},
                    {"name": "基底花岗岩潜山", "aliases": ["基底潜山", "花岗岩潜山"], "props": {
                        "geologic_age": "前寒武纪",
                        "lithology": "花岗岩、花岗片麻岩，裂缝、溶蚀孔洞为主要储集空间",
                        "porosity_range": "2%~12%",
                        "permeability_range": "0.01~200 mD",
                        "reservoir_type": "裂缝-孔洞型",
                        "rock_electric_a": 1.0,
                        "rock_electric_m": 2.2,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "15000~25000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Bach Ho-1", "test_intervals": [
                        {"name": "渐新统试油", "top": 2010, "bottom": 2140, "conclusion": "油层",
                         "oil_production": "210 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        {"name": "柬埔寨", "aliases": [], "basins": [
            {"name": "暹罗湾盆地", "oilfields": [
                {"name": "Kep油田", "formations": [
                    {"name": "渐新统砂岩", "aliases": ["渐新统"], "props": {
                        "geologic_age": "渐新世",
                        "lithology": "滨海三角洲砂岩，分选良好，泥岩夹层发育",
                        "porosity_range": "14%~32%",
                        "permeability_range": "1~450 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.06,
                        "rock_electric_m": 1.94,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "7000~16000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Kep-1", "test_intervals": [
                        {"name": "渐新统试油", "top": 1520, "bottom": 1680, "conclusion": "油层",
                         "oil_production": "96 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]},
        # 南亚
        {"name": "巴基斯坦", "aliases": [], "basins": [
            {"name": "印度河下游盆地", "oilfields": [
                {"name": "Dak油田", "formations": [
                    {"name": "Lower Goru组", "aliases": ["下Goru组"], "props": {
                        "geologic_age": "晚白垩世",
                        "lithology": "三角洲前缘细砂岩、粉砂岩，砂泥互层，局部钙质胶结",
                        "porosity_range": "12%~30%",
                        "permeability_range": "0.5~300 mD",
                        "reservoir_type": "孔隙型",
                        "rock_electric_a": 1.04,
                        "rock_electric_m": 1.96,
                        "rock_electric_n": 2.0,
                        "formation_water_salinity": "9000~20000 mg/L"
                    }}
                ], "wells": [
                    {"name": "Dak-1", "test_intervals": [
                        {"name": "Lower Goru组试油", "top": 2480, "bottom": 2640, "conclusion": "油层",
                         "oil_production": "88 m³/d", "gas_production": "伴生气", "water_production": "0"}
                    ]}
                ]}
            ]}
        ]}
    ],

    "methods": [
        {
            "method_name": "REG气层综合解释法",
            "applicable_regions": ["孟加拉国", "乌兹别克斯坦", "卡塔尔", "阿尔及利亚", "缅甸"],
            "applicable_formations": ["Bokabil组", "Kugitang组", "Khuff组", "Tadrart组", "上新统三角洲砂岩"],
            "input_curves": ["GR", "RT", "AC", "DEN", "NPHI"],
            "formula": "REG = (ΔNPHI * ΔDEN) / (RT_base * GR_norm)",
            "threshold": {"gas_layer": ">0.22", "water_layer": "<0.1"},
            "limitation": "高泥质、致密层失效；泥质重时需校正Vsh",
            "reference_case": "Titas气田、Gazli气田、Hassi R'Mel气田、Yadana气田标定",
            "code_path": "logknow/methods/reg_gas/reg_gas.py",
            "config_path": "logknow/methods/reg_gas/config.yaml",
            "test_path": "logknow/methods/reg_gas/test_reg_gas.py",
            "doc_path": "logknow/methods/reg_gas/README.md"
        },
        {
            "method_name": "盐下碳酸盐岩油层解释图版",
            "applicable_regions": ["巴西", "哈萨克斯坦", "墨西哥"],
            "applicable_formations": ["Barra Velha组", "Asselian组", "Ek-Balam组"],
            "input_curves": ["GR", "RT", "AC", "DEN", "NPHI", "PEF"],
            "formula": "孔隙度=密度-中子交会；含油饱和度=阿尔奇公式",
            "threshold": {"oil_layer": "Rt>30Ω·m, 孔隙度>5%", "water_layer": "Rt<15Ω·m"},
            "limitation": "孔洞非均质性强；盐层畸变干扰；裂缝段易误判",
            "reference_case": "Libra油田、Kashagan油田、Cantarell油田标定",
            "code_path": "logknow/methods/subsalt_carbonate/subsalt_oil.py",
            "config_path": "logknow/methods/subsalt_carbonate/config.yaml",
            "test_path": "logknow/methods/subsalt_carbonate/test_subsalt.py",
            "doc_path": "logknow/methods/subsalt_carbonate/README.md"
        },
        {
            "method_name": "陆相碎屑岩油层解释图版",
            "applicable_regions": ["乍得", "尼日尔", "苏丹", "利比亚", "伊拉克", "印度尼西亚", "埃及", "越南", "柬埔寨", "巴基斯坦", "哥伦比亚", "挪威", "英国"],
            "applicable_formations": ["Kome组", "Goulbi砂岩", "Abu Gabra组", "Sarir砂岩", "Zubair组", "Balikpapan组", "Belayim组", "渐新统砂岩", "Lower Goru组", "Carbonera组", "Brent组", "Paleocene浊积砂"],
            "input_curves": ["GR", "RT", "AC", "DEN", "NPHI"],
            "formula": "孔隙度=声波时差法；含油饱和度=阿尔奇公式",
            "threshold": {"oil_layer": "Rt>15Ω·m, 孔隙度>15%", "water_layer": "Rt<8Ω·m"},
            "limitation": "煤层、炭质泥岩假高阻干扰；钙质夹层易误判",
            "reference_case": "Kome油田、Goulbi油田、Sarir油田、Fula油田标定",
            "code_path": "logknow/methods/clastic_oil/clastic_oil.py",
            "config_path": "logknow/methods/clastic_oil/config.yaml",
            "test_path": "logknow/methods/clastic_oil/test_clastic.py",
            "doc_path": "logknow/methods/clastic_oil/README.md"
        },
        {
            "method_name": "礁滩碳酸盐岩油气层解释图版",
            "applicable_regions": ["乌兹别克斯坦", "土库曼斯坦", "卡塔尔", "阿联酋", "科威特", "沙特阿拉伯", "阿曼", "伊朗", "叙利亚", "也门"],
            "applicable_formations": ["Kugitang组", "牛津阶礁滩组", "Khuff组", "Shuaiba组", "Wara组", "Arab-D组", "Athel组", "Asmari组", "Jeribe组", "Naifa组"],
            "input_curves": ["GR", "RT", "AC", "DEN", "NPHI", "PEF"],
            "formula": "储层分类=孔隙度+渗透率交会；气层识别=中子密度挖掘效应",
            "threshold": {"gas_layer": "挖掘效应明显, Rt>40Ω·m", "oil_layer": "Rt>25Ω·m, 孔隙度>6%", "water_layer": "Rt<20Ω·m"},
            "limitation": "膏盐夹层干扰；礁相相变快；裂缝段定量难",
            "reference_case": "Gazli气田、Galkynysh气田、北方气田、Zakum油田、Ghawar油田标定",
            "code_path": "logknow/methods/reef_carbonate/reef_oilgas.py",
            "config_path": "logknow/methods/reef_carbonate/config.yaml",
            "test_path": "logknow/methods/reef_carbonate/test_reef.py",
            "doc_path": "logknow/methods/reef_carbonate/README.md"
        },
        {
            "method_name": "页岩致密储层解释图版",
            "applicable_regions": ["阿根廷"],
            "applicable_formations": ["Vaca Muerta组"],
            "input_curves": ["GR", "RT", "AC", "DEN", "NPHI", "ECS"],
            "formula": "总有机碳=ΔlogR法；含气量=等温吸附+游离气",
            "threshold": {"sweet_spot": "TOC>2%, 孔隙度>6%", "non_reservoir": "TOC<1%"},
            "limitation": "非均质性极强；水平井参数难定量；需岩心标定",
            "reference_case": "Vaca Muerta页岩标定",
            "code_path": "logknow/methods/shale_tight/shale_tight.py",
            "config_path": "logknow/methods/shale_tight/config.yaml",
            "test_path": "logknow/methods/shale_tight/test_shale.py",
            "doc_path": "logknow/methods/shale_tight/README.md"
        },
        {
            "method_name": "GR泥质含量计算法",
            "applicable_regions": [],
            "applicable_formations": [],
            "input_curves": ["GR"],
            "formula": "Vsh = (GR - GR_clean) / (GR_shale - GR_clean)；经验校正：Ishiguro 或 Clavier 公式",
            "threshold": {"clean_sand": "<15%", "shaly_sand": "15%~40%", "shale": ">40%"},
            "limitation": "放射性矿物、钾长石会造成假高值；需区域标定纯岩基线",
            "reference_case": "全球碎屑岩通用",
            "code_path": "logknow/methods/basic/vsh_gr.py",
            "config_path": "logknow/methods/basic/config_vsh.yaml",
            "test_path": "logknow/methods/basic/test_vsh.py",
            "doc_path": "logknow/methods/basic/vsh_gr.md"
        },
        {
            "method_name": "声波孔隙度计算法",
            "applicable_regions": [],
            "applicable_formations": [],
            "input_curves": ["AC"],
            "formula": "POR = (Δt - Δtma) / (Δtf - Δtma)；压实校正用 Raymer-Hunt-Gardner",
            "threshold": {"effective_reservoir": ">10%"},
            "limitation": "裂缝、次生孔隙、天然气会造成时差偏大；需区域标定骨架时差",
            "reference_case": "全球通用",
            "code_path": "logknow/methods/basic/por_ac.py",
            "config_path": "logknow/methods/basic/config_por_ac.yaml",
            "test_path": "logknow/methods/basic/test_por_ac.py",
            "doc_path": "logknow/methods/basic/por_ac.md"
        },
        {
            "method_name": "密度-中子交会孔隙度法",
            "applicable_regions": [],
            "applicable_formations": [],
            "input_curves": ["DEN", "NPHI"],
            "formula": "POR = 双矿物交会求解；气层识别挖掘效应",
            "threshold": {"effective_reservoir": ">5%"},
            "limitation": "重矿物、石膏、盐岩会干扰密度值；天然气造成挖掘效应",
            "reference_case": "碳酸盐岩+碎屑岩通用",
            "code_path": "logknow/methods/basic/por_den_nphi.py",
            "config_path": "logknow/methods/basic/config_por_den_nphi.yaml",
            "test_path": "logknow/methods/basic/test_por_den_nphi.py",
            "doc_path": "logknow/methods/basic/por_den_nphi.md"
        },
        {
            "method_name": "阿尔奇含油饱和度计算法",
            "applicable_regions": [],
            "applicable_formations": [],
            "input_curves": ["RT", "POR"],
            "formula": "Sw = (a*b*Rw / (Rt * POR^m))^(1/n)；So = 1 - Sw",
            "threshold": {"oil_layer": "So>50%", "water_layer": "Sw>80%"},
            "limitation": "泥质砂岩需用修正阿尔奇；裂缝型储层误差大；需准确Rw",
            "reference_case": "全球通用，区域标定a,m,n参数",
            "code_path": "logknow/methods/basic/sw_archie.py",
            "config_path": "logknow/methods/basic/config_sw_archie.yaml",
            "test_path": "logknow/methods/basic/test_sw_archie.py",
            "doc_path": "logknow/methods/basic/sw_archie.md"
        },
        {
            "method_name": "渗透率经验估算法",
            "applicable_regions": [],
            "applicable_formations": [],
            "input_curves": ["POR", "VSH"],
            "formula": "K = C * POR^n；常用 Timur 公式或区域经验公式",
            "threshold": {"high_perm": ">100 mD", "medium_perm": "1~100 mD", "low_perm": "<1 mD"},
            "limitation": "裂缝、溶蚀孔洞储层误差大；必须区域标定",
            "reference_case": "孔隙型储层通用",
            "code_path": "logknow/methods/basic/perm_empirical.py",
            "config_path": "logknow/methods/basic/config_perm.yaml",
            "test_path": "logknow/methods/basic/test_perm.py",
            "doc_path": "logknow/methods/basic/perm_empirical.md"
        },
        {
            "method_name": "束缚水饱和度计算法",
            "applicable_regions": [],
            "applicable_formations": [],
            "input_curves": ["POR", "PERM"],
            "formula": "Swi = (a / (K^b * POR^c))^d；常用 Timur 或 Wyllie-Rose",
            "threshold": {"movable_oil": "Sw - Swi > 20%"},
            "limitation": "仅适用于孔隙型储层；裂缝、孔洞不适用",
            "reference_case": "全球孔隙型储层通用",
            "code_path": "logknow/methods/basic/swi_timur.py",
            "config_path": "logknow/methods/basic/config_swi.yaml",
            "test_path": "logknow/methods/basic/test_swi.py",
            "doc_path": "logknow/methods/basic/swi_timur.md"
        }
    ]
}


def bootstrap():
    gs = GraphStore()
    print("🔧 开始全量初始化 logknow 知识库（30国校验版）...")

    for country in BENCHMARK_DATA["countries"]:
        props = {"aliases": country["aliases"]}
        gs.add_node("country", country["name"], props)
        for basin in country["basins"]:
            gs.add_node("basin", basin["name"], {})
            gs.add_edge("country", country["name"], "contains", "basin", basin["name"])
            for oilfield in basin["oilfields"]:
                gs.add_node("oilfield", oilfield["name"], {})
                gs.add_edge("basin", basin["name"], "contains", "oilfield", oilfield["name"])
                for fm in oilfield["formations"]:
                    fm_props = fm.get("props", {}).copy()
                    fm_props["aliases"] = fm.get("aliases", [])
                    gs.add_node("formation", fm["name"], fm_props)
                    gs.add_edge("oilfield", oilfield["name"], "has_formation", "formation", fm["name"])
                for well in oilfield.get("wells", []):
                    gs.add_node("well", well["name"], {})
                    gs.add_edge("oilfield", oilfield["name"], "has_well", "well", well["name"])
                    for ti in well.get("test_intervals", []):
                        ti_name = f"{well['name']}_{ti['name']}"
                        gs.add_node("test_interval", ti_name, ti)
                        gs.add_edge("well", well["name"], "has_test", "test_interval", ti_name)
                        for fm in oilfield["formations"]:
                            gs.add_edge("test_interval", ti_name, "belongs_to", "formation", fm["name"])

    for m in BENCHMARK_DATA["methods"]:
        gs.add_node("interpretation_method", m["method_name"], m)
        for fm in m["applicable_formations"]:
            gs.add_edge(
                "interpretation_method", m["method_name"],
                "applicable_to",
                "formation", fm
            )

    print(f"✅ 初始化完成：共 {len(gs.nodes)} 个实体，{len(gs.edges)} 条关系")
    print(f"📁 图谱持久化路径：{GRAPH_FILE}")
    return gs


class KnowledgeAPI:
    def __init__(self):
        self.graph = GraphStore()

    def query_methods(self, region: str, formation: str):
        methods = self.graph.match_methods(region, formation)
        return {
            "ok": True,
            "region": region,
            "formation": formation,
            "count": len(methods),
            "methods": methods
        }

    def lookup_entity(self, etype: str, name: str):
        node = self.graph.lookup(etype, name)
        if not node:
            return {"ok": False, "msg": "未找到实体"}
        children = self.graph.get_children(etype, name)
        return {"ok": True, "entity": node, "children": children}

    def query_formation_props(self, formation: str):
        node = self.graph.lookup("formation", formation)
        if not node:
            return {"ok": False, "msg": "未找到该地层参数"}
        return {"ok": True, "formation": formation, "props": node["props"]}

    def query_well_test(self, well_name: str):
        tests = self.graph.get_children("well", well_name, child_type="test_interval")
        return {"ok": True, "well": well_name, "test_intervals": tests}


def main():
    parser = argparse.ArgumentParser(description="logknow 知识库初始化与一致性校验")
    parser.add_argument("--validate", action="store_true", help="仅执行一致性校验，不入库")
    args = parser.parse_args()

    if args.validate:
        validator = KnowledgeValidator(BENCHMARK_DATA)
        ok = validator.validate()
        sys.exit(0 if ok else 1)

    bootstrap()


if __name__ == "__main__":
    main()
