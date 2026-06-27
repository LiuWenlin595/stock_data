"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import os
import re
import sys
import datetime
from decimal import Decimal, ROUND_HALF_UP
from joblib import Parallel, delayed
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from tqdm import tqdm
import program.Rainbow as Rb


# region 通用函数

def get_file_in_folder(path, file_type, contains=None, filters=[], drop_type=False):
    """
    获取指定文件夹下的文件
    :param path: 文件夹路径
    :param file_type: 文件类型
    :param contains: 需要包含的字符串，默认不含
    :param filters: 字符串中需要过滤掉的内容
    :param drop_type: 是否要保存文件类型
    :return:
    """
    file_list = os.listdir(path)
    file_list = [file for file in file_list if file_type in file]
    if contains:
        file_list = [file for file in file_list if contains in file]
    for con in filters:
        file_list = [file for file in file_list if con not in file]
    if drop_type:
        file_list = [file[:file.rfind('.')] for file in file_list]

    return file_list


def _factors_linear_regression(data, factor, neutralize_list, industry=None):
    """
    使用线性回归对目标因子进行中性化处理，此方法外部不可直接调用。
    :param data: 股票数据
    :param factor: 目标因子
    :param neutralize_list:中性化处理变量list
    :param industry: 行业字段名称，默认为None
    :return: 中性化之后的数据
    """
    lrm = LinearRegression(fit_intercept=True)  # 创建线性回归模型
    if industry:  # 如果需要对行业进行中性化，将行业的列名加入到neutralize_list中
        industry_cols = [col for col in data.columns if '所属行业' in col]
        for col in industry_cols:
            if col not in neutralize_list:
                neutralize_list.append(col)
    train = data[neutralize_list].copy()  # 输入变量
    label = data[[factor]].copy()  # 预测变量
    lrm.fit(train, label)  # 线性拟合
    predict = lrm.predict(train)  # 输入变量进行预测
    data[factor + '_中性'] = label.values - predict  # 计算残差
    return data


def factor_neutralization(data, factor, neutralize_list, industry=None):
    """
    使用线性回归对目标因子进行中性化处理，此方法可以被外部调用。
    :param data: 股票数据
    :param factor: 目标因子
    :param neutralize_list:中性化处理变量list
    :param industry: 行业字段名称，默认为None
    :return: 中性化之后的数据
    """
    df = data.copy()
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=[factor] + neutralize_list, how='any')
    if industry:  # 果需要对行业进行中性化，先构建行业哑变量
        # 剔除中性化所涉及的字段中，包含inf、-inf、nan的部分
        df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=[industry], how='any')
        # 对行业进行哑变量处理
        ind = df[industry]
        ind = pd.get_dummies(ind, columns=[industry], prefix='所属行业',
                             prefix_sep="_", dummy_na=False, drop_first=True)
        """
        drop_first=True会导致某一行业的的哑变量被删除，这样的做的目的是为了消除行业间的多重共线性
        详见：https://www.learndatasci.com/glossary/dummy-variable-trap/
        """
    else:
        ind = pd.DataFrame()
    df = pd.concat([df, ind], axis=1)
    df = df.groupby(['交易日期']).apply(_factors_linear_regression, factor=factor,
                                    neutralize_list=neutralize_list, industry=industry)
    # df[factor + '_中性'] = df.groupby(['交易日期']).apply(_factors_linear_regression, factor=factor,
    #                                                 neutralize_list=neutralize_list, industry=industry)
    df.sort_values(by=['交易日期', '股票代码'], inplace=True)
    return df


# endregion


# region 轮动策略专用函数

def import_benchmark_data(path, po_df, per_oft, start=None, end=None, is_index=False):
    """
    从指定位置读入基准策略的数据
    :param path:文件路径
    :param po_df: period_offset 的df，其中col中的W_0已经变成period_offset字段
    :param start: 开始时间
    :param end: 结束时间
    :param is_index:导入的是否为指数
    :return:
    """
    # 导入基准
    if is_index:
        df_bench = pd.read_csv(path, parse_dates=['candle_end_time'], encoding='gbk')
        df_bench['基准涨跌幅'] = df_bench['close'].pct_change()
        df_bench.rename(columns={'candle_end_time': '交易日期'}, inplace=True)
    else:
        df_bench = pd.read_csv(path, parse_dates=['交易日期'], encoding='gbk', skiprows=1)
        df_bench.rename(columns={'涨跌幅': '基准涨跌幅'}, inplace=True)
    df_bench = df_bench[['交易日期', '基准涨跌幅']]
    if pd.isnull(end):
        is_current_period = is_in_current_period(per_oft, df_bench, po_df)
        end = df_bench['交易日期'].max()
    else:
        is_current_period = False
    if pd.isnull(start):
        start = df_bench['交易日期'].min()
    start_date, end_date = calc_start_and_end_date(po_df, per_oft, start, end)
    df_bench = df_bench[(df_bench['交易日期'] >= start_date) & (df_bench['交易日期'] <= end_date)]
    df_bench.sort_values(by=['交易日期'], inplace=True)
    df_bench.reset_index(inplace=True, drop=True)
    return df_bench, is_current_period


