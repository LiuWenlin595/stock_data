"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import pandas as pd
import numpy as np

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 当前文件的名字

# 文件名格式：周期_offset_选股数量.csv，例如：W_0_30.csv,W_1_30.csv,W_2_30.csv,W_3_30.csv,W_4_30.csv
# 多offset可直接配置不同的文件名后缀，但必须是相同的周期频率的。
# 如果某个策略同时要做周频和月频的轮动建议把这个这个轮动文件copy一份，一个文件专门是周的offset，一个文件专门是月的offset
strategy_param = ['W_0_@.csv']

# 需要导入那些因子数据
factors = {}

select_count = 1  # 选策略数量（必填）

mean_cols = []  # 需要求均值类型的因子（脚本2）

sum_cols = []  # 需要求和类型的因子（脚本2）

sub_stg_list = ['大市值', '小市值']  # 子策略名称，如果为空或者没有这个字段，表示使用所有的子策略


def cal_strategy_factors(data, exg_dict):
    """
    数据降采样之后的处理流程，非必要
    :param data: 传入的数据
    :param exg_dict:resample规则
    :return:
    """
    # 价格分位数
    data['价格分位数_250'] = data['equity_curve'].rolling(window=250, min_periods=250).rank(pct=True)
    exg_dict['价格分位数_250'] = 'last'

    # 均线
    data['ma_20'] = data['equity_curve'].rolling(20, min_periods=1).mean()
    # bias
    data['bias_20'] = data['equity_curve'] / data['ma_20'] - 1
    exg_dict['bias_20'] = 'last'

    return data, exg_dict


def after_resample(data):
    """
    数据合并之后的操作流程，非必要。
    :param data: 策略数据
    :return:
    """
    return data


def filter_and_select_strategies(all_data, count, param):
    """
    过滤函数，在选股前过滤，必要
    :param all_data: 截面数据
    :param count: 选策略数量
    :param param:轮动策略的参数，默认给的参数[],意味着不需要参数，在实盘的策略不要带参数
    :return:
    """

    # 计算因子的排名
    all_data['bias_20排名'] = all_data.groupby('交易日期')['bias_20'].rank(method='min', ascending=False)

    # 用中位数（排名）填充空值
    all_data['bias_20排名'].fillna(value=all_data.groupby('交易日期')['bias_20排名'].transform('median'),
                                 inplace=True)

    # 计算复合因子
    all_data['复合因子'] = all_data['bias_20排名']
    # 将复合因子转化为排名
    all_data['复合因子_排名'] = all_data.groupby('交易日期')['复合因子'].rank(method='min', ascending=True)

    # =空仓择时
    # 判断价格处于高/低位的阈值
    filter_param = 0.9
    # 计算择时信号
    all_data['timing_signal'] = all_data.apply(lambda rows: ma_timing(rows, filter_param), axis=1)
    # 空仓
    all_data = all_data[all_data['timing_signal'] == 1]

    # 保存一份数据用作后续分析
    df_for_group = all_data.copy()
    # 选择排名第一的需要选择的策略
    all_data = all_data[all_data['复合因子_排名'] <= count]

    all_data['策略排名'] = all_data['复合因子_排名']
    all_data.sort_values(by='交易日期', inplace=True)
    return all_data, df_for_group


# 择时空仓函数
def ma_timing(row, para):
    # 当策略当前价格处于极端价格位置时
    if (row['价格分位数_250'] > para) or (row['价格分位数_250'] < 1 - para):
        # 此时还处于下跌状态
        if row['bias_20'] < 0:
            # 那我们就空仓
            return 0
    # 不满足上述条件就开仓
    return 1


def after_select(all_data):
    """
    选策略之后的操作流程，非必要。
    :param all_data: 策略的截面数据
    :return:
    """

    method = '案例1'
    if method == '案例1':
        # 在选30的资金曲线中做选5个的事情
        all_data = all_data.groupby(['交易日期', '策略名称']).apply(lambda x: x[x['选股排名'] <= 5]).reset_index(drop=True)
    elif method == '案例2':
        # 过滤上周期下跌的股票
        time_df = pd.DataFrame(sorted(all_data['交易日期'].unique()), columns=['交易日期'])
        time_df['上周期'] = time_df['交易日期'].shift(1)

        all_data = pd.merge(all_data, time_df, on='交易日期', how='left')
        temp = all_data[['交易日期', '股票代码', '下周期涨跌幅']].copy()
        all_data = pd.merge(all_data, temp, left_on=['上周期', '股票代码'], right_on=['交易日期', '股票代码'], how='left',
                            suffixes=('', '_上周期'))
        con1 = pd.isnull(all_data['下周期涨跌幅_上周期'])
        con2 = all_data['下周期涨跌幅_上周期'] > 0
        all_data = all_data[con1 | con2]
    elif method == '案例3':
        # 过滤历史胜率低的股票
        groups = all_data.groupby(['股票代码'])
        res_list = []
        days = 365
        for name, group in groups:
            group = group.sort_values(by='交易日期').reset_index(drop=True)
            for i in group.index:
                end_date = group.loc[i, '交易日期']
                start_date = end_date - pd.to_timedelta(days, unit='D')
                temp = group[(group['交易日期'] >= start_date) & (group['交易日期'] < end_date)]
                if len(temp) > 0:
                    group.loc[i, '近一年累计收益'] = (temp['下周期涨跌幅'] + 1).prod() - 1
                    group.loc[i, '近一年胜率'] = (temp['下周期涨跌幅'] > 0).mean()
                    group.loc[i, '近一年选中次数'] = len(temp)
                else:
                    group.loc[i, '近一年累计收益'] = np.nan
                    group.loc[i, '近一年胜率'] = np.nan
                    group.loc[i, '近一年选中次数'] = 0
            res_list.append(group)

        res_df = pd.concat(res_list, ignore_index=True)
        res_df = res_df[['交易日期', '股票代码', '近一年累计收益', '近一年胜率', '近一年选中次数']]

        all_data = pd.merge(all_data, res_df, on=['交易日期', '股票代码'], how='left')

        all_data = all_data[all_data['近一年胜率'] > 0.5]
        all_data = all_data[all_data['近一年选中次数'] > 10]

    return all_data
