import os
import time

import pandas as pd

import program.exchange.exchange_api
from program.exchange.weight_method import *
from program.utils.task_control import *
import program.config as cfg
import program.RainbowV1 as Rb

Rb.robot_api = cfg.robot_api
Rb.proxies = cfg.proxies
Rb.same_msg_interval = cfg.same_msg_interval


def cal_allocation_of_cap(ex_api, **kwargs):
    """
    计算资金分配
    :param ex_api:
    :param kwargs:
    :return:
    """
    # 更新账户资金
    ex_api.get_account()
    # 检查资金是否正常
    check_account_total_asset(ex_api)

    # 计算配置中各个策略今日可以开仓的金额：
    # 策略单日开仓金额 = 总资金 x 策略权重 / 资金份数
    total_cap = ex_api.account['总资产']
    balance = ex_api.account['可用资金']
    if pd.isnull(balance):
        Rb.record_log('可用资金为空，请检查资金是否正常', send=True)
        console_check('可用资金为空，请检查资金是否正常')
    temp_hold = pd.merge(left=ex_api.hold, right=ex_api.position[['证券代码', '市值']], on=['证券代码'], how='left')
    ex_api.buy['下单金额'] = 0.0
    for s in ex_api.stg_infos.keys():
        # 获取选股结果
        order_info = ex_api.buy[ex_api.buy['策略名称'] == s].copy()
        if order_info.empty:
            continue
        s_con = ex_api.stg_infos[s]

        # ===处理资金份数
        cap_count = len(s_con['hold_plan'])  # 总资金份数
        open_count = len(order_info['持仓计划'].unique())  # 今日需要开仓的份数
        use_count = len(temp_hold[temp_hold['策略名称'] == s]['交易日期'].unique())
        avb_count = cap_count - use_count - open_count  # 可开仓的资金份数
        # 如果是日内换仓的策略，
        if ('intraday_swap' in s_con.keys()) and s_con['intraday_swap'] > 0:
            avb_count += open_count  # 如果支持日内调仓的策略,可用资金份数需要加上今天开仓的份数

        # 如果无可用资金份数，直接返回
        if avb_count < 0:
            Rb.record_log(f'{s} 资金份数超出限制。最大{cap_count}份资金，已开{use_count}份资金，今日开仓需要{open_count}份资金', send=True)
            continue

        # 策略单日开仓金额 = 总资金 x 策略权重 / 资金份数
        open_amount = total_cap * s_con['strategy_weight'] / cap_count
        # 计算权重分配
        weight_func = eval(s_con['stock_weight'][0])
        order_info = order_info.groupby('持仓计划').apply(lambda g: weight_func(g, s_con))
        order_info['下单金额'] = order_info['股票权重'].apply(lambda x: x * open_amount)
        for i in order_info.index:
            con1 = ex_api.buy['证券代码'] == order_info.at[i, '证券代码']
            con2 = ex_api.buy['策略名称'] == s
            con3 = ex_api.buy['持仓计划'] == order_info.at[i, '持仓计划']
            ex_api.buy.loc[con1 & con2 & con3, '下单金额'] = order_info.at[i, '下单金额']
    # 如果今天开仓的金额大于允许开仓的最大金额，则需要处理
    intraday_s_list = [key for key, value in cfg.intraday_swap_dict.items() if value > 0]  # 日内调仓的策略名称
    all_open_amount = ex_api.buy[~ex_api.buy['策略名称'].isin(intraday_s_list)]['下单金额'].sum()  # 非日内调仓策略的下单金额合计
    if all_open_amount > balance:
        ex_api.buy.loc[~ex_api.buy['策略名称'].isin(intraday_s_list), '下单金额'] = ex_api.buy['下单金额'] * (
                balance / all_open_amount)
    ex_api.buy['下单金额'] = ex_api.buy['下单金额'].apply(lambda x: round(x, 2))
    ex_api.save_buy()  # 及时保存买单信息
    return ex_api


def create_buy_tasks(ex_api, **kwargs):
    """
    生成买入的任务列表
    :param ex_api: 下单接口
    :param kwargs:
    :return:
    """
    task_list = []
    if '委托编号' not in ex_api.buy.columns:
        ex_api.buy['委托编号'] = ''
    else:
        ex_api.buy['委托编号'] = ex_api.buy['委托编号'].apply(lambda x: '' if str(x) == 'nan' else str(int(x)))
    for i in ex_api.buy.index:
        if ex_api.buy.at[i, '策略名称'] == '非策略选股':
            continue
        s_con = ex_api.stg_infos[ex_api.buy.at[i, '策略名称']]
        task = TaskControl(task=f'program.exchange.buy_method.{s_con["buy"][0]}', start='9:15', end='15:00',
                           rest=['11:30', '13:00'], ex_api=ex_api, order_index=i, s_config=s_con, **kwargs)
        task_list.append(task)
    return ex_api, task_list