def index2strategy(cfg, strategy_path, po_df, po_str):
    """
    把指数文件变成策略的函数
    :param cfg:Config模块
    :param strategy_path:策略的路径
    :param po_df:周期 & offset的df
    :param po_str:周期 & offset
    :return:
    """
    # 从Config里面把需要的配置信息先解析出来
    inx_path = cfg.index_strategy_path
    result_path = os.path.join(cfg.select_program_path, 'data/每日选股/选股策略')
    inx_dict = cfg.inx_dict
    end_exchange = cfg.end_exchange
    # 获取指数列表
    index_list = get_file_in_folder(inx_path, '.csv')
    # 遍历每一个指数
    for inx in index_list:
        print('正在将指数转为策略', inx)
        # 读取指数
        df = pd.read_csv(os.path.join(inx_path, inx), encoding='gbk', parse_dates=['交易日期'], skiprows=1)
        # 复制一份数据，备用
        tmp_df = df.copy()
        # 合并指数数据
        df = pd.merge(left=df, right=po_df[['交易日期', po_str]], on='交易日期', how='left')
        # w53空仓那一天的涨跌幅是印花税
        if po_df[po_str].min() < 0:  # 出现W53_0这样有负值的情况
            change_days_list = po_df[po_df[po_str] < 0]['交易日期'].to_list()
            po_df['group'] = po_df[po_str].abs()
            period_last_day_list = po_df.groupby(['group'])['交易日期'].last().to_list()
            df.loc[df['交易日期'].isin(change_days_list), '涨跌幅'] = 0
            df.loc[df['交易日期'].isin(period_last_day_list), '涨跌幅'] = - 1.2 / 10000  # 无印花税，这里是手续费

        min_po = df[po_str].abs().min()
        # period_offset合并后，最小周期+1的第一天开始（因为不保证最小周期就是第一天开始的）
        df = df[df[df[po_str].abs() > min_po].index.min():].reset_index(drop=True)
        if po_df[po_str].min() < 0:  # 出现W53_0这样有负值的情况
            # equity_curve虽然目前没用到，但是稳妥一些，还是重新跑一遍
            df['equity_curve'] = (df['涨跌幅'] + 1).cumprod()
        if inx.replace('.csv', '') in inx_dict.keys():
            inx_stg_name = inx_dict[inx.replace('.csv', '')][0] + '_' + po_str
        else:
            continue
        df['策略名称'] = inx_stg_name
        df = df[['交易日期', '策略名称', '持有股票代码', '涨跌幅', 'equity_curve', '指数涨跌幅', 'benchmark']]
        title = pd.DataFrame(data=['数据由邢不行整理，对数据字段有疑问的，可以直接微信私信邢不行，微信号：xbx297'])
        save_path = os.path.join(strategy_path, f'{inx_stg_name}.csv')
        title.to_csv(save_path, encoding='gbk', index=False, header=False)
        df.to_csv(save_path, encoding='gbk', index=False, mode='a')

        # 保存每日选股结果
        save_path = os.path.join(result_path, f'{inx_stg_name}.csv')
        new_res = pd.DataFrame()

        select_date = df['交易日期'].max()
        if end_exchange:  # 尾盘换仓的交易日期等于选股日期
            trade_date = select_date
        else:  # 正常情况的交易日期等于选股日期的下一个交易日
            select_inx = po_df[po_df['交易日期'] == select_date].index.min()
            trade_date = po_df['交易日期'].iloc[select_inx + 1]

        new_res.loc[0, '选股日期'] = select_date
        new_res.loc[0, '交易日期'] = trade_date
        new_res.loc[0, '股票代码'] = inx_dict[inx.replace('.csv', '')][1]
        new_res.loc[0, '股票名称'] = inx_dict[inx.replace('.csv', '')][0]
        new_res.loc[0, '选股排名'] = 1
        if os.path.exists(save_path):
            res_df = pd.read_csv(save_path, encoding='gbk', parse_dates=['交易日期'])
            res_df = pd.concat([res_df, new_res], ignore_index=True)
            res_df.drop_duplicates(subset=['交易日期'], keep='last', inplace=True)
            res_df.to_csv(save_path, encoding='gbk', index=False)
        else:
            new_res.to_csv(save_path, encoding='gbk', index=False)

        # ===保存历史选股结果
        # 先把数据按照要求进行resample
        tmp_df = pd.merge(tmp_df, po_df[['交易日期', po_str]], on='交易日期', how='left')
        tmp_df['group'] = tmp_df[po_str].abs()
        # 如果是负数，代表提前平仓了，用0替换数据
        tmp_df.loc[tmp_df[po_str] < 0, '涨跌幅'] = 0
        tmp_df['下日_开盘价买入涨跌幅'] = tmp_df['涨跌幅'].shift(-1)
        tmp_df['周期最后交易日'] = tmp_df['交易日期']

        # resample的数据格式
        rule_dict = {'周期最后交易日': 'last', '下日_开盘价买入涨跌幅': 'last', '涨跌幅': 'last', 'equity_curve': 'last'}
        # 按照规则进行resample

        ana_df = tmp_df.groupby('group').agg(rule_dict)
        ana_df['交易日期'] = ana_df['周期最后交易日']
        # 合并数据信息
        ana_df['股票代码'] = inx_dict[inx.replace('.csv', '')][1]
        ana_df['股票名称'] = inx_stg_name
        # 后续考虑补全这些数据
        ana_df['每天涨跌幅'] = tmp_df.groupby('group')['涨跌幅'].apply(lambda x: list(x))
        ana_df['下周期每天涨跌幅'] = ana_df['每天涨跌幅'].shift(-1)
        # 因为指数没那么多数据，所以所有的数据都按照开盘买入涨跌幅和正常收盘卖出涨跌幅来计算（所以带有指数的回测可能会不太准确）
        for col in ['下日_均价买入涨跌幅', '下日_09:35收盘价买入涨跌幅', '下日_09:45收盘价买入涨跌幅', '下日_09:55收盘价买入涨跌幅']:
            ana_df[col] = ana_df['下日_开盘价买入涨跌幅']

        for col in ['下周期_下日_开盘价卖出涨跌幅', '下周期_下日_均价卖出涨跌幅', '下周期_下日_09:35收盘价卖出涨跌幅', '下周期_下日_09:45收盘价卖出涨跌幅',
                    '下周期_下日_09:55收盘价卖出涨跌幅', '下周期_当日_均价卖出涨跌幅']:
            # 因为缺少数据，统一用涨跌幅替代
            ana_df[col] = ana_df['涨跌幅']
        ana_df['涨跌幅'] = ana_df['equity_curve'].pct_change()  # 用复权收盘价计算
        first_ret = (np.array(ana_df['每天涨跌幅'].iloc[0]) + 1).prod() - 1  # 第一个持仓周期的复利涨跌幅
        ana_df['涨跌幅'].fillna(value=first_ret, inplace=True)
        ana_df['选股排名'] = 1
        ana_df['signal'] = 1
        ana_path = os.path.join(cfg.select_program_path, f'data/分析目录/待分析/{inx_stg_name}.pkl')
        ana_df.to_pickle(ana_path)


