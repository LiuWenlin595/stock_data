'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import pandas as pd

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

# 持仓周期以及对应的offset，必须要在period_offset.csv中有对应的列，例如：W_0,W_1,W_2,W_3,W_4
period_offset = ['W_0']

factors = {'ROE': [], '归母净利润同比增速': ['归母净利润同比增速_60'], '最大回撤': [], '成交额相关因子': ['成交额_Mean5']}

select_count = 30  # 选股数量（必填）


def filter_stock(all_data):
    """
    过滤函数，在选股前过滤，必要
    :param all_data: 截面数据
    :return:
    """
    # =删除不能交易的周期数
    # 删除月末为st状态的周期数
    all_data = all_data[all_data['股票名称'].str.contains('ST') == False]
    # 删除月末为s状态的周期数
    all_data = all_data[all_data['股票名称'].str.contains('S') == False]
    # 删除月末有退市风险的周期数
    all_data = all_data[all_data['股票名称'].str.contains('\*') == False]
    all_data = all_data[all_data['股票名称'].str.contains('退') == False]
    # 删除交易天数过少的周期数
    all_data = all_data[all_data['交易天数'] / all_data['市场交易天数'] >= 0.8]

    all_data = all_data[all_data['下日_是否交易'] == 1]
    all_data = all_data[all_data['下日_开盘涨停'] == False]
    all_data = all_data[all_data['下日_是否ST'] == False]
    all_data = all_data[all_data['下日_是否退市'] == False]
    all_data = all_data[all_data['上市至今交易天数'] > 250]

    return all_data


def select_stock(all_data, count, params=[]):
    """
    选股函数，必要
    :param all_data: 截面数据
    :param count: 选股数量
    :param params: 选股策略的参数，默认给的参数[],意味着不需要参数，在实盘的策略不要带参数
    :return:
    """
    # --------------------------------------------------------------------
    # 原策略请查看帖子：https://bbs.quantclass.cn/thread/45165
    # --------------------------------------------------------------------
    all_data = all_data[all_data['成交额_Mean5'] > 50000000]

    # 计算ROE百分比排名
    all_data['ROE排名'] = all_data.groupby('交易日期')['ROE_单季'].rank(ascending=False, method='min', pct=True)
    # 计算归母净利润同比增速百分比排名
    all_data['归母净利润同比增速_60排名'] = all_data.groupby('交易日期')['归母净利润同比增速_60'].rank(ascending=False,
                                                                               method='min',
                                                                               pct=True)
    # 去除ROE较差的20%的股票
    all_data = all_data[all_data['ROE排名'] < 0.8]
    # 保留计算归母净利润同比增速排名靠前20%的股票
    all_data = all_data[all_data['归母净利润同比增速_60排名'] < 0.2]
    # 小市值分域，选择市值排名前10%
    all_data['总市值分位数'] = all_data.groupby('交易日期')['总市值'].rank(pct=True)
    all_data = all_data[all_data['总市值分位数'] <= 0.1]
    # 计算总市值排名
    all_data['总市值排名'] = all_data.groupby('交易日期')['总市值'].rank(ascending=True, method='min')
    # 计算Max_DrawDown_60排名  衡量超跌
    all_data['Max_DrawDown_60排名'] = all_data.groupby('交易日期')['Max_DrawDown_60'].rank(ascending=True, method='min')
    # 计算复合因子
    all_data['复合因子'] = all_data['Max_DrawDown_60排名']

    # 删除因子为空的数据
    all_data.dropna(subset=['复合因子'], inplace=True)
    # 回测从09年开始
    all_data = all_data[all_data['交易日期'] >= pd.to_datetime('2009-01-01')]

    # 拷贝一份数据用作稳健性测试
    df_for_group = all_data.copy()
    all_data['复合因子_排名'] = all_data.groupby('交易日期')['复合因子'].rank(ascending=True)
    # 按照固定的数量选股
    all_data = all_data[all_data['复合因子_排名'] <= count]
    all_data['选股排名'] = all_data['复合因子_排名']

    return all_data, df_for_group