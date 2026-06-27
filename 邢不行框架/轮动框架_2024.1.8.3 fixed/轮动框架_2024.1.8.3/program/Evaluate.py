"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import math
import os
import itertools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objs as go
from plotly.offline import plot
from plotly.subplots import make_subplots
import plotly.express as px
from plotly.io import to_html


# region 通用评价函数

def draw_equity_curve_mat(df, data_dict, date_col=None, right_axis=None, pic_size=[16, 9], dpi=72, font_size=25,
                          log=False, chg=False, title=None, y_label='净值'):
    """
    绘制策略曲线
    :param df: 包含净值数据的df
    :param data_dict: 要展示的数据字典格式：｛图片上显示的名字:df中的列名｝
    :param date_col: 时间列的名字，如果为None将用索引作为时间列
    :param right_axis: 右轴数据 ｛图片上显示的名字:df中的列名｝
    :param pic_size: 图片的尺寸
    :param dpi: 图片的dpi
    :param font_size: 字体大小
    :param chg: datadict中的数据是否为涨跌幅，True表示涨跌幅，False表示净值
    :param log: 是都要算对数收益率
    :param title: 标题
    :param y_label: Y轴的标签
    :return:
    """
    # 复制数据
    draw_df = df.copy()
    # 模块基础设置
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    # plt.style.use('dark_background')

    plt.figure(num=1, figsize=(pic_size[0], pic_size[1]), dpi=dpi)
    # 获取时间轴
    if date_col:
        time_data = draw_df[date_col]
    else:
        time_data = draw_df.index
    # 绘制左轴数据
    for key in data_dict:
        if chg:
            draw_df[data_dict[key]] = (draw_df[data_dict[key]] + 1).fillna(1).cumprod()
        if log:
            draw_df[data_dict[key]] = np.log(draw_df[data_dict[key]])
        plt.plot(time_data, draw_df[data_dict[key]], linewidth=2, label=str(key))
    # 设置坐标轴信息等
    plt.ylabel(y_label, fontsize=font_size)
    plt.legend(loc=0, fontsize=font_size)
    plt.tick_params(labelsize=font_size)
    plt.grid()
    if title:
        plt.title(title, fontsize=font_size)

    # 绘制右轴数据
    if right_axis:
        # 生成右轴
        ax_r = plt.twinx()
        # 获取数据
        key = list(right_axis.keys())[0]
        ax_r.plot(time_data, draw_df[right_axis[key]], 'y', linewidth=1, label=str(key))
        # 设置坐标轴信息等
        ax_r.set_ylabel(key, fontsize=font_size)
        ax_r.legend(loc=1, fontsize=font_size)
        ax_r.tick_params(labelsize=font_size)
    plt.show()