def create_empty_data_for_strategy(bench_data, po_df, per_oft):
    """
    根据基准策略创建空的周期数据，用于填充不交易的日期
    :param bench_data: 基准策略
    :param trans_period: 数据转换周期
    :return:
    """

    po_df['period_offset'] = po_df[per_oft].abs().copy()
    empty_df = pd.merge(left=po_df, right=bench_data, on=['交易日期'], how='right')
    empty_df['周期最后交易日'] = empty_df['交易日期']
    empty_df['涨跌幅'] = 0.0
    empty_df.set_index('交易日期', inplace=True)
    agg_dict = {'周期最后交易日': 'last'}

    empty_period_df = empty_df.groupby('period_offset').agg(agg_dict)
    empty_period_df['每天涨跌幅'] = empty_df.groupby('period_offset')['涨跌幅'].apply(lambda x: list(x))
    # 删除没交易的日期
    empty_period_df.dropna(subset=['周期最后交易日'], inplace=True)

    empty_period_df['下周期每天涨跌幅'] = empty_period_df['每天涨跌幅'].shift(-1)
    empty_period_df.dropna(subset=['下周期每天涨跌幅'], inplace=True)

    # 填仓其他列
    empty_period_df['策略数量'] = 0
    empty_period_df['策略名称'] = 'empty'
    empty_period_df['持有股票代码'] = 'empty'
    empty_period_df['选股下周期涨跌幅'] = 0.0
    empty_period_df.rename(columns={'周期最后交易日': '交易日期'}, inplace=True)
    empty_period_df.set_index('交易日期', inplace=True)

    empty_period_df = empty_period_df[['策略名称', '持有股票代码', '策略数量', '选股下周期涨跌幅', '下周期每天涨跌幅']]
    return empty_period_df


def transfer_strategy_data(df, po_df, period_offset, extra_agg_dict={}):
    """
    将日线数据转换为相应的周期数据
    :param df:数据
    :param po_df:周期offset的df数据
    :param period_type:持仓周期
    :param offset_type:持仓offset
    :param extra_agg_dict:合并规则
    :return:
    """
    # 将交易日期设置为index
    df['周期最后交易日'] = df['交易日期']
    df.set_index('交易日期', inplace=True)

    agg_dict = {
        # 必须列
        '周期最后交易日': 'last',
        '策略名称': 'last',
        '持有股票代码': 'last',
    }
    agg_dict = dict(agg_dict, **extra_agg_dict)

    # _group为含负数的原始数据，用于把对应非交易日的涨跌幅设置为0
    po_df['_group'] = po_df[period_offset].copy()
    # group为绝对值后的数据，用于对股票数据做groupby
    po_df['group'] = po_df['_group'].abs().copy()
    df = pd.merge(left=df, right=po_df[['交易日期', 'group', '_group']], on='交易日期', how='left')
    # 为了W53（周五买周三卖）这种有空仓日期的周期，把空仓日的涨跌幅设置为0
    df.loc[df['_group'] < 0, '涨跌幅'] = 0

    # ===对策略数据数据根据周期offset情况，进行groupby后，得到对应的nD/周线/月线数据
    period_df = df.groupby('group').agg(agg_dict)
    # 剔除不交易的数据，改完后这行应该不起作用
    period_df.dropna(subset=['策略名称'], inplace=True)

    # 计算周期资金曲线
    period_df['每天涨跌幅'] = df.groupby('group')['涨跌幅'].apply(lambda x: list(x))

    # 重新设定index
    period_df.reset_index(inplace=True)
    period_df['交易日期'] = period_df['周期最后交易日']
    del period_df['周期最后交易日']
    del period_df['group']
    cols = period_df.columns.to_list()
    cols.remove('交易日期')
    period_df = period_df[['交易日期'] + cols]
    return period_df


def save_shift_result(sft_res_path, new_res, po_df, is_open, end_exchange, select_date):
    """
    保存最新的轮动结果
    :param sft_res_path:轮动策略结果的路径
    :param new_res:轮动数据
    :param po_df:周期表
    :param is_open:是否开仓
    :param end_exchange:是否尾盘换仓
    :param select_date:选股日期
    :return:
    """
    if is_open:
        if end_exchange:  # 尾盘换仓的交易日期等于选股日期
            trade_date = select_date
        else:  # 正常情况的交易日期等于选股日期的下一个交易日
            select_inx = po_df[po_df['交易日期'] == select_date].index.min()
            trade_date = po_df['交易日期'].iloc[select_inx + 1]
        # 如果选股结果为空，提示
        if new_res.empty:
            Rb.record_log('轮动结果为空，可能是策略空仓，或者指数截止日期比股票截止日期多一天导致的，请检查数据。')
            new_res = pd.DataFrame(columns=['选股日期', '交易日期', '股票代码', '股票名称', '选股排名', '策略名称', '策略排名'])
            new_res.loc[0, '选股日期'] = select_date
            new_res.loc[0, '交易日期'] = trade_date
            new_res.loc[0, '股票代码'] = 'empty'
            new_res.loc[0, '股票名称'] = '轮动策略空仓'
            new_res.loc[0, '选股排名'] = 1
            new_res.loc[0, '策略名称'] = '轮动策略空仓'
            new_res.loc[0, '策略排名'] = 1
        else:
            # 获取最新的选股结果
            new_res['选股日期'] = select_date
            new_res['交易日期'] = trade_date
            new_res = new_res[['选股日期', '交易日期', '股票代码', '股票名称', '选股排名', '策略名称', '策略排名']]
            new_res = new_res.sort_values(by=['策略排名', '选股排名']).reset_index(drop=True)

        # 申明历史选股结果的变量
        res_df = pd.DataFrame()
        # 如果有历史结果，则读取历史结果
        if os.path.exists(sft_res_path):
            res_df = pd.read_csv(sft_res_path, encoding='gbk', parse_dates=['选股日期', '交易日期'])
            # 有新产生持仓，就把历史结果里的相同日期去掉
            if not new_res.empty:
                res_df = res_df[res_df['选股日期'] < new_res['选股日期'].min()]
                res_df = res_df[res_df['交易日期'] < new_res['交易日期'].min()]

        # 将历史选股结果与最新选股结果合并
        res_df = pd.concat([res_df, new_res], ignore_index=True)
        # 清洗数据，保存结果
        res_df.drop_duplicates(subset=['选股日期', '交易日期', '策略名称', '股票代码'], keep='last', inplace=True)
        res_df.sort_values(by=['选股日期', '交易日期', '策略排名', '选股排名'], inplace=True)
        res_df.to_csv(sft_res_path, encoding='gbk', index=False)
    else:
        if not os.path.exists(sft_res_path):
            res_df = pd.DataFrame(columns=['选股日期', '交易日期', '股票代码', '股票名称', '选股排名', '策略名称', '策略排名'])
            res_df.to_csv(sft_res_path, encoding='gbk', index=False)
        new_res = pd.DataFrame(columns=['选股日期', '交易日期', '股票代码', '股票名称', '选股排名', '策略名称', '策略排名'])

    return new_res


