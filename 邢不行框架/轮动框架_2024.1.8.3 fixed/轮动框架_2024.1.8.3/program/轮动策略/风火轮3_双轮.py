"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import pandas as pd
import numpy as np
import os
import program.Config as Cfg

name = __file__.replace('\\', '/').split('/')[-1].replace('.py', '')  # 策略名称（必填）

# 文件名格式：周期_offset_选股数量.csv，例如：W_0_30.csv,W_1_30.csv,W_2_30.csv,W_3_30.csv,W_4_30.csv
# 多offset可直接配置不同的文件名后缀，但必须是相同的周期频率的。
# 如果某个策略同时要做周频和月频的轮动建议把这个这个轮动文件copy一份，一个文件专门是周的offset，一个文件专门是月的offset
strategy_param = ['W_0_@.csv']

# 需要导入那些因子数据
factors = {}  # '成交额': []

select_count = 1  # 选策略数量（必填）

mean_cols = []  # 需要求均值类型的因子（脚本2）

sum_cols = []  # 需要求和类型的因子（脚本2）  '成交额'

'''
跑默认风火轮3的老板可以看这个帖子，有助于复现：https://bbs.quantclass.cn/thread/46026
值得注意的点：
1.选股策略的选股数需要调整为10，默认大小市值的选股策略还是保持30
2.回测时间2014年开始（轮动策略想从2014年开始的话，选股策略建议2012年开始，这样可以计算出2014年选股策略的轮动因子）
3.小市值策略需要去掉5000w的交易额限制
4.尾盘日内换仓
'''

# ==========以下参数是根据策略在框架中额外添加的==========


# ----------下面的参数可以根据你的实际需求进行改动----------
short = 10  # 短参数，控制短动量和波动率
long = 250  # 长参数，控制长动量和分位数
std_factor = 'bbw'  # 可以使用的波动因子有：'bbw', 'bias_abs', 'bias_abs_mean', 'bias_std', 'mtm_std', 'price_std', 'ret_std'
stg_slt_num = 10  # 选股策略的数量，选10只就填10，如果是10选5模式，也要填10
big_list = ['诺亚方舟', '分红策略']  # 大市值策略列表
small_list = ['小市值_基本面优化', '小市值_量价优化', '小市值_行业高分红', '新股小市值', '小市值_lee', '小市值_周黎明']  # 小市值策略列表
first_rotation = {'大市值': 30, '小市值': 30}  # 一轮的策略与选股数。   ”'大市值':30“ 代表使用大市值的选股30只策略来进行一轮

# ----------以下参数不需要改动----------
sub_stg_list = big_list + small_list + list(first_rotation)  # 子策略名称，如果为空或者没有这个字段，表示使用所有的子策略


