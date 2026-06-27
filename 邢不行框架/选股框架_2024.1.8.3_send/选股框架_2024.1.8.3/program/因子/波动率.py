'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import pandas as pd
import numpy as np

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
    # ===异常涨跌幅
    data['异常涨跌幅_250'] = abs(data['涨跌幅']).rolling(250, min_periods=250).apply(lambda x: np.mean(np.sort(x)[-25:]))
    exg_dict['异常涨跌幅_250'] = 'last'

    for n in [5, 10, 20, 60, 120, 250]:
        # ===波动率
        data[f'波动率_{n}'] = data['涨跌幅'].rolling(n).std()
        exg_dict[f'波动率_{n}'] = 'last'

    '''下面的因子不是跑策略必须用的，如果需要可以取消注释'''
    # data['振幅'] = (data['最高价'] - data['最低价']) / data['收盘价']

    # for n in [5, 10, 20, 60, 120, 250]:
    #     # ===bbw
    #     data['ma'] = data['收盘价_复权'].rolling(window=n, min_periods=n).mean()
    #     data['price_std'] = data['收盘价_复权'].rolling(window=n, min_periods=n).std()
    #     data['upper'] = data['ma'] + 2 * data['price_std']
    #     data['lower'] = data['ma'] - 2 * data['price_std']
    #     data[f'bbw_{n}'] = (data['upper'] - data['lower']) / data['ma']
    #     exg_dict[f'bbw_{n}'] = 'last'

    #     # ===bias_abs
    #     data[f'bias_abs_{n}'] = abs(data['收盘价_复权'] / data['ma'] - 1)
    #     exg_dict[f'bias_abs_{n}'] = 'last'

    #     # ===振幅_std
    #     data[f'振幅波动率_{n}'] = data['振幅'].rolling(window=n, min_periods=n).std()
    #     exg_dict[f'振幅波动率_{n}'] = 'last'

    #     # ===上行波动率
    #     data[f'上行波动率_{n}'] = data['涨跌幅'].rolling(window=n, min_periods=n).apply(lambda x: np.std(x[x > 0]))
    #     exg_dict[f'上行波动率_{n}'] = 'last'

    #     # ===下行波动率
    #     data[f'下行波动率_{n}'] = data['涨跌幅'].rolling(window=n, min_periods=n).apply(lambda x: np.std(x[x < 0]))
    #     exg_dict[f'下行波动率_{n}'] = 'last'

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