# endregion


def read_period_and_offset_file(file_path):
    """
    载入周期offset文件
    """
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, encoding='gbk', parse_dates=['交易日期'], skiprows=1)
        return df
    else:
        Rb.record_log(f'文件{file_path}不存在，请获取period_offset.csv文件后再试')
        raise FileNotFoundError('文件不存在')


def calc_start_and_end_date(df, per_oft, start, end):
    """
    计算开始结束时间，3_选策略脚本在开始的时候，要算出需要截取哪些日期使用
    :param df:周期offset数据，其中W_0形式已根据需要替换为period_offset字段。
    :param start:config里配置的开始时间
    :param end:config里配置的结束时间，如果是None，会变成K线最后时间
    :return:
    """
    df['period_offset'] = df[per_oft].abs()  # 为W53做的特别处理
    df['周期结束日'] = df['交易日期'].copy()
    agg_dict = {'交易日期': 'first', '周期结束日': 'last'}
    # ===对策略数据数据根据周期offset情况，进行groupby后，得到对应的nD/周线/月线数据
    period_df = df.groupby('period_offset').agg(agg_dict).reset_index(drop=False)
    real_start = df[df['交易日期'] < pd.to_datetime(start)]['交易日期'].max()
    period_df = period_df[period_df['周期结束日'] >= pd.to_datetime(real_start)]
    period_df = period_df[period_df['period_offset'] > 0]
    period_df = period_df[period_df['周期结束日'] <= pd.to_datetime(end)]
    return period_df['周期结束日'].min(), period_df['周期结束日'].max()


def is_in_current_period(period_offset, index_data, period_and_offset_df):
    """
    判断指数文件的最后一行日期是否命中周期offset选股日（选股日定义：持仓周期最后一日，尾盘需要卖出持仓，次日早盘买入新的标的）
    :return: True选股日，False非选股日
    """
    index_lastday = index_data['交易日期'].iloc[-1]
    # 把周期数据转为选股日标记数据
    period_and_offset_df['period_offset_判断'] = period_and_offset_df[period_offset].abs().diff().shift(-1)
    """
             交易日期  period_offset  W_1  W_2  period_offset_判断
        0  2005-01-05  0.0  0.0  0.0     0.0
        1  2005-01-06  0.0  0.0  0.0     0.0
        2  2005-01-07  0.0  0.0  0.0     1.0
        3  2005-01-10  1.0  0.0  0.0     0.0
        4  2005-01-11  1.0  1.0  0.0     0.0
        5  2005-01-12  1.0  1.0  1.0     0.0
        6  2005-01-13  1.0  1.0  1.0     0.0
        7  2005-01-14  1.0  1.0  1.0     1.0
        8  2005-01-17  2.0  1.0  1.0     0.0
    """
    if period_and_offset_df.loc[period_and_offset_df['交易日期'] == index_lastday, 'period_offset_判断'].iloc[
        -1] == 1:
        # 选股日
        return True
    else:
        # 非选股日
        return False


def merge_offset(equity_list, index_data):
    """
    合并所有offset的策略资金曲线
    :param equity_list: 各offset的资金曲线list
    :param index_data: 指数
    :return: equity_df：合并完的资金曲线数据
    """
    # 合并equity_list中所有资金曲线，填充空值，因为不同offset的起始结束日不同，所以肯定有空值
    _equity_df = pd.concat(equity_list, axis=1, join='outer')
    _equity_df.fillna(method='ffill', inplace=True)
    _equity_df.fillna(value=1, inplace=True)

    # 通过最大最小的时间，从index取出需要画图的这段，算完banchmark
    equity_df = index_data[
        (index_data['交易日期'] >= _equity_df.index.min()) & (index_data['交易日期'] <= _equity_df.index.max())].copy()
    equity_df.set_index('交易日期', inplace=True)
    equity_df['benchmark'] = (equity_df['基准涨跌幅'] + 1).cumprod()
    # 合并资金曲线，通过遍历择时和不择时区分两个
    equity_col = _equity_df.columns.unique().to_list()
    for each_col in equity_col:
        equity_df[each_col] = _equity_df[[each_col]].mean(axis=1)
    # 把交易日期变回非index的列
    equity_df.reset_index(drop=False, inplace=True)
    # 资金曲线反推的时候，需要前面加一行，否则第一个涨跌幅算不出
    equity_df = pd.concat([pd.DataFrame([{'equity_curve': 1}]), equity_df], ignore_index=True)
    equity_df['涨跌幅'] = equity_df['equity_curve'] / equity_df['equity_curve'].shift() - 1
    equity_df.drop([0], axis=0, inplace=True)

    # 不带择时
    equity_df = equity_df[['交易日期', '涨跌幅', 'equity_curve', '基准涨跌幅', 'benchmark']]
    return equity_df


