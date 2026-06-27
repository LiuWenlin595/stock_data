import math

import pandas as pd
from program.exchange.exchange_api import ExchangeAPI
import datetime


def base_risk(ex_api, order_index, s_config, **kwargs):
    """
    基础的风控函数：尾盘按照固定比例止盈止损。
    当天买入的股票不参与风控，因为没办法卖出。
    当天卖出的股票也不参与风控，因为本来就要卖出
    [base_risk,param1,param2,param3]
    param1；亏损多少开始止损， 是一个0-1之间的小数
    param2；盈利到多少开始止盈， 是一个0-1之间的小数
    param3：尾盘的几点开始止损
    :param ex_api:下单接口
    :param order_index:order中的索引
    :param s_config:配置
    :param kwargs:
    :return:
    """

    # 当天买入的股票不能止盈和止损，直接卖出。
    buy_date = ex_api.hold.at[order_index, '交易日期']
    if buy_date == ex_api.trader_calendar.today:
        return 'Finish'
    sell_date = ex_api.hold.at[order_index, '计划卖出日期']
    if sell_date == ex_api.trader_calendar.today:
        return 'Finish'
    strategy_name = ex_api.hold.at[order_index, '策略名称']
    if len(s_config['risk']) == 1:
        ex_api.rb.record_log(f'{strategy_name}_base_risk未填写参数', send=True)
        return 'Finish'
    # 如果还没到止损设定的时间点，就先跳过
    if datetime.datetime.now() < ex_api.get_time(s_config['risk'][3]):
        return 'Pass'

    stock_code = ex_api.hold.at[order_index, '证券代码']
    open_price = ex_api.hold.at[order_index, '成交均价']
    if pd.isnull(open_price):
        ex_api.rb.record_log(f'{stock_code}_未记录到成交均价，无法参与风控', send=True)
        return 'Finish'

    stop_loss = s_config['risk'][1]
    stop_profit = s_config['risk'][2]
    last_price = ex_api.get_tick(stock_code)['最新价']
    pct_change = last_price / open_price - 1
    volume = ex_api.hold.at[order_index, '持仓量']
    remark = ex_api.hold.at[order_index, '订单标记']
    # 先判断是否要止盈
    # 只是随缘的下一单，之后的订单同步工作交给收盘后的compare_hold_and_position（立马同步太耗性能了）
    if pct_change > stop_profit:
        order_id = ex_api.single_order(stock_code, last_price * 0.99, 'SELL', remark, volume)
        if order_id == -2:
            return ex_api, 'Finish'
        ex_api.hold.loc[order_index, '持仓量'] = 0
    if pct_change < -stop_loss:
        order_id = ex_api.single_order(stock_code, last_price * 0.99, 'SELL', remark, volume)
        if order_id == -2:
            return ex_api, 'Finish'
        ex_api.hold.loc[order_index, '持仓量'] = 0
    return ex_api, 'Finish'
