'''
2024分享会
本代码由股票一期牛马小组 - 因子复现koala组提供
组员：koala、Jumbo、BuJunhua、Jacob、DarKnight
'''
import os
import pandas as pd
from joblib import Parallel, delayed
from Tools.utils import PlotFunctions as pFun
from program import Config as Cfg
from program import Rainbow as Rb
from Tools.utils import tFunctions as tFun
import datetime
import warnings
import traceback

warnings.filterwarnings('ignore')

# =====需要配置的东西=====
factor_from = {'成交额相关因子': [], 'Ret': []}
main_factor = '成交额_Std20'  # 你想测试的主因子列表
sub_factor = 'Ret_20'  # 你想测试的次因子列表
period_offset_list = ['W_0']  # 需要分析的周期
multiple_process = False  # True为并行，False为串行；测试：运行内存16G的电脑是能够并行的跑完（刚开始运行读取数据时会很卡），运行内存在16G以下的电脑尽量使用串行


def data_process(df):
    '''
    在这个函数里面处理数据，主要是：过滤，计算符合因子等等
    :param df:
    :return:
    '''

    # 案例1：增加分域的代码
    # df = df[df['收盘价'] < 100]
    # df['总市值分位数'] = df.groupby('交易日期')['总市值'].rank(pct=True)
    # df = df[df['总市值分位数'] >= 0.9]

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
b_rate = 1.2 / 10000  # 买入手续费
s_rate = 1.12 / 1000  # 卖出手续费
keep_cols = ['交易日期', '股票代码', '股票名称', '交易天数', '市场交易天数', '下日_是否交易', '下日_开盘涨停', '下日_是否ST',
             '下日_是否退市', '上市至今交易天数', main_factor, sub_factor, target, next_ret]


def factor_analysis_for_double(per_oft):
    # 记录该offset开始处理的时间
    Rb.record_log(f'双因子分析：{per_oft} {main_factor} {sub_factor}，开始处理数据...')
    _start_date = datetime.datetime.now()

    # 读入主因子数据
    df = tFun.get_factor_by_period(Cfg.factor_path, per_oft, factor_from, keep_cols, data_process)
    # 过滤数据
    df = tFun.filter_stock(df)
    # 过滤NA因子值
    df.dropna(subset=[main_factor, sub_factor], inplace=True)

    # 保留每个周期的股票数量大于limit的日期
    df['当周期股票数'] = df.groupby('交易日期')['交易日期'].transform('count')
    df = df[df['当周期股票数'] > limit].reset_index(drop=True)

    # 将双因子数据按照交易日期和offset进行分组
    df = tFun.offset_grouping_double(df, main_factor, sub_factor, bins)

    # 计算这个offset下的双因子组合分组平均收益、平均占比、双因子过滤分组平均收益
    _mix_nv, _mix_prop, _filter_nv_ms, _filter_nv_sm = tFun.get_group_nv_double(df, next_ret, b_rate, s_rate, per_oft)

    # 计算双因子风格暴露
    _group_style_corr = tFun.get_style_corr_double(df, main_factor, sub_factor, per_oft, target)

    return _mix_nv, _mix_prop, _filter_nv_ms, _filter_nv_sm, _group_style_corr