def cal_strategy_factors(data, exg_dict):
    """
    数据降采样之后的处理流程，非必要
    :param data: 传入的数据
    :param exg_dict:resample规则
    :return:
    """
    for s in [short]:
        # ===短动量
        # 均线
        data[f'ma_{s}'] = data['equity_curve'].rolling(s, min_periods=1).mean()
        # bias
        data[f'bias_{s}'] = data['equity_curve'] / data[f'ma_{s}'] - 1
        exg_dict[f'bias_{s}'] = 'last'

        # ===波动
        # bbw
        data[f'ma_{s}'] = data['equity_curve'].rolling(window=s, min_periods=s).mean()
        data[f'std_{s}'] = data['equity_curve'].rolling(window=s, min_periods=s).std()
        data[f'upper_{s}'] = data[f'ma_{s}'] + 2 * data[f'std_{s}']
        data[f'lower_{s}'] = data[f'ma_{s}'] - 2 * data[f'std_{s}']
        data[f'bbw_{s}'] = (data[f'upper_{s}'] - data[f'lower_{s}']) / data[f'ma_{s}']

        # bias abs
        data[f'bias_abs_{s}'] = data[f'bias_{s}'].abs()

        # bias abs mean
        data[f'bias_abs_mean_{s}'] = data[f'bias_abs_{s}'].rolling(s, min_periods=s).mean()

        # bias std
        data[f'bias_std_{s}'] = data[f'bias_{s}'].rolling(s, min_periods=s).std()

        # mtm std
        data[f'mtm_std_{s}'] = data['equity_curve'].pct_change(s).rolling(s).std()

        # price std
        data[f'price_std_{s}'] = data['equity_curve'].rolling(window=s, min_periods=s).apply(
            lambda x: (x / x.iloc[0]).std())

        # ret std
        data[f'ret_std_{s}'] = data['涨跌幅'].rolling(window=s, min_periods=s).std()

        for l in [long]:
            # ===价格分位数
            data[f'价格分位数_{l}'] = data['equity_curve'].rolling(window=l, min_periods=l).rank(pct=True)
            exg_dict[f'价格分位数_{l}'] = 'last'

            # ===长动量
            # 均线
            data[f'ma_{l}'] = data['equity_curve'].rolling(l, min_periods=1).mean()
            # bias
            data[f'bias_{l}'] = data['equity_curve'] / data[f'ma_{l}'] - 1
            exg_dict[f'bias_{l}'] = 'last'

            # ===波动归一化
            for _factor in [f'bbw_{s}', f'bias_abs_{s}', f'bias_abs_mean_{s}', f'bias_std_{s}', f'mtm_std_{s}',
                            f'price_std_{s}', f'ret_std_{s}']:
                data[f'{_factor}_rank{l}'] = data[_factor].rolling(window=l, min_periods=l).rank(pct=True)
                exg_dict[f'{_factor}_rank{l}'] = 'last'

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
    :return:
    """
    # 计算第一轮轮动
    first_rotation_df, all_data = first_rotation_method(all_data)
    # 将第一次轮动的结果和原始数据合并
    all_data = pd.merge(all_data, first_rotation_df, on='交易日期', how='inner')

    # 根据第一次的轮动结果，筛选出当期需要实盘的策略
    # 第一轮选小时，只保留小市值策略
    con1 = (all_data['市值风格'] == '小市值') & (all_data['子策略名称'].isin(small_list))
    # 第一轮选大时，只保留大市值策略
    con2 = (all_data['市值风格'] == '大市值') & (all_data['子策略名称'].isin(big_list))
    # 筛选出需要选的策略
    all_data = all_data.loc[con1 | con2]

    # 按照风火轮2的方法，再次进行轮动
    all_data = rotation_phase2(all_data)

    # 保存一份数据用作后续分析
    df_for_group = all_data.copy()
    # 选择排名第一的需要选择的策略
    all_data = all_data[all_data['复合因子_排名'] <= count]

    all_data['策略排名'] = all_data['复合因子_排名']
    all_data.sort_values(by='交易日期', inplace=True)
    return all_data, df_for_group


def after_select(all_data):
    """
    选策略之后的操作流程，非必要。
    :param all_data: 策略的截面数据
    :return:
    """

    method = '选5只'
    if method == '选5只':
        # 在选30的资金曲线中做选5个的事情
        all_data = all_data.groupby(['交易日期', '策略名称']).apply(lambda x: x[x['选股排名'] <= 5]).reset_index(drop=True)

    return all_data


# ==============================以下函数是根据策略需要添加进来的==============================


def first_rotation_method(all_data):
    """
    第一次轮动的方法
    :param all_data: 策略数据
    :return:
    """
    # ==先确定当前的周期
    period_in_name = all_data['策略名称'].iloc[0]
    current_period = ''
    for period in strategy_param:
        str_list = period.split('_')
        period = str_list[0] + '_' + str_list[1]
        if period in period_in_name:
            current_period = period
            break

    # ==找到第一次轮动需要的子策略
    first_rotation_strategy_list = []
    for key in first_rotation:
        first_rotation_strategy_list.append(f'{key}_{current_period}_{first_rotation[key]}')
    first_rotation_df = all_data[all_data['策略名称'].isin(first_rotation_strategy_list)].copy()

    # ==按照风火轮2的方式选大 or 选小
    first_rotation_df = rotation_phase2(first_rotation_df)
    first_rotation_df = first_rotation_df[first_rotation_df['复合因子_排名'] <= 1]
    # 判断是否需要择时
    filter_param = 0.8  # 判断价格处于高/低位的阈值
    # 计算择时信号
    first_rotation_df['timing_signal'] = first_rotation_df.apply(
        lambda rows: ma_timing(rows, filter_param, [long, short]), axis=1)
    # 空仓
    first_rotation_df = first_rotation_df[first_rotation_df['timing_signal'] == 1]
    # 只保留必要的字段
    first_rotation_df = first_rotation_df[['交易日期', '子策略名称']].rename(columns={'子策略名称': '市值风格'})

    # ==只保留我们需要的子策略，主要是数量的上的筛选，比如数据里面可能同时有：诺亚方舟_W_0_10 & 诺亚方舟_W_0_20
    con1 = all_data['策略名称'].str.endswith(f'{current_period}_{stg_slt_num}')  # 正常的策略以W_0_10这样的格式结尾
    con2 = all_data['策略名称'].str.endswith(f'{current_period}')  # 指数以W_0这样的格式结尾
    all_data = all_data[con1 | con2]

    return first_rotation_df, all_data


def rotation_phase2(all_data):
    """
    风火轮2的算法
    :param all_data: 策略数据
    :return:
    """
    weight = all_data.groupby('交易日期')[f'{std_factor}_{short}_rank{long}'].max().rename('weight').reset_index()
    all_data = pd.merge(all_data, weight, on='交易日期', how='left')
    all_data['复合因子'] = all_data[f'bias_{short}'] * all_data['weight'] + all_data[f'bias_{long}'] * (1 - all_data['weight'])
    all_data['复合因子_排名'] = all_data.groupby('交易日期')['复合因子'].rank(method='min', ascending=False)
    return all_data


# 择时空仓函数
def ma_timing(row, para, stg_param):
    # 当策略当前价格处于极端价格位置时
    if (row[f'价格分位数_{stg_param[0]}'] > para):
        # 此时还处于下跌状态
        if (row[f'bias_{stg_param[1]}'] < 0):
            # 那我们就空仓
            return 0
    # 不满足上述条件就开仓
    return 1
