import sqlite3
import os
import json

DB_PATH = r"F:\360\src\data\kb\kb.db"

ALIAS_MAP = {
    "乌兹别克": "乌兹别克斯坦",
    "哈国": "哈萨克斯坦",
    "印尼": "印度尼西亚"
}

def norm_name(s: str):
    if not s:
        return ""
    s = s.strip()
    low = s.lower()
    for k, v in ALIAS_MAP.items():
        if k.lower() == low:
            return v
    return s

def get_conn():
    return sqlite3.connect(DB_PATH)

def ensure_entity(name: str, kind: str, source_doc="", conf=0.9):
    canon = norm_name(name)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM entity WHERE kind = ? AND canonical = ?", (kind, canon))
    row = cur.fetchone()
    if row:
        eid = row[0]
        cur.execute("UPDATE entity SET name=?, source_doc=?, conf=? WHERE id=?",
                    (name, source_doc, conf, eid))
    else:
        cur.execute("""
            INSERT INTO entity(kind, name, canonical, props_json, source_doc, conf)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (kind, name, canon, "{}", source_doc, conf))
        eid = cur.lastrowid
    conn.commit()
    conn.close()
    return str(eid)

def add_fact(subj_id: str, rel: str, obj: dict, source_doc="", source_loc="", conf=0.9):
    conn = get_conn()
    cur = conn.cursor()
    obj_str = json.dumps(obj, ensure_ascii=False)
    cur.execute("""
        INSERT INTO fact(subj, rel, obj, props_json, source_doc, source_loc, conf, extractor)
        VALUES (?, ?, ?, '{}', ?, ?, ?, 'bootstrap')
    """, (subj_id, rel, obj_str, source_doc, source_loc, conf))
    conn.commit()
    conn.close()

def bootstrap():
    # 孟加拉
    c_bd = ensure_entity("孟加拉", "country")
    b_bd = ensure_entity("孟加拉盆地", "basin")
    add_fact(b_bd, "located_in", {"country": "孟加拉"}, source_doc="bootstrap")

    fm_bhuban = ensure_entity("Bhuban", "formation")
    add_fact(fm_bhuban, "located_in_basin", {"basin": "孟加拉盆地"}, source_doc="bootstrap")
    add_fact(fm_bhuban, "strata_meta", {
        "sub_layer": "上部气组",
        "lithology": ["石英砂岩", "粉砂岩", "泥岩夹层"],
        "log_response": {
            "gas_sand": {"GR": "25–55", "RT": "8–30", "DEN": "2.38–2.50", "CNL": "12–20", "DT": "72–86"},
            "shale": {"GR": "85–130", "RT": "1–4", "DEN": "2.52–2.62", "CNL": "22–32", "DT": "90–105"}
        },
        "gwc": {"Bhuban Upper": "分气组独立气水界面"},
        "hydrocarbon_type": "天然气",
        "recommend_methods": ["REG气层综合解释法"]
    }, source_doc="bootstrap")

    m_reg = ensure_entity("REG气层综合解释法", "interp_method")
    add_fact(m_reg, "method_meta", {
        "applicable_condition": "碎屑岩气藏，中高孔隙度，三角洲、滨海砂体",
        "input_curves": ["GR", "RT", "DEN", "CNL", "AC"],
        "formula": "电阻率-中子密度挖掘效应联合判气",
        "threshold": {"gas_cut": 0.04},
        "limitation": "高矿化度水层易误判，裂缝碳酸盐岩不适用",
        "reference_case": "孟加拉 Bhuban 组、缅甸海上气田"
    }, source_doc="bootstrap")

    # 巴西
    c_br = ensure_entity("巴西", "country")
    b_santos = ensure_entity("桑托斯盆地", "basin")
    add_fact(b_santos, "located_in", {"country": "巴西"}, source_doc="bootstrap")

    fm_lula = ensure_entity("Lula", "formation")
    add_fact(fm_lula, "located_in_basin", {"basin": "桑托斯盆地"}, source_doc="bootstrap")
    add_fact(fm_lula, "strata_meta", {
        "sub_layer": "盐下碳酸盐岩",
        "lithology": ["溶孔碳酸盐岩", "局部裂缝发育，无溶洞"],
        "log_response": {
            "oil_reservoir": {"GR": "5–20", "RT": "20–200", "DEN": "2.45–2.60", "CNL": "2–8", "DT": "40–60"}
        },
        "gwc": {"Lula": "油水界面随构造/油田变化，需定位至构造、油田甚至单井"},
        "hydrocarbon_type": "原油",
        "recommend_methods": ["碳酸盐岩基质孔隙解释法"]
    }, source_doc="bootstrap")

    m_carbon = ensure_entity("碳酸盐岩基质孔隙解释法", "interp_method")
    add_fact(m_carbon, "method_meta", {
        "applicable_condition": "以溶孔基质孔隙为主，少量裂缝，无大型溶洞",
        "input_curves": ["GR", "RT", "DEN", "CNL", "AC"],
        "formula": "基质孔隙度 + 电阻率烃类判识",
        "threshold": {"por_min": 0.06},
        "limitation": "裂缝密集带、溶洞发育段不适用",
        "reference_case": "巴西桑托斯盐下"
    }, source_doc="bootstrap")

    # 乍得
    c_td = ensure_entity("乍得", "country")
    b_bongor = ensure_entity("邦戈尔盆地", "basin")
    add_fact(b_bongor, "located_in", {"country": "乍得"}, source_doc="bootstrap")

    fm_mimosa = ensure_entity("Mimosa", "formation")
    add_fact(fm_mimosa, "located_in_basin", {"basin": "邦戈尔盆地"}, source_doc="bootstrap")
    add_fact(fm_mimosa, "strata_meta", {
        "sub_layer": "下白垩统砂岩",
        "lithology": ["长石石英砂岩", "泥岩隔层"],
        "log_response": {
            "oil_sand": {"GR": "30–60", "RT": "10–80", "DEN": "2.35–2.48", "CNL": "15–26", "DT": "78–92"}
        },
        "gwc": {"Mimosa": "断块独立油水界面，分断块取值"},
        "hydrocarbon_type": "原油",
        "recommend_methods": ["砂岩常规油层解释法"]
    }, source_doc="bootstrap")

    m_sand_oil = ensure_entity("砂岩常规油层解释法", "interp_method")
    add_fact(m_sand_oil, "method_meta", {
        "applicable_condition": "陆相断陷湖盆砂岩油藏",
        "input_curves": ["GR", "RT", "DEN", "CNL", "AC"],
        "formula": "孔隙度计算 + 饱和度模型",
        "threshold": {"sw_max": 0.6},
        "limitation": "高泥质、高矿化度地层需要校正",
        "reference_case": "乍得邦戈尔盆地多断块"
    }, source_doc="bootstrap")

    print("✅ bootstrap 导入完成")

if __name__ == "__main__":
    bootstrap()
