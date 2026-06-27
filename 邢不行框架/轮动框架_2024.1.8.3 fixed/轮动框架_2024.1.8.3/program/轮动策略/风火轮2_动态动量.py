"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 策略名称（必填）

# 文件名格式：周期_offset_选股数量.csv，例如：W_0_30.csv,W_1_30.csv,W_2_30.csv,W_3_30.csv,W_4_30.csv
# 多offset可直接配置不同的文件名后缀，但必须是相同的周期频率的。
# 如果某个策略同时要做周频和月频的轮动建议把这个这个轮动文件copy一份，一个文件专门是周的offset，一个文件专门是月的offset
strategy_param = ['W_0_30.csv']

# 需要导入那些因子数据
factors = {}  # '成交额': []

select_count = 1  # 选策略数量（必填）

mean_cols = []  # 需要求均值类型的因子（脚本2）

sum_cols = []  # 需要求和类型的因子（脚本2）  '成交额'

sub_stg_list = ['大市值', '小市值']  # 子策略名称，如果为空或者没有这个字段，表示使用所有的子策略


# 参数
short = 10           # 短参数，控制短动量和波动率
long = 250           # 长参数，控制长动量和分位数
std_factor = 'bbw'   # 选择使用哪些因子，目前可以使用的波动因子有：'bbw', 'bias_abs', 'bias_abs_mean', 'bias_std', 'mtm_std', 'price_std', 'ret_std'


def cal_strategy_factors(data, exg_dict):
    """
    数据降采样之后的处理流程，非必要
    :param data: 传入的数据
    :param exg_dict:resample规则
    :return:
    """
    # 价格分位数
    data[f'价格分位数_{long}'] = data['equity_curve'].rolling(window=long, min_periods=long).rank(pct=True)
    exg_dict[f'价格分位数_{long}'] = 'last'

    # 动量
    for n in [short, long]:
        # 均线
        data[f'ma_{n}'] = data['equity_curve'].rolling(n, min_periods=1).mean()
        # bias
        data[f'bias_{n}'] = data['equity_curve'] / data[f'ma_{n}'] - 1
        exg_dict[f'bias_{n}'] = 'last'

    # ===波动
    # bbw
    data[f'equity_curve_mean_{short}'] = data['equity_curve'].rolling(window=short, min_periods=short).mean()
    data[f'equity_curve_std_{short}'] = data['equity_curve'].rolling(window=short, min_periods=short).std()
    data[f'upper_{short}'] = data[f'equity_curve_mean_{short}'] + 2 * data[f'equity_curve_std_{short}']
    data[f'lower_{short}'] = data[f'equity_curve_mean_{short}'] - 2 * data[f'equity_curve_std_{short}']
    data[f'bbw_{short}'] = (data[f'upper_{short}'] - data[f'lower_{short}']) / data[f'equity_curve_mean_{short}']
    data[f'bbw_{short}_rank{long}'] = data[f'bbw_{short}'].rolling(window=long, min_periods=long).rank(pct=True)
    exg_dict[f'bbw_{short}'] = 'last'
    exg_dict[f'bbw_{short}_rank{long}'] = 'last'

    # bias abs
    data[f'bias_abs_{short}'] = data[f'bias_{short}'].abs()
    data[f'bias_abs_{short}_rank{long}'] = data[f'bias_abs_{short}'].rolling(window=long, min_periods=long).rank(
        pct=True)
    exg_dict[f'bias_abs_{short}'] = 'last'
    exg_dict[f'bias_abs_{short}_rank{long}'] = 'last'

    # bias abs mean
    data[f'bias_abs_{short}'] = data[f'bias_{short}'].abs()
    data[f'bias_abs_mean_{short}'] = data[f'bias_abs_{short}'].rolling(short, min_periods=short).mean()
    data[f'bias_abs_mean_{short}_rank{long}'] = data[f'bias_abs_mean_{short}'].rolling(window=long,
                                                                                       min_periods=long).rank(pct=True)
    exg_dict[f'bias_abs_mean_{short}'] = 'last'
    exg_dict[f'bias_abs_mean_{short}_rank{long}'] = 'last'

    # bias std
    data[f'bias_std_{short}'] = data[f'bias_{short}'].rolling(short, min_periods=short).std()
    data[f'bias_std_{short}_rank{long}'] = data[f'bias_std_{short}'].rolling(window=long, min_periods=long).rank(
        pct=True)
    exg_dict[f'bias_std_{short}'] = 'last'
    exg_dict[f'bias_std_{short}_rank{long}'] = 'last'

    # mtm std
    data[f'mtm_std_{short}'] = data['equity_curve'].pct_change(short).rolling(short).std()
    data[f'mtm_std_{short}_rank{long}'] = data[f'mtm_std_{short}'].rolling(window=long, min_periods=long).rank(pct=True)
    exg_dict[f'mtm_std_{short}'] = 'last'
    exg_dict[f'mtm_std_{short}_rank{long}'] = 'last'

    # price std
    data[f'price_std_{short}'] = data['equity_curve'].rolling(window=short, min_periods=short).apply(
        lambda x: (x / x.iloc[0]).std())
    exg_dict[f'price_std_{short}'] = 'last'
    data[f'price_std_{short}_rank{long}'] = data[f'price_std_{short}'].rolling(window=long, min_periods=long).rank(
        pct=True)
    exg_dict[f'price_std_{short}_rank{long}'] = 'last'

    # ret std
    data[f'ret_std_{short}'] = data['涨跌幅'].rolling(window=short, min_periods=short).std()
    data[f'ret_std_{short}_rank{long}'] = data[f'ret_std_{short}'].rolling(window=long, min_periods=long).rank(pct=True)
    exg_dict[f'ret_std_{short}'] = 'last'
    exg_dict[f'ret_std_{short}_rank{long}'] = 'last'

    return data, exg_dict


