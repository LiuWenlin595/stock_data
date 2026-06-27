'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import datetime
import numpy as np
import pandas as pd
import scipy
import gc
import math
import warnings

warnings.filterwarnings('ignore')


def float_num_process(num, return_type=float, keep=2, max=5):
    """
    针对绝对值小于1的数字进行特殊处理，保留非0的N位（N默认为2，即keep参数）
    输入  0.231  输出  0.23
    输入  0.0231  输出  0.023
    输入  0.00231  输出  0.0023
    如果前面max个都是0，直接返回0.0
    :param num: 输入的数据
    :param return_type: 返回的数据类型，默认是float
    :param keep: 需要保留的非零位数
    :param max: 最长保留多少位
    :return:
        返回一个float或str
    """

    # 如果输入的数据是0，直接返回0.0
    if num == 0.:
        return 0.0

    # 绝对值大于1的数直接保留对应的位数输出
    if abs(num) > 1:
        return round(num, keep)
    # 获取小数点后面有多少个0
    zero_count = -int(math.log10(abs(num)))
    # 实际需要保留的位数
    keep = min(zero_count + keep, max)

    # 如果指定return_type是float，则返回float类型的数据
    if return_type == float:
        return round(num, keep)
    # 如果指定return_type是str，则返回str类型的数据
    else:
        return str(round(num, keep))


def get_factor_by_period(folder, period_offset, factor_from, keep_cols, func):
    '''
    读取数据的函数
    :param folder: 数据所在的文件夹路径
    :param period_offset: 根据period_offset
    :param factor_from 因子计算目录名
    :param keep_cols: 读取数据后需要保存的列
    :param func: 处理数据的函数
    :return:
        返回读取到的所有数据
    '''

    print('正在读取并整理数据...')
    start_date = datetime.datetime.now()  # 记录开始时间

    base_path = folder + f'/周期数据/{period_offset}/基础数据/基础数据.pkl'
    df = pd.read_pickle(base_path)
    factors = list(set(['风格因子'] + list(factor_from.keys())))
    common_cols = ['股票代码', '交易日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '成交额', '流通市值',
                   '总市值', '沪深300成分股', '上证50成分股', '中证500成分股', '中证1000成分股', '中证2000成分股',
                   '创业板指成分股', '新版申万一级行业名称', '新版申万二级行业名称', '新版申万三级行业名称', '09:35收盘价',
                   '09:45收盘价', '09:55收盘价', '复权因子', '收盘价_复权', '开盘价_复权', '最高价_复权', '最低价_复权']

    for fa in factors:
        factors_path = folder + f'/周期数据/{period_offset}/{fa}/{fa}.pkl'
        fa_df = pd.read_pickle(factors_path)
        # 只保留需要的列
        if fa != '风格因子':
            if len(factor_from[fa]) > 0:
                fa_df = fa_df[['交易日期', '股票代码'] + factor_from[fa]]

        # 对比一下前后列名是否有重复的
        repeat_cols = list(set(df.columns).intersection(set(fa_df.columns)))
        # 要排除掉交易日期和股票代码两列
        repeat_cols = [col for col in repeat_cols if col not in ['股票代码', '交易日期']]
        if len(repeat_cols) > 0:
            for col in repeat_cols:
                if col in common_cols:  # 如果是公共列，则删除
                    fa_df.drop(columns=[col], inplace=True)
                else:
                    print(f'{fa}文件中的{col}列与已经加载的数据重名，程序已经自动退出，请检查因子重名的情况后重新运行')
                    raise Exception(
                        f'{fa}文件中的{col}列与已经加载的数据重名，程序已经自动退出，请检查因子重名的情况后重新运行')
        df = pd.merge(df, fa_df, on=['交易日期', '股票代码'], how='left')

    # 将总市值一列单独复制一份用于分析
    df['总市值_因子分析'] = df['总市值']
    if '总市值_因子分析' not in keep_cols:
        # 感谢KG老板反馈BUG：https://bbs.quantclass.cn/thread/39772
        keep_cols.append('总市值_因子分析')
    df = data_processing(df, func)

    # 删除必要字段为空的部分
    df = df.dropna(subset=keep_cols, how='any')
    # 筛选出风格因子列
    style_cols = [col for col in df.columns if '风格因子_' in col]
    # 取出部分列数据
    df = df[keep_cols + style_cols]
    gc.collect()  # 内存回收
    # 加入offset列
    df['offset'] = period_offset.split('_')[-1]

    print(f'读取并整理数据完成，耗时：{datetime.datetime.now() - start_date}')

    return df


def offset_grouping(df, factor, bins):
    '''
    分组函数
    :param df: 原数据
    :param factor: 因子名
    :param bins: 分组的数量
    :return:
        返回一个df数据，包含groups列
    '''

    # 根据factor计算因子的排名
    df['因子_排名'] = df.groupby(['交易日期'])[factor].rank(ascending=True, method='first')
    # 根据因子的排名进行分组
    df['groups'] = df.groupby(['交易日期'])['因子_排名'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))

    # 这里不需要判断某个周期的股票数量大于bins，因为之前在处理limit时已经处理过这个问题

    return df


