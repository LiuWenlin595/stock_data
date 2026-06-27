"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import os
import program.Functions as Fun

# =====以下参数可以根据实际情况修改=====
date_start = '2009-01-01'
date_end = None  # 日期，为None时，代表使用到最新的数据，也可以指定日期，例如'2022-11-01'，但是指定日期

buy_method = '开盘'  # 设定买入股票的方法，即在什么时候买入。可以是：开盘价、均价、09:35收盘价、09:45收盘价、09:55收盘价，收盘。其中均价代表当天的均价
intraday_swap = False  # 是否要日内换仓，针对换手率低的股票，日内换仓可以可降低手续费。除开盘和均价模式外，其他模式都会被强制为True

trading_mode = True  # 是否是交易模式，True代表是交易模式，False代表不是交易模式
# 交易模式下会有以下区别
# 1、交易模式下，脚本1整理数据将从date_start开始。研究模式从股票上线开始（最早到指数开始时间）
# 2、交易模式下，整理当前offset的数据，并且回测也只回测当前offset的数据。研究模式会计算全部offset的数据
# 注意：交易模式下把date_start改成最近的日期可以提高速度
#      但是一定要仔细检查计算的因子会不会因为日期不同，导致计算结果不同，特别是复权数据算出来的因子


# 调用那个策略
stg_file = '小市值'

# 策略没有指定，但是需要跑的因子（一般是帮轮动策略或者因子分析跑的）
other_factors = {'风格因子': ['W_0']}

# =====以下参数首次运行时可能需要改一下，之后可以不用管=====

# 是否要尾盘选股，默认是False，表示不做尾盘选股。如果要使用True(尾盘选股)，建议将选股框架复制一份，再改成True。
# 尾盘选股会调用0号脚本去拿一下市场上的数据，这些数据只有市值和价格数据，其他的因子也沿用的是历史数据
# 策略在开发时，其他因子需要使用昨日的数据。
# 如果既有正常换仓的策略，也有尾盘换仓的策略，建议把本代码复制一份，尾盘换仓的策略统一放在一起。
end_exchange = False

# 数据文件夹的位置，关于数据如何存放在本地，可以参考：https://bbs.quantclass.cn/thread/39599
# 如果是数据客户端就填：【设置中心】-->【数据存储文件夹】指向的文件夹
# 如果是数据API就填：config里面的all_data_path指向的文件夹
# 此数据路径需要一行代码写完，且不是r开头的格式，例如禁止: data_folder = r'D:/Data/stock_data/'
data_folder = 'D:/Data/stock_data/'  # 参考：https://bbs.quantclass.cn/thread/39599

# 因子路径：所有的因子数据保存在项目外面，避免IDE卡死，这个路径自己指定，但最好和本程序在同一个硬盘里面
# 此数据路径需要一行代码写完，且不是r开头的格式，例如禁止: factor_path = r'D:/Data/Stock/因子数据/'
factor_path = 'D:/Data/Stock/因子数据/'

# =====以下参数几乎不需要改动=====

_ = os.path.abspath(os.path.dirname(__file__))  # 返回当前文件路径
root_path = os.path.abspath(os.path.join(_, '..'))  # 返回根目录文件夹
# 手续费
c_rate = 1.2 / 10000
# 印花税
t_rate = 1 / 1000

# multiple_process的进程数，由于joblib在windows系统下最多只能利用64线程，所以做了控制
n_job = min(os.cpu_count() - 1, 60)

# 尾盘换仓不需要替换第一天的涨跌幅
if end_exchange:
    buy_method = '收盘'

# 兼容一下部分同学可能还是会写开盘而不是开盘价
if buy_method == '开盘':
    buy_method = '开盘价'

# 非开盘或者均价模式，都用日内换仓
if buy_method not in ['开盘价', '均价']:
    intraday_swap = True

# =====以下参数几乎不需要改动=====
# 股票日线数据，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-trading-data-pro
stock_data_path = Fun.get_data_path(data_folder, 'stock-trading-data-pro')

# 财务数据，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-fin-data-xbx
fin_path = Fun.get_data_path(data_folder, 'stock-fin-data-xbx')

# 指数数据路径，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-main-index-data
index_path = Fun.get_data_path(data_folder, 'stock-main-index-data', 'sh000300.csv')

# 周期和offset预运算数据位置，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-period-offset
period_offset_file = Fun.get_data_path(data_folder, '', 'period_offset.csv')
