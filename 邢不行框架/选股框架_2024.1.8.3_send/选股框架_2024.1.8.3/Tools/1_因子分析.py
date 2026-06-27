'''
2024分享会
author: 邢不行
微信: xbx6660
'''
import os
import datetime
import pandas as pd
from joblib import Parallel, delayed
from Tools.utils import PlotFunctions as PFun
from program import Config as Cfg
from program import Rainbow as Rb
from Tools.utils import tFunctions as tFun
import warnings
import traceback

warnings.filterwarnings('ignore')

# =====需要配置的东西=====
factor_from = {'成交额相关因子': []}  # 参考策略的factors变量，配置这个参数主要是帮你加载数据的
factor_name = '成交额_Std5'  # 最终要测试的因子名称

period_offset_list = ['W_0']  # 需要分析的周期
multiple_process = False  # True为并行，False为串行；测试：运行内存16G的电脑是能够并行的跑完（刚开始运行读取数据时会很卡），运行内存在16G以下的电脑尽量使用串行


def data_process(df):
    '''
    在这个函数里面处理数据，主要是：过滤，计算符合因子等等
    :param df:
    :return:
    '''

    # 案例1：增加分域的代码
    # df['总市值分位数'] = df.groupby('交易日期')['总市值'].rank(pct=True)
    # df = df[df['总市值分位数'] >= 0.9]
    # df = df[df['收盘价'] < 100]

    # 案例2：增加计算复合因子的代码
    # df['总市值排名'] = df.groupby('交易日期')['总市值'].rank()
    # df['成交额排名'] = df.groupby('交易日期')['成交额'].rank(ascending=False)
    # df['复合因子'] = df['总市值排名'] + df['成交额排名']
    return df


# =====需要配置的东西=====

# =====几乎不需要配置的东西=====
bins = 10  # 分箱数
limit = 100  # 1.某个周期至少有100只票，否则过滤掉这个周期；注意：limit需要大于bins；可能会造成不同因子开始时间不一致
target = '下周期涨跌幅'  # 测试因子与下周期涨跌幅的IC，可以选择其他指标比如夏普率等
next_ret = '下周期每天涨跌幅'  # 使用下周期每天涨跌幅画分组持仓走势图
data_folder = os.path.join(Cfg.root_path, 'data/数据整理/')  # 配置读入数据的文件夹路径
industry_col = '新版申万一级行业名称'  # 配置行业的列名
# 行业名称更改信息，比如：21年之前的一级行业采掘在21年之后更名为煤炭
industry_name_change = {'采掘': '煤炭', '化工': '基础化工', '电气设备': '电力设备', '休闲服务': '社会服务',
                        '纺织服装': '纺织服饰', '商业贸易': '商贸零售'}
b_rate = 1.2 / 10000  # 买入手续费
s_rate = 1.12 / 1000  # 卖出手续费
keep_cols = ['交易日期', '股票代码', '股票名称', '交易天数', '市场交易天数', '下日_是否交易', '下日_开盘涨停', '下日_是否ST',
             '下日_是否退市', '上市至今交易天数', factor_name, target, next_ret, industry_col]