def draw_equity_curve_plotly(df, data_dict, date_col=None, right_axis=None, pic_size=[1500, 800], chg=False,
                             title=None, rtn_add=pd.DataFrame(), to_zero=True):
    """
    绘制策略曲线
    :param df: 包含净值数据的df
    :param data_dict: 要展示的数据字典格式：｛图片上显示的名字:df中的列名｝
    :param date_col: 时间列的名字，如果为None将用索引作为时间列
    :param right_axis: 右轴数据 ｛图片上显示的名字:df中的列名｝
    :param pic_size: 图片的尺寸
    :param chg: datadict中的数据是否为涨跌幅，True表示涨跌幅，False表示净值
    :param title: 标题
    :param rtn_add: 回测情况
    :param to_zero: 右轴数据是绘制阴影图还是绘制线图
    :return:
    """
    draw_df = df.copy()

    # 设置时间序列
    if date_col:
        time_data = draw_df[date_col]
    else:
        time_data = draw_df.index

    # 绘制左轴数据
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for key in data_dict:
        if chg:
            draw_df[data_dict[key]] = (draw_df[data_dict[key]] + 1).fillna(1).cumprod()
        fig.add_trace(go.Scatter(x=time_data, y=draw_df[data_dict[key]], name=key, ))

    # 绘制右轴数据
    if right_axis:
        key = list(right_axis.keys())[0]
        if to_zero:
            fig.add_trace(go.Scatter(x=time_data, y=draw_df[right_axis[key]], name=key + '(右轴)', opacity=0.1,
                                     marker_color='orange', line=dict(width=0), fill='tozeroy',
                                     yaxis='y2'))  # 标明设置一个不同于trace1的一个坐标轴
        else:
            fig.add_trace(go.Scatter(x=time_data, y=draw_df[right_axis[key]], name=key + '(右轴)', yaxis='y2'))
    fig.update_layout(template="none", width=pic_size[0], height=pic_size[1],
                      title={'text': title, 'x': 170 / pic_size[0], 'xanchor': 'left'},
                      hovermode="x unified", hoverlabel=dict(bgcolor='rgba(255,255,255,0.5)', ), margin=dict(t=50))
    x_limit = 0.98 if rtn_add.empty else 0.73
    fig.update_layout(
        updatemenus=[dict(buttons=[dict(label="线性 y轴", method="relayout", args=[{"yaxis.type": "linear"}]),
                                   dict(label="Log y轴", method="relayout", args=[{"yaxis.type": "log"}]), ])],
        xaxis=dict(domain=[0.0, x_limit]))

    fig.update_yaxes(showspikes=True, spikemode='across', spikesnap='cursor', spikedash='solid', spikethickness=1)
    fig.update_xaxes(showspikes=True, spikemode='across+marker', spikesnap='cursor', spikedash='solid',
                     spikethickness=1)
    if not rtn_add.empty:
        # 把rtn放进图里
        rtn_add = rtn_add.T
        rtn_add['最大回撤开始时间'] = rtn_add['最大回撤开始时间'].str.replace('00:00:00', '')
        rtn_add['最大回撤结束时间'] = rtn_add['最大回撤结束时间'].str.replace('00:00:00', '')
        rtn_add = rtn_add.T
        header_list = ['项目', '策略表现'] if rtn_add.shape[1] == 1 else ['项目'] + list(rtn_add.columns)
        rtn_add.reset_index(drop=False, inplace=True)
        table_trace = go.Table(header=dict(values=header_list),
                               cells=dict(values=rtn_add.T.values.tolist()),
                               domain=dict(x=[0.77, 1.0], y=[0.0, 0.82]))
        fig.add_trace(table_trace)
        # 图例调一下位置
        fig.update_layout(legend=dict(x=0.8, y=1))

    return_fig = plot(fig, include_plotlyjs=True, output_type='div')
    return return_fig


def draw_bar_plotly(data, x, y, title, text, year_return_add=pd.DataFrame(), pic_size=[1500, 800]):
    """
    绘制柱状图
    :param data:
    :param x: x轴数据
    :param y: y轴数据
    :param title: 标题
    :param text: 文本信息
    :param year_return_add: 历年收益
    :param pic_size: 图片大小
    :return:
    """
    fig = make_subplots()

    fig.add_trace(go.Bar(x=data[x], y=data[y], text=data[text]), row=1, col=1)
    fig.update_layout(width=pic_size[0], height=pic_size[1], title_text=title, xaxis=dict(domain=[0.0, 0.73]),
                      margin=dict(t=50))
    if not year_return_add.empty:
        year_return_add.reset_index(drop=False, inplace=True)
        year_return_add['交易日期'] = pd.to_datetime(year_return_add['交易日期']).dt.date.astype(str)
        year_return_add['交易日期'] = year_return_add['交易日期'].str.replace('-31', '')
        if year_return_add.shape[1] == 6:  # 说明有择时，表格显示会不够，所以简化一下表头
            year_return_add.rename(columns={'交易日期': '年份', '涨跌幅_(带择时)': '带择时', '指数涨跌幅': '指数',
                                            '超额收益': '超额', '超额收益_(带择时)': '择时超额'}, inplace=True)
        table_trace = go.Table(
            header=dict(values=year_return_add.columns.to_list(), fill=dict(color='white'), line=dict(color='black')),
            cells=dict(values=year_return_add.T.values.tolist(), fill=dict(color='white'), line=dict(color='black')),
            domain=dict(x=[0.77, 1], y=[0.0, 0.9]))
        fig.add_trace(table_trace)
    return_fig = plot(fig, include_plotlyjs=True, output_type='div')

    return return_fig