def create_sell_tasks(ex_api, **kwargs):
    """
    生成卖出的任务列表
    :param ex_api: 下单接口
    :param kwargs:
    :return:
    """
    task_list = []
    if '委托编号' not in ex_api.sell.columns:
        ex_api.sell['委托编号'] = ''
    else:
        ex_api.sell['委托编号'] = ex_api.sell['委托编号'].apply(lambda x: '' if str(x) == 'nan' else str(int(x)))
    for i in ex_api.sell.index:
        if ex_api.sell.at[i, '策略名称'] == '非策略选股':
            continue
        s_con = ex_api.stg_infos[ex_api.sell.at[i, '策略名称']]
        task = TaskControl(task=f'program.exchange.sell_method.{s_con["sell"][0]}', start='9:15', end='15:00',
                           ex_api=ex_api, rest=['11:30', '13:00'], order_index=i, s_config=s_con, **kwargs)
        task_list.append(task)
    return ex_api, task_list


def create_risk_tasks(ex_api, **kwargs):
    """
    生成风控任务列表
    :param ex_api: 下单接口
    :param kwargs:
    :return:
    """
    task_list = []
    for i in ex_api.hold.index:
        if ex_api.hold.at[i, '策略名称'] == '非策略选股':
            continue
        s_con = ex_api.stg_infos[ex_api.hold.at[i, '策略名称']]
        if s_con['risk'][0]:
            task = TaskControl(task=f'program.exchange.risk_method.{s_con["risk"][0]}', start='9:25', end='15:00',
                               ex_api=ex_api, rest=['11:30', '13:00'], order_index=i, s_config=s_con, **kwargs)
            task_list.append(task)
    return ex_api, task_list


def console_check(console_tips):
    input_msg = input(console_tips + '\n输入y后按下Enter继续，任意键终止程序\n')
    if not input_msg.lower() == 'y':
        Rb.record_log('人为终止程序', _print=False, send=True)
        raise Exception('人为终止程序')
    else:
        Rb.record_log('已输入y，程序将继续执行')


def order_check(ex_api):
    buy = ex_api.buy.copy()
    # 没有买入计划直接返回。
    if buy.empty:
        return

    # 选择填入证券代码证券的数据
    buy = buy[buy['证券代码'].apply(lambda x: len(x) == 9)]
    # 888888的订单是不用判断金额是不是够的
    buy = buy[(buy['委托编号'].isnull()) | (buy['委托编号'] == '')]
    if buy.empty:
        return
    # 获取最新价，这里因为使用了新的get_now_price，所以不用再用原本的那个容错函数了
    buy['最新价'] = buy['证券代码'].apply(lambda x: ex_api.get_now_price(x))
    buy['最低金额'] = buy['最新价'] * 100
    con1 = buy['证券代码'].apply(lambda x: x[:2] == '68')
    buy.loc[con1, '最低金额'] = buy['最新价'] * 200
    con2 = buy['证券代码'].apply(lambda x: x[:2] in ['11', '12', '18'])
    buy.loc[con2, '最低金额'] = buy['最新价'] * 10
    # 寻找下单金额不足的数据
    lack = buy[buy['下单金额'] < buy['最低金额']]
    if not lack.empty:
        msg = ''
        for i in lack.index:
            msg += f'{lack.loc[i, "策略名称"]} {lack.loc[i, "证券代码"]}不足最小下单金额，' \
                   f'最低需要{round(lack.loc[i, "最低金额"], 2)}元，当前分配{round(lack.loc[i, "下单金额"], 2)}元\n\n'
        Rb.record_log(msg, send=True)
    else:
        Rb.record_log('交易计划检查无异常。')


def check_account_total_asset(ex_api):
    """
    检查账户信息是否异常，若QMT交易端有问题则可能存在异常
    :param ex_api: 下单接口
    :return:
    """
    total_cap = ex_api.account['总资产']
    if pd.isnull(total_cap) or (not float(total_cap) > 0):
        Rb.record_log(f'账户总资产异常{ex_api.account.total_asset}，疑似行情源异常，Rocket退出。\n'
                      f'可参考论坛内容https://bbs.quantclass.cn/thread/18505', send=True)
        # 需要把已经产生的买入卖出计划删掉，否则检查完重启的时候，不会进cal_allocation_of_cap
        today = ex_api.trader_calendar.today
        buy_path = ex_api.recoder_path + f'{today.year}_{today.month}_{today.day}买入计划.csv'
        os.remove(buy_path)
        sell_path = ex_api.recoder_path + f'{today.year}_{today.month}_{today.day}卖出计划.csv'
        os.remove(sell_path)
        raise Exception('账户资产查询异常')
