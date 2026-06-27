"""
2024分享会
author: 邢不行
微信: xbx9585
"""
import os
import sys

import program.Config as Cfg
import program.RainbowV1 as Rb

python_exe = sys.executable
Rb.robot_api = Cfg.robot_api
Rb.proxies = Cfg.proxies

# ===执行选股策略
# 假设需要在每周的第一个交易日执行选股策略
os.environ['PYTHONPATH'] = Cfg.select_program_path
res = os.system(f'{python_exe} {Cfg.select_program_path}/program/1_选股数据整理.py {True}')
Rb.record_log(f'选股：1_选股数据整理 已完成，状态码：{res}', send=True)
res = os.system(f'{python_exe} {Cfg.select_program_path}/program/3_遍历选股.py {True} {True} {True}')
Rb.record_log(f'选股：3_遍历回测 已完成，状态码：{res}', send=True)

# ===执行轮动策略
# 假设需要在每周的第一个交易日执行轮动策略（一般来说需要和选股策略保持同步的）
os.environ['PYTHONPATH'] = Cfg.shift_program_path
res = os.system(f'{python_exe} {Cfg.shift_program_path}/program/1_策略数据整理.py {True}')
Rb.record_log(f'轮动：1_策略数据整理 已完成，状态码：{res}', send=True)
res = os.system(f'{python_exe} {Cfg.shift_program_path}/program/3_轮动策略遍历.py {True} {True} {True}')
Rb.record_log(f'轮动：3_轮动策略遍历实盘 已完成，状态码：{res}', send=True)

# ===执行完交易计划记录一下日志。
Rb.record_log('1_执行交易任务 已完成', send=True)

# ===调用脚本2保存下单计划
os.environ['PYTHONPATH'] = Cfg.root_path
os.system(f'{python_exe} {Cfg.root_path}/program/2_生成交易计划.py')
