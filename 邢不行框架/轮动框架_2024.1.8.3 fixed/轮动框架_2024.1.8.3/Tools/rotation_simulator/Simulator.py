"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import numpy as np
import pandas as pd
import Tools.rotation_simulator.Function as Fun
from joblib import Parallel, delayed
import platform

import dash, os
from dash import html, dcc, ctx
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from dash_iconify import DashIconify
import plotly.express as px
import plotly.graph_objects as go
import matplotlib.colors as mcolors

import dash_mantine_components as dmc

class Simulator():
    def __init__(self, root:dash.Dash, Cfg, show_empty=False):
        self.now_count = Cfg.period_count
        self.period_count = Cfg.period_count
        self.filename = Cfg.shift_bt_file_name
        self.display_factor = ''
        self.root = root
        self.has_factor = False
        self.ftr_btn_dict = {}
        self.show_empty = show_empty
        self.os_type = platform.system()
        self.empty_list = ['empty']
        self.n_jobs = Cfg.n_jobs
        self.stock_data_path = Cfg.stock_data_path
        self.show_stock_return = Cfg.show_stock_return

        sft_df, slt_df, ftr_infos, index_df, slt_stg_list, all_slt_stg_list, hold_stock_df = Fun.load_data(Cfg.sft_bt_path, Cfg.extra_sft_path_list, Cfg.shift_ftr_path, Cfg.slt_bt_path, Cfg.index_path, Cfg.factor_cols, show_empty)
        self.sft_df = sft_df
        self.slt_df = slt_df
        self.ftr_infos = ftr_infos
        self.index_df = index_df
        self.slt_stg_list = slt_stg_list
        self.all_slt_stg_list = all_slt_stg_list
        self.hold_stock_df = hold_stock_df
        self.color_dict = {'None': 'black', '轮动策略': 'blue', '没有下一周期了': 'black'}
        color_list = self.get_color_list()
        for i, _stg in enumerate(all_slt_stg_list):
            if _stg not in self.color_dict.keys():
                self.color_dict[_stg] = color_list[i]
        for i, _stg in enumerate(slt_stg_list):
            if len(_stg.strip().split(' ')) > 1:
                self.color_dict[_stg.strip()] = 'blue'

        if len(self.ftr_infos) > 0:
            self.has_factor = True
            self.display_factor = list(self.ftr_infos.keys())[0]

        self.root.layout = html.Div([
            dmc.Container(
                size="lg",
                children=[
                    html.H1(self.filename, style={"text-align": "center"}),
                    dmc.Grid(
                        children=[
                            dmc.Col(id="graphs-container", span=8),
                            dmc.Col(
                                dmc.Stack([
                                    # dmc.Group：堆叠
                                    dmc.Group([
                                        # dmc.DatePicker：选择日期
                                        dmc.DatePicker(
                                            placeholder="请选择复盘开始时间",
                                            icon=DashIconify(icon="clarity:date-line"),
                                            id="start-date-picker",
                                            maxDate=self.sft_df['交易日期'].iloc[-1],
                                            minDate=self.sft_df['交易日期'].iloc[0],
                                            value=self.sft_df['交易日期'].iloc[0],
                                        ),
                                        dmc.Button(
                                            children="开始",
                                            id="start-button",
                                            n_clicks=0,
                                        ),
                                    ], position="left", spacing="md"),
                                    dmc.Group([
                                        dmc.Button(
                                            "上个周期",
                                            leftIcon=DashIconify(icon="icon-park-outline:to-left"),
                                            id="previous-period-button"
                                        ),
                                        dmc.Button(
                                            "下个周期",
                                            rightIcon=DashIconify(icon="icon-park-outline:to-right"),
                                            id="next-period-button"
                                        ),
                                    ], ),  # spacing="xl", grow=True, mt="lg"
                                    dmc.Stack([
                                        # dmc.Card：创建一个卡片
                                        dmc.Card([
                                            dmc.CardSection(
                                                dmc.Text("当前周期信息", weight="500"),
                                                withBorder=True,
                                                inheritPadding=True,
                                                py="xs"
                                            ),
                                            dmc.Group([
                                                # 通过id更新图片
                                                dmc.Text(
                                                    id="current-strategy-text",
                                                )
                                            ], spacing=0, mt="md"),
                                            dmc.Text(
                                                id="current-period-text"
                                            ),
                                        ], withBorder=True, shadow="sm", radius="md"),
                                        dmc.Card([
                                            dmc.CardSection(
                                                dmc.Text("下一周期信息", weight="500"),
                                                withBorder=True,
                                                inheritPadding=True,
                                                py="xs"
                                            ),
                                            dmc.Group([
                                                dmc.Text(
                                                    id="next-strategy-text",
                                                )
                                            ], spacing=0, mt="md"),
                                            dmc.Text(
                                                id="next-period-text"
                                            ),
                                        ], withBorder=True, shadow="sm", radius="md"),
                                        # 当前周期收益卡片
                                        dmc.Card(id="strategy-return-card", withBorder=True, shadow="sm", radius="md"),
                                        dmc.Card(id="stock-return-card", withBorder=True, shadow="sm", radius="md"),
                                    ]),
                                ]),
                                span=4,
                            ),
                        ]
                    ),
                ])
        ])

        # 注册回调参数
        self.root.callback(
            Output("graphs-container", "children"),
            Output("current-strategy-text", "children"),
            Output("current-strategy-text", "color"),
            Output("current-period-text", "children"),
            Output("next-strategy-text", "children"),
            Output("next-strategy-text", "color"),
            Output("next-period-text", "children"),
            Output("strategy-return-card", "children"),
            Output("stock-return-card", "children"),
            Input("start-button", "n_clicks"),
            Input("previous-period-button", "n_clicks"),
            Input("next-period-button", "n_clicks"),
            State("start-date-picker", "value"),
            # prevent_initial_call=True
        )(self.on_submit_button)
        self.root.callback(
            Output("factor-visual-graph", "figure"),
            Input("factor-select", "value"),
        )(self.on_factor_select)

    def run(self, port):
        self.root.run_server(debug=False, port=port)

    def get_color_list(self):
        color_list = list(mcolors.cnames.keys())
        # 去掉一些颜色太淡的
        del_list = ['aliceblue', 'azure', 'beige', 'blanchedalmond', 'antiquewhite', 'aqua', 'aquamarine', 'bisque', 'cornsilk', 'ivory', 'honeydew', 'lavenderblush']
        first_list = ['red', 'green', 'blue', 'yellow', 'black']
        for color in del_list + first_list:
            if color in color_list:
                color_list.remove(color)
            else:
                print(f'color:{color}不在原本的列表里，不作删除处理（出现该提示可以忽略）')
        color_list = first_list + color_list

        return color_list

    def on_submit_button(self, start_button, previous_button, next_button, date_str):
        if ((start_button is None) and (previous_button is None) and (next_button is None)) or (date_str is None):
            raise PreventUpdate

        button_id = ctx.triggered_id

        if button_id == "previous-period-button":
            self.now_count -= 1
            if self.now_count not in set(self.slt_df['周期'].unique()) & set(self.sft_df['周期'].unique()):
                self.now_count += 1
        elif button_id == "next-period-button":
            self.now_count += 1
            if self.now_count not in set(self.slt_df['周期'].unique()) & set(self.sft_df['周期'].unique()):
                self.now_count -= 1
        else:
            date = pd.to_datetime(date_str)
            period = self.sft_df[self.sft_df['交易日期'] >= date]['周期'].iloc[0]
            self.now_count = period

        return self.refresh_components()

    def refresh_components(self):
        graphs = []
        # 子策略曲线图
        graphs.append(dcc.Graph(
            id="strategy-equity-curve-graph",
            figure=self.create_image(img_type='选股策略'),
            config={'displayModeBar': False}
        ))

        # 因子曲线图
        if self.has_factor:
            select = dmc.Select(
                id="factor-select",
                data=list(self.ftr_infos.keys()),
                value=self.display_factor,
                icon=DashIconify(icon="radix-icons:magnifying-glass"),
                rightSection=DashIconify(icon="radix-icons:chevron-down"),
                style={"width": 200},
                mt="md",
                mb=0,
                ml=40,
            )
            graphs.append(select)
            graphs.append(dcc.Graph(
                id="factor-visual-graph",
                figure=self.create_image(img_type='因子', factor=self.display_factor),
                config={'displayModeBar': False}
            ))

        # 轮动策略曲线图
        graphs.append(dcc.Graph(
            id="rotation-equity-curve-graph",
            figure=self.create_image(img_type='轮动策略'),
            config={'displayModeBar': False}
        ))

        # 指数/BTC蜡烛图绘画
        graphs.append(dcc.Graph(
            id="index-curve-graph",
            figure=self.draw_candle_pic(),
            config={'displayModeBar': False}
        ))

        now_hold, now_period, next_hold, next_period, slt_return_dict = self.get_label_info()

        next_hold = '没有下一周期了' if next_hold == 'None' else next_hold
        next_period = '' if next_period == 'None' else next_period

        return dmc.Stack(id="graphs-stack", children=graphs, spacing=0), \
            now_hold, self.color_dict[now_hold.strip()], now_period, \
            next_hold, self.color_dict[next_hold.strip()], next_period, \
            self.create_strategy_return_components(slt_return_dict, now_hold),\
            self.create_stock_return_components()

    def create_stock_return_components(self):
        elements = []

        elements.append(dmc.CardSection(
            dmc.Text("选择的个股表现", weight="500"),
            withBorder=True,
            inheritPadding=True,
            py="xs"
        ))

        # 控制是否显示个股/币的收益信息
        if not self.show_stock_return:
            elements.append(dmc.Group([
                dmc.Text(
                    '不显示标的信息',
                    color='black'
                ),
            ], mt="md", position="apart")
            )
            return elements

        # 当期持有的个股
        temp_df = self.hold_stock_df[self.hold_stock_df['周期'] == self.now_count]
        # 每个周期的持有股票代码应该是完全一致的，不一致说明有问题
        assert len(temp_df['持有股票代码'].unique()) == 1
        individual_stock_list = temp_df['持有股票代码'].unique()[0].split(' ')

        # b圈用括号分隔
        if '(' in temp_df['持有股票代码'].unique()[0]:
            individual_stock_list = [[i.split('(')[0], i.split('(')[1].split(',')[0], i.split(',')[1].split(')')[0]] for i in individual_stock_list if i]
        # 股票要做指数的处理
        else:
            del_index_list = []
            for index, value in enumerate(individual_stock_list):
                # 如果当期选到了指数，会跟个股/指数拼起来
                if len(value) > 8:
                    temp = value[0:8]
                    if os.path.exists(os.path.join(self.stock_data_path, temp + '.pkl')):
                        individual_stock_list[index] = temp
                    elif os.path.exists(os.path.join(self.stock_data_path, value[-8:] + '.pkl')):
                        individual_stock_list[index] = value[-8:]
                    else:
                        del_index_list.append(index)
                # 如果只选到指数，那么就剔除
                elif not os.path.exists(os.path.join(self.stock_data_path, value + '.pkl')):
                    del_index_list.append(index)
            # 删除指数
            for i in del_index_list:
                individual_stock_list.remove(individual_stock_list[i])

        # 如果当期没有选到个股
        if len(individual_stock_list) < 1:
            elements.append(dmc.Group([
                dmc.Text(
                    '没有选中任何标的',
                    color='black'
                ),
            ], mt="md", position="apart")
            )
            return elements
        # 如果当期空仓
        elif individual_stock_list[0] in self.empty_list:
            elements.append(dmc.Group([
                dmc.Text(
                    '没有选中任何标的',
                    color='black'
                ),
            ], mt="md", position="apart")
            )
            return elements
        else:
            pass
        # 处理异常值
        if '' in individual_stock_list:
            individual_stock_list.remove('')

        start_date = temp_df['交易日期'].iloc[0]
        end_date = temp_df['交易日期'].iloc[-1]
        # 遍历整理策略的数据
        try:  # 如果是pkl文件
            data_path_list = [os.path.join(self.stock_data_path, i + '.pkl') for i in individual_stock_list]
            df_list = Parallel(self.n_jobs)(delayed(pd.read_pickle)(path) for path in data_path_list)
        except:  # 如果是csv文件
            individual_stock_list = {i[0]: [i[1], int(i[2])] for i in individual_stock_list}
            data_path_list = [os.path.join(self.stock_data_path.replace('spot', value[0]), key + '.csv') for key, value in individual_stock_list.items()]
            df_list = Parallel(1)(delayed(pd.read_csv)(path, encoding='gbk', skiprows=1, parse_dates=['candle_begin_time']) for path in data_path_list)
        df = pd.concat(df_list)

        # 如果是b圈数据，要做数据转换
        if 'symbol' in df.columns:
            df = df.rename(columns={'candle_begin_time': '交易日期', 'symbol': '股票代码'})
            df['交易日期'] = df['交易日期'] + pd.Timedelta('1H')
            df['涨跌幅'] = np.where(df['股票代码'] == df['股票代码'].shift(), df['close'].pct_change(), df['close'] / df['open'] - 1)
            df['涨跌幅'].fillna(0, inplace=True)

        df = df[(df['交易日期'] >= start_date) & (df['交易日期'] <= end_date)]
        df = df.groupby('股票代码')['涨跌幅'].apply(lambda x: (1 + x).prod() - 1).reset_index()

        if isinstance(individual_stock_list, dict):
            df['涨跌幅'] = df.apply(lambda x: individual_stock_list[x['股票代码']][1] * x['涨跌幅'], axis=1)
            df['股票代码'] = df.apply(lambda x: x['股票代码'].split('-')[0] + '(' + str(individual_stock_list[x['股票代码']][1]) + ', ' + str(round(x['涨跌幅'] * 100, 2)) + '%)', axis=1)
        else:
            df['股票代码'] = df['股票代码'] + '(' + df['涨跌幅'].apply(lambda x: round(x*100, 2)).astype(str) + '%)'

        df = df.sort_values('涨跌幅', ascending=True).reset_index(drop=True)

        # 如果选股数量太少，没必要展示
        if len(df) <= 1:
            elements.append(dmc.Group([
                dmc.Text(
                    '数量太少，没必要显示',
                    color='black'
                ),
            ], mt="md", position="apart")
            )
            return elements

        # 盈利个股
        elements.append(dmc.Group([
            dmc.Text(
                f'盈利前{min(3, int(len(df) / 2))}的个股',
                color='red'
            ),
            dmc.Text(
                f'亏损前{min(3, int(len(df) / 2))}的个股',
                color='green'
            ),
        ], mt="md", position="apart")
        )
        for i in range(min(3, int(len(df) / 2))):
            elements.append(dmc.Group([
                dmc.Text(
                    df.iloc[-i - 1, 0],
                    color='red' if df.iloc[-i - 1, 1] > 0 else 'green'
                ),
                dmc.Text(
                    df.iloc[i, 0],
                    color='red' if df.iloc[i, 1] > 0 else 'green'
                ),
            ], mt="md", position="apart")
            )

        return elements

    def create_strategy_return_components(self, return_dict, now_hold):
        elements = []

        elements.append(dmc.CardSection(
            dmc.Text("当前周期收益", weight="500"),
            withBorder=True,
            inheritPadding=True,
            py="xs"
        ))

        # 如果当期选中了多个子策略，需要重算轮动策略的收益
        if len(now_hold.split(' ')) > 2:
            chos_stg = now_hold.split(' ')
            if '' in chos_stg:
                chos_stg.remove('')
            temp_rtn_list = []
            for stg in chos_stg:
                if stg in return_dict.keys():
                    temp_rtn_list.append(return_dict[stg][0])
            rotation_rtn = np.mean(temp_rtn_list)
            now_return = round(rotation_rtn * 100, 2)
        else:
            now_return = round(return_dict[now_hold.replace(' ', '')][0] * 100, 2)
        return_list = [now_return/100]
        elements.append(dmc.Group([
            dmc.Text(
                "轮动策略:",
                color='blue'
            ),
            dmc.Text(
                f"{now_return}%",
                color="blue",
            ),
        ], mt="md", position="apart")
        )

        for strategy_name in self.all_slt_stg_list:
            if strategy_name in self.empty_list and self.show_empty == False:
                continue
            slt_return = round(return_dict[strategy_name][0] * 100, 2)
            return_text = f'{slt_return}%' if strategy_name not in self.empty_list else '0%'
            strategy_text = strategy_name

            if '多头' in strategy_text or '多空' in strategy_text:
                elements.append(dmc.Group([
                    dmc.Text(
                        strategy_text,
                        color='red' if '多头' in strategy_text else 'green',
                        weight='bold' if strategy_text in now_hold else 'normal'
                    ),
                    dmc.Text(
                        return_text,
                        color='red' if '多头' in strategy_text else 'green',
                        weight='bold' if strategy_text in now_hold else 'normal'
                    ),
                ], position="apart"))
            else:
                elements.append(dmc.Group([
                    dmc.Text(
                        strategy_text,
                        color='black',
                        weight='bold' if strategy_text in now_hold else 'normal'
                    ),
                    dmc.Text(
                        return_text,
                        color='black',
                        weight='bold' if strategy_text in now_hold else 'normal'
                    ),
                ], position="apart"))
            return_list.append(slt_return/100)

        justify_txt, justify_color = self.get_result_justify(return_list)
        elements.append(
            dmc.Text(justify_txt, color=justify_color, mt="md", weight="500")
        )

        return elements

    def get_result_justify(self, return_list):

        if return_list[0] == max(return_list):
            # 选中的减去最差的大于3%，并且最差的策略涨了3%以上
            if return_list[0] - min(return_list) > 0.03 and min(return_list) < -0.03:
                justify_txt = '选对了!避开大跌!'
            # 选中的减去最差的大于3%，并且选中的策略涨了3%以上
            elif return_list[0] - min(return_list) > 0.03 and return_list[0] > 0.03:
                justify_txt = '选对了!吃到大涨!'
            else:
                justify_txt = '选对了！'
            justify_color = 'red'
        else:
            # 最优的减去选中的大于3%，并且最优的策略涨了3%以上
            if max(return_list) - return_list[0] > 0.03 and max(return_list) > 0.03:
                justify_txt = '选错了!错过大涨!'
            # 最优的减去选中的大于3%，并且选中的策略跌了3%以上
            elif max(return_list) - return_list[0] > 0.03 and return_list[0] < -0.03:
                justify_txt = '选错了!吃到暴跌!'
            else:
                justify_txt = '选错了...'
            justify_color = 'green'

        return justify_txt, justify_color

    def on_factor_select(self, value):
        if value is None:
            raise PreventUpdate
        self.display_factor = value

        return self.create_image(img_type='因子', factor=value)

    def create_image(self, img_type, factor=''):
        start = self.now_count - self.period_count
        end = self.now_count
        y_label = '净值'
        pct = True
        if img_type == '选股策略':
            pic_df = self.slt_df[(self.slt_df['周期'] >= start) & (self.slt_df['周期'] <= end)]
            data_cols = [col for col in pic_df.columns if col not in ['交易日期', '周期', 'empty']]
            title = '子策略资金曲线图'
        elif img_type == '轮动策略':
            if '涨跌幅' in self.sft_df.columns:
                pic_df = self.sft_df[(self.sft_df['周期'] >= start) & (self.sft_df['周期'] <= end)].rename(
                    columns={'涨跌幅': '轮动策略'})
                data_cols = {'轮动策略': '轮动策略'}
                title = '轮动策略资金曲线图'
            else:
                pic_df = self.sft_df[(self.sft_df['周期'] >= start) & (self.sft_df['周期'] <= end)]
                data_cols = [col for col in pic_df.columns if col not in ['交易日期', '策略名称', '周期']]
                title = '轮动策略资金曲线图'
        else:
            if factor == '':
                factor = self.display_factor
            pic_df = self.ftr_infos[factor].copy()
            pic_df = pic_df[(pic_df['周期'] >= start) & (pic_df['周期'] <= end)]
            data_cols = [col for col in pic_df.columns if col not in ['交易日期', '周期']]
            y_label = '因子值'
            pct = False
            title = f'因子：{factor}'
        if img_type == '选股策略' or img_type == '轮动策略':
            pic = self.draw_curve(pic_df, data_cols, self.color_dict, title, y_label, pct=pct, show_number=False)
        else:
            pic = self.draw_curve(pic_df, data_cols, self.color_dict, title, y_label, pct=pct, show_number=True)

        return pic

    @staticmethod
    def draw_curve(df, data_cols, color_dict, title=None, y_label='净值', font_size=12, pct=False, show_number=False):
        """
        绘制策略曲线
        :param df: 包含净值数据的df
        :param data_cols: 要展示的数据字典格式：｛图片上显示的名字:df中的列名｝
        :param font_size: 字体大小
        :param pct: datadict中的数据是否为涨跌幅，True表示涨跌幅，False表示净值
        :param title: 标题
        :param y_label: Y轴的标签
        :return:
        """
        # 复制数据
        draw_df = df.copy()

        data_dict = {}
        if isinstance(data_cols, list):
            for item in data_cols:
                data_dict[item] = item
        else:
            data_dict = data_cols

        # 将周期转换点标记出来
        draw_df['标记点'] = (draw_df['周期'] != draw_df['周期'].shift(-1))

        # 绘制左轴数据
        if pct:
            for key in data_dict:
                draw_df[data_dict[key]] = (draw_df[data_dict[key]] + 1).fillna(1).cumprod()

        fig = px.line(draw_df, x="交易日期", y=pd.Index(data_dict.values()), title=None, height=200, color_discrete_map=color_dict)

        # 选择标记点所在行，并创建散点图数据
        marker_points = draw_df[draw_df['标记点']==True]
        for column in data_dict.values():
            # 为每一列添加散点标记
            scattered_trace = go.Scatter(x=marker_points['交易日期'], y=marker_points[column],
                                         mode='markers', marker=dict(size=7, color=color_dict.get(column)))
            # 将散点图 trace 添加到现有 figure 中
            fig.add_trace(scattered_trace)

        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                          xaxis_title=None,
                          yaxis_title=title,
                          title_x=0,
                          legend=dict(orientation="h",
                                      yanchor="bottom",
                                      y=1.02,
                                      xanchor="right",
                                      x=1),
                          hovermode="x unified")
        # if show_number:
        #     # 获取最后5行数据
        #     last_5_rows = draw_df.iloc[-5:]
        #
        #     annotations = []
        #     for key in data_dict:
        #         # 添加注释到每个点，可以根据实际情况调整注释内容
        #         for i, row in last_5_rows.iterrows():
        #             annotations.append(dict(
        #                 x=row['交易日期'],
        #                 y=row[key],
        #                 text=f"{round(row[key], 2)}",
        #                 showarrow=False,
        #             ))
        #
        #         fig.update_layout(annotations=annotations)

        return fig

    def draw_candle_pic(self):
        start = self.now_count - self.period_count
        end = self.now_count
        pic_df = self.index_df[(self.index_df['周期'] >= start) & (self.index_df['周期'] <= end)]
        # 设置数据
        fig = go.Figure(data=[go.Candlestick(x=pic_df['交易日期'],
                                             open=pic_df['open'],
                                             high=pic_df['high'],
                                             low=pic_df['low'],
                                             close=pic_df['close'],
                                             increasing=dict(fillcolor='red', line_color='red'),
                                             decreasing=dict(fillcolor='green', line_color='green')
                                             )])
        # 设置图形属性
        fig.update_layout(title=None,
                          yaxis_title='指数',
                          xaxis_rangeslider_visible=False,
                          margin=dict(l=0, r=0, t=0, b=0),
                          title_x=0,
                          legend=dict(orientation="h",
                                      yanchor="bottom",
                                      y=1.02,
                                      xanchor="right",
                                      x=1),
                          hovermode="x unified",
                          height=190
                          )

        return fig

    def get_label_info(self, need_show_next_return=False):
        now_hold = str(self.sft_df[self.sft_df['周期'] == self.now_count]['策略名称'].iloc[0])
        now_start = str(self.sft_df[self.sft_df['周期'] == self.now_count]['交易日期'].iloc[0])[:-3]
        now_end = str(self.sft_df[self.sft_df['周期'] == self.now_count]['交易日期'].iloc[-1])[:-3]
        now_period = f'{now_start} - {now_end}'

        if self.now_count + 1 not in self.sft_df['周期'].unique():
            next_hold = 'None'
            next_period = 'None'
        else:
            next_hold = str(self.sft_df[self.sft_df['周期'] == self.now_count + 1]['策略名称'].iloc[0])
            next_start = str(self.sft_df[self.sft_df['周期'] == self.now_count + 1]['交易日期'].iloc[0])[:-3]
            next_end = str(self.sft_df[self.sft_df['周期'] == self.now_count + 1]['交易日期'].iloc[-1])[:-3]
            next_period = f'{next_start} - {next_end}'

        now_return = self.slt_df.loc[(self.slt_df['周期'] == self.now_count), self.slt_df.columns.isin(self.all_slt_stg_list)].apply(lambda x: (1+x).prod() - 1)
        if need_show_next_return:
            if self.now_count + 1 not in self.sft_df['周期'].unique():
                next_return = now_return.copy() * 0
            else:
                next_return = self.slt_df.loc[
                    (self.slt_df['周期'] == self.now_count + 1), self.slt_df.columns.isin(self.slt_stg_list)].apply(
                    lambda x: (1 + x).prod() - 1)
        slt_return_dict = {}
        for stg_name in self.all_slt_stg_list:
            if need_show_next_return:
                slt_return_dict[stg_name] = [now_return[stg_name], next_return[stg_name]]
            else:
                slt_return_dict[stg_name] = [now_return[stg_name]]

        return now_hold, now_period, next_hold, next_period, slt_return_dict
