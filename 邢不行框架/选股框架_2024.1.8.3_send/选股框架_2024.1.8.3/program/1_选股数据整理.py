"""
2024分享会
author: 邢不行
微信: xbx6660
选股策略框架
"""
import os.path
import time
import sys
import traceback
import pandas as pd
from joblib import Parallel, delayed

from program import Config as Cfg
from program import Function_fin as Fin
from program import Functions as Fun
from program import Rainbow as Rb

# ===脚本运行需要设置的变量
# 是否需要多线程处理，True表示多线程，False表示单线程
multiple_process = True

# 如果是外部传入参数
if len(sys.argv) > 1:
    Cfg.trading_mode = True if sys.argv[1] == 'True' else False
    if Cfg.trading_mode:  # 实盘模式默认多线程
        multiple_process = True


# ===循环读取并且合并
def calculate_by_stock(code):
    """
    整理数据核心函数
    :param code: 股票代码
    :return: 一个包含该股票所有历史数据的DataFrame
    """
    try:
        # code = 'sh600007.csv'
        print(code, '开始计算')
        # =读入股票数据
        path = os.path.join(Cfg.stock_data_path, code)
        df = pd.read_csv(path, encoding='gbk', skiprows=1, parse_dates=['交易日期'])

        # =计算涨跌幅
        df['涨跌幅'] = df['收盘价'] / df['前收盘价'] - 1
        # 计算换手率
        df['换手率'] = df['成交额'] / df['流通市值']

        # =计算复权价：计算所有因子当中用到的价格，都使用复权价
        df = Fun.cal_fuquan_price(df, fuquan_type='后复权')

        # =计算交易天数
        df['上市至今交易天数'] = df.index.astype('int') + 1

        # 获取股票基础数据的路径
        stock_base_path = os.path.join(Cfg.factor_path, '日频数据/基础数据/', code.replace('csv', 'pkl'))

        # 对数据进行预处理：合并指数、计算下个交易日状态、基础数据resample等
        total_df, delisted = Fun.pre_process(stock_base_path, df, index_data, po_list, per_oft_df, Cfg.end_exchange)
        # 如果全量数据是空的，则直接返回
        if total_df.empty:
            return

        # =导入财务数据，将个股数据和财务数据合并，并计算需要的财务指标的衍生指标(所有的财务数据都重新合并一下)
        total_df, fin_df, fin_raw_df = Fin.merge_with_finance_data(total_df, code[:-4], Cfg.fin_path, ipt_fin_cols,
                                                                   opt_fin_cols, {})

        # =遍历调用每个策略的load函数，合并其他数据
        for name, func_info in load_functions.items():
            # 遍历看看有没有那个因子是需要用全部数据才能算的
            for _fa in func_info['factors']:
                # 加载额外的数据
                before_len = len(total_df)
                total_df = func_info['func'](total_df)
                if before_len != len(total_df):
                    Rb.record_log(f'股票：{code}使用{name}加载数据后数据长度发生变化，请检查！！！')
                    raise Exception('加载外部数据错误,尽量避免在load函数中对原始的data进行删除或者增加行数的操作')

        # =遍历计算每一个因子
        for _fa in fa_info.keys():
            exg_dict = {}  # 重要变量，在将日线数据转换成周期数据时使用。key为需要转换的数据，对应的value为转换的方法，包括first,max,min,last,sum等.
            # 获取因子的保存路径
            _save_path = os.path.join(Cfg.factor_path, f'日频数据/{_fa}/')
            # 创建文件夹（如果无）
            os.makedirs(_save_path, exist_ok=True)
            # 日频因子的保存路径
            _save_path = os.path.join(_save_path, code.replace('csv', 'pkl'))
            # 计算因子
            before_len = len(total_df)
            total_df, exg_dict = fa_info[_fa]['cls'].cal_factors(total_df, fin_df, fin_raw_df, exg_dict)
            if before_len != len(total_df):
                Rb.record_log(f'股票：{code}使用{_fa}计算因子后数据长度发生变化，请检查！！！')
                raise Exception('计算因子发生错误，尽量避免在cal_factor函数中对原始的data进行删除或者增加行数的操作')
            # 需要保存的因子列表
            factor_cols = list(exg_dict.keys())
            # 只保留需要的字段
            total_factor_df = total_df[['交易日期', '股票代码'] + factor_cols]
            # 全量数据直接保存
            total_factor_df.to_pickle(_save_path)

            # =遍历所有的周期，保存周期因子
            for _po in fa_info[_fa]['per_oft']:
                # 周期因子的保存路径
                _save_path = os.path.join(Cfg.factor_path, f'周期数据/{_po}/{_fa}')
                # 创建保存周期因子数据的文件夹
                os.makedirs(_save_path, exist_ok=True)
                _save_path = os.path.join(_save_path, code.replace('csv', 'pkl'))

                # 全量数据转换成周期数据
                period_df = Fun.transfer_factor_data(total_factor_df, per_oft_df, _po, exg_dict, delisted)
                # 计算周期级别的因子
                before_len = len(period_df)
                period_df = fa_info[_fa]['cls'].after_resample(period_df)
                if before_len != len(period_df):
                    Rb.record_log(f'股票：{code}使用{_fa}.after_resample计算{_po}周期因子后数据长度发生变化，请检查！！！')
                    raise Exception('计算周期因子发生错误，尽量避免在after_resample函数中对原始的data进行删除或者增加行数的操作')
                # 重置索引并保存
                period_df.reset_index(drop=True).to_pickle(_save_path)
    except Exception as err:
        Rb.record_log(code, '出现异常！！！！！！！！！！！！！！！！')
        raise err
    return