def robustness_test(data, bins=10, date_col='交易日期', factor_col='复合因子', ret_next='下周期每天涨跌幅',
                    pic_size=[1500, 800], year_return_add=pd.DataFrame()):
    """
    稳健性测试：也叫分箱测试
    :param data: 原始数据
    :param bins: 分箱数量
    :param date_col: 日期列
    :param factor_col: 因子列
    :param ret_next: 未来收益列
    :param pic_size: 图片大小
    :param year_return_add: 历年收益
    :return:
    """
    # 分组测试稳定性
    data.dropna(subset=['下周期每天涨跌幅'], inplace=True)
    data['复合因子_排名'] = data.groupby(date_col)[factor_col].rank(ascending=True, method='first')
    data['count'] = data.groupby(date_col)[date_col].transform('count')
    data = data[data['复合因子_排名'].notnull()]
    data = data[data[ret_next].notnull()]
    df_for_group = data[data['count'] >= bins]
    # 如果分箱数量较少，进行自动替换
    if df_for_group.empty:
        median = int(data['count'].median())
        if median != 1:
            print(f'分箱数量过少，已自动将分箱数量从{bins}调整为{median}')
            bins = median
            df_for_group = data[data['count'] >= bins]
    if df_for_group.empty:
        print('分箱数量过少，无法输出分箱测试图')
        data = pd.DataFrame({'group': list(range(1, bins + 1)) + ['benchmark'], 'asset': [1] * (bins + 1)})
        # 绘制策略分箱柱状图
        fig = draw_bar_plotly(data, x='group', y='asset', title='数据为空，分箱测试失败',
                              text='asset', pic_size=pic_size, year_return_add=year_return_add)
        return fig

    df_for_group['group'] = df_for_group.groupby(date_col)['复合因子_排名'].transform(
        lambda x: pd.qcut(x, q=bins, labels=range(1, bins + 1), duplicates='drop'))
    df_for_group['下周期收益序列'] = df_for_group[ret_next].apply(lambda x: np.prod(np.array(x) + 1))  # 开盘买入
    group_result = df_for_group.groupby([date_col, 'group'])['下周期收益序列'].mean().to_frame()
    group_result.reset_index('group', inplace=True)
    group_result.group = group_result.group.astype('str')
    # 计算基准资产倍数
    benchmark_result = df_for_group.groupby([date_col])['下周期收益序列'].mean().to_frame()
    benchmark_result['group'] = 'benchmark'
    # 合并结果
    result = pd.concat([group_result, benchmark_result])
    # 计算资产倍数
    result['asset'] = result.groupby('group')['下周期收益序列'].cumprod()
    result['asset'] = result['asset'].apply(lambda x: round(x, 2))

    # 绘制策略分箱柱状图
    fig = draw_bar_plotly(result.loc[result.index == result.index[-2]], x='group', y='asset',
                          title=f'{bins}分箱 资金曲线',
                          text='asset', pic_size=pic_size, year_return_add=year_return_add)
    return fig


def draw_table(table_df, width=1200, row_height=26, title=None):
    """
    绘制表格
    :param table_df: 表格数据
    :param width: 图片的宽度
    :param row_height: 表格的高度
    :param title: 表格的标题
    :return:
    """

    fig = make_subplots()
    height = (table_df.shape[0] * row_height) + 107
    header_list = list(table_df.columns)

    # 计算每一列的最大宽度
    max_widths = [max([len(str(value)) for value in table_df[col]]) for col in header_list]

    # 设置列宽为最大宽度
    column_width = [max_width / np.sum(max_widths) * width for max_width in max_widths]

    table_trace = go.Table(header=dict(values=header_list), cells=dict(values=table_df.T.values.tolist()),
                           domain=dict(x=[0, 1], y=[0, 1]), columnwidth=column_width)
    fig.add_trace(table_trace)
    fig.update_layout(width=width, height=height, title_text=title, title_x=0.5, margin=dict(t=50))
    return_fig = plot(fig, include_plotlyjs=True, output_type='div')

    return return_fig


# endregion

# region 轮动策略&轮动专用评价函数

