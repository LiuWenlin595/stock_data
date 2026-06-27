'''
2024分享会
author: 邢不行
微信: xbx6660
'''

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
    # 需要计算每周的胜率需要知道每周复权后的价格
    exg_dict['收盘价_复权'] = 'last'
    exg_dict['开盘价_复权'] = 'first'
    return data, exg_dict


def after_resample(data):
    '''
    数据降采样之后的处理流程，非必要
    :param data: 传入的数据
    :return:
    '''
    # 计算周涨幅
    data['周涨幅'] = data['收盘价_复权'].pct_change()
    # 第一周的涨跌幅需要用开盘价计算
    data['周涨幅'].fillna(value=data['收盘价_复权'] / data['开盘价_复权'] - 1, inplace=True)

    # 计算最近一年的周胜率，及计算最近50周的涨幅大于0的占比
    data['最近一年周胜率'] = (data['周涨幅'] > 0).rolling(50).mean()

    return data


def cal_cross_factor(data):
    '''
    截面处理数据
    data: 全部的股票数据
    '''

    return data