def get_IC(df, factor, target, offset):
    '''
    计算IC等一系列指标
    :param df: 数据
    :param factor: 因子列名：测试的因子名称
    :param target: 目标列名：计算IC时的下周期数据
    :param offset: 当前执行的是哪个offset的数据
    :return:
        返回计算得到的IC数据
    '''

    print('正在进行因子IC分析...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 计算IC并处理数据
    IC = df.groupby('交易日期').apply(lambda x: x[factor].corr(x[target], method='spearman')).to_frame()
    IC = IC.rename(columns={0: 'RankIC'}).reset_index()

    # 记录offset
    IC['offset'] = offset

    print(f'因子IC分析完成，耗时：{datetime.datetime.now() - start_date}')

    return IC


def get_group_nv(df, next_ret, b_rate, s_rate, offset):
    """
    针对分组数据进行分析，给出分组的资金曲线、分箱图以及各分组的未来资金曲线
    :param df: 输入的数据
    :param next_ret: 未来涨跌幅的list
    :param b_rate: 买入手续费率
    :param s_rate: 卖出手续费率
    :param offset: 当前执行的是哪个offset的数据
    :return:
        返回分组资金曲线、分组持仓走势数据
    """

    print('正在进行因子分组分析...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 由于会对原始的数据进行修正，所以需要把数据copy一份
    temp = df.copy()

    # 将持仓周期的众数当做标准的持仓周期数
    temp['持仓周期'] = temp[next_ret].map(len)
    hold_nums = int(temp['持仓周期'].mode())
    temp[next_ret] = temp[next_ret].map(
        lambda x: x[: hold_nums] if len(x) > hold_nums else (x + [0] * (hold_nums - len(x))))

    # 计算下周期每天的净值，并扣除手续费得到下周期的实际净值
    temp['下周期每天净值'] = temp[next_ret].apply(lambda x: (np.array(x) + 1).cumprod())
    free_rate = (1 - b_rate) * (1 - s_rate)
    temp['下周期净值'] = temp['下周期每天净值'].apply(lambda x: x[-1] * free_rate)

    # 计算得到每组的资金曲线
    group_nv = temp.groupby(['交易日期', 'groups'])['下周期净值'].mean().reset_index()
    group_nv = group_nv.sort_values(by='交易日期').reset_index(drop=True)

    # 将每个周期的净值-1，得到每个周期的涨跌幅
    group_nv['下周期涨跌幅'] = group_nv['下周期净值'] - 1

    # 计算每个分组的累计净值
    group_nv['净值'] = group_nv.groupby('groups')['下周期净值'].cumprod()
    group_nv.drop('下周期净值', axis=1, inplace=True)

    # 计算当前数据有多少个分组
    bins = group_nv['groups'].max()

    # 计算各分组在持仓内的每天收益
    group_hold_value = pd.DataFrame(temp.groupby('groups')['下周期每天净值'].mean()).T
    # 所有分组的第一天都是从1开始的
    for col in group_hold_value.columns:
        group_hold_value[col] = group_hold_value[col].apply(lambda x: [1] + list(x))
    # 将未来收益从list展开成逐行的数据
    group_hold_value = group_hold_value.explode(list(group_hold_value.columns)).reset_index(drop=True).reset_index()
    # 重命名列
    group_cols = ['时间'] + [f'第{i}组' for i in range(1, bins + 1)]
    group_hold_value.columns = group_cols
    group_hold_value['offset'] = offset

    print(f'因子分组分析完成，耗时：{datetime.datetime.now() - start_date}')

    # 返回数据：分组资金曲线、分组持仓走势
    return group_nv, group_hold_value


def get_style_corr(df, factor, offset):
    '''
    计算因子的风格暴露
    :param df: df数据，包含因子列和风格列
    :param factor: 因子列
    :param offset: 当前执行的是哪个offset的数据
    :return:
        返回因子的风格暴露的数据
    '''

    print('正在进行因子风格暴露分析...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 取出风格列，格式：以 风格因子_ 开头
    style_cols = [col for col in df.columns if '风格因子_' in col]

    # 如果df中没有风格因子列，返回空df
    if len(style_cols) == 0:
        return pd.DataFrame()

    # 计算因子与风格的相关系数
    # style_corr = df[[factor] + style_cols].corr(method='spearman').iloc[0, 1:].to_frame().reset_index()

    res = df.groupby('交易日期').apply(lambda x: x[[factor] + style_cols].corr(method='spearman').iloc[0, 1:].to_frame())
    style_corr = res.reset_index().groupby('level_1')[factor].mean().reset_index()
    # 整理数据
    style_corr = style_corr.rename(columns={'level_1': '风格', factor: '相关系数'})
    style_corr['风格'] = style_corr['风格'].map(lambda x: x.split('_')[1])
    style_corr['offset'] = offset

    print(f'因子风格分析完成，耗时：{datetime.datetime.now() - start_date}')

    return style_corr


def get_industry_data(df, factor, target, industry_col, industry_name_change):
    '''
    计算分行业的IC
    :param df: 原始数据
    :param factor: 因子列
    :param target: 目标列
    :param industry_col: 配置的行业列名
    :param industry_name_change: 行业名称前后改变
    :return:
        返回各个行业的RankIC数据、占比数据
    '''

    print('正在进行因子行业分析...')
    start_date = datetime.datetime.now()  # 记录开始时间

    def get_data(temp):
        '''
        计算分行业IC、占比
        :param temp: 每个行业的数据
        :return:
            返回IC序列的均值、第一组占比、最后一组占比
        '''
        # 计算每个行业的IC序列
        ic = temp.groupby('交易日期').apply(lambda x: x[factor].corr(x[target], method='spearman'))
        # 整理IC数据
        ic = ic.to_frame().reset_index().rename(columns={0: 'RankIC'})

        # 计算每个行业的第一组的占比和最后一组的占比
        part_min_group = temp.groupby('交易日期').apply(lambda x: (x['groups'] == min_group).sum())
        part_max_group = temp.groupby('交易日期').apply(lambda x: (x['groups'] == max_group).sum())
        part_min_group = part_min_group / all_min_group
        part_max_group = part_max_group / all_max_group
        # 整理占比数据
        part_min_group = part_min_group.to_frame().reset_index().rename(columns={0: '因子第一组选股在各行业的占比'})
        part_max_group = part_max_group.to_frame().reset_index().rename(columns={0: '因子最后一组选股在各行业的占比'})

        # 将各个数据合并一下
        data = pd.merge(ic, part_min_group, on='交易日期', how='inner')
        data = pd.merge(data, part_max_group, on='交易日期', how='inner')
        data.set_index('交易日期', inplace=True)  # 设置下索引

        return data

    # 替换行业名称
    df[industry_col] = df[industry_col].replace(industry_name_change)
    # 获取以因子分组第一组和最后一组的数量
    min_group, max_group = df['groups'].min(), df['groups'].max()
    all_min_group = df.groupby('交易日期').apply(lambda x: (x['groups'] == min_group).sum())
    all_max_group = df.groupby('交易日期').apply(lambda x: (x['groups'] == max_group).sum())
    # 以行业分组计算IC及占比，并处理数据
    industry_data = df.groupby(industry_col).apply(get_data).reset_index()

    print(f'因子行业分析完成，耗时：{datetime.datetime.now() - start_date}')

    return industry_data


def get_market_value_data(df, factor, target, bins=10):
    '''
    计算分市值的IC数据
    :param df: 原数据
    :param factor: 因子名
    :param target: 目标名
    :param bins: 分组的数量
    :return:
        返回各个市值分组的IC、占比数据
    '''

    print('正在进行因子市值分析...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 先对市值数据进行排名以及分组
    df['市值_排名'] = df.groupby(['交易日期'])['总市值_因子分析'].rank(ascending=True, method='first')
    df['市值分组'] = df.groupby(['交易日期'])['市值_排名'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))

    def get_data(temp):
        '''
        计算分市值IC、占比
        :param temp: 每个市值分组的数据
        :return:
            返回IC序列的均值、第一组占比、最后一组占比
        '''
        # 计算每个市值分组的IC值
        ic = temp.groupby('交易日期').apply(lambda x: x[factor].corr(x[target], method='spearman'))
        # 整理数据
        ic = ic.to_frame().reset_index().rename(columns={0: 'RankIC'})
        # 计算每个市值分组的第一组的占比和最后一组的占比
        part_min_group = temp.groupby('交易日期').apply(lambda x: (x['groups'] == min_group).sum())
        part_max_group = temp.groupby('交易日期').apply(lambda x: (x['groups'] == max_group).sum())
        part_min_group = part_min_group / all_min_group
        part_max_group = part_max_group / all_max_group
        # 整理数据
        part_min_group = part_min_group.to_frame().reset_index().rename(columns={0: '因子第一组选股在各市值分组的占比'})
        part_max_group = part_max_group.to_frame().reset_index().rename(
            columns={0: '因子最后一组选股在各市值分组的占比'})

        # 合并数据
        data = pd.merge(ic, part_min_group, on='交易日期', how='inner')
        data = pd.merge(data, part_max_group, on='交易日期', how='inner')
        data.set_index('交易日期', inplace=True)  # 设置索引

        return data

    # 获取以因子分组第一组和最后一组的数量
    min_group, max_group = df['groups'].min(), df['groups'].max()
    all_min_group = df.groupby('交易日期').apply(lambda x: (x['groups'] == min_group).sum())
    all_max_group = df.groupby('交易日期').apply(lambda x: (x['groups'] == max_group).sum())
    # 根据市值分组计算IC及占比，并处理数据
    market_value_data = df.groupby('市值分组').apply(get_data).reset_index()

    print(f'因子市值分析完成，耗时：{datetime.datetime.now() - start_date}')

    return market_value_data


def IC_analysis(IC_list):
    '''
    整合各个offset的IC数据并计算相关的IC指标
    :param IC_list: 各个offset的IC数据
    :return:
        返回IC数据、IC字符串
    '''

    # 将各个offset的数据合并 并 整理
    IC = pd.concat(IC_list, axis=0)
    IC = IC.sort_values('交易日期').reset_index(drop=True)

    # 计算累计RankIC；注意：因为我们考虑了每个offset，所以这边为了使得各个不同period之间的IC累计值能够比较，故除以offset的数量
    IC['累计RankIC'] = IC['RankIC'].cumsum() / (len(IC['offset'].unique()))

    # ===计算IC的统计值，并进行约等
    # =IC均值
    IC_mean = float_num_process(IC['RankIC'].mean())
    # =IC标准差
    IC_std = float_num_process(IC['RankIC'].std())
    # =ICIR
    ICIR = float_num_process(IC_mean / IC_std)
    # =IC胜率
    # 如果累计IC为正，则计算IC为正的比例
    if IC['累计RankIC'].iloc[-1] > 0:
        IC_ratio = str(float_num_process((IC['RankIC'] > 0).sum() / len(IC) * 100)) + '%'
    # 如果累计IC为负，则计算IC为负的比例
    else:
        IC_ratio = str(float_num_process((IC['RankIC'] < 0).sum() / len(IC) * 100)) + '%'

    # 将上述指标合成一个字符串，加入到IC图中
    IC_info = f'IC均值：{IC_mean}，IC标准差：{IC_std}，ICIR：{ICIR}，IC胜率：{IC_ratio}'

    return IC, IC_info


def get_IC_month(IC):
    '''
    生成IC月历
    :param IC: IC数据
    :return:
        返回IC月历的df数据
    '''

    # resample到月份数据
    IC['交易日期'] = pd.to_datetime(IC['交易日期'])
    IC.set_index('交易日期', inplace=True)
    IC_month = IC.resample('M').agg({'RankIC': 'mean'})
    IC_month.reset_index(inplace=True)
    # 提取出年份和月份
    IC_month['年份'] = IC_month['交易日期'].dt.year.astype('str')
    IC_month['月份'] = IC_month['交易日期'].dt.month
    # 将年份月份设置为index，在将月份unstack为列
    IC_month = IC_month.set_index(['年份', '月份'])['RankIC']
    IC_month = IC_month.unstack('月份')
    IC_month.columns = IC_month.columns.astype(str)
    # 计算各月平均的IC
    IC_month.loc['各月平均', :] = IC_month.mean(axis=0)
    # 按年份大小排名
    IC_month = IC_month.sort_index(ascending=False)

    return IC_month


def group_analysis(group_nv_list, group_hold_value_list):
    '''
    针对分组数据进行分析，给出分组的资金曲线、分箱图以及各分组的未来资金曲线
    :param group_nv_list: 各个offset的分组净值数据
    :param group_hold_value_list: 各个offset的分组持仓走势数据
    :return:
        返回分组资金曲线、分箱图、分组持仓走势数据
    '''

    # 生成时间轴
    dates = []
    for group_nv in group_nv_list:
        dates.extend(list(set(group_nv['交易日期'].to_list())))
    time_df = pd.DataFrame(sorted(dates), columns=['交易日期'])

    # 遍历各个offset的资金曲线数据，合并到时间轴上，将合并后的数据append到列表中
    nv_list = []
    for group_nv in group_nv_list:
        group_nv = group_nv.groupby('groups').apply(
            lambda x: pd.merge(time_df, x, 'left', '交易日期').fillna(method='ffill'))
        group_nv.reset_index(drop=True, inplace=True)
        nv_list.append(group_nv)

    # 将所有offset的分组资金曲线数据合并
    nv_df = pd.concat(nv_list, ignore_index=True)
    # 计算当前数据有多少个分组
    bins = nv_df['groups'].max()
    # 计算不同offset的每个分组的平均净值
    group_curve = nv_df.groupby(['交易日期', 'groups'])['净值'].mean().reset_index()
    # 将数据按照展开
    group_curve = group_curve.set_index(['交易日期', 'groups']).unstack().reset_index()
    # 重命名数据列
    group_cols = ['交易日期'] + [f'第{i}组' for i in range(1, bins + 1)]
    group_curve.columns = group_cols

    # 计算多空净值走势
    # 获取第一组的涨跌幅数据
    first_group_ret = group_curve['第1组'].pct_change()
    first_group_ret.fillna(value=group_curve['第1组'].iloc[0] - 1, inplace=True)
    # 获取最后一组的涨跌幅数据
    last_group_ret = group_curve[f'第{bins}组'].pct_change()
    last_group_ret.fillna(value=group_curve[f'第{bins}组'].iloc[0] - 1, inplace=True)
    # 判断到底是多第一组空最后一组，还是多最后一组空第一组
    if group_curve['第1组'].iloc[-1] > group_curve[f'第{bins}组'].iloc[-1]:
        ls_ret = (first_group_ret - last_group_ret) / 2
    else:
        ls_ret = (last_group_ret - first_group_ret) / 2
    # 计算多空净值曲线
    group_curve['多空净值'] = (ls_ret + 1).cumprod()
    # 计算绘制分箱所需要的数据
    group_value = group_curve[-1:].T[1:].reset_index()
    group_value.columns = ['分组', '净值']

    # 合并各个offset的持仓走势数据
    all_group_hold_value = pd.concat(group_hold_value_list, axis=0)
    # 取出需要求各个offset平均的列
    mean_cols = [col for col in all_group_hold_value.columns if '第' in col]
    # 新建空df
    group_hold_value = pd.DataFrame()
    # 设定时间列
    group_hold_value['时间'] = all_group_hold_value['时间'].unique()
    # 求各个组的mean
    for col in mean_cols:
        group_hold_value[col] = all_group_hold_value.groupby('时间')[col].mean()

    return group_curve, group_value, group_hold_value


def style_analysis(style_corr_list):
    '''
    计算因子的风格暴露
    :param style_corr_list: 各个offset的风格暴露数据
    :return:
       返回因子的风格暴露的数据
    '''

    # 合并各个offset的风格暴露数据
    style_corr = pd.concat(style_corr_list, axis=0)
    # 对各offset求平均
    style_corr = style_corr.groupby('风格')['相关系数'].mean().to_frame().reset_index()

    return style_corr


def industry_analysis(industry_data_list, industry_col):
    '''
    计算各个offset行业分析数据的平均值
    :param industry_data_list: 各个offset的行业分析数据
    :param industry_data_list: 行业列名
    :return:
        返回各个行业的RankIC数据、占比数据
    '''

    # 合并各个offset的数据 并 整理
    all_industry_data = pd.concat(industry_data_list, axis=0)
    all_industry_data = all_industry_data.sort_values(['交易日期', industry_col]).reset_index(drop=True)

    # 对每个行业求IC均值、行业占比第一组均值、行业占比最后一组均值
    industry_data = all_industry_data.groupby(industry_col).apply(
        lambda x: [x['RankIC'].mean(), x['因子第一组选股在各行业的占比'].mean(),
                   x['因子最后一组选股在各行业的占比'].mean()])
    industry_data = industry_data.to_frame().reset_index()  # 整理数据
    # 取出IC数据、行业占比_第一组数据、行业占比_最后一组数据
    industry_data['RankIC'] = industry_data[0].map(lambda x: x[0])
    industry_data['因子第一组选股在各行业的占比'] = industry_data[0].map(lambda x: x[1])
    industry_data['因子最后一组选股在各行业的占比'] = industry_data[0].map(lambda x: x[2])
    # 处理数据
    industry_data.drop(0, axis=1, inplace=True)
    # 以IC排序
    industry_data.sort_values('RankIC', ascending=False, inplace=True)

    return industry_data


def market_value_analysis(market_value_list):
    '''
    计算各个offset市值分析数据的平均值
    :param market_value_list: 各个offset的市值分析数据
    :return:
        返回各个市值分组的RankIC数据、占比数据
    '''

    # 合并各个offset的数据 并 整理
    all_market_value_data = pd.concat(market_value_list, axis=0)
    all_market_value_data = all_market_value_data.sort_values(['交易日期', '市值分组']).reset_index(drop=True)

    # 对每个市值分组求IC均值、市值占比第一组均值、数字hi占比最后一组均值
    market_value_data = all_market_value_data.groupby('市值分组').apply(
        lambda x: [x['RankIC'].mean(), x['因子第一组选股在各市值分组的占比'].mean(),
                   x['因子最后一组选股在各市值分组的占比'].mean()])
    market_value_data = market_value_data.to_frame().reset_index()  # 整理数据
    # 取出IC数据、市值占比_第一组数据、市值占比_最后一组数据
    market_value_data['RankIC'] = market_value_data[0].map(lambda x: x[0])
    market_value_data['因子第一组选股在各市值分组的占比'] = market_value_data[0].map(lambda x: x[1])
    market_value_data['因子最后一组选股在各市值分组的占比'] = market_value_data[0].map(lambda x: x[2])
    # 处理数据
    market_value_data.drop(0, axis=1, inplace=True)
    # 以市值分组大小排序
    market_value_data.sort_index(ascending=True, inplace=True)

    return market_value_data


def auto_offset(period):
    res = [0]
    # 判断指定的period是否为int类型
    if isinstance(period, int):
        # 如果是int类型，则有int个offset
        res = list(range(0, period))
    # 判断指定的period是否为str类型
    elif isinstance(period, str):
        # 判断period中是否包含W
        if ('W' in period.upper()):
            # 如果period只有W，即 period == 'W'
            if len(period) == 1:
                res = [0, 1, 2, 3, 4]
            # 如果period为N个W，比如 period == '2W'，则有两个offset
            else:
                res = list(range(0, int(period[:-1])))
        # 判断period中是否包含M
        elif 'M' in period.upper():
            # 如果period == 'M'
            if len(period) == 1:
                res = [0]
            # 如果period 为 N个M，比如 period == '2M'，则有两个offset
            else:
                res = list(range(0, int(period[:-1])))

    return res


def filter_stock(df):
    """
    过滤函数，ST/退市/交易天数不足等情况
    :param df:
    :return:
    """
    # =删除不能交易的周期数
    # 删除月末为st状态的周期数
    df = df[df['股票名称'].str.contains('ST') == False]
    # 删除月末为s状态的周期数
    df = df[df['股票名称'].str.contains('S') == False]
    # 删除月末有退市风险的周期数
    df = df[df['股票名称'].str.contains('\*') == False]
    df = df[df['股票名称'].str.contains('退') == False]
    # 删除交易天数过少的周期数
    df = df[df['交易天数'] / df['市场交易天数'] >= 0.8]

    df = df[df['下日_是否交易'] == 1]
    df = df[df['下日_开盘涨停'] == False]
    df = df[df['下日_是否ST'] == False]
    df = df[df['下日_是否退市'] == False]
    df = df[df['上市至今交易天数'] > 250]

    return df


def data_processing(df, func):
    df = func(df)
    return df


def offset_grouping_double(df, main_factor, sub_factor, bins):
    '''
    分组函数
    :param df: 原数据
    :param main_factor: 主因子名
    :param sub_factor: 次因子名
    :param bins: 分组的数量
    :return:
        返回一个df数据，包含groups列
    '''

    print(f'正在对双因子 {main_factor} 和 {sub_factor} 分组...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 根据主因子计算主因子的排名method='min'与风格因子保持相同取法
    df['排名_主因子'] = df.groupby(['交易日期'])[main_factor].rank(ascending=True, method='first')
    # 根据次因子计算次因子的排名
    df['排名_次因子'] = df.groupby(['交易日期'])[sub_factor].rank(ascending=True, method='first')
    # 根据主因子的排名进行分组
    df['groups_主因子'] = df.groupby(['交易日期'])['排名_主因子'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))
    # 根据次因子的排名进行分组
    df['groups_次因子'] = df.groupby(['交易日期'])['排名_次因子'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))
    # 在主因子分组基础上，再根据次因子的排名进行分组
    df['groups_主因子分箱_次因子'] = df.groupby(['交易日期', 'groups_主因子'])['排名_次因子'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))
    # 在次因子分组基础上，再根据主因子的排名进行分组
    df['groups_次因子分箱_主因子'] = df.groupby(['交易日期', 'groups_次因子'])['排名_主因子'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))

    # 这里不需要判断某个周期的股票数量大于bins，因为之前在处理limit时已经处理过这个问题
    print(f'双因子 {main_factor} 和 {sub_factor} 分组完成，耗时：{datetime.datetime.now() - start_date}')
    return df