def strategy_evaluate(equity, select_stock):
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
    if not select_stock.empty:
        # ===统计每个周期
        results.loc[0, '盈利周期数'] = len(select_stock.loc[select_stock['选股下周期涨跌幅'] > 0])  # 盈利笔数
        results.loc[0, '亏损周期数'] = len(select_stock.loc[select_stock['选股下周期涨跌幅'] <= 0])  # 亏损笔数
        results.loc[0, '胜率'] = format(results.loc[0, '盈利周期数'] / len(select_stock), '.2%')  # 胜率
        results.loc[0, '每周期平均收益'] = format(select_stock['选股下周期涨跌幅'].mean(), '.2%')  # 每笔交易平均盈亏
        results.loc[0, '盈亏收益比'] = round(
            select_stock.loc[select_stock['选股下周期涨跌幅'] > 0]['选股下周期涨跌幅'].mean() / \
            select_stock.loc[select_stock['选股下周期涨跌幅'] <= 0]['选股下周期涨跌幅'].mean() * (-1), 2)  # 盈亏比
        results.loc[0, '单周期最大盈利'] = format(select_stock['选股下周期涨跌幅'].max(), '.2%')  # 单笔最大盈利
        results.loc[0, '单周期大亏损'] = format(select_stock['选股下周期涨跌幅'].min(), '.2%')  # 单笔最大亏损

        # ===连续盈利亏损
        results.loc[0, '最大连续盈利周期数'] = max(
            [len(list(v)) for k, v in
             itertools.groupby(np.where(select_stock['选股下周期涨跌幅'] > 0, 1, np.nan))])  # 最大连续盈利次数
        results.loc[0, '最大连续亏损周期数'] = max(
            [len(list(v)) for k, v in
             itertools.groupby(np.where(select_stock['选股下周期涨跌幅'] <= 0, 1, np.nan))])  # 最大连续亏损次数

    # ===每年、每月收益率
    equity.set_index('交易日期', inplace=True)
    year_return = equity[['涨跌幅']].resample(rule='A').apply(lambda x: (1 + x).prod() - 1)
    year_return['基准涨跌幅'] = equity[['基准涨跌幅']].resample(rule='A').apply(lambda x: (1 + x).prod() - 1)
    year_return['超额收益'] = year_return['涨跌幅'] - year_return['基准涨跌幅']

    def num2pct(x):
        return str(round(x * 100, 2)) + '%'

    year_return['涨跌幅'] = year_return['涨跌幅'].apply(num2pct)
    year_return['基准涨跌幅'] = year_return['基准涨跌幅'].apply(num2pct)
    year_return['超额收益'] = year_return['超额收益'].apply(num2pct)

    monthly_return = equity[['涨跌幅']].resample(rule='M').apply(lambda x: (1 + x).prod() - 1)
    monthly_return['基准涨跌幅'] = equity[['基准涨跌幅']].resample(rule='M').apply(lambda x: (1 + x).prod() - 1)
    monthly_return['超额收益'] = monthly_return['涨跌幅'] - monthly_return['基准涨跌幅']

    return results.T, year_return, monthly_return


def strategies_describe(equity, df):
    """
    分析所有子策略在轮动中的表现
    :param equity: 回测结果
    :param df: 个股数据""
    :return:
    """
    res = pd.DataFrame()

    groups = df.groupby(['策略名称'])
    df['下周期涨跌幅'] = df['下周期每天涨跌幅'].apply(lambda x: (np.array(x) + 1).prod()) - 1
    for t, g in groups:
        max_inx = res.index.max()
        new_inx = 0 if math.isnan(max_inx) else max_inx + 1
        res.loc[new_inx, '策略名称'] = t
        res.loc[new_inx, '入选次数'] = str(len(g['交易日期'].drop_duplicates().unique()))
        res.loc[new_inx, '平均涨幅'] = str(round(g['下周期涨跌幅'].mean() * 100, 2)) + '%'
        res.loc[new_inx, '涨幅中值'] = str(round(g['下周期涨跌幅'].median() * 100, 2)) + '%'
        res.loc[new_inx, '最大涨幅'] = str(round(g['下周期涨跌幅'].max() * 100, 2)) + '%'
        res.loc[new_inx, '最小涨幅'] = str(round(g['下周期涨跌幅'].min() * 100, 2)) + '%'
        if '货币ETF' in t:
            g = pd.merge(g, equity[['基准涨跌幅']], 'left', left_on=['交易日期'], right_on=equity.index)
            win_rate = g[g['基准涨跌幅'] < 0].shape[0] / g.shape[0]
            res.loc[new_inx, '涨幅胜率'] = str(round(win_rate * 100, 2)) + '%'
        else:
            win_rate = g[g['下周期涨跌幅'] > 0].shape[0] / g['下周期涨跌幅'].shape[0]
            res.loc[new_inx, '涨幅胜率'] = str(round(win_rate * 100, 2)) + '%'

    # 计算空仓的数据
    empty = equity[equity['策略名称'] == 'empty']
    if not empty.empty:
        max_inx = res.index.max() + 1
        res.loc[max_inx, '策略名称'] = 'empty'
        res.loc[max_inx, '入选次数'] = str(int(empty.shape[0]))
        res.loc[max_inx, '平均涨幅'] = '0.00%'
        res.loc[max_inx, '涨幅中值'] = '0.00%'
        res.loc[max_inx, '最大涨幅'] = '0.00%'
        res.loc[max_inx, '最小涨幅'] = '0.00%'
        win_rate = empty[empty['基准涨跌幅'] < 0].shape[0] / empty.shape[0]
        res.loc[max_inx, '涨幅胜率'] = str(round(win_rate * 100, 2)) + '%'
    return res