def get_variable_from_py_file(py_path, var_dict):
    """
    从py文件中获取字段，请注意，需要获取的变量需要再一行只内写完。
    :param py_path: py文件名，
    :param var_dict: 参数列表，{参数名:类型}
    :return:
    """
    # 判断文件是否存在
    if os.path.exists(py_path):
        # 逐行读入文件
        with open(py_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        # 寻找需要的变量的行
        res = {}
        for var in var_dict.keys():
            for line in lines:
                if line.startswith(var):
                    # 如果这行代码又注释，把注释之后的内容去掉
                    if '#' in line:
                        inx = line.find('#')
                        line = line[:inx]
                    # 替换掉字符串中的空格及换行
                    line = line.replace('\n', '').replace(' ', '')
                    sub_str = line.split('=')
                    if var_dict[var] == str and sub_str[1].replace('\'', '').replace('\"', '') == 'None':
                        res[sub_str[0]] = None
                    elif var_dict[var] == bool:
                        res[sub_str[0]] = eval(sub_str[1])
                    elif var_dict[var] == str:
                        res[sub_str[0]] = sub_str[1].replace('\'', '').replace('\"', '')
                    elif var_dict[var] == 'eval':
                        res[sub_str[0]] = eval(sub_str[1])
                    else:
                        res[sub_str[0]] = var_dict[var](sub_str[1])
                    break
        return res
    else:
        Rb.record_log(f'路径错误，未找到对应的py文件：{py_path}')
        raise Exception(f'路径错误，未找到对应的py文件：{py_path}')


def load_factor_data(factor_path, stg_param_dict, n_job, trading_mode, inx_data, po_df):
    """
    加载因子数据
    :param factor_path: 因子路径
    :param stg_param_dict: 策略的参数列表
    :param n_job: 多线程状态
    :param trading_mode: 是否要运行所有的offset
    :param inx_data: 指数数据
    :param po_df: 周期 & offset数据
    :return:
    """
    df = pd.DataFrame()
    # 公共列
    common_cols = ['股票代码', '交易日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '成交额', '流通市值', '总市值', '沪深300成分股', '上证50成分股',
                   '中证500成分股', '中证1000成分股', '中证2000成分股', '创业板指成分股', '新版申万一级行业名称', '新版申万二级行业名称', '新版申万三级行业名称',
                   '09:35收盘价', '09:45收盘价', '09:55收盘价', '复权因子', '收盘价_复权', '开盘价_复权', '最高价_复权', '最低价_复权']
    # 先确定有多少策略需要运行
    stg_list = []
    for param, stg_set in stg_param_dict.items():
        if not trading_mode:  # 回测模式所有的策略都需要运行
            for stg in stg_set:
                if stg not in stg_list:
                    stg_list.append(stg)
        else:  # 实盘模式只运行需要的策略
            per_oft = param.split('_')[0] + '_' + param.split('_')[1]
            is_open = is_in_current_period(per_oft, inx_data, po_df)
            if is_open:
                for stg in stg_set:
                    if stg not in stg_list:
                        stg_list.append(stg)

    # 先拿到所有的因子信息
    factors = {}
    for stg in stg_list:
        for fa in stg.factors.keys():
            # 如果因子记录过，则记录一下
            if fa not in factors.keys():
                factors[fa] = stg.factors[fa]
            else:  # 如果已经记录过了，对比一下两者之间的差异
                # 但凡有一个因子全选了，则都需要全选
                if len(factors[fa]) == 0 or len(stg.factors[fa]) == 0:
                    factors[fa] = []
                else:  # 寻找两个集合的并集
                    factors[fa] = list(set(factors[fa]).union(set(stg.factors[fa])))

    for fa in factors:
        Rb.record_log(f'\n=====正在读取因子数据：{fa}=====')
        fa_path = os.path.join(factor_path, f'日频数据/{fa}')
        stock_list = get_file_in_folder(fa_path, '.pkl')

        df_list = Parallel(n_job)(delayed(pd.read_pickle)(os.path.join(fa_path, stock)) for stock in tqdm(stock_list))
        fa_df = pd.concat(df_list, ignore_index=True)
        # 如果只筛选指定的列
        if len(factors[fa]) > 0:
            fa_df = fa_df[['交易日期', '股票代码'] + factors[fa]]

        # 对比一下前后列名是否有重复的
        repeat_cols = list(set(df.columns).intersection(set(fa_df.columns)))
        # 要排除掉交易日期和股票代码两列
        repeat_cols = [col for col in repeat_cols if col not in ['股票代码', '交易日期']]
        if len(repeat_cols) > 0:
            for col in repeat_cols:
                if col in common_cols:  # 如果是公共列，则删除
                    fa_df.drop(columns=[col], inplace=True)
                else:
                    Rb.record_log(f'{fa}文件中的{col}列与已经加载的数据重名，程序已经自动退出，请检查因子重名的情况后重新运行')
                    raise Exception(f'{fa}文件中的{col}列与已经加载的数据重名，程序已经自动退出，请检查因子重名的情况后重新运行')
        if df.empty:
            df = fa_df
        else:
            df = pd.merge(df, fa_df, on=['交易日期', '股票代码'], how='left')
    return df


def list_to_str(ipt_list):
    """
    将list格式转换成字符串格式，仅支持可以用字符串表达的list
    :param ipt_list: 输入的list
    :return:
    """
    res_str = ''
    for item in ipt_list:
        res_str += str(item) + '+'
    res_str = res_str[:-1]
    return res_str


def str_to_list(ipt_str, item_type='str'):
    """
    将输入的字符串格式转换会list格式
    :param ipt_str: 输入的字符串
    :param item_type: list中每个元素的类别
    :return:
    """
    res_list = ipt_str.split('+')
    if item_type != 'str':
        for i in range(0, len(res_list)):
            res_list[i] = eval(f'{item_type}({res_list[i]})')
    return res_list


def save_back_test_result(stg, per_oft, param, rtn, years_ret, path):
    """
    保存回测结果
    :param stg:
    :param per_oft:
    :param param:
    :param rtn:
    :param years_ret:
    :param path:
    :return:
    """
    save_path = os.path.join(path, 'data/回测结果/遍历结果.csv')
    res_df = pd.DataFrame()
    res_df.loc[0, '策略名称'] = stg.name
    res_df.loc[0, '周期&offset'] = per_oft
    res_df.loc[0, '策略参数'] = list_to_str(param)
    res_df.loc[0, '选股数量'] = stg.select_count

    # 把回测指标加到要保存的数据中
    col = '带择时' if '带择时' in rtn.columns else 0
    for i in rtn.index:
        res_df.loc[0, i] = rtn.loc[i, col]
    years = years_ret.copy()
    # 保存历年收益
    years_col = '涨跌幅_(带择时)' if '涨跌幅_(带择时)' in years.columns else '涨跌幅'
    # 有数据的地方开始计算
    years['累计涨跌'] = years[years_col].apply(lambda x: float(x.replace('%', '')))
    years['累计涨跌'] = years['累计涨跌'].cumsum()
    # 防止策略每年正常有收益数据，但累计涨跌加总恰好为0
    years['_累计涨跌'] = years['累计涨跌'].abs().cumsum()
    years = years[years['_累计涨跌'] != 0]
    years.drop(columns=['_累计涨跌'], inplace=True)
    # 删除累计涨跌数据

    year_range = str(years.index.min().year) + '_' + str(years.index.max().year)
    year_rtn_info = list_to_str(years[years_col].to_list())
    res_df.loc[0, '年份区间'] = year_range
    res_df.loc[0, '历年收益'] = year_rtn_info

    # 保存文件
    if os.path.exists(save_path):
        res_df.to_csv(save_path, encoding='gbk', index=False, header=False, mode='a')
    else:
        res_df.to_csv(save_path, encoding='gbk', index=False)

    return


def get_data_path(data_folder, data_name, file_name=''):
    """
    获取数据路径
    :param data_folder: 数据存放的文件夹
    :param data_name: 数据名称
    :param file_name: 具体的文件名
    :return:
    """
    data_exists = False
    if file_name != '':
        # 常规指数默认全部走stock-main-index-data
        if data_name == 'index':
            data_name = 'stock-main-index-data'
        if data_name == '':
            data_name = file_name
            data_path = os.path.join(data_folder, file_name)
        else:
            data_path = os.path.join(data_folder, data_name, file_name)
        if not os.path.exists(data_path):
            if data_name == 'stock-main-index-data':  # 指数还有可能在index里面
                data_path = data_path.replace('stock-main-index-data', 'index')
            data_exists = True if os.path.exists(data_path) else False
        else:
            data_exists = True
    else:
        data_path = os.path.join(data_folder, data_name)
        if os.path.exists(data_path):
            data_exists = True
    if data_exists:
        # 如果是period_offset数据，需要提醒一下数据太旧了
        if file_name == 'period_offset.csv':
            df = pd.read_csv(data_path, encoding='gbk', skiprows=1, parse_dates=['交易日期'])
            date_max = df['交易日期'].max()
            today = pd.to_datetime(datetime.datetime.today())
            span = (date_max - today).days
            if span < 40:
                Rb.record_log('period_offset数据即将更新，请及时关注：https://www.quantclass.cn/data/stock/stock-period-offset')
            if span < 0:
                Rb.record_log('period_offset数据已经更新，请前往下载：https://www.quantclass.cn/data/stock/stock-period-offset')
                exit()
        return data_path
    else:
        url_name = data_name.replace('.csv', '') if data_name != 'period_offset.csv' else 'stock-period-offset'
        Rb.record_log(f'{data_name}数据不存在，未找到数据路径：{data_path}\n'
                      f'请前往:https://www.quantclass.cn/data/stock/{url_name}下载\n'
                      f'下载完成后，请参考此链接处理：https://bbs.quantclass.cn/thread/39599\n'
                      f'程序已退出！！！')
        raise Exception('文件不存在')


def get_equity_list(param, cfg, equity_path):
    # 截取匹配的数据
    math_txt = '_' + param if param[0] != '_' else param
    # 带@的参数表示任意选股数量都可以
    if '@' in math_txt.split('_')[3]:
        math_txt = math_txt[:math_txt.find('@')]
    equity_list = get_file_in_folder(equity_path, '.csv', math_txt)
    # 找到目前还在的策略文件
    sub_stg_path = os.path.join(cfg.select_program_path, 'program/选股策略')
    sub_stg_list = get_file_in_folder(sub_stg_path, '.py', filters=['__init__.py'], drop_type=True)
    # 只保留有策略文件的资金曲线
    equity_list = [e for e in equity_list if e.split(math_txt)[0] in sub_stg_list]
    if len(equity_list) == 0:
        Rb.record_log(f'未找到匹配的选股策略文件，请检查参数是否正确：{math_txt}')
        raise Exception(f'未找到匹配的选股策略文件，请检查参数是否正确：{math_txt}')
    # 把指数也加到列表中
    str_list = param.split('_')
    per_oft = str_list[0] + '_' + str_list[1] if param[0] != '_' else str_list[1] + '_' + str_list[2]
    index_list = [cfg.inx_dict[key][0] + '_' + per_oft + '.csv' for key in cfg.inx_dict.keys()]
    equity_list += index_list
    return equity_list


def import_index_data(path, trading_mode=False, date_start=None, date_end=None):
    """
    从指定位置读入指数数据。

    :param trading_mode: 交易模式，如果是实盘模式，回测数据从date_start开始
    :param date_start: 回测开始时间
    :param date_end: 回测结束时间
    :param path:
    :return:
    """
    # 导入指数数据
    df_index = pd.read_csv(path, parse_dates=['candle_end_time'], encoding='gbk')
    df_index['指数涨跌幅'] = df_index['close'].pct_change()  # 计算涨跌幅
    df_index = df_index[['candle_end_time', '指数涨跌幅']]
    df_index.dropna(subset=['指数涨跌幅'], inplace=True)
    df_index.rename(columns={'candle_end_time': '交易日期'}, inplace=True)

    Rb.record_log(f'从指数获取最新交易日：{df_index["交易日期"].iloc[-1].strftime("%Y-%m-%d")}，交易模式：{trading_mode}')
    # 保留需要的时间段的数据
    if trading_mode:
        if date_start:
            df_index = df_index[df_index['交易日期'] >= pd.to_datetime(date_start)]
            Rb.record_log(f'回测开始时间：{df_index["交易日期"].iloc[0].strftime("%Y-%m-%d")}')
    if date_end:
        df_index = df_index[df_index['交易日期'] <= pd.to_datetime(date_end)]
        Rb.record_log(f'回测结束时间：{df_index["交易日期"].iloc[-1].strftime("%Y-%m-%d")}')
    # 按时间排序和去除索引
    df_index.sort_values(by=['交易日期'], inplace=True)
    df_index.reset_index(inplace=True, drop=True)

    return df_index


def get_stock_data(data, cfg, per_oft, is_open):
    # 先拿到所有策略的列表
    slt_stg_list = list(data['策略名称'].unique())
    # 读取待分析里面的结果
    ana_path = os.path.join(cfg.select_program_path, 'data/分析目录/待分析')
    ana_df_list = []
    for slt_stg in slt_stg_list:
        temp = pd.read_pickle(os.path.join(ana_path, slt_stg + '.pkl'))
        temp['策略名称'] = slt_stg
        ana_df_list.append(temp)

    ana_df = pd.concat(ana_df_list, ignore_index=True)

    # 合并数据
    temp = pd.merge(ana_df, data[['交易日期', '策略名称', '策略排名']], on=['交易日期', '策略名称'], how='left', indicator=True)

    # 只保留被策略选中的数据
    temp = temp[temp['_merge'] == 'both']

    return temp


def _cal_stock_weight_of_each_period(group, date_df):
    """
    计算每个个股每个周期的权重
    :param group:
    :param date_df:
    :return:
    """
    # 将个股数据与周期数据合并
    group = pd.merge(date_df, group, 'left', '交易日期')
    # 填充空数据
    group['股票代码'].fillna(value=group[group['股票代码'].notnull()]['股票代码'].iloc[0], inplace=True)
    group['占比'].fillna(value=0, inplace=True)

    # 获取上周期占比和下周期占比
    group['上周期占比'] = group['占比'].shift(1).fillna(value=0)
    group['下周期占比'] = group['占比'].shift(-1).fillna(value=0)

    # 计算开仓比例
    group['开仓比例'] = group['占比'] - group['上周期占比']
    group['开仓比例'] = group['开仓比例'].apply(lambda x: x if x > 0 else 0)

    # 计算平仓比例
    group['平仓比例'] = group['占比'] - group['下周期占比']
    group['平仓比例'] = group['平仓比例'].apply(lambda x: x if x > 0 else 0)

    return group


def _cal_next_period_pct_change(row, cfg):
    """
    计算下个周期扣除手续费后的涨跌幅
    :param row:
    :param cfg:
    :return:
    """
    # 扣除买入手续费
    row['选股下周期每天资金曲线'] = row['选股下周期每天资金曲线'] * (1 - cfg.c_rate * row['开仓比例'])  # 计算有不精准的地方
    # 扣除卖出手续费
    row['选股下周期每天资金曲线'] = list(row['选股下周期每天资金曲线'][:-1]) + [
        row['选股下周期每天资金曲线'][-1] * (1 - row['平仓比例'] * (cfg.c_rate + cfg.t_rate))]

    return row['选股下周期每天资金曲线']


def cal_fee_rate(df, cfg):
    """
    计算手续费，
    :param df:
    :param cfg:
    :return:
    """
    # 找到择时空仓的地方，删除相同的列，将股票代码替换为empty，并且将涨跌幅设置为0
    df.loc[df['signal'] != 1, '股票代码'] = 'empty'
    df.loc[df['signal'] != 1, '股票名称'] = 'empty'

    # 有必要的话，需要替换第一行的涨跌幅
    if cfg.buy_method != '收盘':
        df[f'下日_{cfg.buy_method}买入涨跌幅'] = df[f'下日_{cfg.buy_method}买入涨跌幅'].apply(lambda x: [x])
        df['下周期每天涨跌幅'] = df['下周期每天涨跌幅'].apply(lambda x: x[1:])
        df['下周期每天涨跌幅'] = df[f'下日_{cfg.buy_method}买入涨跌幅'] + df['下周期每天涨跌幅']

    if cfg.buy_method == '均价' and cfg.intraday_swap == False:
        df['下周期_当日_均价卖出涨跌幅'] = df['下周期_当日_均价卖出涨跌幅'].apply(lambda x: [x])
        df['下周期每天涨跌幅'] = df['下周期每天涨跌幅'].apply(lambda x: x[:-1])
        df['下周期每天涨跌幅'] = df['下周期每天涨跌幅'] + df['下周期_当日_均价卖出涨跌幅']
    if cfg.buy_method in ['开盘价', '均价', '09:35收盘价', '09:45收盘价', '09:55收盘价'] and cfg.intraday_swap == True:
        df[f'下周期_下日_{cfg.buy_method}卖出涨跌幅'] = df[f'下周期_下日_{cfg.buy_method}卖出涨跌幅'].apply(lambda x: [x])
        df['下周期每天涨跌幅'] = df['下周期每天涨跌幅'].apply(lambda x: x[:-1])
        df['下周期每天涨跌幅'] = df['下周期每天涨跌幅'] + df[f'下周期_下日_{cfg.buy_method}卖出涨跌幅']

    df.loc[df['signal'] != 1, '下周期每天涨跌幅'] = df['下周期每天涨跌幅'].apply(lambda x: [0.0] * len(x))

    # ===挑选出选中股票
    df['股票代码'] += ' '
    df['股票名称'] += ' '
    group = df.groupby('交易日期')
    select_stock = pd.DataFrame()
    # ===统计一些数据用于后续计算
    select_stock['股票数量'] = group['股票名称'].size()
    select_stock['买入股票代码'] = group['股票代码'].sum()
    select_stock['买入股票名称'] = group['股票名称'].sum()

    # =====计算资金曲线
    # 计算下周期每天的资金曲线
    select_stock['选股下周期每天资金曲线'] = group['下周期每天涨跌幅'].apply(
        lambda x: np.cumprod(np.array(list(x)) + 1, axis=1).mean(axis=0))

    # 非收盘模式的换仓，会在上一个交易日全部卖掉，本交易日全部买回，相对简单
    if cfg.intraday_swap == False:
        # 扣除买入手续费
        select_stock['选股下周期每天资金曲线'] = select_stock['选股下周期每天资金曲线'] * (1 - cfg.c_rate)  # 计算有不精准的地方
        # 扣除卖出手续费、印花税。最后一天的资金曲线值，扣除印花税、手续费
        select_stock['选股下周期每天资金曲线'] = select_stock['选股下周期每天资金曲线'].apply(
            lambda x: list(x[:-1]) + [x[-1] * (1 - cfg.c_rate - cfg.t_rate)])

    # 收盘模式换仓，对比要卖出和要买入的股票相同的部分，针对相同的部分进行买卖交易
    else:
        # 针对计算各个股票的占比
        stocks = df[['交易日期', '策略名称', '股票代码']].sort_values(['交易日期', '策略名称', '股票代码']).reset_index(drop=True)

        # 计算当前策略在当周期的占比
        stocks['策略数量'] = stocks.groupby('交易日期')['策略名称'].transform(lambda x: len(x.drop_duplicates()))
        # 找到每个策略的选股数量占比
        stocks['股票数量'] = stocks.groupby(['交易日期', '策略名称'])['股票代码'].transform('count')
        # 计算具体到每个股票的占比
        stocks['占比'] = 1 / stocks['策略数量'] / stocks['股票数量']

        # 计算日期序列
        date_df = pd.DataFrame(stocks['交易日期'].unique(), columns=['交易日期'])

        # 计算每个个股每个周期的权重
        stocks = stocks.groupby('股票代码').apply(lambda g: _cal_stock_weight_of_each_period(g, date_df))
        stocks.reset_index(inplace=True, drop=True)
        # 如果是empty，开平仓比例都是0
        stocks.loc[stocks['股票代码'] == 'empty', '开仓比例'] = 0
        stocks.loc[stocks['股票代码'] == 'empty', '平仓比例'] = 0

        # 计算当前周期的开仓比例和平仓比例
        select_stock['开仓比例'] = stocks.groupby('交易日期')['开仓比例'].sum()
        select_stock['平仓比例'] = stocks.groupby('交易日期')['平仓比例'].sum()

        # 记录平均的开平仓比例
        Rb.record_log(f'平均开平仓比例：{round(select_stock["开仓比例"].mean(), 3)}')
        # 扣除交易的手续费
        select_stock['选股下周期每天资金曲线'] = select_stock.apply(lambda row: _cal_next_period_pct_change(row, cfg), axis=1)

    return select_stock


def create_empty_data(index_data, period_offset, po_df):
    """
    按照格式和需要的字段创建一个空的dataframe，用于填充不选股的周期

    :param index_data: 指数数据
    :param period_offset: 给定offset周期
    :param po_df: 包含全部offset的dataframe
    """
    empty_df = index_data[['交易日期']].copy()
    empty_df['涨跌幅'] = 0.0
    empty_df['周期最后交易日'] = empty_df['交易日期']
    agg_dict = {'周期最后交易日': 'last'}
    po_df['group'] = po_df[f'{period_offset}'].abs().copy()
    group = po_df[['交易日期', 'group']].copy()
    empty_df = pd.merge(left=empty_df, right=group, on='交易日期', how='left')
    empty_period_df = empty_df.groupby('group').agg(agg_dict)
    empty_period_df['每天涨跌幅'] = empty_df.groupby('group')['涨跌幅'].apply(lambda x: list(x))
    # 删除没交易的日期
    empty_period_df.dropna(subset=['周期最后交易日'], inplace=True)

    empty_period_df['选股下周期每天涨跌幅'] = empty_period_df['每天涨跌幅'].shift(-1)
    empty_period_df.dropna(subset=['选股下周期每天涨跌幅'], inplace=True)

    # 填仓其他列
    empty_period_df['股票数量'] = 0
    empty_period_df['买入股票代码'] = 'empty'
    empty_period_df['买入股票名称'] = 'empty'
    empty_period_df['选股下周期涨跌幅'] = 0.0
    empty_period_df.rename(columns={'周期最后交易日': '交易日期'}, inplace=True)

    empty_period_df.set_index('交易日期', inplace=True)

    empty_period_df = empty_period_df[
        ['股票数量', '买入股票代码', '买入股票名称', '选股下周期涨跌幅', '选股下周期每天涨跌幅']]
    return empty_period_df


def get_sub_stg_name(x):
    """
    获取子策略名称
    :param x:
    :return:
    """

    # 指数和策略传入的格式是不太一样的
    # 指数：上证50指数_W_0
    # 策略：策略名称_W_0_30

    # 处理指数
    if len(x.split('_')) == 3:
        p_list = x.split('_')[-2:]
        po = '_' + p_list[0] + '_' + p_list[1]
    else:  # 处理策略
        p_list = x.split('_')[-3:]
        po = '_' + p_list[0] + '_' + p_list[1] + '_' + p_list[2]
    res = x.split(po)[0]
    return res


def get_date_max(data, per_oft_df):
    # 获取最大的交易日期
    date_max = data['交易日期'].max()
    # 获取该交易日期对应的周期数
    per_count = data[data['交易日期'] == date_max]['下周期每天涨跌幅'].transform(lambda x: len(x)).median()
    # 找到最大日期在日历里的索引
    date_inx = per_oft_df[per_oft_df['交易日期'] == date_max].index.min()
    # 通过索引和周期数找到真正的截止日期
    end_date = per_oft_df.loc[date_inx + per_count, '交易日期']
    # 记录信息
    Rb.record_log(f'{date_max}对应的周期数是{per_count}，最大日期在日历里的索引是{date_inx}，'
                  f'找到真正的截止日期是{end_date}')
    # 返回截止日期
    return end_date
