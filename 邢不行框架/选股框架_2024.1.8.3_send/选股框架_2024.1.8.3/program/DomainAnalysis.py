"""
2024分享会
author: 邢不行
微信: xbx6660
选股策略框架
"""
import itertools
import pandas as pd
import numpy as np
import os

from program import Config as Cfg
from program import Evaluate as Eva
import program.Functions as Fun

pd.set_option('expand_frame_repr', False)
pd.set_option('display.max_rows', 5000)  # 最多显示数据的行数


# 关于本脚本如何使用，可以看帖子：https://bbs.quantclass.cn/thread/42432


def cal_tr(row):
    # 计算row['股票名称']和row['上周期股票名称']这个两个集合之间的差集数量
    if not isinstance(row['上周期股票名称'], list):
        return 1
    same_count = len(list(set(row['股票名称']) & set(row['上周期股票名称'])))
    max_count = max(len(row['股票名称']), len(row['上周期股票名称']))
    res = 1 - same_count / max_count
    return res


def process_data(df_for_group):
    mv_dict = {0: '小市值组', 1: '中市值组', 2: '大市值组', 3: '大市值组'}
    df_for_group['市值分组'] = df_for_group['总市值分位数'].apply(lambda x: mv_dict[int(x / (1 / 3))])

    rule_dict = {'总市值': 'mean', '成交额': 'mean', '总市值分位数': 'mean', '成交额分位数': 'mean'}
    period = df_for_group.groupby('交易日期').agg(rule_dict)
    period['股票数量'] = df_for_group.groupby('交易日期')['股票名称'].count()
    period['股票名称'] = df_for_group.groupby('交易日期')['股票名称'].apply(list)
    period['新版申万一级行业名称'] = df_for_group.groupby('交易日期')['新版申万一级行业名称'].apply(list)

    period['上周期股票名称'] = period['股票名称'].shift(1)
    period['周期换手率'] = period.apply(lambda rows: cal_tr(rows), axis=1)

    # 计算大公司的数量、平均市值、占比
    period['大公司数量'] = df_for_group.groupby('交易日期').apply(lambda x: len(x[x['市值分组'] == '大市值组']))
    period['大公司平均市值'] = df_for_group.groupby('交易日期').apply(lambda x: x[x['市值分组'] == '大市值组']['总市值'].mean())
    period['大公司占比'] = period['大公司数量'] / period['股票数量']

    # 计算中型公司的数量、平均市值、占比
    period['中型公司数量'] = df_for_group.groupby('交易日期').apply(lambda x: len(x[x['市值分组'] == '中市值组']))
    period['中型公司平均市值'] = df_for_group.groupby('交易日期').apply(lambda x: x[x['市值分组'] == '中市值组']['总市值'].mean())
    period['中型公司占比'] = period['中型公司数量'] / period['股票数量']

    # 计算小公司的数量、平均市值、占比
    period['小公司数量'] = df_for_group.groupby('交易日期').apply(lambda x: len(x[x['市值分组'] == '小市值组']))
    period['小公司平均市值'] = df_for_group.groupby('交易日期').apply(lambda x: x[x['市值分组'] == '小市值组']['总市值'].mean())
    period['小公司占比'] = period['小公司数量'] / period['股票数量']

    period.reset_index(inplace=True)
    return period


def get_top_three_industries(df):
    # 按年份和行业分组，计算每年各行业的股票数量
    industry_counts = df.groupby(['Year', '新版申万一级行业名称']).size().reset_index(name='Count')

    # 对每个年份的行业按选中数量降序排序，并重置索引以方便后续操作
    sorted_counts = industry_counts.sort_values(['Year', 'Count'], ascending=[True, False]).reset_index(drop=True)

    # 为每个年份的行业分配排名
    sorted_counts['Rank'] = sorted_counts.groupby('Year')['Count'].rank(method='first', ascending=False)

    # 选取每年排名前三的行业
    top_three = sorted_counts[sorted_counts['Rank'] <= 3]

    return top_three