# endregion

# region 事件策略专用评价函数

def frequency_statistics(all_data, index_df, event, date_col='交易日期', draw_pic=True):
    """
    统计事件发生的频率
    :param all_data:读取all_stock_data的数据
    :param index_df:指数数据
    :param event:事件名称
    :param date_col:时间列
    :param draw_pic:是否需要画图片
    :return:
    """
    df = all_data.copy()

    # 统计每天发生事件的次数
    df = df.groupby([date_col])[[event]].sum()

    # 将事件和指数数据merge合并
    df = pd.merge(left=index_df, right=df[event], on=[date_col], how='left')
    df.fillna(value=0, inplace=True)  # 将没有发生事件的日期填充为0

    # 统计事件的数据
    result = pd.DataFrame()
    result.loc[event, '总次数'] = df[event].sum()  # 计算事件的总次数
    result['日均次数'] = result['总次数'] / df.shape[0]  # 计算日均次数 = 总次数/交易日数
    result.loc[event, '最大值'] = df[event].max()  # 区间内单日发生事件的最大值
    result.loc[event, '中位数'] = df[event].median()  # 区间内单日发生事件的中位数
    result.loc[event, '无事件天数'] = (df[event] == 0).sum()  # 计算无事件天数
    result['无事件占比'] = result['无事件天数'] / df.shape[0]  # 无事件占比 = 无事件天数/交易日期

    # 计算最大连续有事件天数 & 最大连续无事件天数
    result.loc[event, '最大连续有事件天数'] = max(
        [len(list(v)) for k, v in itertools.groupby(np.where(df[event] > 0, 1, np.nan))])  # 最大有事件最大连续天数
    result.loc[event, '最大连续无事件天数'] = max(
        [len(list(v)) for k, v in itertools.groupby(np.where(df[event] == 0, 1, np.nan))])  # 最大无事件最大连续天数
    if draw_pic:
        draw_equity_curve_mat(df, date_col=date_col, data_dict={'event': event}, font_size=20, y_label='事件频率')
    return result


