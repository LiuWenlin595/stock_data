"""
2024分享会
author: 邢不行
微信: xbx9585
"""
import os
import pandas as pd

_ = os.path.abspath(os.path.dirname(__file__))  # 返回当前文件路径
root_path = os.path.abspath(os.path.join(_, '..'))  # 返回根目录文件夹

# ==========需要配置的内容==========
# 选股策略的路径：如果有尾盘模式的项目需要自定义给一个项目
select_program_path = 'D:/Code/直播代码/选股框架_2024.1.8.1'
# 轮动策略的路径
shift_program_path = 'D:/Code/直播代码/轮动框架_2024.1.8.1'

# 需要实盘的选股策略，填该策略的文件名即可，轮动的子策略不需要填进来！！！
select_strategy_list = []
# 需要实盘的轮动策略，填该策略的文件名即可
shift_strategy_list = ['测试策略']

# 交易计划的路径，可以修改成实盘程序中交易计划的路径
trade_plan_path = os.path.join(root_path, 'data/交易计划.csv')
# trade_plan_path = 'C:/Users/Quant/Desktop/直播代码/实盘框架_2024.1.2/Rocket_2024.1.2/data/账户信息/交易计划.csv'

# 发送机器人消息的API
# 相关配置教程：https://bbs.quantclass.cn/thread/10975     注意我们只需要填key=后面的即可
robot_api = ''

# ==========以下内容不需要配置==========

# ===各种策略的最新选股结果
select_res_path = select_program_path + '/data/每日选股/选股策略/'
shift_res_path = shift_program_path + '/data/每日选股/轮动策略/'

# 事件框架的最新选股结果
# event_res_path = event_program_path + '/data/每日选股/事件策略/'  # （如果有的话，注意：暂不支持23版）

# 如果交易计划的文件不存在，就生成一下这个文件
if not os.path.exists(trade_plan_path):
    df = pd.DataFrame(columns=['交易日期', '策略名称', '证券代码', '持仓计划', '其他'])
    df.to_csv(trade_plan_path, encoding='gbk', index=False)

proxies = {}  # 代理服务器
