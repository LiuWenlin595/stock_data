'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import numpy as np
import pandas as pd
import os
import program.Functions as Fun
import program.Config as Cfg

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

ipt_fin_cols = []  # 输入的财务字段，财务数据上原始的

opt_fin_cols = []  # 输出的财务字段，需要保留的

dividend_path = Fun.get_data_path(Cfg.data_folder, 'stock-dividend-delivery')

"""
请注意：本因子不要和《近一年分红.py》一起跑

本因子可以完全替代《近一年分红.py》
"""


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
    exg_dict['分红率_登记日'] = 'last'
    exg_dict['分红率_登记日_近年均值'] = 'last'
    exg_dict['分红率_登记日_近年标准差'] = 'last'
    exg_dict['分红率_登记日_近年次数'] = 'last'
    exg_dict['连续分红年份'] = 'last'
    exg_dict['分红率_最近日'] = 'last'

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


def load_dividend_delivery(data):
    '''
    加载分红数据
    :param data:
    :return:
    '''

    stock_code = data['股票代码'].iloc[-1]
    path = os.path.join(dividend_path, f'{stock_code}.csv')
    keep_cols = ['近一年分红', '分红率_登记日', '分红率_登记日_近年均值', '分红率_登记日_近年标准差', '分红率_登记日_近年次数', '连续分红年份']

    if os.path.exists(path):
        # 读取分红数据
        dividend_data = pd.read_csv(path, encoding='gbk', skiprows=1, parse_dates=['股权登记日', '报告期'])
        # 股权登记日一定是交易日期，为了merge方便，直接重命名
        dividend_data.rename(columns={'股权登记日': '交易日期'}, inplace=True)
        # 删除相同交易日的数据，保留最新的
        dividend_data = dividend_data.drop_duplicates(subset=['交易日期'], keep='last')
        # 把收盘价数据拿过来
        dividend_data = pd.merge(dividend_data, data[['交易日期', '收盘价']], on='交易日期', how='left')
        # 计算分红率
        dividend_data['分红率_登记日'] = dividend_data['近一年分红'] / dividend_data['收盘价']
        # 计算登记日的年份
        dividend_data['年份'] = dividend_data['报告期'].dt.year

        # 计算最近3年的分红状态
        for i in dividend_data.index:
            hist_report_date = dividend_data.loc[i, '报告期'] - pd.DateOffset(years=3)
            temp_hist = dividend_data[
                (dividend_data['报告期'] > hist_report_date) & (dividend_data['报告期'] <= dividend_data.loc[i, '报告期'])]
            dividend_data.loc[i, '分红率_登记日_近年均值'] = temp_hist['分红率_登记日'].mean()
            dividend_data.loc[i, '分红率_登记日_近年标准差'] = temp_hist['分红率_登记日'].std()
            dividend_data.loc[i, '分红率_登记日_近年次数'] = temp_hist['分红率_登记日'].count()

            # 计算连续多少年分红
            temp_hist = dividend_data[:i + 1].copy()  # 获取至今的所有数据
            dividend_years = list(set(temp_hist['年份']))  # 有些年份会分好几次
            year_range = list(range(dividend_data.loc[i, '报告期'].year, temp_hist['报告期'].min().year - 1, -1))
            j = 0
            for year in year_range:
                if year in dividend_years:
                    j += 1
                else:
                    break
            dividend_data.loc[i, '连续分红年份'] = j

        # 将分红数据与日线数据和财务数据合并
        temp = pd.merge(left=data[['交易日期', '收盘价']], right=dividend_data[['交易日期'] + keep_cols], on=['交易日期'], how='left')

        # 按照最新交易日期计算分红
        temp['近一年分红'].fillna(method='ffill', inplace=True)
        temp['分红率_最近日'] = temp['近一年分红'] / temp['收盘价']
        keep_cols.append('分红率_最近日')

        # ===分红数据只保留270个交易日，如果270日以后还没有分红数据，判定公司下一年不分红了，将分红数据修正为nan
        mark_index = temp[~pd.isnull(temp['分红率_登记日'])].index
        index_list = []
        for index in mark_index:
            index_list += list(range(index, index + 271))
        # index_list可能有重复值，去重
        index_list = list(set(index_list))
        # 先填充，再赋nan
        temp.fillna(method='ffill', inplace=True)
        # index_list以外的数据，分红数据修正为nan
        temp.loc[~temp.index.isin(index_list), keep_cols] = np.nan

        # 将分红数据与日线数据和财务数据合并
        data = pd.merge(data, temp[['交易日期'] + keep_cols], on='交易日期', how='left')

    else:
        # 没有分红数据，用空值代替
        keep_cols.append('分红率_最近日')
        for col in keep_cols:
            data[col] = np.nan

    return data