def evaluate_investment_for_event_driven(pos_data, day_event_df, rule_type='A', date_col='交易日期'):
    """
    计算资金曲线的各项评价指标，以及每年（月、季）的超额收益
    :param pos_data:资金曲线
    :param day_event_df:事件曲线
    :param rule_type:A 年度，Q季度，M月度
    :param date_col:交易日期
    :return:
    """
    t = pos_data.copy()
    # ===新建一个dataframe保存回测指标
    results = pd.DataFrame()

    # 将数字转为百分数
    def num_to_pct(value):
        return '%.2f%%' % (value * 100)

    # ===计算累积净值
    results.loc[0, '累积净值'] = round(t['净值'].iloc[-1], 2)

    # ===计算年化收益
    annual_return = (t['净值'].iloc[-1]) ** (
            '1 days 00:00:00' / (t[date_col].iloc[-1] - t[date_col].iloc[0]) * 365) - 1
    results.loc[0, '年化收益'] = num_to_pct(annual_return)

    # ===计算最大回撤，最大回撤的含义：《如何通过3行代码计算最大回撤》https://mp.weixin.qq.com/s/Dwt4lkKR_PEnWRprLlvPVw
    # 计算当日之前的资金曲线的最高点
    t['max2here'] = t['净值'].expanding().max()
    # 计算到历史最高值到当日的跌幅，drowdwon
    t['dd2here'] = t['净值'] / t['max2here'] - 1
    # 计算最大回撤，以及最大回撤结束时间
    end_date, max_draw_down = tuple(t.sort_values(by=['dd2here']).iloc[0][[date_col, 'dd2here']])
    # 计算最大回撤开始时间
    start_date = t[t[date_col] <= end_date].sort_values(by='净值', ascending=False).iloc[0][
        date_col]
    # 将无关的变量删除
    t.drop(['max2here', 'dd2here'], axis=1, inplace=True)
    results.loc[0, '最大回撤'] = num_to_pct(max_draw_down)
    results.loc[0, '最大回撤开始时间'] = str(start_date)
    results.loc[0, '最大回撤结束时间'] = str(end_date)

    # ===年化收益/回撤比：我个人比较关注的一个指标
    results.loc[0, '年化收益/回撤比'] = round(annual_return / abs(max_draw_down), 2)

    # ===开始处理每笔交易的数据
    # 由于不是每天发生事件都会被买入的，所以需要筛选掉没有买入日期的事件
    buy_date = t[t['投出资金'] > 0][date_col].to_list()
    real_buy = day_event_df[day_event_df.index.isin(buy_date)].copy()

    real_buy['每笔涨跌幅'] = real_buy['持仓每日净值'].apply(lambda x: x[-1] - 1)
    # 盈利次数
    results.loc[0, '盈利次数'] = real_buy[real_buy['每笔涨跌幅'] > 0].shape[0]
    # 亏损次数
    results.loc[0, '亏损次数'] = real_buy[real_buy['每笔涨跌幅'] <= 0].shape[0]
    # 每笔交易平均盈亏
    results.loc[0, '每笔交易平均盈亏'] = num_to_pct(real_buy['每笔涨跌幅'].mean())
    # 单笔最大盈利
    results.loc[0, '单笔最大盈利'] = num_to_pct(real_buy['每笔涨跌幅'].max()) if real_buy[
                                                                          '每笔涨跌幅'].max() >= 0 else None
    # 单笔最大亏损
    results.loc[0, '单笔最大亏损'] = num_to_pct(real_buy['每笔涨跌幅'].min()) if real_buy[
                                                                          '每笔涨跌幅'].min() < 0 else None
    # 计算买入胜率与盈亏比
    results.loc[0, '胜率'] = num_to_pct(results.loc[0, '盈利次数'] / real_buy.shape[0])

    results.loc[0, '盈亏比'] = round(
        real_buy[real_buy['每笔涨跌幅'] > 0]['每笔涨跌幅'].mean() / real_buy[real_buy['每笔涨跌幅'] <= 0][
            '每笔涨跌幅'].mean() * -1, 2)

    # ===开始计算资金使用率
    describe_df = t['资金使用率'].describe()
    for i in ['mean', '25%', '50%', '75%']:
        results.loc[0, '资金使用率_' + i] = num_to_pct(describe_df[i])

    results.loc[0, '年化收益/资金占用'] = num_to_pct(annual_return / describe_df['mean'])

    # ===开始计算年度和月度的超额收益
    t = t.resample(rule=rule_type, on=date_col, ).agg({
        '净值': 'last',
        '基准净值': 'last',
    })
    # 策略年（月）度收益率
    t['策略收益率'] = t['净值'].pct_change()
    t.loc[t['策略收益率'].isna(), '策略收益率'] = t['净值'] - 1
    # 基准年（月）度收益率
    t['基准收益率'] = t['基准净值'].pct_change()
    t.loc[t['基准收益率'].isna(), '基准收益率'] = t['基准净值'] - 1
    # 策略超额收益率
    t['超额收益率'] = t['策略收益率'] - t['基准收益率']
    # 转为百分比
    t['基准收益率'] = t['基准收益率'].apply(num_to_pct)
    t['超额收益率'] = t['超额收益率'].apply(num_to_pct)
    t['策略收益率'] = t['策略收益率'].apply(num_to_pct)
    t = t[['策略收益率', '基准收益率', '超额收益率']]

    return results.T, t


