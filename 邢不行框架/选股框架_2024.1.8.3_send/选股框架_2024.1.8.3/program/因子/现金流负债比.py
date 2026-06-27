'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import program.Functions as Fun

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

ipt_fin_cols = ['C_ncf_from_oa@xbx', 'B_total_current_liab@xbx', 'B_total_noncurrent_liab@xbx']

opt_fin_cols = ['C_ncf_from_oa@xbx', 'B_total_current_liab@xbx', 'B_total_noncurrent_liab@xbx']  # 输出的财务字段，需要保留的


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
    # 现金流负债比：经营活动现金流量净额/负债总额
    data['现金流负债比'] = data['C_ncf_from_oa@xbx'] / (data['B_total_current_liab@xbx'] + data['B_total_noncurrent_liab@xbx'])
    exg_dict['现金流负债比'] = 'last'

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
