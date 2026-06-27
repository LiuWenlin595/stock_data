"""
2024分享会
author: 邢不行
微信: xbx9585
"""
import random
import sys
import os
import pandas as pd
import pprint

python_exe = sys.executable


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


def get_select_strategy_info(stg_name, program_path, stg_info):
    stg_path = os.path.join(program_path, f'program/选股策略/{stg_name}.py')
    files = {}
    if os.path.exists(stg_path):
        if stg_name not in stg_info.keys():
            stg_info[stg_name] = []
        stg_cfg = get_variable_from_py_file(stg_path, {'period_offset': str, 'select_count': int})
        period_offset = stg_cfg['period_offset'][1:-1].split(',')
        for per_oft in period_offset:
            files[stg_name + f'_{per_oft}_{stg_cfg["select_count"]}'] = per_oft
            stg_info[stg_name].append(per_oft)
        stg_info[stg_name].append(stg_cfg['select_count'])
    return files, stg_info


def get_shift_strategy_info(stg_name, program_path, stg_info):
    stg_path = os.path.join(program_path, f'program/轮动策略/{stg_name}.py')
    files = {}
    if os.path.exists(stg_path):
        if stg_name not in stg_info.keys():
            stg_info[stg_name] = []
        stg_cfg = get_variable_from_py_file(stg_path, {'strategy_param': str, 'select_count': int})
        sub_stg_count = 0
        strategy_param = stg_cfg['strategy_param'][1:-1].split(',')
        for param in strategy_param:
            '''
            轮动策略会填的内容有：'5_0_5.csv'  '5_0_5'  '_5_0_5.csv'
            需要将轮动策略中的 period offset取出来才能自动推算其对应的周期
            注意：2024版本的轮动只允许选股数量相同的策略一起轮动了
            '''
            if param.startswith('_'):
                param = param[1:]
            str_list = param.split('_')
            if len(str_list) > 2:
                stg_info[stg_name].append(f'{str_list[0]}_{str_list[1]}')
                files[stg_name + f'_{param.replace(".csv", "")}_{stg_cfg["select_count"]}'] = \
                    f'{str_list[0]}_{str_list[1]}'
                if '@' in str_list[2]:
                    sub_stg_count = 0  # 如果是任意数量的轮动，则给0
                else:
                    if sub_stg_count != 0:
                        sub_stg_count = max(float(str_list[2].replace('.csv', '')), sub_stg_count)
        stg_info[stg_name].append(sub_stg_count * stg_cfg['select_count'])
    return files, stg_info


def get_event_strategy_info(stg_name, program_path, stg_info):
    stg_path = program_path + '/program/事件策略'
    files = {}
    if os.path.exists(stg_path + f'/{stg_name}.py'):
        if stg_path not in sys.path:
            sys.path.append(stg_path)
        if stg_name not in stg_info.keys():
            stg_info[stg_name] = []
        cls = __import__(stg_name, fromlist=('',))
        files['event_' + stg_name + f'_P_{cls.hold_period}_{cls.select_count}'] = ' '

        # 事件策略资金分数和持仓周期相同
        for i in range(0, cls.hold_period):
            stg_info[stg_name].append(f'{cls.hold_period}_{i}')
        stg_info[stg_name].append(cls.select_count)
    return files, stg_info


