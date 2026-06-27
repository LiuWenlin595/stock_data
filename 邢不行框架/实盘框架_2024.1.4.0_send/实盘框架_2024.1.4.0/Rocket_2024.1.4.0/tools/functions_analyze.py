import datetime
import os
import pandas as pd
import plotly.graph_objs as go
from plotly.offline import plot
from plotly.subplots import make_subplots


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


def check_analyze_path(ent_path, start=None, end=None):
    path = './分析目录/'
    if not os.path.exists(path):
        os.mkdir(path)
    if not os.path.exists(ent_path):
        print(f'无订单信息，无法分析')
        exit()
    else:
        save_path = path + f'/分析结果_{start.replace("-", "")}-{end.replace("-", "")}/'
        if not os.path.exists(save_path):
            os.mkdir(save_path)
        ent_file_list = get_file_in_folder(ent_path, '.csv')
        file_list = []
        for each_file in ent_file_list:
            if (each_file > f'{start}_订单.csv') and (each_file < f'{end}_订单.csv'):
                file_list.append(each_file)
        print(
            f'滑点分析说明：滑点计算的基准价买入开盘价、卖出收盘价，无论买卖负滑点对自己有利。\n'
            f'分析开始时间{start} 结束时间{end}\n'
            f'输出目录 {save_path}')

        return save_path, file_list


def load_ent_file(ent_path, file_name):
    date_str = file_name.strip('_订单.csv')  # yyyy-mm-dd的str
    ent_file = os.path.join(ent_path, file_name)
    if not os.path.exists(ent_file):
        return pd.DataFrame()
    entrusts_df = pd.read_csv(ent_file, encoding='gbk')
    entrusts_df['成交额'] = entrusts_df['成交均价'] * entrusts_df['成交量']
    entrusts_df['下单额'] = entrusts_df['下单价格'] * entrusts_df['下单量']
    entrusts_df['下单计数'] = 1
    entrusts_df['有成交计数'] = 0
    entrusts_df.loc[entrusts_df['成交额'] > 0, '有成交计数'] = 1
    entrusts_df['买卖'] = '买入'
    entrusts_df.loc[entrusts_df['下单类型'].str.contains('卖出'), '买卖'] = '卖出'
    entrusts_df['订单标记'].fillna(value='非策略选股', inplace=True)
    agg_dict = {'下单计数': 'sum', '有成交计数': 'sum', '成交额': 'sum', '成交量': 'sum', '下单额': 'sum',
                '下单量': 'sum',
                '下单时间': 'first'}

    trade_df = entrusts_df.groupby(['订单标记', '证券代码', '买卖']).agg(agg_dict).reset_index(drop=False)
    trade_df = trade_df[trade_df['成交量'] > 0]  # 新股和撤单都会去掉
    trade_df.rename(columns={'下单时间': '首次下单时间'}, inplace=True)
    trade_df['成交均价'] = trade_df['成交额'] / trade_df['成交量']
    trade_df['下单均价'] = trade_df['下单额'] / trade_df['下单量']
    trade_df['策略名称'] = trade_df['订单标记'].apply(lambda x: x.split('_')[0])  # 这里的策略名称会受order_remark长度限制的影响
    trade_df['交易日期'] = pd.to_datetime(date_str)
    return trade_df


def format_col(df):
    for col_name in ['滑点', '滑点(加权)']:
        if col_name in df.columns:
            df[col_name] = df[col_name].apply(lambda x: '{:.3f}%'.format(x * 100))
    if '成交额' in df.columns:
        df['成交额'] = df['成交额'].apply(lambda x: f'{x / 10000:.2f}')
        df.rename(columns={'成交额': '成交额(万)'}, inplace=True)
    for col_name in ['日均成交额(万)', '日均下单数', '日均成交单数', '日均标的数量', '单均成交额(万)', '滑点收益']:
        if col_name in df.columns:
            df[col_name] = df[col_name].apply(lambda x: f'{x:.2f}')
    if '盈亏' in df.columns:
        df['盈亏'] = df['盈亏'].apply(lambda x: f'{x:.2f}')
    return df


