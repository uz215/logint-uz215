---
title: 1-SPS-108 / 地质·地层
category: stratigraphy
well_name: 1-SPS-108
country: Brazil
basin: 桑托斯盆地
sag: 中央隆起带
structure: CuraCao构造
field: ARAM油田
generator: kb_ingest
region: 桑托斯盆地
updated_at: 2026-11-08 19:14:14
---
# 1-SPS-108 / stratigraphy


## 自动抽取（2026-11-08 18:12）

> 由 `kb_ingest` 从井资料目录抽取；只收无歧义项，待核见本节末。源：`CT CMG 025 2022 SPS-108 Parceria 28_03_22 SEDIMENTOLOGICAL DESCRIPTIONS OF SIDEWALL （壁心沉积描述及薄片照片）.pdf`、`CT CMG 025 2022 SPS-108 Parceria 28_03_22（灰岩薄片照片）.pdf`、`CT_CMG_19_22_1SPS108SP_INTERNAL（82块SWC宏观描述）.pdf`、`CT_GEG_001_22_SPS-108_petro_macro &amp; micro PA（火成岩壁心宏微观鉴定报告）.pdf`、`CuraCao-1井数据 .xlsx`、`Curacao-1井阶段汇报（测井）.pptx`

### 层位/组（21）

- PIC、Barra Velha、Ariri、Parati Basalt、BVE、Parati 
Basalt、Marambaia、Itajai-Açu、Itanhaem、Itajaí-Açu、Itanhaém、M Lula、BVE110、BVE120、BVE130、BVE200、M Lula、BVE110、BVE120、BVE130、BVE200

### 参数（5）

| 参数 | 值 | 单位 | 来源 |
|---|---|---|---|
| 构造高点 | -6200.0 | m | 巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P5 |
| 闭合幅度 | 500.0 | m | 巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P5 |
| 圈闭面积 | 1307.0 | km2 | 巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P5 |
| 溢出点 | -6375.0 | m | 巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P6 |
| 目的层厚度 | 136.0 | m | 巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P6 |

```json
{
  "formation_tops": [
    {
      "formation": "M Lula",
      "top": 6302.0,
      "base": 6319.0,
      "source": "CuraCao-1井数据 .xlsx:Fm"
    },
    {
      "formation": "BVE110",
      "top": 6319.0,
      "base": 6350.0,
      "source": "CuraCao-1井数据 .xlsx:Fm"
    },
    {
      "formation": "BVE120",
      "top": 6350.0,
      "base": 6420.0,
      "source": "CuraCao-1井数据 .xlsx:Fm"
    },
    {
      "formation": "BVE130",
      "top": 6420.0,
      "base": 6439.0,
      "source": "CuraCao-1井数据 .xlsx:Fm"
    },
    {
      "formation": "BVE200",
      "top": 6439.0,
      "base": 6476.0,
      "source": "CuraCao-1井数据 .xlsx:Fm"
    }
  ],
  "target_formation": "",
  "formation_names": [
    "M Lula",
    "BVE110",
    "BVE120",
    "BVE130",
    "BVE200"
  ],
  "note": "地层顶来自井数据 Fm/Formation 表或地质设计；逐条岩性知识带 formation；无地层顶时标“未提供”。",
  "auto_ingest": {
    "generated_at": "2026-11-08 18:12",
    "intervals": [],
    "params": {
      "构造高点": {
        "value": -6200.0,
        "unit": "m",
        "cat": "stratigraphy",
        "src": "巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P5",
        "conf": 0.6
      },
      "闭合幅度": {
        "value": 500.0,
        "unit": "m",
        "cat": "stratigraphy",
        "src": "巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P5",
        "conf": 0.6
      },
      "圈闭面积": {
        "value": 1307.0,
        "unit": "km2",
        "cat": "stratigraphy",
        "src": "巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P5",
        "conf": 0.6
      },
      "溢出点": {
        "value": -6375.0,
        "unit": "m",
        "cat": "stratigraphy",
        "src": "巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P6",
        "conf": 0.6
      },
      "目的层厚度": {
        "value": 136.0,
        "unit": "m",
        "cat": "stratigraphy",
        "src": "巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf@P6",
        "conf": 0.6
      }
    },
    "levels": [
      "PIC",
      "Barra Velha",
      "Ariri",
      "Parati Basalt",
      "BVE",
      "Parati \nBasalt",
      "Marambaia",
      "Itajai-Açu",
      "Itanhaem",
      "Itajaí-Açu",
      "Itanhaém",
      "M Lula",
      "BVE110",
      "BVE120",
      "BVE130",
      "BVE200"
    ],
    "sources": [
      "CT CMG 025 2022 SPS-108 Parceria 28_03_22 SEDIMENTOLOGICAL DESCRIPTIONS OF SIDEWALL （壁心沉积描述及薄片照片）.pdf",
      "CT CMG 025 2022 SPS-108 Parceria 28_03_22（灰岩薄片照片）.pdf",
      "CT_CMG_19_22_1SPS108SP_INTERNAL（82块SWC宏观描述）.pdf",
      "CT_GEG_001_22_SPS-108_petro_macro &amp; micro PA（火成岩壁心宏微观鉴定报告）.pdf",
      "CuraCao-1井数据 .xlsx",
      "Curacao-1井2022-0216.pptx",
      "Curacao-1井阶段汇报（测井）.pptx",
      "Drilling Workshop Curaçao.pdf",
      "PreRead - Aram - WS8 DST Design.pdf",
      "井目录知识流水线(build_well_knowledge)",
      "巴西阿拉姆项目Curacao-1井跟踪日报(2021-11-14）-1.pdf",
      "巴西阿拉姆项目Curacao-1井跟踪日报(2021.8.28).pdf"
    ],
    "pending": []
  }
}
```
