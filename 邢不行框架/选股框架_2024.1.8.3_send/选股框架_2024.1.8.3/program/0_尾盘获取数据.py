"""
2024分享会
author: 邢不行
微信: xbx6660
选股策略框架
"""
import datetime
import os
import shutil
import traceback
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm

from program import Config as Cfg
from program import Functions as Fun
from program import Rainbow as Rb

# ===脚本运行需要设置的变量
# 是否需要多线程处理，True表示多线程，False表示单线程
multiple_process = True

# 选择数据处理是否为回滚模式
# False表示更新数据，即从行情网站上抓取最新的量价数据，并增加到已有的K线中
# True表示回滚数据，即把今日从行情网站上更新的数据从全息数据中剔除
rolls_back = False


def concat_data(tag, group):
    """
    将从行情网站上抓到的实时个股行情数据合并到本地的全息数据中
    :param tag:    股票代码
    :param group:  行情网站上抓到的实时个股行情数据
    """

    # 获取本地的个股存放路径
    stock_path = os.path.join(Cfg.stock_data_path, f'{tag}.csv')

    # 判断一下文件是否存在，如果不存在文件，则说明是今天新上线的股票
    if not os.path.exists(stock_path):
        # 新股有缺失的字段，用空值填充
        for col in source_columns:
            if col not in group:
                group[col] = np.nan
        # 填充完成即可，不需要合并历史数据（新股没有历史数据）
        df = group
    else:  # 处理非新股的流程
        # 读取本地数据
        df = pd.read_csv(stock_path, encoding='gbk', parse_dates=['交易日期'], skiprows=1)
        # 合并本地数据与线上数据
        df = pd.concat([df, group], ignore_index=True)
        # 按照交易日期排序
        df.sort_values('交易日期', inplace=True)
        # 删除重复的交易日期
        df.drop_duplicates(subset=['交易日期'], inplace=True, keep='last')
        df.reset_index(inplace=True, drop=True)

        # 如果行数大于1，说明有历史数据，今天的空值需要用上一个交易日的数据填充
        if df.shape[0] > 1:
            # 最后一行的空数据用前一天的数据补充
            max_inx = df.index.max()
            for col in df.columns:
                if pd.isnull(df.loc[max_inx, col]):
                    df.loc[max_inx, col] = df.loc[max_inx - 1, col]

    # 先把文件临时保存到临时文件，确认无误后再移动到正确的路径里面
    temp_stock_path = os.path.join(temp_path, f'{tag}.csv')
    # 加入数据
    df.columns = pd.MultiIndex.from_tuples(
        zip(['数据由邢不行整理，对数据字段有疑问的，可以直接微信私信邢不行，微信号：xbx297'] + [''] * (
                df.shape[1] - 1), df.columns))
    # 保存文件到临时位置
    df.to_csv(temp_stock_path, encoding='gbk', index=False)
    # 移动数据到正确的数据位置
    shutil.move(temp_stock_path, stock_path)

    return


def rolls_back_data(tag, groups):
    """
    把今日从行情网站上更新的数据从全息数据中剔除
    :param tag:    个股代码
    :param group:  获取到的今天的该个股数据
    """
    # 获取本地的个股存放路径
    stock_path = os.path.join(Cfg.stock_data_path, f'{tag}.csv')

    # 判断股票文件是否存在
    if os.path.exists(stock_path):
        # 读取数据
        df = pd.read_csv(stock_path, encoding='gbk', parse_dates=['交易日期'], skiprows=1)
        # 删除今日的数据
        df = df[df['交易日期'] != trade_date]
        # 如果是新股，删除今天的数据就会直接变空，需要删除文件
        if df.empty:
            os.remove(stock_path)
        else:
            # 先把文件临时保存到临时文件，确认无误后再移动到正确的路径里面
            temp_stock_path = os.path.join(temp_path, f'{tag}.csv')
            # 加入数据
            df.columns = pd.MultiIndex.from_tuples(
                zip(['数据由邢不行整理，对数据字段有疑问的，可以直接微信私信邢不行，微信号：xbx297'] + [''] * (
                        df.shape[1] - 1), df.columns))
            # 保存数据到临时位置
            df.to_csv(temp_stock_path, encoding='gbk', index=False)
            # 移动数据
            shutil.move(temp_stock_path, stock_path)
    return