def calc_mean_slip(trade_df, index_df):
    trade_df['股票名称'] = trade_df['股票名称'] + trade_df['滑点'].apply(lambda x: f'{x:.3%}')

    agg_dict = {'成交额': 'sum', '下单计数': 'sum', '有成交计数': 'sum', '证券代码': 'count', '滑点': 'mean',
                '滑点收益': 'sum'}
    # 按日分策略
    daily_strategy_df = trade_df.groupby(['交易日期', '买卖', '策略名称']).agg(agg_dict)
    daily_strategy_df.rename(columns={'证券代码': '标的数量'}, inplace=True)
    daily_strategy_df['滑点(加权)'] = trade_df.groupby(['交易日期', '买卖', '策略名称']).apply(
        lambda x: (x['滑点'] * x['成交额']).sum() / x['成交额'].sum())
    daily_strategy_df['最大滑点标的'] = trade_df.groupby(['交易日期', '买卖', '策略名称']).apply(
        lambda x: x.loc[x['滑点'].idxmax(), '股票名称'])
    daily_strategy_df['最小滑点标的'] = trade_df.groupby(['交易日期', '买卖', '策略名称']).apply(
        lambda x: x.loc[x['滑点'].idxmin(), '股票名称'])
    daily_strategy_df.reset_index(drop=False, inplace=True)

    # 按日不分策略
    daily_df = trade_df.groupby(['交易日期', '买卖']).agg(agg_dict)
    daily_df.rename(columns={'证券代码': '标的数量'}, inplace=True)
    daily_df['滑点(加权)'] = trade_df.groupby(['交易日期', '买卖']).apply(
        lambda x: (x['滑点'] * x['成交额']).sum() / x['成交额'].sum())
    daily_df['最大滑点标的'] = trade_df.groupby(['交易日期', '买卖']).apply(
        lambda x: x.loc[x['滑点'].idxmax(), '股票名称'])
    daily_df['最小滑点标的'] = trade_df.groupby(['交易日期', '买卖']).apply(
        lambda x: x.loc[x['滑点'].idxmin(), '股票名称'])
    daily_df.reset_index(drop=False, inplace=True)

    # 按策略不分日
    trade_df['股票名称'] = trade_df['股票名称'] + '_' + trade_df['交易日期'].dt.strftime('%Y%m%d')
    strategy_df = trade_df.groupby(['买卖', '策略名称']).agg(agg_dict)
    strategy_df.rename(columns={'证券代码': '标的数量'}, inplace=True)
    strategy_df['滑点(加权)'] = trade_df.groupby(['买卖', '策略名称']).apply(
        lambda x: (x['滑点'] * x['成交额']).sum() / x['成交额'].sum())
    strategy_df['最大滑点标的'] = trade_df.groupby(['买卖', '策略名称']).apply(
        lambda x: x.loc[x['滑点'].idxmax(), '股票名称'])
    strategy_df['最小滑点标的'] = trade_df.groupby(['买卖', '策略名称']).apply(
        lambda x: x.loc[x['滑点'].idxmin(), '股票名称'])
    strategy_df.reset_index(drop=False, inplace=True)
    trade_days = index_df.shape[0]
    strategy_df['日均成交额(万)'] = strategy_df['成交额'] / (trade_days * 10000)
    strategy_df['日均下单数'] = strategy_df['下单计数'] / trade_days
    strategy_df['日均成交单数'] = strategy_df['有成交计数'] / trade_days
    strategy_df['日均标的数量'] = strategy_df['标的数量'] / trade_days
    strategy_df['单均成交额(万)'] = strategy_df['成交额'] / (strategy_df['有成交计数'] * 10000)
    strategy_df = strategy_df[['买卖', '策略名称', '滑点', '滑点(加权)', '最大滑点标的', '最小滑点标的',
                               '日均成交额(万)', '日均下单数', '日均成交单数', '单均成交额(万)', '日均标的数量']]
    return daily_strategy_df, daily_df, strategy_df


