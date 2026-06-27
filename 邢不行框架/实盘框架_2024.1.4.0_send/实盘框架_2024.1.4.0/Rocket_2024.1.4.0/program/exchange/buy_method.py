import datetime
import math
import random

import pandas as pd

from program.exchange.exchange_api import ExchangeAPI
import numpy as np
import random


def base_buy(ex_api: ExchangeAPI, order_index, s_config, **kwargs):
    """
    基础买入函数，按照指定的涨跌幅买入，[base_buy,param1]
    param1表示相较于最新价的涨跌幅,建议在1.005-1.019之间
    :param ex_api:下单接口
    :param order_index:在order中的索引
    :param s_config:策略配置
    :param kwargs:
    :return:
    """
    code = ex_api.buy.at[order_index, '证券代码']
    amount = ex_api.buy.at[order_index, '下单金额']
    remark = ex_api.buy.at[order_index, '订单标记']
    order_id = ex_api.buy.at[order_index, '委托编号']

    # 处理还没下单的情况
    if order_id == '':
        time_limit = ex_api.get_time('09:25:02')
        if datetime.datetime.now() < time_limit:
            return ex_api, 'Pass'
        price = float(ex_api.get_now_price(code))
        order_id = ex_api.single_order(code, price, 'BUY', remark, amount=amount)
        if order_id == -2:
            return ex_api, 'Finish'
        if order_id != -1:
            ex_api.buy.loc[order_index, '委托编号'] = order_id
            ex_api.save_buy()
    else:
        state = ex_api.query_order(order_id)
        # 将成交信息汇总同步到hold中
        if (state == '已成') or (state == '部成'):
            ex_api.syn_hod(remark, order_id, s_config)
            if state == '已成':
                return ex_api, 'Finish'
        if (state == '已报') or (state == '部成'):
            end_time_limit = ex_api.get_time('9:30:30')
            if datetime.datetime.now() > end_time_limit:
                # 撤单之前先判断一下是不是涨停了
                price_state = ex_api.price_limit_state(code)
                if price_state == '涨停':
                    return ex_api
                # 先撤掉原来的单
                _, state = ex_api.cancel_order(order_id)
                if state in ['已撤', '部撤']:
                    # 同步一下成交信息
                    ex_api.syn_hod(remark, order_id, s_config)
                else:
                    return ex_api
        if (state == '已撤') or (state == '部撤') or (state == '废单'):
            if state in ['已撤', '部撤']:
                # 同步一下成交信息
                ex_api.syn_hod(remark, order_id, s_config)
            # 获取已经同步的数据
            inx = ex_api.hold.loc[(ex_api.hold['订单标记'] == remark)].index.min()
            if pd.isnull(inx):
                hold_amount = 0
            else:
                hold_amount = ex_api.hold.loc[inx, '持仓量']
            if pd.isnull(hold_amount):
                hold_amount = 0
            # 计算未成交的金额 = 下单金额 - 成交量 x 成交均价
            not_deal = amount if pd.isnull(inx) else amount - hold_amount * ex_api.hold.loc[inx, '成交均价']
            # 重新下单
            # 下单价格 = 最新价 * 配置的价格比例
            price = ex_api.get_now_price(code)
            pct_change = s_config['buy'][1] if s_config['buy'][1] > 1 else 1 + s_config['buy'][1]
            price = price * pct_change
            order_id = ex_api.single_order(code, price, 'BUY', remark, amount=not_deal, price_clamp=True)
            if order_id == -2:
                return ex_api, 'Finish'
            if order_id != -1:
                ex_api.buy.loc[order_index, '委托编号'] = order_id
                ex_api.save_buy()
            else:  # 下单量不足的情况下，直接结束
                return ex_api, 'Finish'
        ex_api.save_hold()  # 及时保存结果
    return ex_api