def _get_hold_net_value(zdf_list, hold_period):
    """
    输入涨跌幅数据，根据持有期输出净值数据。（这是个内部函数）
    :param zdf_list: 涨跌幅数据
    :param hold_period: 持有期
    :return:
    """
    zdf_count = len(zdf_list)
    if zdf_count < hold_period:
        zdf_list = zdf_list
    else:
        zdf_list = zdf_list[:hold_period]
    net_value = np.cumprod(np.array(list(zdf_list)) + 1)
    return net_value


def get_max_trade(all_stock_data, df, hold_period, stock_num=5, date_col='交易日期'):
    """
    获取回测结果中盈利（亏损）最大的几次交易
    :param all_stock_data: 所有数据的集合
    :param df: 回测的结果（back_test）
    :param hold_period: 持有期数据
    :param stock_num: 需要查看的最大盈利（亏损）的个数
    :param date_col: 时间列的名字
    :return:
    """
    # 先从回测结果中取出真正下单的数据
    buy_date = df[df['投出资金'] > 0][date_col].to_list()
    # 从all_data中保留真正下单买入的数据
    real_buy = all_stock_data[all_stock_data[date_col].isin(buy_date)].copy()

    # 计算每笔交易的净值
    real_buy['持仓每日净值'] = real_buy['未来N日涨跌幅'].apply(_get_hold_net_value, hold_period=hold_period)
    real_buy['最终涨跌幅'] = real_buy['持仓每日净值'].apply(lambda x: x[-1] - 1)

    # 只保留必要的列
    real_buy = real_buy[[date_col, '股票代码', '股票名称', '最终涨跌幅']]

    # 获取盈利最多的数据
    profit_max = real_buy.sort_values(by='最终涨跌幅', ascending=False).head(stock_num).reset_index(drop=True)
    # 获取亏算最大的数据
    loss_max = real_buy.sort_values(by='最终涨跌幅', ascending=True).head(stock_num).reset_index(drop=True)

    return profit_max, loss_max


def merge_html(folder_path, fig_list, strategy_file):
    os.makedirs(folder_path, exist_ok=True)
    # 创建合并后的网页文件
    merged_html_file = os.path.join(folder_path, f'{strategy_file}.html')

    # 创建自定义HTML页面，嵌入fig对象的HTML内容
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
    <meta Charset="UTF-8">
    <style>
        .figure-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
    </style>
    </head>
    <body>"""
    for fig in fig_list:
        # 将fig对象转换为HTML字符串
        if not isinstance(fig, str):
            fig = to_html(fig, full_html=False)
        html_content += f"""
        <div class="figure-container">
            {fig}
        </div>
        """
    html_content += '</body> </html>'

    # 保存自定义HTML页面
    with open(merged_html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    res = os.system('start ' + merged_html_file)
    if res != 0:
        os.system('open ' + merged_html_file)


def draw_bar(data, factor_name_list, indicator):
    fig = px.bar(data, x=factor_name_list[0], y=indicator, title=indicator)
    return fig


def draw_heatmap(data, factor_name_list: list, indicator):
    # 画参数热力图
    temp = pd.pivot_table(data, values=indicator, index=data[factor_name_list[0]], columns=data[factor_name_list[1]])

    fig = px.imshow(temp, title=indicator)

    return fig


def draw_distribution(data, col, bins=50, pic_size=[1500, 800], title=None):
    # 删除空数据
    temp = data[data[col].notnull()][col]
    # 使用Plotly Express创建直方图
    fig = px.histogram(temp, x=temp, nbins=bins, histnorm='percent')
    # 计算中位数
    median = np.median(temp)
    # 添加垂直虚线标记中位数
    fig.add_shape(type='line', x0=median, x1=median, y0=0, y1=1, yref='paper', xref='x',
                  line=dict(color='red', width=2, dash='dash'))
    # 更新图表的宽度和高度
    fig.update_layout(width=pic_size[0], height=pic_size[1], yaxis_title="占比 （%）", xaxis_title=col)

    # 计算累计百分比
    counts, bin_edges = np.histogram(temp, bins=bins)
    cdf = np.cumsum(counts) / len(temp) * 100

    # 创建一个新的trace，将其添加到图表中，并设置y轴为右侧
    fig.add_trace(go.Scatter(x=bin_edges[1:], y=cdf, mode='lines', name='累计占比', yaxis='y2'))
    fig.update_layout(yaxis2=dict(overlaying='y', side='right'), xaxis=dict(domain=[0.0, 0.98]), title_text=title)
    return fig
# endregion