def basic_earnings_analysis(trade_df):
    print(f'盈利分析不含非策略选股，已包含交易税费')
    # ==== 盈利分析
    for col_name in ['成交额', '成交量']:
        trade_df.loc[trade_df['买卖'] == '卖出', col_name] = -trade_df[col_name]
    # 去掉非策略
    match_trade_df = trade_df[~trade_df['订单标记'].str.contains('非策略选股')].groupby(['订单标记']).agg(
        {'策略名称': 'last', '成交额': 'sum', '成交量': 'sum', '证券代码': 'last', '股票名称': 'last'}).reset_index(
        drop=False)
    # 配对交易
    match_trade_df = match_trade_df[match_trade_df['成交量'] == 0]
    unmatch_trade_df = trade_df[~trade_df['订单标记'].isin(match_trade_df['订单标记'])].copy()
    # 已配对按股票合并
    match_stock_df = match_trade_df.groupby(['证券代码']).agg(
        {'成交额': 'sum', '股票名称': 'last'}).reset_index(drop=False)
    match_stock_df['策略名称'] = match_trade_df.groupby(['证券代码'])['策略名称'].apply(
        lambda x: '-'.join(x.unique())).reset_index(drop=True)
    match_stock_df['股票名称'] = match_stock_df['股票名称'].apply(lambda x: x.split('_')[0])
    match_stock_df.sort_values(by='成交额', ascending=False, inplace=True)
    match_stock_df.rename(columns={'成交额': '盈亏'}, inplace=True)
    match_stock_df['盈亏'] = -match_stock_df['盈亏']
    # 已配对按策略合并
    match_strategy_df = match_trade_df.groupby(['策略名称']).agg(
        {'成交额': 'sum'}).reset_index(drop=False)
    match_strategy_df['标的数量'] = match_trade_df.groupby(['策略名称'])['证券代码'].apply(
        lambda x: len(x.unique())).reset_index(drop=True)
    match_strategy_df.sort_values(by='成交额', ascending=False, inplace=True)
    match_strategy_df.rename(columns={'成交额': '盈亏'}, inplace=True)
    match_strategy_df['盈亏'] = -match_strategy_df['盈亏']
    # 未配对存储
    unmatch_trade_df.sort_values(by='成交额', ascending=False, inplace=True)
    unmatch_trade_df.rename(columns={'成交额': '盈亏'}, inplace=True)
    unmatch_trade_df['盈亏'] = -unmatch_trade_df['盈亏']
    print_text = (f'可配对交易{match_trade_df.shape[0]}组，合计盈利：{match_trade_df["成交额"].sum():.2f}，'
                  f'不可配对及非策略选股交易{unmatch_trade_df.shape[0]}个')
    return match_stock_df, match_strategy_df, unmatch_trade_df, print_text


def daily_slip_pic(_df):
    del _df['滑点']
    _df.rename(columns={'滑点(加权)': '滑点'}, inplace=True)
    fig_list = []
    if '策略名称' not in _df.columns:
        _df['策略名称'] = '按日'
    s_list = list(_df['策略名称'].unique())
    s_list.sort()
    for stg in s_list:
        for direction in ['买入', '卖出']:
            df = _df[(_df['买卖'] == direction) & (_df['策略名称'] == stg)].copy()
            if df.empty:
                continue
            df['累积滑点'] = df['滑点'].cumsum()
            df['累积滑点收益'] = df['滑点收益'].cumsum()
            title = f'{stg if stg != "按日" else ""}{direction} 滑点统计'
            info = (f'累计标的数量{df["标的数量"].sum()}个，合计下单量{df["有成交计数"].sum()}单，'
                    f'平均滑点{df["滑点"].mean():.4%}，累积滑点收益{df["累积滑点收益"].iloc[-1] / 10000:.2f}万')
            add_list = []
            for trade_count, stock_count, max_slip, min_slip in zip(df['有成交计数'], df['标的数量'],
                                                                    df['最大滑点标的'], df['最小滑点标的']):
                add_list.append(
                    f'<br>下单量:{trade_count}<br>标的量:{stock_count}<br>最大{max_slip}<br>最小{min_slip}')
            fig_list.append(
                draw_slip_plotly(df['交易日期'], [df['滑点'], df['滑点收益']], [df['累积滑点'], df['累积滑点收益']],
                                 add_list, title, info))
    return fig_list