def tracking_buy(ex_api: ExchangeAPI, order_index, s_config, **kwargs):
    """
    基础买入函数，按照指定的涨跌幅买入，[tracking_std_buy,parm1]
        param1表示相较于最新价的涨跌幅,建议在1.005-1.019之间

    注意，本函数下单之后就不会重新撤单再买入了
    所以价格涨得比较快的话，可能会一直帮你挂单导致无法买入
    不过实测下来，这个情况发生的比例相当低

    :param ex_api:下单接口
    :param order_index:在order中的索引
    :param s_config:策略配置
    :param kwargs:
    :return:
    """
    code = ex_api.buy.at[order_index, '证券代码']
    amount = ex_api.buy.at[order_index, '下单金额']
    remark = ex_api.buy.at[order_index, '订单标记']
    order_id = ex_api.buy.at[order_index, '委托编号']

    # 处理还没下单的情况
    if order_id == '':
        pre_price = ex_api.get_tick(code)['前收盘价']
        if pre_price < 2:
            end_time_limit = ex_api.get_time('9:25:04')
        else:
            end_time_limit = ex_api.get_time('9:30:04')
        if datetime.datetime.now() < end_time_limit:
            return ex_api
        if pre_price < 2:
            temp = ex_api.get_tick(code)
            price = temp['最新价'] if temp['开盘价'] == 0 else temp['开盘价']
            order_id = ex_api.single_order(code, price, 'BUY', remark, amount=amount, price_clamp=True)
        else:
            tick_df = ex_api.get_market_data(code, period='tick')
            if tick_df.empty:
                return ex_api
            tick_df['至今最低价'] = tick_df['最新价'].expanding().min()
            tick_df['开仓价格'] = tick_df['至今最低价'] * 1.002
            con = tick_df['最新价'] > tick_df['开仓价格']

            tick_df.loc[con, 'signal'] = 1
            if tick_df['signal'].iloc[-1] == 1:
                pct_change = s_config['buy'][1] if s_config['buy'][1] > 1 else 1 + s_config['buy'][1]
                price = tick_df['最新价'].iloc[-1] * pct_change
                order_id = ex_api.single_order(code, price, 'BUY', remark, amount=amount, price_clamp=True)
        if order_id == -2:
            return ex_api, 'Finish'
        if order_id != -1:
            ex_api.buy.loc[order_index, '委托编号'] = order_id
            ex_api.save_buy()
    else:
        state = ex_api.query_order(order_id)
        # 将成交信息汇总同步到hold中
        if (state == '已成') or (state == '部成'):
            ex_api.syn_hod(remark, order_id, s_config)
            if state == '已成':
                return ex_api, 'Finish'
        if state == '废单':
            # 获取已经同步的数据
            inx = ex_api.hold.loc[(ex_api.hold['订单标记'] == remark)].index.min()
            if pd.isnull(inx):
                hold_amount = 0
            else:
                hold_amount = ex_api.hold.loc[inx, '持仓量']
            if pd.isnull(hold_amount):
                hold_amount = 0
            # 计算未成交的金额 = 下单金额 - 成交量 x 成交均价
            not_deal = amount if pd.isnull(inx) else amount - hold_amount * ex_api.hold.loc[inx, '成交均价']
            # 重新下单
            # 下单价格 = 最新价 * 配置的价格比例
            price = ex_api.get_now_price(code)
            pct_change = s_config['buy'][1] if s_config['buy'][1] > 1 else 1 + s_config['buy'][1]
            price = price * pct_change
            order_id = ex_api.single_order(code, price, 'BUY', remark, amount=not_deal, price_clamp=True)
            if order_id == -2:
                return ex_api, 'Finish'
            if order_id != -1:
                ex_api.buy.loc[order_index, '委托编号'] = order_id
                ex_api.save_buy()
            else:  # 下单量不足的情况下，直接结束
                return ex_api, 'Finish'
        ex_api.save_hold()  # 及时保存结果
    return ex_api