def get_trade_plan(trade_df, stg_name, path, tc, period_offset, rb, stg_type=' '):
    """
    将新的交易计划添加到交易计划表中
    :param trade_df: 已经有的交易计划
    :param stg_name: 策略名称
    :param path: 策略文件路径
    :param tc: 交易日历
    :param period_offset: 持仓信息
    :param rb: Rainbow模块
    :param stg_type: 策略类型，可以填：选股、轮动、事件，默认是空的
    :return:
    """
    # 判断一下文件是否存在
    if not os.path.exists(path):
        rb.record_log(f'路径不存在：{path}\n，请运行对应的代码生成文件。例如：选股策略运行 2_选股.py')
        return trade_df

    # 读取最新策略的文件
    df = pd.read_csv(path, encoding='gbk', parse_dates=['交易日期', '选股日期'])
    # 只保留今天的选股结果
    res = df[df['交易日期'] == tc.today]
    # 如果当前策略没有选到股票，直接去获取下一个策略的结果
    if res.empty:
        return trade_df

    # 轮动策需要把文件额外处理一下
    if stg_type == '轮动':
        # 重命名一下，避免列重复
        res.rename(columns={'策略名称': '子策略名称'}, inplace=True)
        # 删除策略中的选股数量信息
        res['子策略名称'] = res['子策略名称'].apply(lambda x: x[:x.rfind('_')])

    # trade_df可能有之前这个策略的选股，最好删掉重新给
    con1 = trade_df['交易日期'] == tc.today
    con2 = trade_df['策略名称'] == stg_name
    con3 = trade_df['持仓计划'] == period_offset
    con4 = ~trade_df['其他'].str.contains('√')
    trade_df = trade_df[~(con1 & con2 & con3 & con4)]

    # 昨天选的股票，交易日期是今天
    res['交易日期'] = tc.today
    res['策略名称'] = stg_name
    res.rename(columns={'股票代码': '证券代码'}, inplace=True)
    res['持仓计划'] = period_offset
    if stg_type == '选股':
        res['其他'] = res['股票名称']
    elif stg_type == '轮动':
        res['其他'] = res['子策略名称'] + ':' + res['股票名称']
        # 轮动策略选中指数，需要按照选策略数量把指数多copy几次
        index_list = ['上证指数', '上证50指数', '沪深300指数', '中证500指数', '中证1000指数', '创业板指数']
        temp = res[res['股票名称'].isin(index_list)]
        select_count = path.split('_')[-2]
        if select_count == '@':
            res = pd.concat([res, temp], ignore_index=True)
        else:
            select_count = int(select_count)
            if select_count - 1 > 0:
                index_df = pd.concat([temp] * (select_count - 1), ignore_index=True)
                res = pd.concat([res, index_df], ignore_index=True)
    elif stg_type == '事件':
        res['其他'] = res['股票名称']
    else:
        res['其他'] = ' '
    res = res[['交易日期', '策略名称', '证券代码', '持仓计划', '其他']]
    # 保存数据
    trade_df = pd.concat([trade_df, res], ignore_index=True)
    # 按照交易日期排序
    trade_df = trade_df.sort_values(by=['交易日期', '策略名称']).reset_index(drop=True)
    return trade_df


def create_config_info(stg_info):
    infos = {}
    stg_info['非策略选股'] = ['5_0', '5_1', '5_2', '5_3', '5_4', 5]  # 添加一个默认的非策略选股
    for stg in stg_info.keys():
        infos[stg] = {}
        # 默认的策略权重是0
        infos[stg]['strategy_weight'] = 0.0
        infos[stg]['hold_plan'] = stg_info[stg][:-1]
        infos[stg]['select_count'] = stg_info[stg][-1]
        infos[stg]['stock_weight'] = ["equal_weight", False]
        infos[stg]['buy'] = ["t_wap", f'09:24:{random.randint(10, 59)}', random.randint(25, 45),
                             random.randint(6000, 12000), 1.005]
        infos[stg]['sell'] = ["base_sell", f'14:{random.randint(45, 55)}:{random.randint(10, 59)}']
        infos[stg]['risk'] = [False]
        infos[stg]['intraday_swap'] = 0

    pprint.pprint(infos)


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
                    elif var_dict[var] == 'eval':
                        res[sub_str[0]] = eval(sub_str[1])
                    else:
                        res[sub_str[0]] = var_dict[var](sub_str[1])
                    break
        return res
    else:
        raise Exception(f'路径错误，未找到对应的py文件：{py_path}')
