"""
2024分享会
author: 邢不行
微信: xbx9585
"""
import pandas as pd

import program.Config as Cfg
import program.Function as Fun
import program.RainbowV1 as Rb
from program.trade_calendar import TradeCalendar

import warnings

warnings.filterwarnings('ignore')
# ===初始化
Rb.robot_api = Cfg.robot_api
Rb.proxies = Cfg.proxies
# ===生成交易日历
trade_plan_df = pd.read_csv(Cfg.trade_plan_path, encoding='gbk', parse_dates=['交易日期'])
tc = TradeCalendar(Rb)
strategies_info = {}

# ===选股策略交易计划
# 假设需要在每周的第一个交易日执行选股策略
for stg_name in Cfg.select_strategy_list:
    files, strategies_info = Fun.get_select_strategy_info(stg_name, Cfg.select_program_path, strategies_info)
    if len(files) == 0:
        Rb.record_log(f'选股策略：{stg_name}  策略文件不存在或未配置offset信息，请检查！', send=True)
    for f in files.keys():
        path = Cfg.select_res_path + f + '.csv'
        trade_plan_df = Fun.get_trade_plan(trade_plan_df, stg_name, path, tc, files[f], Rb, '选股')

# ===轮动策略交易计划
# 假设需要在每周的第一个交易日执行轮动策略
for stg_name in Cfg.shift_strategy_list:
    files, strategies_info = Fun.get_shift_strategy_info(stg_name, Cfg.shift_program_path, strategies_info)
    if len(files) == 0:
        Rb.record_log(f'轮动策略：{stg_name}  策略文件不存在或未配置offset信息，请检查！', send=True)
    for f in files.keys():
        path = Cfg.shift_res_path + f + '.csv'
        trade_plan_df = Fun.get_trade_plan(trade_plan_df, stg_name, path, tc, files[f], Rb, '轮动')

# ===保存数据
# 如果选到货币eft，直接删除。会自动买逆回购，收益查不到，但是手续费更低。
trade_plan_df = trade_plan_df[trade_plan_df['证券代码'] != 'sz159001']
# 保存数据
trade_plan_df.to_csv(Cfg.trade_plan_path, encoding='gbk', index=False)

# ===生成推荐的配置信息
print('\n ==========以下是根据配置自动推荐的参数，请酌情修改后使用==========\n')
Fun.create_config_info(strategies_info)
