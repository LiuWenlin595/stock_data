"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import os, glob
import pandas as pd

def get_variable_from_py_file(py_path, var_dict):
    """
    从py文件中获取字段，请注意，需要获取的变量需要再一行只内写完。
    :param py_path: py文件名，
    :param var_dict: 参数列表，{参数名:类型}
    :return:
    """
    # 判断文件是否存在
    if os.path.exists(py_path):
        # 逐行读入文件
        with open(py_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        # 寻找需要的变量的行
        res = {}
        for var in var_dict.keys():
            for line in lines:
                if line.startswith(var):
                    # 如果这行代码又注释，把注释之后的内容去掉
                    if '#' in line:
                        inx = line.find('#')
                        line = line[:inx]
                    # 替换掉字符串中的空格及换行
                    line = line.replace('\n', '').replace(' ', '')
                    sub_str = line.split('=')
                    if var_dict[var] == str and sub_str[1].replace('\'', '').replace('\"', '') == 'None':
                        res[sub_str[0]] = None
                    elif var_dict[var] == bool:
                        res[sub_str[0]] = eval(sub_str[1])
                    elif var_dict[var] == str:
                        res[sub_str[0]] = sub_str[1].replace('\'', '').replace('\"', '')
                    else:
                        res[sub_str[0]] = var_dict[var](sub_str[1])
                    break
        return res
    else:
        print('路径错误，未找到对应的py文件：', py_path)
        return {}


def unpack_data(df, type_name, target, period_df, min_date, fill0=False):
    # 数据截取
    df = df[df['交易日期'] >= min_date].reset_index(drop=True)

    # 数据拆包
    df.set_index(['交易日期', type_name], inplace=True)
    df = df.unstack([type_name])[target].reset_index()

    # 填充空值
    if fill0:
        df.fillna(value=0.0, inplace=True)

    # 合并周期
    df = pd.merge(df, period_df, 'left', '交易日期')
    df['周期'].fillna(method='bfill', inplace=True)
    return df


def load_data(sft_bt_path, extra_sft_path_list, ftr_path, slt_bt_path, index_path, factor_cols, show_empty):
    '''
    return:
    sft_df:轮动策略的df
    slt_df:选股策略的df
    ftr_infos:因子的df,存在字典中
    index_df:指数数据
    slt_stg_list：轮动策略中涉及到的所有的子策略（包括子策略组合）
    all_slt_stg_list：所有独立的子策略
    '''
    sft_df = pd.read_csv(sft_bt_path, encoding='gbk', parse_dates=['交易日期'])
    sft_df['策略名称'].fillna(method='ffill', inplace=True)
    ftr_df = pd.read_pickle(ftr_path)

    period_df = pd.DataFrame(ftr_df['交易日期'].unique(), columns=['交易日期'])
    period_df = period_df[period_df['交易日期'] >= sft_df['交易日期'].min()].reset_index(drop=True)
    period_df['周期'] = period_df.index + 1
    sft_df = pd.merge(sft_df, period_df, 'left', '交易日期')
    sft_df['周期'].fillna(method='bfill', inplace=True)
    sft_df = sft_df.dropna(subset=['周期'], axis=0).reset_index(drop=True)

    # 获取轮动策略里面涉及到的所有策略，包括策略池
    slt_stg_list = sorted(list(sft_df['策略名称'].unique()), reverse=False)

    # 单独取出每个子策略并处理，获得子策略列表
    all_slt_stg_list = []
    for stg in slt_stg_list:
        all_slt_stg_list += stg.split(' ')
    all_slt_stg_list = sorted(list(set(all_slt_stg_list)), reverse=False)
    if '' in all_slt_stg_list:
        all_slt_stg_list.remove('')

    temp_list = []
    for stg in all_slt_stg_list:
        if not show_empty and stg == 'empty':
            continue
        temp_df = pd.read_csv(os.path.join(slt_bt_path, stg + '.csv'), encoding='gbk', parse_dates=['交易日期'],
                              skiprows=1)
        temp_list.append(temp_df)
    slt_df = pd.concat(temp_list, ignore_index=True)
    slt_df = unpack_data(slt_df, '策略名称', '涨跌幅', period_df, sft_df['交易日期'].min(), True)
    slt_df['empty'] = 0.0

    ftr_df = ftr_df[ftr_df['策略名称'].isin(list(all_slt_stg_list))]
    ftr_infos = {}
    for factor in factor_cols:
        _ftr_df = ftr_df[['交易日期', '策略名称', factor]].copy()
        _ftr_df = unpack_data(_ftr_df, '策略名称', factor, period_df, sft_df['交易日期'].min(), True)
        ftr_infos[factor] = _ftr_df

    # 保存一下持仓信息
    hold_stock_df = sft_df[['交易日期', '策略名称', '持有股票代码', '周期']]
    sft_df = sft_df[['交易日期', '策略名称', '涨跌幅', '周期']]

    # 读取指数数据
    try:
        index_df = pd.read_csv(index_path, parse_dates=['candle_end_time'], encoding='gbk')
    except:
        index_df = pd.read_csv(index_path, parse_dates=['candle_end_time'], encoding='gbk', skiprows=1)
    index_df = index_df[['candle_end_time', 'open', 'high', 'low', 'close']].rename(columns={'candle_end_time': '交易日期'})
    index_df = index_df[index_df['交易日期'] >= sft_df['交易日期'].min()].reset_index(drop=True)
    index_df = pd.merge(index_df, period_df, on='交易日期', how='left')
    index_df['周期'].fillna(method='bfill', inplace=True)

    if len(extra_sft_path_list) >= 1:
        for path in extra_sft_path_list:
            sft_name = path.split('\\')[-1].split('.csv')[0]
            temp_df = pd.read_csv(path, encoding='gbk', parse_dates=['交易日期'])[['交易日期', '涨跌幅']].rename(columns={'涨跌幅': sft_name})
            sft_df = pd.merge(sft_df, temp_df, on='交易日期', how='left')
        sft_name = sft_bt_path.split('\\')[-1].split('.csv')[0]
        sft_df = sft_df.rename(columns={'涨跌幅': sft_name})

    return sft_df, slt_df, ftr_infos, index_df, slt_stg_list, all_slt_stg_list, hold_stock_df


def get_window_size(width, count):
    pic_width = width - 400
    pic_height = int(pic_width * 0.3)
    if count > 0:
        high = 50 + pic_height + 25 + pic_height + 50 + pic_height + 25
    else:
        high = 50 + pic_height + 25 + pic_height + 25
    return f'{width}x{high}', pic_width, pic_height

# ===b圈需要的函数===
def get_equity_path(base_strategy_dict, base_config_path):
    """
    获取对应策略中指定的hold_period、offset、所有对应的资金曲线文件
    :param base_strategy_dict:
    :param base_config_path:
    :return:
        hold_period、offset、资金曲线列表
    """
    # 获取指定策略文件的所有hold_period和offset
    hold_period_set, offset_set = set(), set()
    if_use_spots = []

    # 遍历每个策略文件名
    for stg_name in base_strategy_dict:
        stg_name += '.py'  # 在策略文件名后加上后缀  .py
        stg_path = os.path.join(base_config_path, 'program/strategy', stg_name)  # 拼接路径取出策略文件的路径

        # 获取策略文件名中的hold_period、offset变量
        stg_params = get_variable_from_py_file(stg_path, {'hold_period': eval, 'offset': int, 'if_use_spot': bool})
        if len(stg_params) == 0:
            print('请检查路径配置及对应的策略文件是否存在。')
            exit()
        _hold_period = stg_params['hold_period']  # 取出hold_period
        _offset = stg_params['offset']  # 取出offset
        _if_use_spot = stg_params['if_use_spot']
        if_use_spots.append(_if_use_spot)

        # 将该策略文件中的hold_period、offset添加到集合中
        hold_period_set.add(_hold_period)
        offset_set.add(_offset)

    # 如果各策略文件存在多个持仓周期或offset，则会退出
    if (len(hold_period_set) > 1) | (len(offset_set) > 1):
        print('存在多个持仓周期或offset，请调整一致。')
        exit()

    # 取出唯一的hold_period和offset
    hold_period = list(hold_period_set)[0]
    offset = list(offset_set)[0]

    # 资金曲线文件路径
    equity_path = os.path.join(base_config_path, 'data/回测结果/')
    # 获取所有的资金曲线文件，只找hold_period和offset对应的资金曲线文件
    all_equity_file = []  # 创建新列表保存资金曲线文件
    for i, stg in enumerate(list(base_strategy_dict.keys())):  # 遍历每个策略文件名
        if_use_spot = if_use_spots[i]
        if if_use_spot:
            label = 'SPOT'
        else:
            label = 'SWAP'

        file_name = f'{stg.split("_")[1]}_{label}_资金曲线_{hold_period}_{offset}.csv'  # 以策略文件名_后的部分开头，之后是SPOT或SWAP，再接着hold_period和offset
        equity_file = glob(equity_path + file_name)  # 将文件夹下所有对应的资金曲线文件找出来
        if len(equity_file) == 0:
            print('没有找到对应策略的资金曲线：', stg)
            print('请修改策略配置或生成对应的资金曲线')
            exit()
        all_equity_file.extend(equity_file)  # 添加到列表中

    return hold_period, offset, if_use_spots, all_equity_file


def adjust_file(sft_bt_path, shift_ftr_path, all_equity_file, base_strategy_dict, index_path):
    rename_cols = {'candle_begin_time': '交易日期', 'symbol': '策略名称', '选币': '持有股票代码', '轮动涨跌幅': '涨跌幅',
                   '每小时涨跌幅': '下周期每天涨跌幅'}

    # 转换轮动资金曲线数据
    sft_bt_file = pd.read_csv(sft_bt_path, encoding='gbk')
    sft_bt_file.rename(columns=rename_cols, inplace=True)
    sft_bt_file['持有股票代码'] = sft_bt_file['持有股票代码'].map(lambda x: x.split("'"))
    sft_bt_file['持有股票代码'] = sft_bt_file['持有股票代码'].map(lambda x: [i + ' ' for i in x if len(i) > 2])
    sft_bt_file['持有股票代码'] = sft_bt_file['持有股票代码'].map(lambda x: ''.join(x))
    sft_bt_file['交易日期'] = pd.to_datetime(sft_bt_file['交易日期'])
    timedelta = sft_bt_file['交易日期'].iloc[1] - sft_bt_file['交易日期'].iloc[0]
    sft_bt_file['交易日期'] = sft_bt_file['交易日期'] + timedelta
    sft_bt_file_name = os.path.basename(sft_bt_path).split('.')[0] + '_轮动模拟器.' + os.path.basename(sft_bt_path).split('.')[1]
    sft_bt_path = os.path.join(os.path.dirname(sft_bt_path), sft_bt_file_name)
    sft_bt_file.to_csv(sft_bt_path, encoding='gbk', index=False)

    # 转换轮动策略中间数据
    shift_ftr_file = pd.read_pickle(shift_ftr_path)
    shift_ftr_file.rename(columns=rename_cols, inplace=True)
    shift_ftr_file['交易日期'] = pd.to_datetime(shift_ftr_file['交易日期'])
    timedelta = pd.Series(shift_ftr_file['交易日期'].unique()).iloc[1] - pd.Series(shift_ftr_file['交易日期'].unique()).iloc[0]
    shift_ftr_file['交易日期'] = shift_ftr_file['交易日期'] + timedelta
    shift_ftr_file_name = os.path.basename(shift_ftr_path).split('.')[0] + '_轮动模拟器.' + os.path.basename(shift_ftr_path).split('.')[1]
    shift_ftr_path = os.path.join(os.path.dirname(shift_ftr_path), shift_ftr_file_name)
    shift_ftr_file.to_pickle(shift_ftr_path)

    # 转换子策略资金曲线数据
    for file_path in all_equity_file:
        base_name = os.path.basename(file_path)  # 取出路径的基础文件名，即资金曲线的文件名
        equity_name = base_name.split('_')[0]  # 解析资金曲线文件名，是由哪个策略跑出的资金曲线
        equity_cols = base_strategy_dict[f'Strategy_{equity_name}']  # 根据 资金曲线文件名 取出对应的参与轮动的资金曲线
        equity_cols = [col.split('资金曲线')[0] for col in equity_cols]

        file = pd.read_csv(file_path, encoding='gbk', parse_dates=['candle_begin_time'])
        file.rename(columns={'candle_begin_time': '交易日期', '选币': '持有股票代码', '涨跌幅': '多空涨跌幅'}, inplace=True)
        file = file[['交易日期', '持有股票代码', '多空涨跌幅', '多头涨跌幅', '空头涨跌幅']]
        file['多空_持有股票代码'] = file['持有股票代码'].apply(lambda x: [symbol.strip() for symbol in x.split(' ')][: -1])  # 如果当周期为空仓，则选币为空[]
        file['多头_持有股票代码'] = file['多空_持有股票代码'].apply(lambda x: [symbol for symbol in x if symbol.endswith(',1)')])
        file['空头_持有股票代码'] = file['多空_持有股票代码'].apply(lambda x: [symbol for symbol in x if symbol.endswith(',-1)')])

        for equity_col in equity_cols:
            temp = file[['交易日期', equity_col + '涨跌幅', equity_col + '_持有股票代码']].copy()
            temp.rename(columns={equity_col + '_持有股票代码': '持有股票代码', equity_col + '涨跌幅': '涨跌幅'}, inplace=True)
            temp['策略名称'] = equity_name + '_' + equity_col

            file_name = equity_name + '_' + equity_col + '.csv'
            save_path = os.path.join(os.path.dirname(file_path), file_name)
            warning = '本数据供邢不行数字货币量化课程、策略分享会专用，由邢不行整理，微信：xbx6660'
            file_title = pd.DataFrame(columns=[warning])
            file_title.to_csv(save_path, index=False, encoding='GBK', mode='w')
            temp.to_csv(save_path, encoding='gbk', index=False, mode='a')

    try:
        BTC = pd.read_csv(index_path, encoding='gbk', parse_dates=['candle_begin_time'])
    except:
        BTC = pd.read_csv(index_path, encoding='gbk', parse_dates=['candle_begin_time'], skiprows=1)
    BTC['candle_begin_time'] = BTC['candle_begin_time'].shift()
    BTC = BTC.dropna(axis=0).reset_index(drop=True)
    BTC.rename(columns={'candle_begin_time': 'candle_end_time'}, inplace=True)
    index_save_path = os.path.join(os.path.dirname(shift_ftr_path), 'index_data.csv')
    BTC.to_csv(index_save_path, encoding='gbk', index=False)

    return sft_bt_path, shift_ftr_path, index_save_path