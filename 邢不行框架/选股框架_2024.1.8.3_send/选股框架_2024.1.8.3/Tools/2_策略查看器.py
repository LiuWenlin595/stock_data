'''
2024分享会
author: 邢不行
微信: xbx6660
'''

import ast
import os
import warnings

import numpy as np
import pandas as pd

from Tools.utils import sFunctions as Fun
from program import Config as Cfg
from program import Rainbow as Rb
import traceback

warnings.filterwarnings('ignore')

# =====需要配置的参数
start = '2020-03-01'  # 分析开始时间
end = '2021-02-28'  # 分析结束时间
add_days = 120  # 画K线的数据前后增加多少天
filename = '小市值_W_0_30.pkl'  # /data/分析目录/待分析目录下的文件
factors = {'EP': []}  # 策略中不存在，但是你需要的因子

# 主图增加,均为折线图。除指数外，均需要在cal_factors中可被计算出
add_factor_main_list = [
    {'因子名称': '指数', '次坐标轴': True},
]

# 附图增加，一个dict为一个子图
# 因子名称的list大于1个值，则会被画在同一个图中，没用次坐标轴概念
# 图形样式有且仅有三种选择K线图\柱状图\折线图
add_factor_sub_list = [
    {'因子名称': ['价格分位数_60', '价格分位数_250'], '图形样式': '折线图'},
    {'因子名称': ['EP'], '图形样式': '折线图'},
    {'因子名称': ['Ret因子_5', 'Ret因子_10'], '图形样式': '折线图'},
]
# 按因子名称指定颜色，K线展示的内容固定颜色指定无效。
# 颜色仅为plotly支持的颜色格式，基本上你知道的颜色相关的英文单词都有，没有会报错。
# 不指定颜色会随机配色
color_dict = {'指数': 'red', '成交额': 'blue', '价格分位数': 'green', 'Ret_5': 'royalblue'}