def strategy_profit_pic(df, info):
    fig = draw_profit_plotly(df['策略名称'], df['盈亏'], df['标的数量'], title='各策略收益(仅可配对)', info=info)
    return [fig]


# 绘制收益图
def draw_profit_plotly(x, y, add_data, title='', info='', pic_size=[1800, 600]):
    fig = make_subplots(rows=1, cols=1)
    hover_text = []
    for p, c in zip(y, add_data):
        hover_text.append(f'{p / 10000:.2f}万元<br>标的数量：{c}')
    # 添加柱状图轨迹
    fig.add_trace(
        go.Bar(
            x=x,  # X轴数据
            y=y / 10000,  # 第一个y轴数据
            text=[f'{val / 10000:.2f}万元' for val in y],
            hovertext=hover_text,
            hovertemplate='%{hovertext}',  # 百分比格式
            name=y.name,  # 第一个y轴的名字
            marker_color=['red' if val >= 0 else 'green' for val in y],  # 设置颜色
            marker_line_color=['red' if val >= 0 else 'green' for val in y],  # 设置柱状图边框的颜色
            width=1 - 1 / len(x),
        ),
        row=1, col=1, secondary_y=False
    )
    # 更新布局

    fig.update_layout(
        plot_bgcolor='rgb(255, 255, 255)',  # 设置绘图区背景色
        width=pic_size[0],  # 调整宽度
        height=pic_size[1],  # 调整高度
        title={
            'text': title,  # 标题文本
            'x': 0.377,  # 标题相对于绘图区的水平位置
            'y': 0.9,  # 标题相对于绘图区的垂直位置
            'xanchor': 'center',  # 标题的水平对齐方式
            'font': {'color': 'black', 'size': 20}  # 标题的颜色和大小
        },
        xaxis=dict(domain=[0.0, 0.73]),  # 设置 X 轴的显示范围
        legend=dict(
            x=0.8,  # 图例相对于绘图区的水平位置
            y=1.0,  # 图例相对于绘图区的垂直位置
            bgcolor='white',  # 图例背景色
            bordercolor='gray',  # 图例边框颜色
            borderwidth=1  # 图例边框宽度
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor='rgba(255,255,255,0.5)', ),
        annotations=[
            dict(
                x=0.5,  # 文字的 x 轴位置
                y=1.03,  # 文字的 y 轴位置
                xref='x',  # 使用相对布局
                yref='paper',  # 使用相对布局
                text=info,  # 文字内容
                showarrow=False,  # 是否显示箭头
                font=dict(
                    size=14  # 设置文字的字体大小
                )
            ),
            dict(
                text='*盈利分析不含非策略选股，已包含交易税费',  # 备注文字
                x=0.05,  # x坐标位置居中
                y=-0.1,  # y坐标位置为负值，向下偏移
                xref='paper',  # 使用相对布局
                yref='paper',  # 使用相对布局
                showarrow=False,  # 不显示箭头
                font=dict(size=12)  # 备注字体大小
            )
        ]
    )
    # 更新y轴设置，将刻度格式设置为万
    fig.update_yaxes(tickformat=".2f", secondary_y=False)  # 将刻度格式设置为整数形式

    # 将图表转换为 HTML 格式
    return_fig = plot(fig, include_plotlyjs=True, output_type='div')
    return return_fig


