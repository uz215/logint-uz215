# 3-SPS-111D 井目录知识（未填写/未填写/未填写/未填写/ARAM/3-SPS-111D）

- 知识层级: 未填写/未填写/未填写/未填写/ARAM/3-SPS-111D
- 井目录: D:\360\Bangladesh\3-SPS-111D
- 来源: 标定表
- 深度说明: 录井/XRD/XRF 为录井深度，本摘要按大致井段统计，不强制与测井深度对齐；SWC 为测井深度。用于 logInt 检索时按井段/岩性/数值范围引用。
- 错误: 未找到井目录标定表（SWC/XRD/XRF/Coredata）；将用设计/录井图/井信息生成知识

## 0. 基础数据
| 项 | 值 |
|---|---|
| country | 未填写 |
| field | ARAM |
| well | 3-SPS-111D |
| company | PETROBRAS |
| coordinates | {'latitude': '25Â° 38\' 39.488" S', 'longitude': '44Â° 36\' 2.154" W'} |
| bit_size | 8.5 |
| bit_program | 8.5 |
| mud_type | FPBNA Oleofinico com Salmoura de Cloreto de calcio |
| mud_density | 12.30000019073 |
| mud_viscosity | 142 |
| fluid_loss | 2.400000095367 |
| note | 坐标/井别/钻头程序/套管程序/日期等归基础数据；空值表示井信息未提供。 |

## 0b. 地层
- 地层顶来自井数据 Fm/Formation 表或地质设计；逐条岩性知识带 formation；无地层顶时标“未提供”。

## 6c. 测井解释
- 层数: 37；岩性: {'limestone': 33, 'dolomite': 2, 'halite': 1, 'anhydrite': 1}；流体: {'DRY': 21, 'OIL': 12, 'NonReservoir': 2, 'WATER': 2}
| 顶 | 底 | 岩性 | 解释 |
|---|---|---|---|
| 6487.8 | 6489.9 | limestone | OIL |
| 6522.0 | 6526.6 | limestone | OIL |
| 6528.9 | 6530.3 | limestone | OIL |
| 6536.0 | 6537.8 | limestone | DRY |
| 6607.0 | 6628.3 | limestone | OIL |
| 6628.4 | 6629.2 | dolomite | DRY |
| 6631.1 | 6636.6 | limestone | OIL |
| 6638.2 | 6642.4 | limestone | DRY |
| 6644.1 | 6645.1 | limestone | OIL |
| 6648.7 | 6649.4 | limestone | OIL |
| 6649.5 | 6654.1 | limestone | DRY |
| 6659.7 | 6661.6 | limestone | OIL |
| 6667.5 | 6668.1 | limestone | OIL |
| 6668.2 | 6674.7 | limestone | DRY |
| 6674.8 | 6677.2 | limestone | OIL |

## 7. 录井图
- 井目录未发现标准 masterlog/录井图；岩性段以 lithall/SWC/XRD 近似。

## 8. logInt 调用提示
- 查询井名 + 井段/岩性关键词；本摘要用于区域/本井先验，不替代测井点级标定。