try:
    # =====以下内容请勿修改
    per_oft = filename.split('_')[-3] + '_' + filename.split('_')[-2]
    select_path = os.path.join(Cfg.root_path, f'data/分析目录/待分析/{filename.replace(".csv", ".pkl")}')
    period, offset, select_count = filename.replace('.csv', '').split('_')[-3:]  # 为了防止某些策略里本来就有_，所以用-4
    strategy_name = filename.split(f'_{period}_{offset}_{select_count}')[0]
    cls = __import__(f'program.选股策略.{strategy_name}', fromlist=('',))

    # ===读取数据 & 截取数据
    # 读取数据
    select = pd.read_pickle(select_path)
    select.dropna(subset=['下周期每天涨跌幅'], inplace=True)
    # 只保留分析区间内的数据
    select = select[select['交易日期'] >= pd.to_datetime(start)]
    select = select[select['交易日期'] <= pd.to_datetime(end)]
    # 只保留策略开仓时的策略
    select = select[select['signal'] == 1]

    # 载入周期数据，处理买卖日期
    period_and_offset_df = Fun.read_period_and_offset_file(Cfg.period_offset_file)
    period_and_offset_df['group'] = period_and_offset_df[f'{period}_{offset}'].copy()
    period_and_offset_df['持有开始'] = period_and_offset_df['交易日期'].copy()
    period_and_offset_df['持有到期'] = period_and_offset_df['交易日期'].copy()
    period_and_offset_df.loc[period_and_offset_df['group'] < 0, '持有到期'] = None
    period_and_offset_df['持有天数'] = 1
    period_and_offset_df.loc[period_and_offset_df['group'] < 0, '持有天数'] = 0
    period_and_offset_df['group'] = period_and_offset_df['group'].abs()
    po_df = period_and_offset_df.groupby(['group']).agg(
        {'持有开始': 'first', '持有到期': 'last', '交易日期': 'last', '持有天数': 'sum'}).reset_index()
    po_df['持有周期'] = po_df['持有开始'].dt.date.apply(str) + '--' + po_df['持有到期'].dt.date.apply(str)
    po_df['持有周期'] = po_df['持有周期'].shift(-1)
    po_df['持有天数'] = po_df['持有天数'].shift(-1)
    select = pd.merge(left=select, right=po_df[['交易日期', '持有周期', '持有天数']], on='交易日期', how='left')

    # 这里一定要重算一下，原本的下周期涨跌幅是尾盘买，这里改成buy_method模式，否则后面是对不平的
    select['下周期涨跌幅'] = select['下周期每天涨跌幅'].apply(lambda x: np.prod(np.array(x) + 1) - 1)
    groups = select.groupby(['股票代码'])
    res_list = []  # 储存分组结果的list
    # 遍历各个分组
    for t, g in groups:
        # ===分组处理数据
        g.sort_values(by='交易日期', inplace=True)

        # ===统计结果
        res = pd.DataFrame()  # 需要返回的结果
        res.loc[0, '股票代码'] = t  # 股票代码
        res.loc[0, '股票名称'] = g['股票名称'].iloc[-1]
        res.loc[0, '选中次数'] = len(g['交易日期'].unique())
        res.loc[0, '累计持股天数'] = g['持有天数'].sum()
        res.loc[0, '累计持股收益'] = (g['下周期涨跌幅'] + 1).prod() - 1
        res.loc[0, '次均收益率_复利'] = (res.loc[0, '累计持股收益'] + 1) ** (1 / res.loc[0, '选中次数']) - 1
        res.loc[0, '次均收益率_单利'] = g['下周期涨跌幅'].mean()
        res.loc[0, '日均收益率_复利'] = (res.loc[0, '累计持股收益'] + 1) ** (1 / res.loc[0, '累计持股天数']) - 1
        res.loc[0, '日均收益率_单利'] = np.sum(g['下周期每天涨跌幅'].sum()) / res.loc[0, '累计持股天数']
        res.loc[0, '首次选中时间'] = g['交易日期'].dt.date.iloc[0]
        res.loc[0, '最后选中时间'] = g['交易日期'].dt.date.iloc[-1]
        res['持有周期'] = ''  # 小tips：需要往DataFrame的cell里面插入list，这一列需要是object类型（所以这里给了''，字符串就是object）
        res.at[0, '持有周期'] = g['持有周期'].to_list()  # 往数据中插入list时，需要用at函数，loc不行。

        # 将计算的结果添加到结果汇总中
        res_list.append(res)

    # =====汇总所有结果，再按照方向拆成多头和空头
    # 汇总所有分组的分析结果
    all_res = pd.concat(res_list, ignore_index=True)

    # =====针对分析结果进行进一步分析
    describe = pd.DataFrame()  # 分析结果储存的df

    # 1.分析数据
    describe.loc[0, '选股数'] = all_res.shape[0]
    describe.loc[0, '平均选中次数'] = all_res['选中次数'].mean()
    describe.loc[0, '平均累计持股天数'] = all_res['累计持股天数'].mean()
    describe.loc[0, '平均日均收益率'] = all_res['日均收益率_复利'].mean()
    describe.loc[0, '平均次均收益率'] = all_res['次均收益率_复利'].mean()
    describe.loc[0, '平均持股累计收益'] = all_res['累计持股收益'].mean()
    describe.loc[0, '选股胜率'] = all_res[all_res['累计持股收益'] > 0].shape[0] / describe.loc[0, '选股数']
    # 打印分析结果
    print(describe.T)

    # =====结果保存
    # 保存数据的文件夹是否存在
    save_path = os.path.join(Cfg.root_path, f'data/分析目录/分析结果/{strategy_name}_{offset}_{start}_{end}/')
    os.makedirs(save_path, exist_ok=True)
    # 保存数据
    describe.T.to_csv(os.path.join(save_path, '02_分析汇总.csv'), encoding='gbk', header=False)

    # 绘制的时候K线向历史前后多扩展add_days天
    # K线开始时间
    d_start = pd.to_datetime(start) - pd.to_timedelta(f'{add_days}d')  # 日线数据开始时间
    # K线结束时间
    d_end = pd.to_datetime(end) + pd.to_timedelta(f'{add_days}d')  # 日线数据结束时间

    # 导入上证指数
    index_data = Fun.import_index_data(Cfg.index_path)
    _index_data = index_data[(index_data['交易日期'] >= d_start) & (index_data['交易日期'] <= d_end)].copy()
    fig_save_path = os.path.join(save_path, '选股行情图/')
    os.makedirs(fig_save_path, exist_ok=True)

    total_stock_num = all_res.shape[0]
    all_add_factor = [item['因子名称'] for item in add_factor_main_list] + \
                     [name for item in add_factor_sub_list for name in item['因子名称']]
    all_add_factor = list(set(all_add_factor))

    # 开始遍历每一行数据画图
    for i in all_res.index:
        # 获取币种名称
        code = all_res.loc[i, '股票代码']
        name = all_res.loc[i, '股票名称']
        print(f'正在绘制：第{i + 1}/{total_stock_num}个 {code}_{name}')
        # 读取股票信息
        df = Fun.load_back_test_daily_data(cls, os.path.join(Cfg.factor_path, '日频数据/'), code, factors, per_oft)
        if '指数' in all_add_factor:
            df = pd.merge(left=df, right=index_data, on='交易日期', how='left', sort=True, indicator=True)

        # 把因子排名从select里合入（如果有的话）
        rank_add_factor = []
        for each_factor in all_add_factor:
            if each_factor + '_排名' in select.columns:
                rank_add_factor.append(each_factor + '_排名')
        if len(rank_add_factor) > 0:
            df = pd.merge(left=df, right=select[['股票代码', '交易日期'] + rank_add_factor],
                          on=['股票代码', '交易日期'], how='left')
        df = df[(df['交易日期'] >= d_start) & (df['交易日期'] <= d_end)]
        # 获取所有的买入时间点
        open_times = [pd.to_datetime(time_range.split('--')[0]) for time_range in all_res.loc[i, '持有周期']]
        # 获取所有的卖出时间点
        close_times = [pd.to_datetime(time_range.split('--')[1]) for time_range in all_res.loc[i, '持有周期']]

        # 在数据中加入买入信息
        df.loc[df['交易日期'].isin(open_times), '买入时间'] = '买入'
        # 在数据中加入卖出信息
        df.loc[df['交易日期'].isin(close_times), '卖出时间'] = '卖出'

        # 产生交易表
        trade_df = Fun.get_trade_info(df, open_times, close_times, Cfg.buy_method)
        _add_factor_main_list, _add_factor_sub_list = Fun.check_factor_in_df(df, add_factor_main_list,
                                                                             add_factor_sub_list)
        # 绘制中性策略的买卖信息
        Fun.draw_hedge_signal_plotly(df, _index_data, fig_save_path, f'{code}_{name}_{offset}', trade_df,
                                     all_res.loc[i], _add_factor_main_list, _add_factor_sub_list, color_dict,
                                     buy_method=Cfg.buy_method)
        file_path = os.path.join('选股行情图', f'{code}_{name}_{offset}.html')
        all_res.loc[i, '股票名称'] = f'=HYPERLINK("{file_path}","{name}")'
    all_res.to_excel(save_path + '01_选股分析结果.xlsx', index=False)
except Exception as err:
    err_txt = traceback.format_exc()
    err_msg = Rb.match_solution(err_txt, False)
    raise ValueError(err_msg)