try:
    # 创建列表，用来保存各个offset的数据
    mix_nv_list = []  # 双因子组合分组平均收益列表
    mix_prop_list = []  # 双因子组合分组股票占比列表
    filter_nv_ms_list = []  # 双因子过滤分组平均收益列表，主因子分组的基础上，次因子再分组
    filter_nv_sm_list = []  # 双因子过滤分组平均收益列表，次因子分组的基础上，主因子再分组
    style_corr_list = []  # 双因子风格暴露列表

    # 双因子主处理
    Rb.record_log(f'开始进行双因子 {main_factor} 和 {sub_factor} 分析...')
    # 记录开始时间
    s_date = datetime.datetime.now()

    if multiple_process:
        result_list = Parallel(Cfg.n_job)(delayed(factor_analysis_for_double)(per_oft) for per_oft in period_offset_list)
        # 将返回的数据添加到对应的列表中
        for idx, per_oft in enumerate(period_offset_list):
            if not result_list[idx][0].empty:
                mix_nv_list.append(result_list[idx][0])
                mix_prop_list.append(result_list[idx][1])
                filter_nv_ms_list.append(result_list[idx][2])
                filter_nv_sm_list.append(result_list[idx][3])
                style_corr_list.append(result_list[idx][4])
    else:
        for per_oft in period_offset_list:
            result_list = factor_analysis_for_double(per_oft)
            if not result_list[0].empty:
                mix_nv_list.append(result_list[0])
                mix_prop_list.append(result_list[1])
                filter_nv_ms_list.append(result_list[2])
                filter_nv_sm_list.append(result_list[3])
                style_corr_list.append(result_list[4])

    # 生成一个包含图的列表，之后的代码每画出一个图都添加到该列表中，最后一起画出图
    fig_list = []

    Rb.record_log('正在汇总各offset数据并画图...')
    start_date = datetime.datetime.now()  # 记录开始时间

    # 计算双因子分组的组合平均收益、平均占比、双因子分组的过滤平均收益
    mix_nv, mix_prop, filter_nv_ms, filter_nv_sm = tFun.group_nv_analysis(mix_nv_list, mix_prop_list, filter_nv_ms_list,
                                                                          filter_nv_sm_list, bins)
    # 计算双因子风格暴露
    style_corr, corr_txt = tFun.group_style_analysis(style_corr_list)

    # 画双因子平均收益组合热力图
    mix_nv_hot_fig = pFun.draw_hot_plotly(x=mix_nv.columns, y=mix_nv.index, z=mix_nv,
                                          title=f'双因子组合 - 日平均收益(‰)<br />主：{main_factor}   次：{sub_factor}')
    fig_list.append(mix_nv_hot_fig)
    # 画双因子平均占比组合热力图
    mix_prop_hot_fig = pFun.draw_hot_plotly(x=mix_prop.columns, y=mix_prop.index, z=mix_prop,
                                            title=f'双因子组合 - 平均占比(%)<br />主：{main_factor}   次：{sub_factor}')
    fig_list.append(mix_prop_hot_fig)
    # 画双因子平均收益过滤热力图
    filter_nv_ms_hot_fig = pFun.draw_hot_plotly(x=filter_nv_ms.columns, y=filter_nv_ms.index, z=filter_nv_ms,
                                                title=f'双因子过滤 - 日平均收益(‰)<br />在【{main_factor}】分组的基础上，对【{sub_factor}】分组')
    fig_list.append(filter_nv_ms_hot_fig)
    filter_nv_sm_hot_fig = pFun.draw_hot_plotly(x=filter_nv_sm.columns, y=filter_nv_sm.index, z=filter_nv_sm,
                                                title=f'双因子过滤 - 日平均收益(‰)<br />在【{sub_factor}】分组的基础上，对【{main_factor}】分组')
    fig_list.append(filter_nv_sm_hot_fig)
    # 画双因子风格暴露图
    style_corr_fig = pFun.draw_three_bar_plotly(x=style_corr['风格'], y1=style_corr['相关系数_主因子'],
                                                y2=style_corr['相关系数_次因子'], y3=style_corr['相关系数_双因子'], title=corr_txt)
    fig_list.append(style_corr_fig)

    # 整合上面所有的图
    path = os.path.join(Cfg.root_path, 'data/绘图信息/双因子分析')
    os.makedirs(path, exist_ok=True)
    pFun.merge_html(path, fig_list=fig_list, strategy_file=f'{main_factor}和{sub_factor}_分析报告',
                    bbs_id='45302')

    Rb.record_log(f'双因子 {main_factor} 和 {sub_factor} 分析完成，耗时：{datetime.datetime.now() - s_date}')

except Exception as err:
    err_txt = traceback.format_exc()
    err_msg = Rb.match_solution(err_txt, False)
    raise ValueError(err_msg)
