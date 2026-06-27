'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import os

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm

import program.Config as Cfg
import program.Functions as Fun

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

ipt_fin_cols = []  # 输入的财务字段，财务数据上原始的

opt_fin_cols = []  # 输出的财务字段，需要保留的

# =====以下变量是自己加的=====
# 原始邢不行资金流数据数据的位置，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-money-flow-xbx
cash_flow_path = Fun.get_data_path(Cfg.data_folder, 'stock-money-flow-xbx')
# 处理过后的邢不行资金流数据的保存位置
cash_flow_save_path = 'D:/Data/Stock/邢不行资金流数据'
os.makedirs(cash_flow_save_path, exist_ok=True)


def special_data():
    '''
    处理策略需要的专属数据，非必要。
    :return:
    '''
    # 打印执行信息
    print(f'\n开始执行{name}.special_data()')
    # 获取所有的资金流数据文件列表
    file_list = Fun.get_file_in_folder(cash_flow_path, '.csv')
    # 多线程读取所有的资金流数据
    df_list = Parallel(Cfg.n_job)(
        delayed(pd.read_csv)(os.path.join(cash_flow_path, file), encoding='gbk', skiprows=1) for file in file_list)
    # 数据合并
    cash_flow_df = pd.concat(df_list, ignore_index=True)
    # 按照股票代码对数据进行拆分
    groups = cash_flow_df.groupby('股票代码')

    # 创建路径
    os.makedirs(cash_flow_save_path, exist_ok=True)

    # 按照股票保存数据
    def save_data(code, df):
        save_path = os.path.join(cash_flow_save_path, code + '.csv')
        df.to_csv(save_path, encoding='gbk', index=False)

    # 多线程保存数据
    Parallel(Cfg.n_job)(delayed(save_data)(tag, group) for tag, group in tqdm(groups))

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
    # 计算中单买入占比因子（单位是万元，所以要乘以10000）
    data['中单买入占比'] = data['中单(买入金额)'] * 10000 / data['成交额']
    exg_dict['中单买入占比'] = 'last'
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


def load_xbx_cash_flow(data):
    """
    加载邢不行资金流数据
    :param data:
    :return:
    """
    # 获取股票代码
    code = data['股票代码'].iloc[-1]

    # 需要合并的字段
    need_cols = ['交易日期', '特大单(买入金额)', '大单(买入金额)', '中单(买入金额)', '小单(买入金额)',
                 '特大单(卖出金额)', '大单(卖出金额)', '中单(卖出金额)', '小单(卖出金额)']

    # 如果存在文件则读取
    if os.path.exists(os.path.join(cash_flow_save_path, code + '.csv')):
        # 读取邢不行资金流数据
        cash_flow_df = pd.read_csv(os.path.join(cash_flow_save_path, code + '.csv'), encoding='gbk',
                                   parse_dates=['交易日期'])
        # 只保留需要的数据
        cash_flow_df = cash_flow_df[need_cols]
        # 数据合并
        data = pd.merge(data, cash_flow_df, 'left', '交易日期')
    else:
        # 不存在的情况下，对应的列给空数据
        for col in need_cols:
            # 跳过交易日期列
            if col == '交易日期':
                continue
            data[col] = np.nan

    return data
