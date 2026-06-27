'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import os

import numpy as np
import pandas as pd

import program.Config as Cfg
import program.Functions as Fun

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

ipt_fin_cols = []  # 输入的财务字段，财务数据上原始的

opt_fin_cols = []  # 输出的财务字段，需要保留的

# 港股股票数据存放路径，数据下载地址：https://www.quantclass.cn/data/stock/stock-hk-stock-data
hk_stock_folder = Fun.get_data_path(Cfg.data_folder, 'stock-hk-stock-data')
# 人民币兑港币的汇率数据存放路径，数据下载地址：https://www.quantclass.cn/data/stock/stock-cny-rate
hkd_cny = Fun.get_data_path(Cfg.data_folder, 'stock-cny-rate', 'HKD_CNY_rate.csv')
hkd_cny = pd.read_csv(hkd_cny, encoding='gbk', skiprows=1, parse_dates=['日期'])


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

    # 保存下面的因子，用于转换成周期数据来使用
    exg_dict['A股溢价率'] = 'last'
    exg_dict['溢价率分位数'] = 'last'
    exg_dict['A股溢价率_超额强化'] = 'last'
    exg_dict['溢价率分位数_超额强化'] = 'last'

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


def load_hk_stock(data):
    # 个股股票代码
    code = data['股票代码'].iloc[0]
    # 港股个股数据路径
    hk_stock_path = os.path.join(hk_stock_folder, code + '_HK.csv')
    # 如果可以找到这个港股的个股数据
    if os.path.exists(hk_stock_path):
        # 读取港股个股数据
        hk_df = pd.read_csv(hk_stock_path, encoding='gbk', parse_dates=['交易日期'], usecols=['交易日期', '收盘价', '前收盘价'],
                            skiprows=1)
        hk_df['收盘价'].fillna(method='ffill', inplace=True)
        hk_df['前收盘价'].fillna(method='ffill', inplace=True)
        # 计算复权因子
        hk_df['复权因子'] = (hk_df['收盘价'] / hk_df['前收盘价']).cumprod()
        # 计算前复权、后复权收盘价
        hk_df['收盘价_复权'] = hk_df['复权因子'] * (hk_df.iloc[0]['收盘价'] / hk_df.iloc[0]['复权因子'])

        # 合并该股票的A股和港股数据
        temp = pd.merge_ordered(hk_df.rename(columns={'交易日期': '交易日期_港股'}), data,
                                left_on='交易日期_港股',
                                right_on='交易日期', fill_method='ffill', suffixes=('_港股', ''))

        temp.dropna(subset=['交易日期'], inplace=True)
        # 按照交易日期列作为subset，遇到重复的日期，保留最新的数据
        temp = temp.drop_duplicates(subset='交易日期', keep='last')

        # 判断该股票在港股是不是已经退市：如果A股和港股的最新交易日期相差10天以上，就认为该股票已经退市
        if (temp['交易日期'].iloc[-1] - temp['交易日期_港股'].iloc[-1]).days > 10:
            # 获取hk_df最新的交易日期，将data里的收盘价_港股超过这个日期的数据赋值为nan
            last_date = hk_df['交易日期'].iloc[-1]
            temp.loc[temp['交易日期'] > last_date, '收盘价_港股'] = pd.NA

        # 删除港股交易日期列
        temp.drop(columns=['交易日期_港股'], inplace=True)

        # 合并股票数据和汇率数据
        temp = pd.merge_ordered(left=temp, right=hkd_cny[['日期', '收盘价']], left_on='交易日期', right_on='日期',
                                fill_method='ffill', suffixes=('', '_汇率'))
        temp.dropna(subset=['交易日期'], inplace=True)
        # 按照交易日期列作为subset，遇到重复的日期，保留最新的数据
        temp = temp.drop_duplicates(subset='交易日期', keep='last')
        # 删除汇率交易日期列
        temp.drop(columns=['日期'], inplace=True)

        data = pd.merge(data, temp[['交易日期', '收盘价_港股', '收盘价_汇率', '收盘价_复权_港股']], on='交易日期', how='left')

        # 计算A股溢价率 = A股股价/（港股股价*汇率）-1
        data['A股溢价率'] = data['收盘价'] / (data['收盘价_港股'] * data['收盘价_汇率']) - 1

        # ===以下因子来自直播：24分享会策略直播8-笛卡尔2选股策略

        data['溢价率分位数'] = data['A股溢价率'].rolling(250).rank(pct=True)
        # 计算A股和港股的5日涨跌
        data['a_ret5'] = data['收盘价_复权'] / data['收盘价_复权'].shift(5)
        data['h_ret5'] = data['收盘价_复权_港股'] / data['收盘价_复权_港股'].shift(5)
        data['港股超额'] = data['h_ret5'] / data['a_ret5']
        # 计算超额增强因子
        data['A股溢价率_超额强化'] = data['A股溢价率'] / data['港股超额']
        data['溢价率分位数_超额强化'] = data['A股溢价率_超额强化'].rolling(250).rank(pct=True)

    # 找不到个股数据，就给个nan值
    else:
        data['A股溢价率'] = np.nan
        data['溢价率分位数'] = np.nan
        data['A股溢价率_超额强化'] = np.nan
        data['溢价率分位数_超额强化'] = np.nan
    return data
