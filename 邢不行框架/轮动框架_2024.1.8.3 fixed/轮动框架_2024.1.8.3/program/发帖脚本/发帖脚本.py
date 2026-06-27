"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import pandas as pd
from program.Config import *

name = __import__(f'program.轮动策略.{sft_stg_file}', fromlist=('',))

param = name.strategy_param[0].replace('.csv', '')

rtn_path = os.path.join(root_path, f'data/回测结果/统计信息/{sft_stg_file}_策略评价_{param}.csv')
select_stat_path = os.path.join(root_path, f'data/回测结果/统计信息/{sft_stg_file}_year_{param}.csv')
describe_path = os.path.join(root_path, f'data/回测结果/统计信息/{sft_stg_file}_describe_{param}.csv')

rtn = pd.read_csv(rtn_path, encoding='gbk', index_col=[0])
year_return = pd.read_csv(select_stat_path, encoding='gbk')
describe = pd.read_csv(describe_path, encoding='gbk')

# 低版本的pandas，不支持 index 参数
# 安装高版本 pandas 命令 ： pip install pandas==1.5.3
tx_rtn = rtn.to_markdown()

tx_year_return = year_return.to_markdown(index=False)
tx_describe = describe.to_markdown(index=False)

with open(root_path + '/program/发帖脚本/样本模板.txt', 'r', encoding='utf8') as file:
    bbs_post = file.read()
    bbs_post = bbs_post % (tx_rtn, tx_year_return, tx_describe)
    print(bbs_post)