def rtn_data(df_for_group):
    # 将日期列转换为日期类型
    df_for_group['交易日期'] = pd.to_datetime(df_for_group['交易日期'])

    # 提取年份作为新列
    df_for_group['Year'] = df_for_group['交易日期'].dt.year
    top_three_result = get_top_three_industries(df_for_group)
    top_three_result = pd.DataFrame(top_three_result)

    df_new = top_three_result.groupby('Year').apply(lambda x: pd.Series({
        'Top1行业': x['新版申万一级行业名称'][x['Rank'] == 1.0].iloc[0] if (x['Rank'] == 1.0).any() else None,
        'Top1行业选中个数': x['Count'][x['Rank'] == 1.0].iloc[0] if (x['Rank'] == 1.0).any() else None,
        'Top2行业': x['新版申万一级行业名称'][x['Rank'] == 2.0].iloc[0] if (x['Rank'] == 2.0).any() else None,
        'Top2行业选中个数': x['Count'][x['Rank'] == 2.0].iloc[0] if (x['Rank'] == 2.0).any() else None,
        'Top3行业': x['新版申万一级行业名称'][x['Rank'] == 3.0].iloc[0] if (x['Rank'] == 3.0).any() else None,
        'Top3行业选中个数': x['Count'][x['Rank'] == 3.0].iloc[0] if (x['Rank'] == 3.0).any() else None
    })).reset_index()

    return df_new


def domain_factor_analysis(df, select_count, factor_list, ret_next='下周期涨跌幅'):
    res = pd.DataFrame()
    for factor in factor_list:
        insert_inx = 0 if pd.isnull(res.index.max()) else res.index.max() + 1
        df[factor + '_排名'] = df.groupby('交易日期')[factor].rank()
        temp = df[df[factor + '_排名'] <= select_count].copy()
        res.loc[insert_inx, '因子名称'] = factor.replace('风格因子_', '')
        IC = df.groupby('交易日期').apply(lambda x: x[factor].corr(x[ret_next], method='spearman')).to_frame()

        res.loc[insert_inx, '域内IC'] = round(IC.mean()[0], 4)
        res.loc[insert_inx, '域内ICIR'] = round(IC.mean()[0] / IC.std()[0], 4)
        res.loc[insert_inx, f'选{select_count}只平均收益'] = round(temp[ret_next].mean(), 4)
        res.loc[insert_inx, f'选{select_count}只胜率'] = round(
            temp[temp[ret_next] > 0][ret_next].count() / temp[ret_next].count(), 4)

    return res


