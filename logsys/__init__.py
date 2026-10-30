# -*- coding: utf-8 -*-
"""logsys 智能测井解释系统 —— 新代码包。

原则：
- 新逻辑进本包，旧 logInt/logKnow/logvis 只做兼容层；
- 每个子模块可独立运行、可单测（不依赖 GUI、不写项目目录）；
- 所有阈值来自 config/*.json，代码内不出现业务阈值。
"""

__version__ = '0.1.0'
