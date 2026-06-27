"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import os
import program.Function as Fun

# ==========以下内容需要根据实际情况适当改动==========
date_start = '2009-01-01'  # 回测开始时间
date_end = None  # 回测结束时间，将这个参数改为None，就可以数据的最新的选股结果

trading_mode = False  # 是否是交易模式，True代表是交易模式，False代表不是交易模式
# 交易模式下会有以下区别
# 1、交易模式下，脚本1整理数据将从date_start开始。研究模式从股票上线开始（最早到指数开始时间）
# 2、交易模式下，整理当前offset的数据，并且回测也只回测当前offset的数据。研究模式会计算全部offset的数据
# 注意：交易模式下把date_start改成最近的日期可以提高速度
#      但是一定要仔细检查计算的因子会不会因为日期不同，导致计算结果不同，特别是复权数据算出来的因子

# 调用那个策略
sft_stg_file = '测试策略'  # 轮动策略文件

# 选股策略的项目路径
select_program_path = 'D:/Code/直播代码/选股框架_2024.1.8.3/'

# ==========以下内容几乎不需要改动==========
# 根目录
_ = os.path.abspath(os.path.dirname(__file__))  # 返回当前文件路径
root_path = os.path.abspath(os.path.join(_, '..'))  # 返回根目录文件夹

# 多线程的CPU参与计算的数量
n_job = min(60, os.cpu_count() - 1)  # 多线程的最大数量，未修改的joblib在windows环境下只支持最高63

# 主流指数映射表，选ETF的两个点：规模、跟踪误差。
# 注意点1：如果想要删除某个指数，不要修改下面的inx_dict，在轮动策略中过滤此指数即可。例如不想要创业板指数：
#         在filter_and_select_strategies函数中加入all_data = all_data[all_data['策略名称'] != '创业板指数_week_3']
# 注意点2：如果实盘选中了货币ETF，不要买etf，直接空仓，实盘程序会自动帮你买国债逆回购，原因是两者收益接近，但逆回购的手续费低。
inx_dict = {'sh000001': ['上证指数', 'sh510210'],
            'sh000016': ['上证50指数', 'sh510050'],
            'sh000300': ['沪深300指数', 'sh510300'],
            'sh000905': ['中证500指数', 'sh512510'],
            'sh000852': ['中证1000指数', 'sh512100'],
            'sz159001': ['货币ETF', 'sz159001'],
            'sz399006': ['创业板指数', 'sz159915']}

# ==========以下内容几乎不需要改动==========
# =导入选股策略的config文件
py_file = os.path.join(select_program_path, 'program/Config.py')
# 请注意，需要获取的变量需要再一行只内写完。
slt_cfg = Fun.get_variable_from_py_file(py_file, {'end_exchange': bool, 'factor_path': str, 'data_folder': str,
                                                  'buy_method': str, 'intraday_swap': bool, 'c_rate': 'eval',
                                                  't_rate': 'eval'})
# 针对获取到是变量进行解包，这些变量的详细含义见：选股策略的config.py文件
end_exchange = slt_cfg['end_exchange']
factor_path = slt_cfg['factor_path']
data_folder = slt_cfg['data_folder']
buy_method = slt_cfg['buy_method']
intraday_swap = slt_cfg['intraday_swap']
c_rate = slt_cfg['c_rate']
t_rate = slt_cfg['t_rate']

# 兼容一下部分同学可能还是会写开盘而不是开盘价
if buy_method == '开盘':
    buy_method = '开盘价'

# 尾盘换仓不需要替换第一天的涨跌幅
if end_exchange:
    buy_method = '收盘'

# 非开盘或者均价模式，都用日内换仓
if buy_method not in ['开盘价', '均价']:
    intraday_swap = True

# 周期和offset预运算数据位置，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-period-offset
period_offset_file = Fun.get_data_path(data_folder, '', 'period_offset.csv')

# 指数数据路径，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-main-index-data
index_path = Fun.get_data_path(data_folder, 'stock-main-index-data', 'sh000300.csv')

# 指数成分股资金曲线，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-ind-element-equity
index_strategy_path = Fun.get_data_path(data_folder, 'stock-ind-element-equity')

# 股票日线数据，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-trading-data-pro
stock_data_path = Fun.get_data_path(data_folder, 'stock-trading-data-pro')