try:
    # 如果target列向下shift1个周期，则更新下target指定的列
    # 创建列表，用来保存各个offset的数据
    IC_list = []  # IC数据列表
    group_nv_list = []  # 分组净值列表
    group_hold_value_list = []  # 分组持仓走势列表
    style_corr_list = []  # 风格暴露列表
    industry_data_list = []  # 行业分析数据列表
    market_value_list = []  # 市值分析数据列表


    def factor_analysis(per_oft):
        # 记录该offset开始处理的时间
        Rb.record_log(f'offset：{per_oft}，开始处理数据...')
        _start_date = datetime.datetime.now()

        # 读入数据
        df = tFun.get_factor_by_period(Cfg.factor_path, per_oft, factor_from, keep_cols, data_process)
        # 过滤数据
        df = tFun.filter_stock(df)

        # 如果返回的数据为空，则跳过该offset继续读取下一个offset的数据
        if df.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        # 删除必要字段为空的部分
        df = df.dropna(subset=keep_cols, how='any')
        # 将因子信息转换成float类型
        df[factor_name] = df[factor_name].astype(float)
        # =保留每个周期的股票数量大于limit的日期
        df['当周期股票数'] = df.groupby('交易日期')['交易日期'].transform('count')
        df = df[df['当周期股票数'] > limit].reset_index(drop=True)

        # 将数据按照交易日期和offset进行分组
        df = tFun.offset_grouping(df, factor_name, bins)

        # ===计算这个offset下的IC
        _IC = tFun.get_IC(df, factor_name, target, per_oft)
        # ===计算这个offset下的分组资金曲线、分组持仓走势
        _group_nv, _group_hold_value = tFun.get_group_nv(df, next_ret, b_rate, s_rate, per_oft)
        # ===计算风格暴露
        _style_corr = tFun.get_style_corr(df, factor_name, per_oft)
        # ===计算行业平均IC以及行业占比
        _industry_data = tFun.get_industry_data(df, factor_name, target, industry_col, industry_name_change)
        # ===计算不同市值分组内的平均IC以及市值占比
        _market_value_data = tFun.get_market_value_data(df, factor_name, target, bins)

        Rb.record_log(f'per_oft：{per_oft}, 处理数据完成，耗时：{datetime.datetime.now() - _start_date}')

        return _IC, _group_nv, _group_hold_value, _style_corr, _industry_data, _market_value_data


    Rb.record_log(f'开始进行 {factor_name} 因子分析...')
    s_date = datetime.datetime.now()  # 记录开始时间
    if multiple_process:
        result_list = Parallel(Cfg.n_job)(delayed(factor_analysis)(per_oft) for per_oft in period_offset_list)
        # 将返回的数据添加到对应的列表中
        for idx, per_oft in enumerate(period_offset_list):
            if not result_list[idx][0].empty:
                IC_list.append(result_list[idx][0])
                group_nv_list.append(result_list[idx][1])
                group_hold_value_list.append(result_list[idx][2])
                style_corr_list.append(result_list[idx][3])
                industry_data_list.append(result_list[idx][4])
                market_value_list.append(result_list[idx][5])
    else:
        for per_oft in period_offset_list:  # 遍历offset进行因子分析
            IC, group_nv, group_hold_value, style_corr, industry_data, market_value_data = factor_analysis(per_oft)
            if not IC.empty:
                # 将返回的数据添加到对应的列表中
                IC_list.append(IC)
                group_nv_list.append(group_nv)
                group_hold_value_list.append(group_hold_value)
                style_corr_list.append(style_corr)
                industry_data_list.append(industry_data)
                market_value_list.append(market_value_data)

    # 生成一个包含图的列表，之后的代码每画出一个图都添加到该列表中，最后一起画出图
    fig_list = []

    Rb.record_log('正在汇总各offset数据并画图...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # ===计算IC、累计IC以及IC的评价指标
    IC, IC_info = tFun.IC_analysis(IC_list)
    # =画IC走势图，并将IC图加入到fig_list中，最后一起画图
    Rank_fig = PFun.draw_ic_plotly(x=IC['交易日期'], y1=IC['RankIC'], y2=IC['累计RankIC'], title='因子RankIC图',
                                   info=IC_info)
    fig_list.append(Rank_fig)
    # =画IC热力图（年份月份），并将图添加到fig_list中
    # 处理IC数据，生成每月的平均IC
    IC_month = tFun.get_IC_month(IC)
    # 画图并添加
    hot_fig = PFun.draw_hot_plotly(x=IC_month.columns, y=IC_month.index, z=IC_month, title='RankIC热力图(行：年份，列：月份)')
    fig_list.append(hot_fig)

    # ===计算分组资金曲线、分箱图、分组持仓走势
    group_curve, group_value, group_hold_value = tFun.group_analysis(group_nv_list, group_hold_value_list)
    # =画分组资金曲线...
    cols_list = [col for col in group_curve.columns if '第' in col]
    group_fig = PFun.draw_line_plotly(x=group_curve['交易日期'], y1=group_curve[cols_list], y2=group_curve['多空净值'],
                                      if_log=True, title='分组资金曲线')
    fig_list.append(group_fig)
    # =画分箱净值图
    group_fig = PFun.draw_bar_plotly(x=group_value['分组'], y=group_value['净值'], title='分组净值')
    fig_list.append(group_fig)
    # =画分组持仓走势
    group_fig = PFun.draw_line_plotly(x=group_hold_value['时间'], y1=group_hold_value[cols_list], update_xticks=True,
                                      if_log=False, title='分组持仓走势')
    fig_list.append(group_fig)

    # ===计算风格暴露
    style_corr = tFun.style_analysis(style_corr_list)
    if not style_corr.empty:
        # =画风格暴露图
        style_fig = PFun.draw_bar_plotly(x=style_corr['风格'], y=style_corr['相关系数'], title='因子风格暴露图', y_range=[-1.0, 1.0])
        fig_list.append(style_fig)

    # ===行业
    # =计算行业平均IC以及行业占比
    industry_data = tFun.industry_analysis(industry_data_list, industry_col)
    # =画行业分组RankIC
    industry_fig1 = PFun.draw_bar_plotly(x=industry_data[industry_col], y=industry_data['RankIC'], title='行业RankIC图')
    fig_list.append(industry_fig1)
    # =画行业暴露
    industry_fig2 = PFun.draw_double_bar_plotly(x=industry_data[industry_col],
                                                y1=industry_data['因子第一组选股在各行业的占比'],
                                                y2=industry_data['因子最后一组选股在各行业的占比'],
                                                title='行业占比（可能会受到行业股票数量的影响）')
    fig_list.append(industry_fig2)
    # ===市值
    # =计算不同市值分组内的平均IC以及市值占比
    market_value_data = tFun.market_value_analysis(market_value_list)
    # =画市值分组RankIC
    market_value_fig1 = PFun.draw_bar_plotly(x=market_value_data['市值分组'], y=market_value_data['RankIC'],
                                             title='市值分组RankIC')
    fig_list.append(market_value_fig1)
    # =画市值暴露
    info = '1-{bins}代表市值从小到大分{bins}组'.format(bins=bins)
    market_value_fig2 = PFun.draw_double_bar_plotly(x=market_value_data['市值分组'],
                                                    y1=market_value_data['因子第一组选股在各市值分组的占比'],
                                                    y2=market_value_data['因子最后一组选股在各市值分组的占比'],
                                                    title='市值占比', info=info)
    fig_list.append(market_value_fig2)

    # ===整合上面所有的图
    save_path = os.path.join(Cfg.root_path, 'data/绘图信息/单因子分析')
    PFun.merge_html(save_path, fig_list=fig_list, strategy_file=f'{factor_name}因子分析报告', bbs_id='31614')
    Rb.record_log(f'汇总数据并画图完成，耗时：{datetime.datetime.now() - start_date}')
    Rb.record_log(f'{factor_name} 因子分析完成，耗时：{datetime.datetime.now() - s_date}')
except Exception as err:
    err_txt = traceback.format_exc()
    err_msg = Rb.match_solution(err_txt, False)
    raise ValueError(err_msg)