def t_wap(ex_api: ExchangeAPI, order_index, s_config, **kwargs):
    """
    简单的t_wap函数，按照固定金额进行拆单
    参数为[t_wap,param1,param2,param3,param4]
    param1表示t_wap的开始时间，这个时间不可以是9点15之前  9点30分04
    param2表示t_wap的间隔，单位是s
    param3表示t_wap每次下单的金额
    param4表示t_wap的滑点比例，是一个比1大的数字，例如1.005

    :param ex_api:下单接口
    :param order_index:在order中的索引
    :param s_config:策略配置
    :param kwargs:
    :return:
    """
    code = ex_api.buy.at[order_index, '证券代码']
    amount = ex_api.buy.at[order_index, '下单金额']
    remark = ex_api.buy.at[order_index, '订单标记']
    order_id = ex_api.buy.at[order_index, '委托编号']

    t_start = s_config['buy'][1]
    t_step = s_config['buy'][2]
    t_amount = s_config['buy'][3]
    t_slip = s_config['buy'][4]

    # 兼容一下，历史版本，第三个参数是拆单次数，如果第三个参数小于100，给一个随机数
    if t_amount < 100:
        t_amount = random.randint(6000, 12000)

    # 计算下单信息，并保存到buffer里面
    if not remark in ex_api.buffer.keys():
        # 将拆单信息保存到buffer里面
        t_wap_info = {'next_time': ex_api.get_time(t_start)}
        ex_api.buffer[remark] = t_wap_info

    # 开始下单
    now_time = datetime.datetime.now()
    if now_time > ex_api.buffer[remark]['next_time']:
        ex_api.buffer[remark]['next_time'] = now_time + pd.to_timedelta(f'{t_step}s')
        # 如果之前委托过
        if order_id != '':
            # 撤单之前先判断一下是不是涨停了
            price_state = ex_api.price_limit_state(code)
            if price_state == '涨停':
                return ex_api
            # 撤销之前的单子，如果已经成交了就不起作用了
            _, state = ex_api.cancel_order(order_id)
            if state in ['已成', '已撤', '部撤', '废单']:
                # 同步之前的订单
                ex_api.syn_hod(remark, order_id, s_config)
            else:
                return ex_api

        # 计算一下还需要下多少金额
        # 获取一下已经下单了多少金额（如果没有下过单，这个数据是0）
        inx = ex_api.hold.loc[(ex_api.hold['订单标记'] == remark)].index.min()
        if pd.isnull(inx):
            hold_amount = 0
            avg_price = 0
        else:
            hold_amount = 0 if pd.isnull(ex_api.hold.loc[inx, '持仓量']) else ex_api.hold.loc[inx, '持仓量']
            avg_price = 0 if pd.isnull(ex_api.hold.loc[inx, '成交均价']) else ex_api.hold.loc[inx, '成交均价']

        # 计算未成交的金额 = 下单金额 - 成交量 x 成交均价
        not_deal = amount - hold_amount * avg_price
        # 计算一下下单一笔最低需多少钱
        min_volume = 200 if code[:2] == '68' else 100
        tick = ex_api.get_tick(code)
        last_price = tick['前收盘价'] if tick['最新价'] == 0 else tick['最新价'] * t_slip
        min_amount = last_price * min_volume
        # 如果min_amount 大于我们计划买入的金额not_deal，直接退出
        if min_amount > not_deal:
            ex_api.rb.record_log(f'{remark} t_wap信息：计划下单金额{round(amount, 2)}元，剩余下单金额{round(not_deal, 2)}元，'
                                 f'最小下单金额{round(min_amount, 2)}元，本次交易已完成', send=True)
            return ex_api, 'Finish'
        # 如果min_amount大于我们的t_amount,则需要把我们的t_amount设置为min_amount
        t_amount = max(t_amount, min_amount)
        # 如果需要当前股票的下单金额not_deal 小于设置的 t_amount,则t_amount设置为not_deal
        t_amount = min(t_amount, not_deal)

        # 如果时间在9点30之前，或者在午盘休市的时候，只往后推迟下次运行的事件
        if ((now_time > ex_api.get_time('09:25')) and (now_time < ex_api.get_time('09:30'))) or (
                (now_time > ex_api.get_time('11:30') and (now_time < ex_api.get_time('13:00')))):
            return ex_api
        else:
            _price = ex_api.get_now_price(code)
            _price = _price * t_slip
            order_id = ex_api.single_order(code, _price, 'BUY', remark, amount=t_amount, price_clamp=True)
            if order_id == -2:
                return ex_api, 'Finish'
            if order_id != -1:
                ex_api.buy.loc[order_index, '委托编号'] = order_id
                ex_api.save_buy()
                next_time = now_time + pd.to_timedelta(f'{t_step}s')
                ex_api.buffer[remark]['next_time'] = next_time
                ex_api.rb.record_log(
                    f'{remark} t_wap信息:  下单价格{round(_price, 2)}，下单金额{round(t_amount, 2)},下次下单时间{next_time}')
        return ex_api

    else:
        return ex_api