if __name__ == '__main__':
    try:
        # 清理历史日志
        Fun.clean_logs(Rb.log_path)
        now = time.time()  # 用于记录运行时间

        # 如果要尾盘换仓，需要先从行情网站拿一下数据
        if Cfg.end_exchange:
            python_exe = sys.executable
            os.system(f'{python_exe} {Cfg.root_path}/program/0_尾盘获取数据.py')

        # 因子检查：查看因子文件的MD5值是否发生变更，如果发送变更，说明改过因子的文件内容，因子可能需要重新跑
        Fun.check_factor_change(os.path.join(Cfg.root_path, 'program/因子/'),
                                os.path.join(Cfg.root_path, 'data/数据整理/因子MD5记录.csv'))

        # ===读取：股票列表、指数数据、策略信息、周期表等
        # 1.读取所有股票代码的列表
        stock_code_list = Fun.get_file_in_folder(Cfg.stock_data_path, '.csv', filters=['bj'])
        Rb.record_log(f'脚本1：股票数量：{len(stock_code_list)}')
        # 2.导入上证指数，保证指数数据和股票数据在同一天结束，不然会出现问题。
        index_data = Fun.import_index_data(Cfg.index_path, Cfg.trading_mode, Cfg.date_start, Cfg.date_end)
        # 3.导入策略文件夹中的所有选股策略
        stg_file = Fun.get_file_in_folder(os.path.join(Cfg.root_path, f'program/选股策略/'), '.py', filters=['_init_'],
                                          drop_type=True)
        # 4.加载所有周期所有offset的df
        per_oft_df = Fun.read_period_and_offset_file(Cfg.period_offset_file)

        # ===获取运行信息
        # 本函数输入：策略文件、周期表、是否回测模式、交易日期，其他因子
        # 输出：因子运行信息fa_info、原始财务字段ipt_fin_cols、输出的财务字段，外部数据函数合集load_functions，周期列表po_list
        # 详细内容建议点进函数内部查看
        fa_info, ipt_fin_cols, opt_fin_cols, load_functions, po_list = Fun.get_run_info(stg_file, per_oft_df,
                                                                                        Cfg.trading_mode,
                                                                                        index_data['交易日期'].iloc[-1],
                                                                                        Cfg.other_factors)
        # 打印当前的回测模式
        Rb.record_log(f'{"脚本1：实盘模式，仅对应offset将被运行" if Cfg.trading_mode else "脚本1：回测模式，所有offset都将运行"}')

        # 运行每个因子的special_data函数
        for factor in fa_info.keys():
            fa_info[factor]['cls'].special_data()

        # ===遍历每个股票，计算各个股票的因子（并行或者串行）
        # 并行计算，速度快但cpu负载高，速度和负载取决于config.n_job的大小
        if multiple_process:
            Parallel(Cfg.n_job)(delayed(calculate_by_stock)(code) for code in stock_code_list)
        # 串行计算，一个一个算，速度慢但负载低
        else:
            for stock in stock_code_list:
                calculate_by_stock(stock)

        # 将基础数据也加入到fa_info中
        fa_info['基础数据'] = {'per_oft': po_list}
        # 遍历每个因子，计算其截面数据
        for fa in fa_info.keys():
            # 遍历该因子所有的周期
            for po in fa_info[fa]['per_oft']:
                # 周期因子数据路径
                period_factor_path = os.path.join(Cfg.factor_path, f'周期数据/{po}/{fa}/')
                # 获取周期因子数据的文件名
                file_list = Fun.get_file_in_folder(period_factor_path, '.pkl', filters=[fa])
                # 批量读取数据
                df_list = Parallel(Cfg.n_job)(
                    delayed(pd.read_pickle)(os.path.join(period_factor_path, code)) for code in file_list)
                # 合并读到的所有该周期下的因子数据
                all_df = pd.concat(df_list, ignore_index=True)
                # 周期因子数据保存路径
                save_path = os.path.join(period_factor_path, f'{fa}.pkl')
                if fa != '基础数据':
                    # 计算截面因子
                    all_df = fa_info[fa]['cls'].cal_cross_factor(all_df)
                    # 重置索引
                    all_df.reset_index(drop=True, inplace=True)
                # 保存路径
                all_df.to_pickle(save_path)
                # 记录数据
                max_date = all_df['交易日期'].max()
                Rb.record_log(f'脚本1：因子{fa}、周期{po}计算完成，最新交易日期为：{max_date}')
        # 打印一下数据整理的整体耗时
        Rb.record_log(f'脚本1：耗时：{time.time() - now}')
    except Exception as err:
        err_txt = traceback.format_exc()
        err_msg = Rb.match_solution(err_txt, False)
        raise ValueError(err_msg)
