'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import pandas as pd
import program.DomainAnalysis as da
from sklearn.linear_model import LassoCV, LinearRegression, RidgeCV

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

# 持仓周期以及对应的offset，必须要在period_offset.csv中有对应的列，例如：W_0,W_1,W_2,W_3,W_4
period_offset = ['W_0']

factors = {'红利因子': [], '归母净利润同比增速': [], '风格因子': [], '波动率': []}  # 策略要用到的因子

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

    # 删除收盘价大于100的股票
    all_data = all_data[all_data['收盘价'] <= 100]

    return all_data


def select_stock(all_data, count, params=[]):
    """
    选股函数，必要
    :param all_data: 截面数据
    :param count: 选股数量
    :param params: 选股策略的参数，默认给的参数[],意味着不需要参数，在实盘的策略不要带参数
    :return:
    """
    all_data['总市值分位数'] = all_data.groupby('交易日期')['总市值'].rank(pct=True)
    all_data['成交额分位数'] = all_data.groupby('交易日期')['成交额'].rank(pct=True)
    # 拷贝一份全量数据用作分域分析
    temp = all_data.copy()

    # 分红分域分析：15年7月因为大量股票停牌，可能会导致有异常的数据点，可以把15年7月的数据删掉

    method = '行业分红域_低波红利策略'

    if method == '高分红策略':
        # 高分红策略：选择分红率排名靠前的股票
        all_data['分红率_排名'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, method='min')
        all_data['复合因子'] = all_data['分红率_排名']
    elif method == '高分红域':
        # 高分红域：1、分红率排名靠前的20%   2、连续分红2年及以上
        all_data['分红率分位数'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, pct=True)
        all_data = all_data[all_data['分红率分位数'] <= 0.2]
        all_data = all_data[all_data['连续分红年份'] > 1]
        # 分域分析
        da.domain_analysis(all_data, temp)

        # 简单的选择分红率排名靠前的股票
        all_data['分红率_排名'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, method='min')
        all_data['复合因子'] = all_data['分红率_排名']

    elif method == '行业高分红域':
        # 行业高分红域：1、行业内分红率排名靠前的20%   2、连续分红2年及以上
        all_data['分红率分位数'] = all_data.groupby(['交易日期', '新版申万一级行业名称'])['分红率_登记日'].rank(ascending=False, pct=True)
        all_data = all_data[all_data['分红率分位数'] <= 0.2]
        all_data = all_data[all_data['连续分红年份'] > 1]
        # 分域分析
        da.domain_analysis(all_data, temp)

        # 简单的选择分红率排名靠前的股票
        all_data['分红率_排名'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, method='min')
        all_data['复合因子'] = all_data['分红率_排名']
    elif method == '市值高分红域':
        # 市值高分红域：1、市值分组内分红率排名靠前的20%   2、连续分红2年及以上
        # 先将市值分10组
        all_data['市值分组'] = all_data.groupby('交易日期')['总市值'].transform(
            lambda x: pd.qcut(x, q=10, labels=range(1, 10 + 1), duplicates='drop'))

        all_data['分红率分位数'] = all_data.groupby(['交易日期', '市值分组'])['分红率_登记日'].rank(ascending=False, pct=True)
        all_data = all_data[all_data['分红率分位数'] <= 0.2]
        all_data = all_data[all_data['连续分红年份'] > 1]
        # 分域分析
        da.domain_analysis(all_data, temp)

        # 简单的选择分红率排名靠前的股票
        all_data['分红率_排名'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, method='min')
        all_data['复合因子'] = all_data['分红率_排名']
    elif method == '行业分红域_红利策略':
        # 行业分红域_红利策略：1、行业内分红率排名靠前的20%   2、连续分红2年及以上   3、R_np_atoopc@xbx_单季同比大于0  4、选择分红率靠前的股票
        all_data['分红率分位数'] = all_data.groupby(['交易日期', '新版申万一级行业名称'])['分红率_登记日'].rank(ascending=False, pct=True)
        all_data = all_data[all_data['分红率分位数'] <= 0.2]
        all_data = all_data[all_data['连续分红年份'] > 1]
        all_data = all_data[all_data['R_np_atoopc@xbx_单季同比'] > 0]

        # 简单的选择分红率排名靠前的股票
        all_data['分红率_排名'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, method='min')
        all_data['复合因子'] = all_data['分红率_排名']
    elif method == '行业分红域_低波策略':
        # 行业分红域_低波策略：1、行业内分红率排名靠前的20%   2、连续分红2年及以上   3、R_np_atoopc@xbx_单季同比大于0  4、选择波动率较低的股票
        all_data['分红率分位数'] = all_data.groupby(['交易日期', '新版申万一级行业名称'])['分红率_登记日'].rank(ascending=False, pct=True)
        all_data = all_data[all_data['分红率分位数'] <= 0.2]
        all_data = all_data[all_data['连续分红年份'] > 1]
        all_data = all_data[all_data['R_np_atoopc@xbx_单季同比'] > 0]

        # 选择波动率较低的股票
        all_data['波动率_250_排名'] = all_data.groupby(['交易日期'])['波动率_250'].rank(ascending=True, method='min')
        all_data['复合因子'] = all_data['波动率_250_排名']
    elif method == '行业分红域_低波红利策略':
        # 行业分红域_低波红利策略：1、行业内分红率排名靠前的20%   2、连续分红2年及以上   3、R_np_atoopc@xbx_单季同比大于0  4、选分红靠前且波动较低的股票
        all_data['分红率分位数'] = all_data.groupby(['交易日期', '新版申万一级行业名称'])['分红率_登记日'].rank(ascending=False, pct=True)
        all_data = all_data[all_data['分红率分位数'] <= 0.2]
        all_data = all_data[all_data['连续分红年份'] > 1]
        all_data = all_data[all_data['R_np_atoopc@xbx_单季同比'] > 0]

        # 低波因子和红利因子等权组合
        all_data['波动率_250_排名'] = all_data.groupby(['交易日期'])['波动率_250'].rank(ascending=True, method='min')
        all_data['分红率_排名'] = all_data.groupby(['交易日期'])['分红率_登记日'].rank(ascending=False, method='min')
        all_data['复合因子'] = all_data['分红率_排名'] + all_data['波动率_250_排名']
    elif method == '铁公鸡域':
        # 铁公鸡域：1、上市时间超过3年   2、最近3年没分红
        all_data = all_data[all_data['上市至今交易天数'] >= 750]
        all_data = all_data[all_data['连续分红年份'].isnull()]
        # 分域分析
        da.domain_analysis(all_data, temp)

        # 铁公鸡域内的使用低波因子
        all_data['波动率_250_排名'] = all_data.groupby(['交易日期'])['波动率_250'].rank(ascending=True, method='min')
        all_data['复合因子'] = all_data['波动率_250_排名']

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