def domain_evaluate(equity):
    """
    :param equity:  每天的资金曲线
    :param select_stock: 每周期选出的股票
    :return:
    """

    # ===新建一个dataframe保存回测指标
    results = pd.DataFrame()

    # ===计算累积净值
    results.loc[0, '累积净值'] = round(equity['equity_curve'].iloc[-1], 2)

    # ===计算年化收益
    annual_return = (equity['equity_curve'].iloc[-1]) ** (
            '1 days 00:00:00' / (equity['交易日期'].iloc[-1] - equity['交易日期'].iloc[0]) * 365) - 1
    results.loc[0, '年化收益'] = str(round(annual_return * 100, 2)) + '%'

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    equity['max2here'] = equity['equity_curve'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    equity['dd2here'] = equity['equity_curve'] / equity['max2here'] - 1
    # 计算最大回撤，以及最大回撤结束时间
    end_date, max_draw_down = tuple(equity.sort_values(by=['dd2here']).iloc[0][['交易日期', 'dd2here']])
    # 计算最大回撤开始时间
    start_date = equity[equity['交易日期'] <= end_date].sort_values(by='equity_curve', ascending=False).iloc[0][
        '交易日期']
    # 将无关的变量删除
    # equity.drop(['max2here', 'dd2here'], axis=1, inplace=True)
    results.loc[0, '最大回撤'] = format(max_draw_down, '.2%')
    results.loc[0, '最大回撤开始时间'] = str(start_date)
    results.loc[0, '最大回撤结束时间'] = str(end_date)

    # ===年化收益/回撤比：我个人比较关注的一个指标
    results.loc[0, '年化收益/回撤比'] = round(annual_return / abs(max_draw_down), 2)

    # ===统计每个周期

    results.loc[0, '盈利周期数'] = len(equity.loc[equity['下周期涨跌幅'] > 0])  # 盈利笔数
    results.loc[0, '亏损周期数'] = len(equity.loc[equity['下周期涨跌幅'] <= 0])  # 亏损笔数
    results.loc[0, '胜率'] = format(results.loc[0, '盈利周期数'] / len(equity), '.2%')  # 胜率
    results.loc[0, '每周期平均收益'] = format(equity['下周期涨跌幅'].mean(), '.2%')  # 每笔交易平均盈亏
    results.loc[0, '盈亏收益比'] = round(
        equity.loc[equity['下周期涨跌幅'] > 0]['下周期涨跌幅'].mean() / \
        equity.loc[equity['下周期涨跌幅'] <= 0]['下周期涨跌幅'].mean() * (-1), 2)  # 盈亏比
    results.loc[0, '单周期最大盈利'] = format(equity['下周期涨跌幅'].max(), '.2%')  # 单笔最大盈利
    results.loc[0, '单周期大亏损'] = format(equity['下周期涨跌幅'].min(), '.2%')  # 单笔最大亏损

    # ===连续盈利亏损
    results.loc[0, '最大连续盈利周期数'] = max(
        [len(list(v)) for k, v in
         itertools.groupby(np.where(equity['下周期涨跌幅'] > 0, 1, np.nan))])  # 最大连续盈利次数
    results.loc[0, '最大连续亏损周期数'] = max(
        [len(list(v)) for k, v in
         itertools.groupby(np.where(equity['下周期涨跌幅'] <= 0, 1, np.nan))])  # 最大连续亏损次数

    return results.T


def cal_domain_curve(df, b_rate=1 / 10000, s_rate=1.1 / 1000, ret_next='下周期每天涨跌幅'):
    # 由于会对原始的数据进行修正，所以需要把数据copy一份
    temp = df.copy()
    temp = temp[temp['下周期每天涨跌幅'].notnull()]
    # 计算下周期每天的净值，并扣除手续费得到下周期的实际净值
    temp['下周期每天净值'] = temp[ret_next].apply(lambda x: (np.array(x) + 1).cumprod())
    free_rate = (1 - b_rate) * (1 - s_rate)
    temp['下周期净值'] = temp['下周期每天净值'].apply(lambda x: x[-1] * free_rate)

    # 计算得到每组的资金曲线
    period_nv = temp.groupby(['交易日期'])['下周期净值'].mean().reset_index()
    period_nv = period_nv.sort_values(by='交易日期').reset_index(drop=True)

    # 将每个周期的净值-1，得到每个周期的涨跌幅
    period_nv['下周期涨跌幅'] = period_nv['下周期净值'] - 1

    # 计算每个分组的累计净值
    period_nv['equity_curve'] = period_nv['下周期净值'].cumprod()

    rtn = domain_evaluate(period_nv)

    inx_df = Fun.import_index_data(Cfg.index_path, True, period_nv['交易日期'].min())
    inx_df['benchmark'] = (inx_df['指数涨跌幅'] + 1).cumprod()

    period_nv = pd.merge(period_nv, inx_df, on='交易日期', how='left')

    return period_nv, rtn


def domain_analysis(_df_for_group: pd.DataFrame, total_df=pd.DataFrame()):
    '''
    分域画图分析函数
    :param df_for_group:
    :return: html file
    '''
    df_for_group = _df_for_group.copy()
    # 把总市值和成交额缩小1亿倍
    df_for_group['总市值'] = df_for_group['总市值'] / 100000000
    df_for_group['成交额'] = df_for_group['成交额'] / 100000000
    # 函数计算相邻日期间不同股票的数量
    result = process_data(df_for_group)

    # 计算域内的资金曲线
    domain_curve, rtn = cal_domain_curve(df_for_group)

    fig_list = []
    draw_data_dict = {'策略资金曲线': 'equity_curve', '基准资金曲线': 'benchmark'}
    right_axis_dict = {'回撤': 'dd2here'}
    fig0 = Eva.draw_equity_curve_plotly(domain_curve, title='域内全选资金曲线', data_dict=draw_data_dict, date_col='交易日期',
                                        right_axis=right_axis_dict, rtn_add=rtn, pic_size=[1500, 600])
    fig_list.append(fig0)

    result['交易日期'] = pd.to_datetime(result['交易日期'])
    draw_data_dict = {'股票数量': '股票数量'}
    right_axis_dict = {'周期换手率': '周期换手率'}
    txt = '股票数量：%s-%s，均值：%s，中值：%s    周期换手率：%.2f-%.2f，均值：%.2f，中值：%.2f' % (
        result['股票数量'].min(), result['股票数量'].max(), int(result['股票数量'].mean()), int(result['股票数量'].median()),
        result['周期换手率'].min(), result['周期换手率'].max(), result['周期换手率'].mean(), result['周期换手率'].median())

    fig1 = Eva.draw_equity_curve_plotly(result, date_col='交易日期', title=txt, data_dict=draw_data_dict,
                                        right_axis=right_axis_dict, pic_size=[1200, 675], to_zero=False)
    fig_list.append(fig1)

    draw_data_dict = {'平均市值(亿)': '总市值'}
    right_axis_dict = {'平均成交额(亿)': '成交额'}
    txt = '平均市值：%.2f-%.2f，均值：%.2f，中值：%.2f    平均成交额：%.2f-%.2f，均值：%.2f，中值：%.2f' % (
        result['总市值'].min(), result['总市值'].max(), result['总市值'].mean(), result['总市值'].median(),
        result['成交额'].min(), result['成交额'].max(), result['成交额'].mean(), result['成交额'].median())
    fig2 = Eva.draw_equity_curve_plotly(result, date_col='交易日期', title=txt, data_dict=draw_data_dict,
                                        right_axis=right_axis_dict, pic_size=[1200, 330], to_zero=False)
    fig_list.append(fig2)

    draw_data_dict = {'总市值分位数': '总市值分位数'}
    right_axis_dict = {'成交额分位数': '成交额分位数'}
    txt = '总市值分位数：%.2f-%.2f，均值：%.2f，中值：%.2f    成交额分位数：%.2f-%.2f，均值：%.2f，中值：%.2f' % (
        result['总市值分位数'].min(), result['总市值分位数'].max(), result['总市值分位数'].mean(), result['总市值分位数'].median(),
        result['成交额分位数'].min(), result['成交额分位数'].max(), result['成交额分位数'].mean(), result['成交额分位数'].median())
    fig3 = Eva.draw_equity_curve_plotly(result, date_col='交易日期', title=txt, data_dict=draw_data_dict,
                                        right_axis=right_axis_dict, pic_size=[1200, 330], to_zero=False)
    fig_list.append(fig3)

    # 绘制大中小市值的市值分布图
    draw_data_dict = {'大公司平均市值': '大公司平均市值', '中型公司平均市值': '中型公司平均市值', '小公司平均市值': '小公司平均市值'}
    txt = '大公司市值：%.0f-%.0f，中值：%.0f    中型公司市值：%.0f-%.0f，中值：%.0f    小公司市值：%.0f-%.0f，中值：%.0f  单位：亿' % (
        result['大公司平均市值'].min(), result['大公司平均市值'].max(), result['大公司平均市值'].median(),
        result['中型公司平均市值'].min(), result['中型公司平均市值'].max(), result['中型公司平均市值'].median(),
        result['小公司平均市值'].min(), result['小公司平均市值'].max(), result['小公司平均市值'].median())
    fig31 = Eva.draw_equity_curve_plotly(result, draw_data_dict, date_col='交易日期', title=txt, pic_size=[1200, 330])
    fig_list.append(fig31)

    draw_data_dict = {'大公司占比': '大公司占比', '中型公司占比': '中型公司占比', '小公司占比': '小公司占比'}
    txt = '大公司占比：%.2f-%.2f，中值：%.2f    中型公司占比：%.2f-%.2f，中值：%.2f    小公司占比：%.2f-%.2f，中值：%.2f' % (
        result['大公司占比'].min(), result['大公司占比'].max(), result['大公司占比'].median(),
        result['中型公司占比'].min(), result['中型公司占比'].max(), result['中型公司占比'].median(),
        result['小公司占比'].min(), result['小公司占比'].max(), result['小公司占比'].median())
    fig32 = Eva.draw_equity_curve_plotly(result, draw_data_dict, date_col='交易日期', title=txt, pic_size=[1200, 330])
    fig_list.append(fig32)

    rtn = rtn_data(df_for_group)  # 导入外部数据
    rtn['Top1行业'] = rtn['Top1行业'] + '_' + rtn['Top1行业选中个数'].astype(str)
    rtn['Top2行业'] = rtn['Top2行业'] + '_' + rtn['Top2行业选中个数'].astype(str)
    rtn['Top3行业'] = rtn['Top3行业'] + '_' + rtn['Top3行业选中个数'].astype(str)
    rtn = rtn.drop(columns=['Top1行业选中个数', 'Top2行业选中个数', 'Top3行业选中个数'])
    fig4 = Eva.draw_table(rtn, title='历年选中频率前三行业及数量')
    fig_list.append(fig4)

    # 计算基础风格因子在域内的表现
    factor_list = [col for col in df_for_group.columns if col.startswith('风格因子_')]
    result = domain_factor_analysis(df_for_group, 10, factor_list)
    fig5 = Eva.draw_table(result, title='风格因子在域内的基本表现')
    fig_list.append(fig5)

    # 如果全量数据不为空，还需要绘制域外的表现
    if not total_df.empty:
        factor_list = [col for col in total_df.columns if col.startswith('风格因子_')]
        total_df = pd.merge(total_df, df_for_group[['交易日期', '股票代码']], on=['交易日期', '股票代码'], how='left', indicator=True)
        # 计算各个估值的分位数
        for factor in factor_list:
            total_df[factor + '_分位数'] = total_df.groupby('交易日期')[factor].rank(pct=True)

        outside_df = total_df[total_df['_merge'] == 'left_only']
        inside_df = total_df[total_df['_merge'] == 'both']

        # 做一个全域分析的对比
        to_res = domain_factor_analysis(total_df, 10, factor_list)
        ic = pd.merge(result, to_res, on='因子名称', suffixes=('', '_全市场'), how='left')
        ic.rename(columns={'域内IC_全市场': '全市场IC', '域内ICIR_全市场': '全市场ICIR'}, inplace=True)
        ic = ic[['因子名称', '域内IC', '域内ICIR', '全市场IC', '全市场ICIR']]
        ic['IC绝对值变化'] = (ic['域内IC'].abs() - ic['全市场IC'].abs()).apply(lambda x: round(x, 4))
        ic['ICIR绝对值变化'] = (ic['域内ICIR'].abs() - ic['全市场ICIR'].abs()).apply(lambda x: round(x, 4))
        ic = ic.sort_values('域内IC').reset_index(drop=True)

        fig6 = Eva.draw_table(ic, title='域内&全市场风格因子IC表现')
        fig_list.append(fig6)

        res_df = pd.DataFrame()
        temp_fig_list = []
        for factor in factor_list:
            insert_inx = 0 if pd.isnull(res_df.index.max()) else res_df.index.max() + 1
            res = pd.DataFrame()
            res[f'域内{factor[5:]}_分位数'] = inside_df.groupby('交易日期')[factor + '_分位数'].mean()
            res[f'域外{factor[5:]}_分位数'] = outside_df.groupby('交易日期')[factor + '_分位数'].mean()
            res.reset_index(inplace=True)
            res_df.loc[insert_inx, '因子名称'] = factor[5:]
            res_df.loc[insert_inx, '域内_平均分位数'] = round(res[f'域内{factor[5:]}_分位数'].mean(), 4)
            res_df.loc[insert_inx, '域外_平均分位数'] = round(res[f'域外{factor[5:]}_分位数'].mean(), 4)
            res_df.loc[insert_inx, '分位数差异'] = round(res_df.loc[insert_inx, '域内_平均分位数'] - res_df.loc[insert_inx,
                                                                                                    '域外_平均分位数'], 4)
            draw = True
            if draw:
                txt = f'{factor[5:]} 域内外 分位数'
                draw_data_dict = {f'域内{factor[5:]}_分位数': f'域内{factor[5:]}_分位数',
                                  f'域外{factor[5:]}_分位数': f'域外{factor[5:]}_分位数'}
                temp_fig = Eva.draw_equity_curve_plotly(res, date_col='交易日期', title=txt, data_dict=draw_data_dict,
                                                        pic_size=[1200, 300])

                temp_fig_list.append(temp_fig)

        fig7 = Eva.draw_table(res_df, title='域内外风格因子平均分位数表现')
        fig_list.append(fig7)

        fig_list += temp_fig_list

    # 储存并打开策略结果html
    Eva.merge_html(os.path.join(Cfg.root_path,'data/绘图信息/分域分析'), fig_list, Cfg.stg_file)