def justify_trading_day():
    '''
    通过period_offset文件判断今天是不是交易日
    :return: True表示今天是交易日，False表示今天不是交易日
    '''
    today = pd.to_datetime(datetime.datetime.now().date())
    po_df = pd.read_csv(Cfg.period_offset_file, parse_dates=['交易日期'], encoding='gbk', skiprows=1)
    if today in po_df['交易日期'].to_list():
        return True
    else:
        return False

if __name__ == '__main__':
    # 判断今天是不是交易日，如果今天不是交易日就不运行了
    if not justify_trading_day():
        print('今天不是交易日，不更新数据')
        exit()

    try:
        # 打印当前的模式
        mode = '回滚模式' if rolls_back else '更新模式'
        Rb.record_log(f'\n开始执行脚本0，{mode}')
        # 股票基础数据的字段，合并模式时，这些字段的空值会用上一个交易日的值填充
        source_columns = ['股票代码', '股票名称', '交易日期', '开盘价', '最高价', '最低价', '收盘价', '前收盘价', '成交量',
                          '成交额', '流通市值', '总市值', '净利润TTM', '现金流TTM', '净资产', '总资产', '总负债',
                          '净利润(当季)', '中户资金买入额', '中户资金卖出额', '大户资金买入额', '大户资金卖出额', '散户资金买入额',
                          '散户资金卖出额', '机构资金买入额', '机构资金卖出额', '沪深300成分股', '上证50成分股', '中证500成分股',
                          '中证1000成分股', '中证2000成分股', '创业板指成分股', '新版申万一级行业名称', '新版申万二级行业名称',
                          '新版申万三级行业名称', '09:35收盘价', '09:45收盘价', '09:55收盘价']

        # 获取运行程序的当前日期作为交易日期，非交易日期不要运行此代码
        trade_date = pd.to_datetime(datetime.datetime.now().date())
        # 读取日历，非交易日不需要从网上拉数据
        per_oft_df = pd.read_csv(Cfg.period_offset_file, encoding='gbk', skiprows=1, parse_dates=['交易日期'])
        if trade_date not in per_oft_df['交易日期'].to_list():
            Rb.record_log('脚本0：当前日期非交易日，【0_尾盘获取数据.py】无需执行')
            exit()

        # 临时文件的保存位置：最好和全息数据的放在一个硬盘上，这样移动的时候会快一点
        temp_path = os.path.join(Cfg.root_path, 'data/数据整理/临时文件/')
        # 新建文件夹
        os.makedirs(temp_path, exist_ok=True)

        # 获取本地的个股数量：线上更新到的股票数量超过本地的95%就认为更新完成了
        stock_count = len(Fun.get_file_in_folder(Cfg.stock_data_path, '.csv'))
        # 从线上获取今天交易日的个股数据
        new_date = Fun.get_stock_data_from_internet(trade_date, stock_count)
        Rb.record_log(f'脚本0：本地股票数量：{stock_count}，线上获取到的股票数量：{new_date.shape[0]}')
        # 按照股票代码对新获取到的股票行情数据进行分组
        groups = new_date.groupby('股票代码')

        # ===选择数据更新是【合并模式】还是【回滚模式】
        # 回滚模式，定义func为回滚数据的函数
        if rolls_back:
            Rb.record_log('脚本0：开始回滚数据')
            func = rolls_back_data
        # 合并模式，定义func为获取线上数据的函数
        else:
            Rb.record_log('脚本0：开始获取最新数据')
            func = concat_data

        # ===是否并行处理
        # 并行处理（多个股票用多个cpu核心同时运算，速度更快但是会加大cpu负载）
        if multiple_process:
            Parallel(Cfg.n_job)(delayed(func)(t, g) for t, g in tqdm(groups))
        # 串行处理（算完一个开始下一个，速度慢但cpu负载小）
        else:
            for t, g in tqdm(groups):
                func(t, g)

        # ===处理指数数据
        # 回滚模式：删除今日的数据
        if rolls_back:
            Rb.record_log('开始回滚指数数据')
            index = pd.read_csv(Cfg.index_path, parse_dates=['candle_end_time'], encoding='gbk')
            index = index[index['candle_end_time'] != trade_date]
            index.to_csv(Cfg.index_path, encoding='gbk', index=False)
        # 合并模式：从线上更新最新的指数数据
        else:
            Rb.record_log('开始获取指数数据')
            # 从指数路径中获取指数的代码
            index = Cfg.index_path[-12:-4]
            Fun.update_stock_index(index, Cfg.index_path)
    except Exception as err:
        err_txt = traceback.format_exc()
        err_msg = Rb.match_solution(err_txt, False)
        raise ValueError(err_msg)
