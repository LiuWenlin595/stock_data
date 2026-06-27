'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import pandas as pd
import numpy as np
import datetime

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

ipt_fin_cols = []  # 输入的财务字段，财务数据上原始的

opt_fin_cols = []  # 输出的财务字段，需要保留的


def special_data():
    '''
    处理策略需要的专属数据，非必要。
    :return:
    '''

    return


def cal_factors(data, fin_data, fin_raw_data, exg_dict):
    '''
    合并数据后计算策略需要的因子，非必要
    :param data:传入的数据
    :param fin_data:财报数据（去除废弃研报)
    :param fin_raw_data:财报数据（未去除废弃研报）
    :param exg_dict:resample规则
    :return:
    '''
    # ===均线胜率
    data['ma_60'] = data['收盘价_复权'].rolling(60, min_periods=60).mean()
    # 计算均线当前值与最近值的差值
    data['ma_diff_60'] = np.where(data['ma_60'].diff() > 0, 1, 0)
    # 计算ma_diff大于0的天数占比
    data['均线胜率_60'] = data['ma_diff_60'].rolling(250, min_periods=250).mean()
    exg_dict['均线胜率_60'] = 'last'

    '''下面的因子不是跑策略必须用的，如果需要可以取消注释'''
    # data['胜率'] = np.where(data['涨跌幅'] > 0, 1, 0)

    # for n in [5, 10, 20, 60, 120, 250]:
    #     # ===Ret
    #     data[f'Ret_{n}'] = data['收盘价_复权'].pct_change(n)
    #     exg_dict[f'Ret_{n}'] = 'last'
    #     # ===RSI
    #     data[f'RSI_{n}'] = data['收盘价_复权'].diff().rolling(n, min_periods=n).apply(lambda x: np.sum(x[x > 0]) / np.sum(abs(x)))
    #     exg_dict[f'RSI_{n}'] = 'last'
    #     # ===符号动量
    #     data[f'Sign_mtm_{n}'] = data['胜率'].rolling(n, min_periods=n).mean()
    #     exg_dict[f'Sign_mtm_{n}'] = 'last'
    #     # ema_ret
    #     data[f'Ema_ret_{n}'] = data['涨跌幅'].ewm(span=n, min_periods=n).mean()
    #     exg_dict[f'Ema_ret_{n}'] = 'last'

    return data, exg_dict


def after_resample(data):
    '''
    数据降采样之后的处理流程，非必要
    :param data: 传入的数据
    :return:
    '''
    return data

def cal_cross_factor(data):
    '''
    截面处理数据
    data: 全部的股票数据
    '''

    return data