def get_group_nv_double(df, next_ret, b_rate, s_rate, offset):
    """
    针对双因子分组数据进行分析，给出双因子分组的组合平均收益、过滤平均收益数据
    :param df: 输入的数据
    :param next_ret: 未来涨跌幅的list
    :param b_rate: 买入手续费率
    :param s_rate: 卖出手续费率
    :param offset: 当前执行的是哪个offset的数据
    :return:
        返回双因子组合分组平均收益、双因子组合分组平均占比、双因子过滤分组平均收益数据
    """

    print('计算双因子平均收益...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 由于会对原始的数据进行修正，所以需要把数据copy一份
    temp = df.copy()

    # 计算下周期每天的净值，并扣除手续费得到下周期的实际净值
    temp['下周期每天净值'] = temp[next_ret].apply(lambda x: (np.array(x) + 1).cumprod())
    free_rate = (1 - b_rate) * (1 - s_rate)
    temp['下周期平均收益'] = temp['下周期每天净值'].apply(lambda x: np.power((x[-1] * free_rate), 1 / len(x)) - 1)

    # 计算双因子组合分组在持仓内的平均收益
    mix_nv = temp.groupby(['groups_主因子', 'groups_次因子'])['下周期平均收益'].mean().reset_index()
    mix_nv['offset'] = offset

    # 计算双因子组合分组在持仓内的股票占比
    mix_prop = temp.groupby(['交易日期', 'groups_主因子', 'groups_次因子']).agg(
        {'股票名称': 'count', '当周期股票数': 'last'}).reset_index()
    mix_prop['当周期平均占比'] = mix_prop['股票名称'] / mix_prop['当周期股票数']
    mix_prop['当周期平均占比'].fillna(0, inplace=True)
    mix_prop = mix_prop.groupby(['groups_主因子', 'groups_次因子'])['当周期平均占比'].mean().reset_index()
    mix_prop['offset'] = offset

    # 计算双因子过滤分组在持仓内的平均收益 主->次
    filter_nv_ms = temp.groupby(['groups_主因子', 'groups_主因子分箱_次因子'])['下周期平均收益'].mean().reset_index()
    filter_nv_ms['offset'] = offset

    # 计算双因子过滤分组在持仓内的平均收益 次->主
    filter_nv_sm = temp.groupby(['groups_次因子', 'groups_次因子分箱_主因子'])['下周期平均收益'].mean().reset_index()
    filter_nv_sm['offset'] = offset

    print(f'计算双因子平均收益完成，耗时：{datetime.datetime.now() - start_date}')
    return mix_nv, mix_prop, filter_nv_ms, filter_nv_sm


def group_nv_analysis(mix_nv_list, mix_prop_list, filter_nv_ms_list, filter_nv_sm_list, bins):
    '''
    根据双因子分组的组合平均收益、过滤平均收益数据生成热力图
    :param mix_nv_list: 双因子分组的组合平均收益列表
    :param mix_prop_list: 双因子分组的组合平均占比列表
    :param filter_nv_ms_list: 双因子分组的过滤平均收益列表，主因子分组的基础上，次因子再分组
    :param filter_nv_sm_list: 双因子分组的过滤平均收益列表，次因子分组的基础上，主因子再分组
    :param bins: 分组数量
    :return:
        返回双因子组合分组平均收益热力图、双因子过滤分组平均收益数据热力图
    '''

    print('整理双因子热力图数据...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 合并列表
    mix_nv = pd.concat(mix_nv_list, ignore_index=True).groupby(['groups_主因子', 'groups_次因子'])[
        '下周期平均收益'].mean().reset_index()
    mix_prop = pd.concat(mix_prop_list, ignore_index=True).groupby(['groups_主因子', 'groups_次因子'])[
        '当周期平均占比'].mean().reset_index()
    filter_nv_ms = pd.concat(filter_nv_ms_list, ignore_index=True).groupby([
        'groups_主因子', 'groups_主因子分箱_次因子'])['下周期平均收益'].mean().reset_index()
    filter_nv_sm = pd.concat(filter_nv_sm_list, ignore_index=True).groupby([
        'groups_次因子', 'groups_次因子分箱_主因子'])['下周期平均收益'].mean().reset_index()

    # 下周期平均收益转换单位千分之,当周期平均占比转换单位百分之
    mix_nv['下周期平均收益'] = mix_nv['下周期平均收益'].apply(lambda x: x * 1000)
    mix_prop['当周期平均占比'] = mix_prop['当周期平均占比'].apply(lambda x: x * 100)
    filter_nv_ms['下周期平均收益'] = filter_nv_ms['下周期平均收益'].apply(lambda x: x * 1000)
    filter_nv_sm['下周期平均收益'] = filter_nv_sm['下周期平均收益'].apply(lambda x: x * 1000)

    # 将groups_次因子、groups_主因子设置为index，在将groups_主因子为列
    mix_nv['groups_主因子'] = mix_nv['groups_主因子'].apply(lambda x: '主因子' + str(x))
    mix_nv['groups_次因子'] = mix_nv['groups_次因子'].apply(lambda x: '次因子' + str(x))
    mix_nv = mix_nv.set_index(['groups_次因子', 'groups_主因子'])['下周期平均收益']
    mix_nv = mix_nv.unstack('groups_主因子')
    # 添加平均收益
    mix_nv.loc['主因子平均收益'] = mix_nv.mean()
    mix_nv['次因子平均收益'] = mix_nv.mean(axis=1)

    mix_prop['groups_主因子'] = mix_prop['groups_主因子'].apply(lambda x: '主因子' + str(x))
    mix_prop['groups_次因子'] = mix_prop['groups_次因子'].apply(lambda x: '次因子' + str(x))
    mix_prop = mix_prop.set_index(['groups_次因子', 'groups_主因子'])['当周期平均占比']
    mix_prop = mix_prop.unstack('groups_主因子')

    # 计算双因子过滤组合主因子分箱平均收益，主因子分组的基础上，次因子再分组
    filter_nv_main_mean = filter_nv_ms.groupby(['groups_主因子']).agg(
        {'groups_主因子分箱_次因子': 'first', '下周期平均收益': 'mean'}).reset_index()
    filter_nv_main_mean['groups_主因子分箱_次因子'] = 0
    filter_nv_ms = pd.concat([filter_nv_ms, filter_nv_main_mean], ignore_index=True)
    filter_nv_ms['groups_主因子'] = filter_nv_ms['groups_主因子'].astype(int)
    filter_nv_ms['groups_主因子分箱_次因子'] = filter_nv_ms['groups_主因子分箱_次因子'].astype(int)
    filter_nv_ms.sort_values(by=['groups_主因子', 'groups_主因子分箱_次因子'], inplace=True, ignore_index=True)

    filter_nv_ms = filter_nv_ms.set_index(['groups_主因子分箱_次因子', 'groups_主因子'])['下周期平均收益']
    filter_nv_ms = filter_nv_ms.unstack('groups_主因子')
    # 根据bins的数量来重命名
    rename_dict = {i: f'主因子{i}' for i in range(1, bins + 1)}
    filter_nv_ms.rename(columns=rename_dict, inplace=True)
    rename_dict = {i: f'次因子{i}' for i in range(1, bins + 1)}
    rename_dict[0] = '主因子平均收益'
    filter_nv_ms.rename(index=rename_dict, inplace=True)
    filter_nv_ms.loc['主因子平均收益'] = filter_nv_ms.mean()
    filter_nv_ms['次因子平均收益'] = filter_nv_ms.mean(axis=1)

    # 计算双因子过滤组合主因子分箱平均收益，次因子分组的基础上，主因子再分组
    filter_nv_sub_mean = filter_nv_sm.groupby(['groups_次因子']).agg(
        {'groups_次因子分箱_主因子': 'first', '下周期平均收益': 'mean'}).reset_index()
    filter_nv_sub_mean['groups_次因子分箱_主因子'] = 0
    filter_nv_sm = pd.concat([filter_nv_sm, filter_nv_sub_mean], ignore_index=True)
    filter_nv_sm['groups_次因子'] = filter_nv_sm['groups_次因子'].astype(int)
    filter_nv_sm['groups_次因子分箱_主因子'] = filter_nv_sm['groups_次因子分箱_主因子'].astype(int)
    filter_nv_sm.sort_values(by=['groups_次因子', 'groups_次因子分箱_主因子'], inplace=True, ignore_index=True)
    filter_nv_sm = filter_nv_sm.set_index(['groups_次因子分箱_主因子', 'groups_次因子'])['下周期平均收益']
    filter_nv_sm = filter_nv_sm.unstack('groups_次因子')
    # 根据bins的数量来重命名
    rename_dict = {i: f'次因子{i}' for i in range(1, bins + 1)}
    filter_nv_sm.rename(columns=rename_dict, inplace=True)
    rename_dict = {i: f'主因子{i}' for i in range(1, bins + 1)}
    rename_dict[0] = '次因子平均收益'
    filter_nv_sm.rename(index=rename_dict, inplace=True)
    filter_nv_sm.loc['次因子平均收益'] = filter_nv_sm.mean()
    filter_nv_sm['主因子平均收益'] = filter_nv_sm.mean(axis=1)

    print(f'整理双因子热力图数据完成，耗时：{datetime.datetime.now() - start_date}')
    return mix_nv, mix_prop, filter_nv_ms, filter_nv_sm


def get_style_corr_double(df, main_factor, sub_factor, offset, target):
    '''
    计算因子的风格暴露
    :param df: df数据，包含双因子的因子列和风格列
    :param main_factor: 主因子列
    :param sub_factor: 次因子列
    :param offset: 当前执行的是哪个offset的数据
    :param target: 测试因子与下周期涨跌幅的IC
    :return:
        返回双因子的风格暴露的数据
    '''

    print('正在进行因子风格暴露分析...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 由于会对原始的数据进行修正，所以需要把数据copy一份
    temp = df.copy()

    temp['排名_主因子'] = temp.groupby(['交易日期'])[main_factor].rank(ascending=True, method='first')
    # 根据次因子计算次因子的排名
    temp['排名_次因子'] = temp.groupby(['交易日期'])[sub_factor].rank(ascending=True, method='first')

    # 计算因子IC值
    main_factor_ic = df.groupby('交易日期').apply(
        lambda x: x[main_factor].corr(x[target], method='spearman')).to_frame()
    main_factor_ic = main_factor_ic.rename(columns={0: 'RankIC'}).reset_index()
    main_factor_ic_mean = main_factor_ic['RankIC'].mean()
    sub_factor_ic = df.groupby('交易日期').apply(lambda x: x[sub_factor].corr(x[target], method='spearman')).to_frame()
    sub_factor_ic = sub_factor_ic.rename(columns={0: 'RankIC'}).reset_index()
    sub_factor_ic_mean = sub_factor_ic['RankIC'].mean()
    double_factor_ic_flag = 1 if main_factor_ic_mean * sub_factor_ic_mean >= 0 else -1

    # 计算双因子等权
    temp['风格因子_双因子'] = temp['排名_主因子'] + temp['排名_次因子'] * double_factor_ic_flag

    # 取出风格列，格式：以 风格因子_ 开头
    factor_style_cols = [col for col in temp.columns if '风格因子_' in col]

    def func(x, factor, style):
        if len(x) > 100:
            res = x[[factor] + style].corr(method='spearman').iloc[0, 1:].to_frame()
        else:
            res = pd.Series()
        return res

    temp.dropna(subset=['排名_次因子', '排名_次因子', '风格因子_双因子'] + factor_style_cols, inplace=True)
    main_res = temp.groupby('交易日期').apply(lambda x: func(x, '排名_主因子', factor_style_cols))
    main_factor_style_corr = main_res.reset_index().groupby('level_1')['排名_主因子'].mean().reset_index()

    sub_res = temp.groupby('交易日期').apply(lambda x: func(x, '排名_次因子', factor_style_cols))
    sub_factor_style_corr = sub_res.reset_index().groupby('level_1')['排名_次因子'].mean().reset_index()

    double_res = temp.groupby('交易日期').apply(lambda x: func(x, '风格因子_双因子', factor_style_cols))
    double_factor_style_corr = double_res.reset_index().groupby('level_1')['风格因子_双因子'].mean().reset_index()

    # 风格因子_双因子 这里是主次因子的相关系数
    max_inx = double_factor_style_corr.index.max()
    double_factor_style_corr.loc[max_inx, '风格因子_双因子'] = \
        temp[[main_factor, sub_factor]].corr(method='spearman').iloc[0, 1]

    # 整理数据
    main_factor_style_corr = main_factor_style_corr.rename(columns={'level_1': '风格', '排名_主因子': '相关系数_主因子'})
    sub_factor_style_corr = sub_factor_style_corr.rename(columns={'level_1': '风格', '排名_次因子': '相关系数_次因子'})
    double_factor_style_corr = double_factor_style_corr.rename(columns={'level_1': '风格', '风格因子_双因子': '相关系数_双因子'})

    # 合并数据并设置offset
    group_style_corr = pd.merge(main_factor_style_corr, sub_factor_style_corr, how='left', on='风格')
    group_style_corr = pd.merge(group_style_corr, double_factor_style_corr, how='left', on='风格')
    group_style_corr['offset'] = offset
    group_style_corr['风格'] = group_style_corr['风格'].apply(lambda x: x.split('_')[1])

    print(f'因子风格分析完成，耗时：{datetime.datetime.now() - start_date}')
    return group_style_corr


def group_style_analysis(group_style_corr_list):
    '''
    计算因子的风格暴露
    :param group_style_corr: 双因子各个offset的风格暴露数据
    :return:
       返回双因子风格暴露数据、双因子相关系数
    '''

    # 合并双因子各个offset的风格暴露数据
    group_style_corr = pd.concat(group_style_corr_list, axis=0)
    # 对各offset求平均
    group_style_corr = group_style_corr.groupby('风格').agg(
        {'相关系数_主因子': 'mean', '相关系数_次因子': 'mean', '相关系数_双因子': 'mean'}).reset_index()
    # 获取双因子相关系数
    main_sub_corr = float_num_process(group_style_corr[group_style_corr['风格'] == '双因子']['相关系数_双因子'].iloc[-1])
    main_comp_corr = float_num_process(group_style_corr[group_style_corr['风格'] == '双因子']['相关系数_主因子'].iloc[-1])
    sub_comp_corr = float_num_process(group_style_corr[group_style_corr['风格'] == '双因子']['相关系数_次因子'].iloc[-1])

    corr_txt = f'corr(主，次)：{main_sub_corr}    corr(主，复)：{main_comp_corr}    corr(次，复)：{sub_comp_corr}'
    # 删除双因子相关系数
    group_style_corr = group_style_corr[group_style_corr['风格'] != '双因子']

    return group_style_corr, corr_txt
