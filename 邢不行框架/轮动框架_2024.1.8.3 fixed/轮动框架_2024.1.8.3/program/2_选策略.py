"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import sys
import os
import warnings
import traceback
import pandas as pd
import numpy as np
import program.Config as Cfg
import program.Evaluate as Eva
import program.Function as Fun
import program.Rainbow as Rb

warnings.filterwarnings('ignore')
pd.set_option('expand_frame_repr', False)  # 当列太多时不换行
pd.set_option('display.max_rows', 5000)  # 最多显示数据的行数

# =====判断是否是手工运行本程序
if_manual = True  # 默认手工运行
if len(sys.argv) > 1:
    Cfg.sft_stg_file = sys.argv[1]  # 外出输入的参数：跑哪个策略
    Cfg.trading_mode = True if sys.argv[2] == 'True' else False  # 外出输入的参数：是否要运行所有的周期
    stg_param = Fun.str_to_list(sys.argv[3])  # 外出输入的参数：策略参数，字符串格式，需要到策略内部去解析
    save_result = True if sys.argv[4] == 'True' else False  # 外出输入的参数：是否保存结果
    if_manual = False  # 如果有外部输入，即为程序调用，不是手工运行程序
else:
    stg_param = [0]  # 策略参数，字符串格式，需要到策略内部去解析
    save_result = True

