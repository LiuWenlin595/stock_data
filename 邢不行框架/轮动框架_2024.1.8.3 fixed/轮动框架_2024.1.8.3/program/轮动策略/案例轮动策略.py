"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import pandas as pd
import numpy as np

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

# 文件名格式：周期_offset_选股数量.csv，例如：W_0_30.csv,W_1_30.csv,W_2_30.csv,W_3_30.csv,W_4_30.csv
# 多offset可直接配置不同的文件名后缀，但必须是相同的周期频率的。
# 如果某个策略同时要做周频和月频的轮动建议把这个这个轮动文件copy一份，一个文件专门是周的offset，一个文件专门是月的offset
strategy_param = ['W_0_30.csv']

# 需要导入那些因子数据
factors = {}

select_count = 1  # 选策略数量（必填）

mean_cols = []  # 需要求均值类型的因子（脚本2）

sum_cols = []  # 需要求和类型的因子（脚本2）

sub_stg_list = ['大市值', '小市值']  # 子策略名称，如果为空或者没有这个字段，表示使用所有的子策略


def cal_strategy_factors(data, exg_dict):
    """
    数据降采样之后的处理流程，非必要
    :param data: 传入的数据
    :param exg_dict:resample规则
    :return:
    """

    # 涨跌幅
    data['涨跌幅_5'] = data['equity_curve'].pct_change(5)
    data.loc[data['涨跌幅_5'].isna(), '涨跌幅_5'] = data['equity_curve'] / data['equity_curve'].iloc[0] - 1
    exg_dict['涨跌幅_5'] = 'last'

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
    :param param:轮动策略的参数，默认给的参数[],意味着不需要参数，在实盘的策略不要带参数
    :return:
    """

    # 计算因子的排名
    all_data['涨跌幅_5排名'] = all_data.groupby('交易日期')['涨跌幅_5'].rank(method='min', ascending=False)

    # 用中位数（排名）填充空值
    all_data['涨跌幅_5排名'].fillna(value=all_data.groupby('交易日期')['涨跌幅_5排名'].transform('median'),
                                   inplace=True)

    # 计算复合因子
    all_data['复合因子'] = all_data['涨跌幅_5排名']
    all_data['复合因子_排名'] = all_data.groupby('交易日期')['复合因子'].rank(method='min', ascending=True)

    df_for_group = all_data.copy()
    all_data = all_data[all_data['复合因子_排名'] <= count]

    all_data['策略排名'] = all_data['复合因子_排名']
    all_data.sort_values(by='交易日期', inplace=True)
    return all_data, df_for_group