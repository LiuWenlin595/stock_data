"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import os
import re
import sys
import traceback
import pandas as pd
import psutil
from joblib import Parallel, delayed

import program.Config as Cfg
import program.Function as Fun
import program.Rainbow as Rb

# ===脚本运行需要设置的变量
# 是否需要多线程处理，True表示多线程，False表示单线程
multiple_process = True

# 如果是外部传入参数
if len(sys.argv) > 1:
    Cfg.trading_mode = True if sys.argv[1] == 'True' else False
    if Cfg.trading_mode:  # 实盘模式默认多线程
        multiple_process = True


def cal_equity_factor(factor_data, strategy_equity):
    """
    计算策略资金曲线的因子
    :param factor_data:
    :param strategy_equity: 策略回测文件
    :return:
    """
    # strategy_equity = '策略1_流动性溢价轮动策略_week_3.csv'
    print(strategy_equity, '开始计算')
    # =读入回测数据，优先读取本地文件，本地文件不存在再去读取线上策略。
    path = os.path.join(slt_equity_path, strategy_equity)
    df = pd.read_csv(path, encoding='gbk', parse_dates=['交易日期'], skiprows=1)
    df['策略上线天数'] = df.index + 1

    # ===== 开始计算因子
    exg_dict = {'策略上线天数': 'last'}  # 数据合并周线（月线）规则
    # 1、先将基本面因子合并到资金曲线上（量价因子的量因子需要在这里合并）
    # 将股票代码展开成list的形式
    df['股票代码'] = df['持有股票代码'].apply(lambda x: re.findall('([sz|bj|sh]+[0-9]+)', x))  # 正则表达式
    # 将数据按照股票代码展开
    temp = df[['交易日期', '股票代码']].explode('股票代码')

    # 如果有个股因子的情况
    if not factor_data.empty:
        # 合并之前计算好的因子数据
        temp = pd.merge(left=temp, right=factor_data, on=['交易日期', '股票代码'], how='left')

        # 讲数据按照交易日期进行合并，部分字段是求和，部分字段是求均值
        # 求和的字段
        sum_factors = temp.groupby(['交易日期'])[sum_cols].sum(min_count=1)
        # ===求均值的的字段
        mean_factors = temp.groupby(['交易日期'])[mean_cols].mean()

        # 合并数据
        base_factors = pd.merge(left=sum_factors, right=mean_factors, on=['交易日期'], how='left')
        base_factors.reset_index(inplace=True)

        # 将基本面数据合并到日线数据上
        df = pd.merge(left=df, right=base_factors, on=['交易日期'], how='left')
        for c in sum_cols + mean_cols:
            df[c].fillna(method='ffill', inplace=True)
            exg_dict[c] = 'last'

    # 计算策略需要用到的因子
    for strategy in strategy_param_dict[po_param]:
        before_len = len(df)
        df, exg_dict = strategy.cal_strategy_factors(df, exg_dict)
        if len(df) != before_len:
            Rb.record_log(f'【{strategy.name}】在调用cal_strategy_factors函数计算因子数据时，数据长度发生变化，请检查')
            raise Exception(f'【{strategy.name}】在调用cal_strategy_factors函数计算因子数据时，数据长度发生变化，请检查')

    # =将日线数据转化为月线或者周线
    df = Fun.transfer_strategy_data(df, per_oft_df, period_offset, extra_agg_dict=exg_dict)

    # 处理合并周期后的流程
    for strategy in strategy_param_dict[po_param]:
        before_len = len(df)
        df = strategy.after_resample(df)
        if len(df) != before_len:
            Rb.record_log(f'【{strategy.name}】在调用after_resample函数计算因子数据时，数据长度发生变化，请检查')
            raise Exception(f'【{strategy.name}】在调用after_resample函数计算因子数据时，数据长度发生变化，请检查')

    # 计算下周期每天涨幅
    df['下周期每天涨跌幅'] = df['每天涨跌幅'].shift(-1)
    df['持有股票代码'] = df['持有股票代码'].shift(-1)
    del df['每天涨跌幅']

    # 将指数的持仓更改为etf持仓
    stg_name = strategy_equity.split('_')[0]
    if stg_name in [Cfg.inx_dict[i][0] for i in Cfg.inx_dict.keys()]:
        for i in Cfg.inx_dict.keys():
            if stg_name == Cfg.inx_dict[i][0]:
                df['持有股票代码'] = Cfg.inx_dict[i][1]
                break

    return df  # 返回计算好的数据