def after_resample(data):
    """
    数据合并之后的操作流程，非必要。
    :param data: 策略数据
    :return:
    """
    return data


def filter_and_select_strategies(all_data, count, param):
    """
    过滤函数，在选股前过滤，必要
    :param all_data: 截面数据
    :param count: 选策略数量
    :return:
    """

    # 计算复合因子
    weight = all_data.groupby('交易日期')[f'{std_factor}_{short}_rank{long}'].max().rename('weight').reset_index()
    all_data = pd.merge(all_data, weight, on='交易日期', how='left')
    all_data['复合因子'] = all_data[f'bias_{short}'] * all_data[f'weight'] + all_data[f'bias_{long}'] * (
            1 - all_data[f'weight'])

    # 将复合因子转化为排名
    all_data['复合因子_排名'] = all_data.groupby('交易日期')['复合因子'].rank(method='min', ascending=False)

    # =空仓择时
    # 判断价格处于高/低位的阈值
    filter_param = 0.8
    # 计算择时信号
    all_data['timing_signal'] = all_data.apply(lambda rows: ma_timing(rows, filter_param, [long, short]), axis=1)
    # 空仓
    all_data = all_data[all_data['timing_signal'] == 1]

    # 保存一份数据用作后续分析
    df_for_group = all_data.copy()
    # 选择排名第一的需要选择的策略
    all_data = all_data[all_data['复合因子_排名'] <= count]

    all_data['策略排名'] = all_data['复合因子_排名']
    all_data.sort_values(by='交易日期', inplace=True)
    return all_data, df_for_group


# 择时空仓函数
def ma_timing(row, para, stg_param):
    # 当策略当前价格处于极端价格位置时
    if (row[f'价格分位数_{stg_param[0]}'] > para):
        # 此时还处于下跌状态
        if (row[f'bias_{stg_param[1]}'] < 0):
            # 那我们就空仓
            return 0
    # 不满足上述条件就开仓
    return 1
