'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import pandas as pd

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

# 持仓周期以及对应的offset，必须要在period_offset.csv中有对应的列，例如：W_0,W_1,W_2,W_3,W_4
period_offset = ['W_0']

factors = {'周频因子': [], '归母净利润': [], '邢不行资金流': []}

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
    # ===构建策略需要的因子
    all_data['中单买入占比_排名'] = all_data.groupby('交易日期')['中单买入占比'].rank(ascending=False)
    all_data['最近一年周胜率_排名'] = all_data.groupby('交易日期')['最近一年周胜率'].rank(ascending=False)
    all_data['单季度归母净利润_中性_排名'] = all_data.groupby('交易日期')['单季度归母净利润_中性'].rank(ascending=False)

    # === 计算复合因子
    all_data['复合因子'] = all_data['中单买入占比_排名'] + all_data['最近一年周胜率_排名'] + all_data['单季度归母净利润_中性_排名']

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


def timing(equity, params=[]):
    """
    择时函数，非必须
    :param equity: 资金曲线
    :param params: 参数
    :return:
    """
    # 长短均线参数
    short = 5
    long = 20

    # 计算长短期均线
    equity['ma_short'] = equity['equity_curve'].rolling(short, min_periods=1).mean()
    equity['ma_long'] = equity['equity_curve'].rolling(long, min_periods=1).mean()

    # 计算择时信号
    equity.loc[equity['ma_short'] > equity['ma_long'], 'signal'] = 1
    equity['signal'].fillna(value=0, inplace=True)

    # 合并成周期的数据
    period_df = equity.groupby(['周期']).agg({'交易日期': 'last', 'signal': 'last'})

    return period_df
