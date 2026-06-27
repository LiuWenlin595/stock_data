'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import program.Functions as Fun

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
    # ===WR
    data['5日复权最高价'] = data["最高价_复权"].rolling(5, min_periods=1).max()
    data['5日复权最低价'] = data["最低价_复权"].rolling(5, min_periods=1).min()
    data['WR_5'] = 100 * ((data['5日复权最高价'] - data["收盘价_复权"])/(data['5日复权最高价'] - data["5日复权最低价"]))
    exg_dict['WR_5'] = "last"
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