try:
    # 合并不同offset及合并做图用
    equity_list = []
    fig_list = []
    # 导入策略
    cls = __import__(f'program.轮动策略.{Cfg.sft_stg_file}', fromlist=('',))

    # 载入周期offset的csv，根据对应周期
    per_oft_df = Fun.read_period_and_offset_file(Cfg.period_offset_file)

    # 遍历策略中所有文件后缀名称
    for po_param in cls.strategy_param:
        po_param = po_param.replace('.csv', '')
        per_oft = po_param.split('_')[0] + '_' + po_param.split('_')[1]

        # ===导入数据
        # 导入基准策略的数据：这里载指数
        # 只有在选股日（选策略日），才写实盘数据，否则不写。
        # 特别注意，只有在date_end=None的时候，才会写实盘
        bench_data, is_open = Fun.import_benchmark_data(Cfg.index_path, per_oft_df, per_oft, start=Cfg.date_start,
                                                        end=Cfg.date_end, is_index=True)
        Rb.record_log(f'脚本1：基准起始时间:{bench_data["交易日期"].min()},基准结束时间:{bench_data["交易日期"].max()}')
        if Cfg.trading_mode and (not is_open):  # 实盘模式不在正确周期则跳过
            Rb.record_log(f'实盘模式，per_oft：{per_oft}  不计算')
            continue
        Rb.record_log('\n' + '=' * 10 + f'正在回测：{cls.name}  {per_oft}  {cls.select_count}' + '=' * 10)

        # 从pkl文件中读取整理好的所有股票数据
        df = pd.read_pickle(os.path.join(Cfg.root_path, f'data/数据整理/all_strategy_data_{po_param}.pkl'))
        # 记录最大的交易日期
        select_date = df['交易日期'].max()
        Rb.record_log(f'脚本2：原始数据截止时间：{select_date}')
        df = df[(df['交易日期'] >= bench_data['交易日期'].min()) & (df['交易日期'] <= bench_data['交易日期'].max())]
        # 获取子策略的名称
        df['子策略名称'] = df['策略名称'].apply(lambda x: Fun.get_sub_stg_name(x))
        # 看看策略是不是只需要特定的字策略
        if hasattr(cls, "sub_stg_list"):
            if len(cls.sub_stg_list) > 0:
                df = df[df['子策略名称'].isin(cls.sub_stg_list)]

        # 选出每周需要的策略
        df, df_for_group = cls.filter_and_select_strategies(df, cls.select_count, stg_param)
        # 检查是否为空数据
        if df.empty:
            Rb.record_log(f'策略{cls.name}周期{per_oft}参数{stg_param},经过filter_and_select_strategies后已经变成空数据。\n'
                          f'请检查{cls.name}.filter_and_select_strategies函数是否有bug\n'
                          f'例如：指定了只做【小市值】和【大市值】的轮动，但是原始数据中不包含这个两个策略\n'
                          f'本次回测已经跳过')
            continue

        # 匹配选中的股票数据
        df = Fun.get_stock_data(df, Cfg, per_oft, is_open)
        # 如果策略有选股后的流程
        if hasattr(cls, "after_select"):
            df = cls.after_select(df)
            if df.empty:
                Rb.record_log(f'策略{cls.name}周期{per_oft}参数{stg_param},经过after_select后已经变成空数据。\n'
                              f'请检查{cls.name}.after_select函数是否有bug\n'
                              f'本次回测已经跳过')
                continue

        # 保存最新的实盘结果
        new_select_stock = df[df['下周期每天涨跌幅'].isna() & (df['交易日期'] == select_date) & (df['signal'] == 1)].copy()
        # 删除数据
        df.dropna(subset=['下周期每天涨跌幅'], inplace=True)
        df_for_group.dropna(subset=['下周期每天涨跌幅'], inplace=True)

        # 获取数据的截止时间
        date_max = Fun.get_date_max(df, per_oft_df)
        bench_data = bench_data[bench_data['交易日期'] <= date_max].copy()

        # 只有在选股日，且date_end为最新的时候才会保存选股结果
        if save_result and is_open and pd.isnull(Cfg.date_end):
            res_file_name = f'{cls.name}_{po_param.replace(".csv", "")}_{cls.select_count}.csv'
            sft_stg_path = os.path.join(Cfg.root_path, f'data/每日选股/轮动策略/{res_file_name}')
            Fun.save_shift_result(sft_stg_path, new_select_stock, per_oft_df, is_open, Cfg.end_exchange, select_date)

        # 计算手续费
        select_stock = Fun.cal_fee_rate(df, Cfg)
        # 在数据上加上策略名称
        df['策略名称'] += ' '
        hold_stg_name = df.groupby('交易日期')['策略名称'].apply(lambda x: x.unique().sum())

        # 计算下周期整体涨跌幅
        select_stock['选股下周期涨跌幅'] = select_stock['选股下周期每天资金曲线'].apply(lambda x: x[-1] - 1)
        # 计算下周期每天的涨跌幅
        select_stock['选股下周期每天涨跌幅'] = select_stock['选股下周期每天资金曲线'].apply(
            lambda x: list(pd.DataFrame([1] + x).pct_change()[0].iloc[1:]))

        # 为了防止有的周期没有选出股票，创造一个空的df，用于填充不选股的周期
        empty_df = Fun.create_empty_data(bench_data, per_oft, per_oft_df)
        # 将选股结果更新到empty_df上
        empty_df.update(select_stock)
        select_stock = empty_df
        # 合并策略名称
        select_stock['策略名称'] = hold_stg_name

        # 从第一个选股结果不为0的地方开始
        select_stock = select_stock[select_stock['股票数量'].cumsum() > 0]

        # 计算整体资金曲线
        select_stock.reset_index(inplace=True)
        select_stock['资金曲线'] = (select_stock['选股下周期涨跌幅'] + 1).cumprod()

        # =====计算选中股票每天的资金曲线
        #  将选股的资金曲线和大盘指数合并
        equity = pd.merge(left=bench_data, right=select_stock[['交易日期', '买入股票代码', '策略名称']], on=['交易日期'], how='left',
                          sort=True)
        # 轮动策略没选中策略时，要把策略名称为空的地方也设置为empty
        con1 = equity['买入股票代码'] == 'empty'
        con2 = equity['策略名称'].isna()
        equity.loc[con1 & con2, '策略名称'] = 'empty'

        # 做些数据整理
        equity['持有股票代码'] = equity['买入股票代码'].shift()
        equity['策略名称'] = equity['策略名称'].shift()
        if not new_select_stock.empty:
            equity = equity[equity['交易日期'] <= new_select_stock['交易日期'].max()]
        equity['持有股票代码'].fillna(method='ffill', inplace=True)
        equity['策略名称'].fillna(method='ffill', inplace=True)
        equity.dropna(subset=['持有股票代码'], inplace=True)
        del equity['买入股票代码']

        # 计算全部资金曲线和基准曲线
        equity['涨跌幅'] = select_stock['选股下周期每天涨跌幅'].sum()
        equity['equity_curve'] = (equity['涨跌幅'] + 1).cumprod()
        equity['benchmark'] = (equity['基准涨跌幅'] + 1).cumprod()

        equity_file_name = f'{cls.name}_{po_param.replace(".csv", "")}_{cls.select_count}.csv'
        equity_path = os.path.join(Cfg.root_path, f'data/回测结果/轮动策略/{equity_file_name}')

        equity.to_csv(equity_path, encoding='gbk', index=False)
        equity_list.append(equity)
        # ===计算策略评价指标
        rtn, year_return, month_return = Eva.strategy_evaluate(equity, select_stock)
        rtn_path = os.path.join(Cfg.root_path, f'data/回测结果/统计信息/{Cfg.sft_stg_file}_策略评价_{po_param}.csv')
        rtn.to_csv(rtn_path, encoding='GBK')
        year_return_path = os.path.join(Cfg.root_path, f'data/回测结果/统计信息/{Cfg.sft_stg_file}_year_{po_param}.csv')
        year_return.to_csv(year_return_path, encoding='GBK')
        print(rtn)
        print(year_return)

        # 将计算结果保存一下
        Fun.save_back_test_result(cls, per_oft, stg_param, rtn, year_return, Cfg.root_path)

        describe = Eva.strategies_describe(equity, df)
        describe_path = os.path.join(Cfg.root_path, f'data/回测结果/统计信息/{Cfg.sft_stg_file}_describe_{po_param}.csv')
        describe.to_csv(describe_path, encoding='GBK', index=False)
        print(describe)

        if if_manual:
            # ===画图
            title = f'{Cfg.sft_stg_file.split("_")[0]} per_oft：{per_oft} 选策略个数：{cls.select_count}' \
                    f'区间:{equity.index.min().date().strftime("%y%m%d")}-{equity.index.max().date().strftime("%y%m%d")}  ' \
                    f'换仓模式:{Cfg.buy_method}-{"日内" if Cfg.intraday_swap else "非日内"}'
            fig = Eva.draw_equity_curve_plotly(equity, data_dict={'策略表现': 'equity_curve', '指数': 'benchmark'},
                                               right_axis={'回撤曲线': 'dd2here'}, title=title, rtn_add=rtn,
                                               pic_size=[1500, 550])
            fig_list.append(fig)
            # 分组测试稳定性
            fig = Eva.robustness_test(df_for_group, bins=5, year_return_add=year_return, pic_size=[1500, 550])
            fig_list.append(fig)

    if (not Cfg.trading_mode) and if_manual:
        # 做合并曲线
        if len(equity_list) > 1:
            # 由于前面的index载入起始时间都不同，所以这里重载指数
            index_data = pd.read_csv(Cfg.index_path, parse_dates=['candle_end_time'], encoding='gbk')
            index_data['基准涨跌幅'] = index_data['close'].pct_change()
            index_data.rename(columns={'candle_end_time': '交易日期'}, inplace=True)
            # 资金曲线做合并
            equity = Fun.merge_offset(equity_list, index_data)
            # ===计算策略评价指标
            rtn, year_return, month_return = Eva.strategy_evaluate(equity, pd.DataFrame())
            title = Cfg.sft_stg_file.split('_')[0] + f' 周期offset个数{len(cls.strategy_param)} 选策略个数：{cls.select_count}'
            fig = Eva.draw_equity_curve_plotly(equity, data_dict={'策略表现': 'equity_curve', '指数': 'benchmark'},
                                               right_axis={'回撤曲线': 'dd2here'}, title=title, rtn_add=rtn,
                                               pic_size=[1500, 550])
            fig_list = [fig] + fig_list
        # 储存并打开策略结果html
        Eva.merge_html(os.path.join(Cfg.root_path, 'data/绘图信息/策略资金曲线'), fig_list, Cfg.sft_stg_file.split('_')[0])
except Exception as err:
    err_txt = traceback.format_exc()
    err_msg = Rb.match_solution(err_txt, False)
    raise ValueError(err_msg)
