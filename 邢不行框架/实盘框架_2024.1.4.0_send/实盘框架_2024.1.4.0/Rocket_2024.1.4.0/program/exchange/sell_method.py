from program.exchange.exchange_api import ExchangeAPI
import pandas as pd
import datetime


def base_sell(ex_api: ExchangeAPI, order_index, s_config, **kwargs):
    """
    基础的卖出函数：当日需要卖出的函数先挂涨停价-0.01，如果到尾盘还没卖掉，再转市价卖掉。
    :param ex_api:
    :param order_index:
    :param s_config:
    :param kwargs:
    :return:
    """
    code = ex_api.sell.at[order_index, '证券代码']
    volume = ex_api.sell.at[order_index, '持仓量']
    remark = ex_api.sell.at[order_index, '订单标记']
    order_id = ex_api.sell.at[order_index, '委托编号']
    time_str = s_config['sell'][1]
    # 处理还没下单的情况
    if order_id == '':
        price = ex_api.get_security_detail(code)['涨停价']
        if price > 5:  # 5元以上的报涨停-0.01
            price -= 0.01
        order_id = ex_api.single_order(code, price, 'SELL', remark, volume=volume)
        if order_id == -2:
            return ex_api, 'Finish'
        if order_id != -1:
            ex_api.sell.loc[order_index, '委托编号'] = order_id
            ex_api.save_sell()
    else:  # 处理已完成下单的情况
        # 查询委托信息
        state = ex_api.query_order(order_id)
        # 将成交信息汇总同步到hold中
        if state == '已成':
            ex_api.syn_hod(remark, order_id, s_config)
            return ex_api, 'Finish'
        if (state == '已报') or (state == '部成'):
            # 部成也同步一下持仓
            if state == '部成':
                ex_api.syn_hod(remark, order_id, s_config)
            # 如果只成交了一部分，并且现在已经快接近尾盘了,撤单并且积极促进成交
            end_time_limit = ex_api.get_time(time_str)
            if datetime.datetime.now() >= end_time_limit:  # 接近尾盘的时候 or 废单，撤单重新卖
                # 撤单之前要看看是不是已经跌停了
                price_state = ex_api.price_limit_state(code)
                if price_state == '跌停':
                    return ex_api
                # 撤单下单
                _, state = ex_api.cancel_order(order_id)
                if state in ['已撤', '部撤']:
                    # 同步一下成交信息
                    ex_api.syn_hod(remark, order_id, s_config)
                else:
                    return ex_api

        if (state == '已撤') or (state == '部撤') or (state == '废单'):
            # 做inx查询
            inx = ex_api.hold.loc[ex_api.hold['订单标记'] == remark].index.min()
            if pd.isnull(inx):
                ex_api.rb.record_log(f'{remark}持仓不存在，可能已经卖出。')
                return ex_api, 'Finish'
            # ==重新下单
            end_time_limit = ex_api.get_time(time_str)
            if datetime.datetime.now() >= end_time_limit:
                # 下单价格 = 买一价 * 0.99
                price = ex_api.get_now_price(code)
                price = price * 0.99
                order_id = ex_api.single_order(code, price, 'SELL', remark, volume=ex_api.hold.loc[inx, '持仓量'],
                                               price_clamp=True)
            else:
                # 这里考虑的盘中增加的订单因为买卖对冲合并导致的撤单。时间还没到撤单时间的话，就去把涨停单挂上。
                price = ex_api.get_security_detail(code)['涨停价']
                if price > 5:  # 5元以上的报涨停-0.01
                    price -= 0.01
                order_id = ex_api.single_order(code, price, 'SELL', remark, volume=ex_api.hold.loc[inx, '持仓量'])

            if order_id == -2:
                return ex_api, 'Finish'
            # 修改下单信息
            if order_id != -1:
                ex_api.sell.loc[order_index, '委托编号'] = order_id
                ex_api.save_sell()
            ex_api.save_hold()  # 及时保存结果
    return ex_api