# 绘制滑点图
def draw_slip_plotly(x, y1_list, y2_list, add_data_list, title='', info='', pic_size=[1800, 600]):
    '''
    IC画图函数
    :param x: x轴，时间轴
    :param y1_list: 第一个y轴，[0]每周期的滑点,[1]每周期的滑点盈利
    :param y2_list: 第二个y轴，[0]累计滑点,[1]累积盈利
    :param add_data_list: 悬浮框上的信息
    :param title: 图标题
    :param info: 滑点统计字符串
    :param pic_size: 图片大小
    :return:
    '''

    # 创建子图
    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
    # 添加柱状图轨迹
    fig.add_trace(
        go.Bar(
            x=x,  # X轴数据
            y=y1_list[0],  # 第一个y轴数据
            text=y1_list[0],
            name=y1_list[0].name,  # 第一个y轴的名字
            marker_color='#FF9B50',  # 设置颜色
            marker_line_color='#FF9B50',  # 设置柱状图边框的颜色
            hovertemplate='%{text:.3%}',  # 百分比格式
            textposition='none'  # 隐藏文本

        ),
        row=1, col=1, secondary_y=False
    )

    # 添加折线图轨迹
    fig.add_trace(
        go.Scatter(
            x=x,  # X轴数据
            y=y2_list[0],  # 第二个y轴数据
            text=y2_list[0],  # 第二个y轴的文本
            name=y2_list[0].name,  # 第二个y轴的名字
            marker_color='#8B1874',  # 设置颜色
            hovertemplate='%{text:.3%}<br>%{customdata}',  # 百分比格式
            customdata=add_data_list,
        ),
        row=1, col=1, secondary_y=True
    )
    # 添加柱状图轨迹
    colors = ['#FBA1B7' if value >= 0 else '#C8E4B2' for value in y1_list[1]]

    fig.add_trace(
        go.Bar(
            x=x,  # X轴数据
            y=y1_list[1],  # 第一个y轴数据
            text=y1_list[1] / 10000,
            name=y1_list[1].name,  # 第一个y轴的名字
            marker_color=colors,  # 设置颜色
            marker_line_color=colors,  # 设置柱状图边框的颜色
            textposition='none',  # 隐藏文本
            hovertemplate='%{text:.2f}万',  # 百分比格式
            visible="legendonly"

        ),
        row=1, col=1, secondary_y=False
    )

    # 添加折线图轨迹
    fig.add_trace(
        go.Scatter(
            x=x,  # X轴数据
            y=y2_list[1],  # 第二个y轴数据
            text=y2_list[1] / 10000,  # 第二个y轴的文本
            name=y2_list[1].name,  # 第二个y轴的名字
            marker_color='#78C1F3',  # 设置颜色
            hovertemplate='%{text:.2f}万',  # 百分比格式
            visible="legendonly"
        ),
        row=1, col=1, secondary_y=True
    )
    # 更新x轴设置，非交易日在X轴上排除
    date_range = pd.date_range(start=x.min(), end=x.max(), freq='D')
    miss_dates = date_range[~date_range.isin(x)].to_list()
    fig.update_xaxes(rangebreaks=[dict(values=miss_dates)])

    fig.update_yaxes(range=[y1_list[0].min() - 0.01, y1_list[0].max() + 0.01], secondary_y=False, tickformat='.2%')
    fig.update_yaxes(range=[y2_list[0].min() - 0.01, y2_list[0].max() + 0.01], secondary_y=True, tickformat='.2%')
    # 更新布局
    fig.update_layout(
        plot_bgcolor='rgb(255, 255, 255)',  # 设置绘图区背景色
        width=pic_size[0],  # 调整宽度
        height=pic_size[1],  # 调整高度
        title={
            'text': title,  # 标题文本
            'x': 0.377,  # 标题相对于绘图区的水平位置
            'y': 0.9,  # 标题相对于绘图区的垂直位置
            'xanchor': 'center',  # 标题的水平对齐方式
            'font': {'color': 'black', 'size': 20}  # 标题的颜色和大小
        },
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                active=0,
                x=0.885,
                y=1.1,
                buttons=list([
                    dict(label="滑点百分比",
                         method="update",
                         args=[{"visible": [True, True, "legendonly", "legendonly"]},
                               {
                                   "yaxis": {"range": [y1_list[0].min() - 0.01, y1_list[0].max() + 0.01],
                                             "tickformat": '.2%'},
                                   "yaxis2": {"range": [y2_list[0].min() - 0.01, y2_list[0].max() + 0.01],
                                              "tickformat": '.2%',
                                              "overlaying": "y",
                                              "side": "right"}
                               }
                               ]),
                    dict(label="滑点收益",
                         method="update",
                         args=[{"visible": ["legendonly", "legendonly", True, True], },
                               {
                                   "yaxis": {"range": [y1_list[1].min() - abs(y1_list[1].min()) * 0.1,
                                                       y1_list[1].max() + abs(y1_list[1].max()) * 0.1]},
                                   "yaxis2": {"range": [y2_list[1].min() - abs(y2_list[1].min()) * 0.1,
                                                        y2_list[1].max() + abs(y2_list[1].max()) * 0.1],
                                              "overlaying": "y",
                                              "side": "right"}
                               }
                               ]),
                ]),
            )
        ],
        xaxis=dict(domain=[0.0, 0.73]),  # 设置 X 轴的显示范围
        legend=dict(
            x=0.8,  # 图例相对于绘图区的水平位置
            y=1.0,  # 图例相对于绘图区的垂直位置
            bgcolor='white',  # 图例背景色
            bordercolor='gray',  # 图例边框颜色
            borderwidth=1  # 图例边框宽度
        ),
        annotations=[dict(
            x=x.iloc[len(x) // 2],  # 文字的 x 轴位置
            # y=(y1_list[0].max() + 0.01) * 0.9,  # 文字的 y 轴位置
            # x=0.377,
            y=1.03,
            # xref="paper",
            yref="paper",
            text=info,  # 文字内容
            showarrow=False,  # 是否显示箭头
            font=dict(size=14)  # 设置文字的字体大小
        )],
        hovermode="x unified",
        hoverlabel=dict(bgcolor='rgba(255,255,255,0.5)', )
    )

    # 将图表转换为 HTML 格式
    return_fig = plot(fig, include_plotlyjs=True, output_type='div')
    return return_fig


