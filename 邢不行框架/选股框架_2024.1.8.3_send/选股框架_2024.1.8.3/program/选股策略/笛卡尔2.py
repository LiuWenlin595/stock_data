'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import pandas as pd

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

# 持仓周期以及对应的offset，必须要在period_offset.csv中有对应的列，例如：W_0,W_1,W_2,W_3,W_4
period_offset = ['W_0']

factors = {'A股溢价率': []}    # 策略要用到的因子

select_count = 10  # 选股数量（必填）


def filter_stock(all_data):
    """
    过滤函数，在选股前过滤，必要
    :param all_data: 截面数据
    :return:
    """
    all_data = all_data[all_data['新版申万一级行业名称'] != '银行']
    all_data = all_data[all_data['新版申万一级行业名称'] != '非银金融']
    # =删除不能交易的周期数
    # 删除月末为st状态的周期数
    all_data = all_data[all_data['股票名称'].str.contains('ST') == False]
    # 删除月末为s状态的周期数
    all_data = all_data[all_data['股票名称'].str.contains('S') == False]
    # 删除月末有退市风险的周期数
    all_data = all_data[all_data['股票名称'].str.contains('退') == False]
    # 删除交易天数过少的周期数
    all_data = all_data[all_data['交易天数'] / all_data['市场交易天数'] >= 0.8]

    all_data = all_data[all_data['下日_是否交易'] == 1]
    all_data = all_data[all_data['下日_开盘涨停'] == False]
    all_data = all_data[all_data['下日_是否ST'] == False]
    all_data = all_data[all_data['下日_是否退市'] == False]

    return all_data


def select_stock(all_data, count, params=[]):
    """
    选股函数，必要
    :param all_data: 截面数据
    :param count: 选股数量
    :param params: 选股策略的参数，默认给的参数[],意味着不需要参数，在实盘的策略不要带参数
    :return:
    """
    # ===构建策略需要的因子
    # 剔除当前溢价率水平在历史上偏高的股票
    all_data = all_data[all_data['溢价率分位数_超额强化'] < 0.8]
    # 计算A股溢价率和溢价率分位数的因子排名
    all_data['A股溢价率_超额强化_排名'] = all_data.groupby('交易日期')['A股溢价率_超额强化'].rank(ascending=True, method='first')
    all_data['溢价率分位数_超额强化_排名'] = all_data.groupby('交易日期')['溢价率分位数_超额强化'].rank(ascending=True, method='first')

    # 计算复合因子
    all_data['复合因子'] = all_data['A股溢价率_超额强化_排名'] + all_data['溢价率分位数_超额强化_排名']

    # 删除因子为空的数据
    all_data.dropna(subset=['复合因子'], inplace=True)

    # 拷贝一份数据用作稳健性测试
    df_for_group = all_data.copy()
    all_data['复合因子_排名'] = all_data.groupby('交易日期')['复合因子'].rank(ascending=True)
    # 按照固定的数量选股
    all_data = all_data[all_data['复合因子_排名'] <= count]
    all_data['选股排名'] = all_data['复合因子_排名']

    return all_data, df_for_group