# ===并行提速的办法
if __name__ == '__main__':
    try:
        # =====读取数据
        # 载入周期offset的csv
        per_oft_df = Fun.read_period_and_offset_file(Cfg.period_offset_file)
        index_data = Fun.import_index_data(Cfg.index_path, Cfg.trading_mode, Cfg.date_start, Cfg.date_end)
        Rb.record_log(f'脚本1：指数起始时间:{index_data["交易日期"].min()},指数结束时间:{index_data["交易日期"].max()}')
        Rb.record_log(f'{"脚本1：实盘模式，仅对应offset将被运行" if Cfg.trading_mode else "脚本1：回测模式，所有offset都将运行"}')

        # 按照策略参数将策略分类
        strategy_param_dict = {}
        # 获取所有的轮动策略文件
        stg_file = Fun.get_file_in_folder(os.path.join(Cfg.root_path, 'program/轮动策略/'), '.py', filters=['_init_'],
                                          drop_type=True)
        # 遍历每个策略文件
        for file in stg_file:
            cls = __import__(f'program.轮动策略.{file}', fromlist=('',))
            # 遍历策略中的strategy_param
            for po_param in cls.strategy_param:
                if po_param not in strategy_param_dict.keys():
                    strategy_param_dict[po_param] = [cls]
                else:
                    strategy_param_dict[po_param].append(cls)

        # 读取因子数据
        all_factor_data = Fun.load_factor_data(Cfg.factor_path, strategy_param_dict, Cfg.n_job,
                                               Cfg.trading_mode, index_data, per_oft_df)

        # 轮动策略资金曲线及最新结果
        slt_equity_path = os.path.join(Cfg.select_program_path, 'data/回测结果/选股策略')
        slt_res_path = os.path.join(Cfg.select_program_path, 'data/每日选股/选股策略')

        # =====按照参数整理数据
        for po_param in strategy_param_dict.keys():
            # 将需要的指数转为策略数据
            period_offset = po_param.split('_')[0] + '_' + po_param.split('_')[1]
            if Cfg.trading_mode:
                # 实盘模式
                is_current_period = Fun.is_in_current_period(period_offset, index_data, per_oft_df)
                if not is_current_period:  # 实盘模式不在正确周期则跳过
                    Rb.record_log(f'非回测模式，per_oft ：{period_offset} 不计算')
                    continue
            Rb.record_log(f'==========文件后缀：{po_param}==========')
            Fun.index2strategy(Cfg, slt_equity_path, per_oft_df, period_offset)
            # ===获取的策略历史表现
            equity_list = Fun.get_equity_list(po_param, Cfg, slt_equity_path)

            sum_cols = []  # 计算因子时需要求和的字段
            mean_cols = []  # 计算因子时需要求均值的字段

            # 遍历每个策略，找到要求和及求均值的列
            for strategy in strategy_param_dict[po_param]:
                sum_cols += strategy.sum_cols
                mean_cols += strategy.mean_cols
            sum_cols = list(set(sum_cols))
            mean_cols = list(set(mean_cols))
            Rb.record_log(f'周期参数：{po_param}，求和字段：{sum_cols}，求均值字段：{mean_cols}')

            # 遍历整理策略的数据
            if multiple_process:
                file_size = sys.getsizeof(all_factor_data)  # 文件大小
                free_size = psutil.virtual_memory().free  # 可用内存大小
                Rb.record_log(f'文件大小：{file_size}，可用内存大小：{free_size}')
                thread_count = max(int(free_size / file_size), 1)  # 需要开的线程数量
                thread_count = min(os.cpu_count() - 1, thread_count, Cfg.n_job)
                Rb.record_log(f'==========多线程数量：{thread_count}==========')
                df_list = Parallel(thread_count)(
                    delayed(cal_equity_factor)(all_factor_data, equity) for equity in equity_list)
            else:
                df_list = []
                for equity in equity_list:
                    res_df = cal_equity_factor(all_factor_data, equity)
                    df_list.append(res_df)

            # 合并为一个大的DataFrame
            all_strategy_data = pd.concat(df_list, ignore_index=True)
            all_strategy_data.sort_values(['交易日期', '策略名称'], inplace=True)
            all_strategy_data.reset_index(inplace=True, drop=True)

            # 将数据存储到pickle文件
            po_param = po_param.replace('.csv', '')
            all_strategy_data.to_pickle(os.path.join(Cfg.root_path, f'data/数据整理/all_strategy_data_{po_param}.pkl'))
    except Exception as err:
        err_txt = traceback.format_exc()
        err_msg = Rb.match_solution(err_txt, False)
        raise ValueError(err_msg)