def merge_html(file_path, fig_list, start_date, end_date):
    # 创建合并后的网页文件
    merged_html_file = file_path + f'/交易情况分析.html'

    # 创建自定义HTML页面，嵌入fig对象的HTML内容
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        .body {{
            width: 2000px;
            height:100%;
            }},
        .figure-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
    </style>
    </head>
    <body>
        <h1 style="hight:45px;"></h1>
    <h1 style="margin-left:90px; color: black; font-size: 20px;">{}分析</h1>
    """.format(f'{start_date}至{end_date}交易情况')
    for fig in fig_list:
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


def trans_code(code):
    if code[-3] == '.':
        return code[-2:].lower() + code[:-3]
    else:
        return code[2:] + '.' + code[:2].upper()


def get_days_price(code_list, stock_data_path, bond_data_path, start, end):
    all_data_list = []
    for each_code in code_list:
        if each_code[:2] in ['11', '12', '18']:  # 可转债
            file_path = os.path.join(bond_data_path, each_code + '.csv')
        else:
            file_path = os.path.join(stock_data_path, trans_code(each_code) + '.csv')
        if os.path.exists(file_path):
            df = pd.read_csv(file_path, encoding='gbk', skiprows=1, parse_dates=['交易日期'])
            df = df[(df['交易日期'] >= start) & (df['交易日期'] <= end)]
            df.rename(columns={'可转债简称': '股票名称'}, inplace=True)  # 可转债特别处理
            df['证券代码'] = each_code
            df = df[['交易日期', '证券代码', '股票名称', '前收盘价', '开盘价', '最高价', '最低价', '收盘价']]
            all_data_list.append(df)
    if len(all_data_list) > 0:
        df = pd.concat(all_data_list, ignore_index=True)
        return df
    else:
        return pd.DataFrame()
