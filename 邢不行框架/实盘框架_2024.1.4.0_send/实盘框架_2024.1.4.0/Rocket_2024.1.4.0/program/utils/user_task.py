import math

import numpy as np
import pandas as pd
from program.utils.functions import *
import re
from program.exchange.exchange_api import ExchangeAPI
import requests
import json


def reverse_repo(ex_api, keep=0):
    # 获取账户信息
    account = ex_api.get_account()
    # 计算下单量
    amount = account['可用资金'] - keep
    volume = int(amount / 1000) * 10
    if volume < 0:
        return ex_api

    # 获取深交所一天逆回购
    sz_code = '131810.SZ'
    sz_tick = ex_api.get_tick(sz_code)['委买价'][1]
    # 获取上交所一天逆回购
    sh_code = '204001.SH'
    sh_tick = ex_api.get_tick(sh_code)['委买价'][1]

    code = sz_code
    exchange = '深交所'
    yrt = sz_tick
    if sh_tick > sz_tick:
        code = sh_code
        exchange = '上交所'
        yrt = sh_tick

    # 利率要高于一定水平，避免因为手续费产生亏损
    if yrt > 0.4:
        ex_api.single_order(code, yrt, 'SELL', f'{exchange}国债逆回购', volume)
    else:
        Rb.record_log(f'{exchange}逆回购价格过低{yrt}，已跳过')
    return ex_api


def get_news(**kwargs):
    drop = ('金十', '点击', 'href', '幅扩大')
    try:
        referer_url = "http://finance.sina.com.cn/7x24/?tag=0"
        cookie = "UOR=www.baidu.com,tech.sina.com.cn,; SINAGLOBAL=114.84.181.236_1579684610.152568; UM_distinctid=16fcc8a8b704c8-0a1d2def9ca4c6-33365a06-15f900-16fcc8a8b718f1; lxlrttp=1578733570; gr_user_id=2736e487-ee25-4d52-a1eb-c232ac3d58d6; grwng_uid=d762fe92-912b-4ea8-9a24-127a43143ebf; __gads=ID=d79f786106eb99a1:T=1582016329:S=ALNI_MZoErH_0nNZiM3D4E36pqMrbHHOZA; Apache=114.84.181.236_1582267433.457262; ULV=1582626620968:6:4:1:114.84.181.236_1582267433.457262:1582164462661; ZHIBO-SINA-COM-CN=; SUB=_2AkMpBPEzf8NxqwJRmfoWz2_ga4R2zQzEieKfWADoJRMyHRl-yD92qm05tRB6AoTf3EaJ7Bg2UU4l1CDZXUBCzEuJv3mP; SUBP=0033WrSXqPxfM72-Ws9jqgMF55529P9D9WhqhhGsPWdPjar0R99pFT8s"
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Cookie": cookie,
            "Host": "zhibo.sina.com.cn",
            "Referer": referer_url,
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36"
        }
        url = f'http://zhibo.sina.com.cn/api/zhibo/feed?&page={1}&page_size={100}&zhibo_id=152'
        res = requests.get(url, headers=headers)
        data = res.json()['result']['data']['feed']['list']
        df = pd.DataFrame(data)
        df = df[df['tag'].apply(lambda x: '焦点' in str(x))]
        df = df[['create_time', 'rich_text']]
        df.rename(columns={'create_time': '时间', 'rich_text': '内容'}, inplace=True)
        df['时间'] = pd.to_datetime(df['时间'])
        last_run_time = kwargs['last_run_time']
        df = df[df['时间'] >= last_run_time]

        if not df.empty:
            def _sentence_filter(x, keywords):
                result = re.sub("|".join(keywords), "***", x)
                if '***' in result:
                    return True
                else:
                    return False

            df['drop_flag'] = df['内容'].apply(_sentence_filter, keywords=drop)
            news_df = df[df['drop_flag'] == False]
            del news_df['drop_flag']
            # 排序
            news_df.sort_values(by='时间', inplace=True)
            text = '市场热点：'
            if not news_df.empty:
                for i in news_df.index:
                    text += f'\n{news_df.at[i, "时间"].strftime("%H:%M")}  {news_df.at[i, "内容"]}'
            if len(text) > 10:
                Rb.send_message(text, 'news')
                Rb.record_log('新闻发送成功')
        else:
            return 'Pass'
    except Exception as err:
        text = '抓取新浪新闻数据错误:' + str(err)
        Rb.record_log(text, send=True)
        return 'Pass'
    return


def get_north_fund(**kwargs):
    # 联网获取北向数据，单位亿
    url = "http://push2his.eastmoney.com/api/qt/kamt.kline/get"
    params = {
        "fields1": "f1,f3,f5",
        "fields2": "f51,f52",
        "klt": "101",
        "lmt": "5000",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "cb": "jQuery18305732402561585701_1584961751919",
        "_": "1584962164273",
    }
    r = requests.get(url, params=params)
    data_text = r.text
    data_json = json.loads(data_text[data_text.find("{"): -2])
    nf_df = (
        pd.DataFrame(data_json["data"]["s2n"])
            .iloc[:, 0]
            .str.split(",", expand=True)
    )
    nf_df.columns = ["date", "value"]
    nf_df["value"] = pd.to_numeric(nf_df["value"])

    net_flow_in = round(nf_df['value'].iloc[-1] / 10000, 2)
    last_north_fund = kwargs['last_fun_res']
    if isinstance(last_north_fund, str):
        last_north_fund = 0
    if pd.isna(last_north_fund):
        last_north_fund = 0
    # 当前北向资金数据等级（135亿属于130亿级）
    now_level = net_flow_in - net_flow_in % 10
    # 上一次北向资金数据等级
    last_level = last_north_fund - last_north_fund % 10
    # 如果两次等级超过10亿就发出通知
    if (abs(now_level - last_level) >= 10) and ((net_flow_in - last_north_fund) > 5):
        text = None
        if net_flow_in > 0:
            text = f'当前北向金流入{net_flow_in}亿'
        elif net_flow_in < 0:
            text = f'当前北向金流出{abs(net_flow_in)}亿'
        if text:
            Rb.send_message(text, 'news')
            Rb.record_log(f'北向数据更新成功：{net_flow_in}')
    return now_level


def send_buy_info(ex_api, strategy_filter=[]):
    temp_buy = ex_api.buy.copy()
    temp_buy = temp_buy[~temp_buy['策略名称'].isin(strategy_filter)]
    # 所有订单都有均价时，说明已经完成今日的买入任务
    if not temp_buy['成交均价'].isnull().any():
        temp_buy['开盘价'].fillna(value=0, inplace=True)
        buy_open_zero = temp_buy[temp_buy['开盘价'] == 0].copy()
        if not buy_open_zero.empty:
            # 存在开盘价 = 0,尝试补齐开盘价
            for inx in buy_open_zero.index:
                code = buy_open_zero.loc[inx, '证券代码']
                order_remark = buy_open_zero.loc[inx, '订单标记']
                try:
                    last_price = ex_api.get_tick(code)['开盘价']
                    if pd.notnull(last_price) and float(last_price) > 0:
                        ex_api.buy.loc[ex_api.buy['订单标记'] == order_remark, '开盘价'] = last_price
                        temp_buy.loc[temp_buy['订单标记'] == order_remark, '开盘价'] = last_price
                except:
                    continue
            ex_api.save_buy()
        if temp_buy['开盘价'].eq(0).any():
            Rb.record_log(f'买入计划疑似完成,但是开盘价未被补齐,暂不能发送滑点信息.', send=True)
        else:
            temp_buy['滑点(‰)'] = (temp_buy['成交均价'] / temp_buy['开盘价'] - 1) * 1000
            msg = '=====开盘买入计划已完成=====\n' + ex_api.df2txt(temp_buy[['策略名称', '证券代码', '其他', '滑点(‰)']],
                                                          float_cols=['滑点(‰)'])
            Rb.send_message(msg)
            return 'Finish'


def load_trade_plan(ex_api: ExchangeAPI, **kwargs):
    # 盘中加载订单
    buy_order_path = ex_api.recoder_path + '交易计划.csv'
    buy_order = pd.read_csv(buy_order_path, encoding='gbk', parse_dates=['交易日期'])
    order_date = ex_api.trader_calendar.today
    # 条件1：交易日期是今天的股票
    con1 = buy_order['交易日期'] == order_date
    # 条件2：删除股票代码是empty的内容
    con2 = buy_order['证券代码'] != 'empty'
    today_buy_order = buy_order[con1 & con2].reset_index()
    today_buy_order['证券代码'] = today_buy_order['证券代码'].apply(ex_api.trans_code)

    # 判断一下是否已经被加载过
    today_buy_order['其他'] = today_buy_order['其他'].astype(str)
    con = today_buy_order['其他'].str.contains('√')

    # 没有打钩的就是没有加载过的数据
    new_plan = today_buy_order[~con].copy()

    # 如果没有新的交易计划，直接返回。
    if new_plan.empty:
        return ex_api

    # 加上订单标记
    time_str = order_date.strftime('%y%m%d')
    new_plan['索引'] = new_plan.index
    new_plan['订单标记'] = new_plan['策略名称'] + '+' + time_str + '盘中' + new_plan['索引'].apply(str)

    # 补充一下没有的列
    for col in ex_api.buy.columns:
        if col not in new_plan.columns:
            new_plan[col] = np.nan

    # 如果没有新的交易计划，直接返回。
    if new_plan.empty:
        return ex_api

    # 更新账户资金,如果账户资金异常，说明行情源可能挂了，不去做买入计划的增加
    ex_api.get_account()
    total_cap = ex_api.account['总资产']
    if pd.isnull(total_cap) or (not float(total_cap) > 0):
        Rb.record_log(f'盘中增加交易计划失败，账户总资产异常{ex_api.account.total_asset}，疑似行情源异常。\n'
                   f'可查看论坛https://bbs.quantclass.cn/thread/18505', send=True)
        return ex_api

    # 持仓计划需要补全
    for i in new_plan.index:
        if (new_plan.loc[i, '持仓计划'] == ' ') or pd.isnull(new_plan.loc[i, '持仓计划']):
            if len(ex_api.stg_infos[new_plan.loc[i, '策略名称']]['open_offset']) > 0:
                new_plan.loc[i, '持仓计划'] = ex_api.stg_infos[new_plan.loc[i, '策略名称']]['open_offset'][0]
            else:
                new_plan.loc[i, '持仓计划'] = ex_api.stg_infos[new_plan.loc[i, '策略名称']]['hold_plan'][0]

    # 计算配置中各个策略今日可以开仓的金额：
    # 这里就不会去帮你处理份数限制的事情了，一定要注意。
    # 策略单日开仓金额 = 总资金 x 策略权重 / 资金份数
    for s in ex_api.stg_infos:
        # 获取选股结果
        order_info = new_plan[new_plan['策略名称'] == s].copy()
        if order_info.empty:
            continue
        s_con = ex_api.stg_infos[s]

        # ===处理资金份数
        cap_count = len(s_con['hold_plan'])  # 总资金份数
        open_count = len(order_info['持仓计划'].unique())  # 今日需要开仓的份数
        use_count = len(ex_api.hold[ex_api.hold['策略名称'] == s]['交易日期'].unique())
        avb_count = cap_count - use_count  # 可开仓的资金份数

        # 如果是日内换仓的策略，
        if ('intraday_swap' in s_con.keys()) and s_con['intraday_swap'] > 0:
            avb_count += open_count  # 如果支持日内调仓的策略,可用资金份数需要加上今天开仓的份数

        if avb_count < 0:
            Rb.record_log(f'{s} 资金份数超出限制。最大{cap_count}份资金，已开{use_count}份资金，今日开仓需要{open_count}份资金', send=True)
            continue
        # 策略单日开仓金额 = 总资金 x 策略权重 / 资金份数
        open_amount = total_cap * s_con['strategy_weight'] / cap_count
        # 计算权重分配
        weight_func = eval(s_con['stock_weight'][0])
        order_info = order_info.groupby('持仓计划').apply(lambda g: weight_func(g, s_con))
        order_info['下单金额'] = order_info['股票权重'].apply(lambda x: round(x * open_amount, 2))
        for i in order_info.index:
            con1 = new_plan['证券代码'] == order_info.at[i, '证券代码']
            con2 = new_plan['策略名称'] == s
            new_plan.loc[con1 & con2, '下单金额'] = order_info.at[i, '下单金额']

    if '下单金额' not in new_plan.columns:
        new_plan['下单金额'] = 0
    new_plan['下单金额'].fillna(value=0, inplace=True)
    if new_plan['下单金额'].eq(0).any():
        Rb.record_log('盘中加载订单时,下单金额计算存在异常,检查买入、持仓文件和策略cap_count', send=True)

    # 新的交易计划需要添加到
    new_plan['委托编号'] = ''
    for inx in new_plan.index:
        max_inx = 0 if pd.isnull(ex_api.buy.index.max()) else ex_api.buy.index.max() + 1
        new_plan.loc[inx, '真实索引'] = max_inx
        for col in ex_api.buy.columns:
            ex_api.buy.loc[max_inx, col] = new_plan.loc[inx, col]

    # 将真实索引设置为索引
    new_plan.set_index('真实索引', drop=True, inplace=True)

    # 日内买卖的盘中对冲流程
    new_plan = ex_api.intraday_swap_process(cfg.intraday_swap_dict, new_plan, startup_time=0)

    # 获取一下当前下单需要买入多少钱
    buy_amount = new_plan['下单金额'].sum()
    # 获取一下可用资金
    account = ex_api.get_account()
    # 如果钱不够下单了，需要处理一下
    if buy_amount > account['可用资金']:
        # 这个代码需要debug  需要根据今天卖出之后能用来买的金额，调整新下单股票的金额
        sell_df = ex_api.sell.copy()
        sell_df['当前价格'] = sell_df['证券代码'].apply(lambda x: ex_api.get_now_price(x))
        sell_amount = (sell_df['当前价格'] * sell_df['持仓量']).sum()

        # 卖出之后，可用的资金 = 卖出金额 + 原本的可用资金
        # 同时要考虑价格波动，避免下不了单子，乘以0.95的系数
        can_use = (sell_amount + account['可用资金'])
        # 如果钱还是不足，就需要缩放了
        if buy_amount > can_use:
            adj_rate = can_use / buy_amount
            new_plan['下单金额'] *= adj_rate

    # ===创建买入任务
    if '委托编号' not in new_plan.columns:
        new_plan['委托编号'] = ''
    else:
        new_plan['委托编号'] = new_plan['委托编号'].apply(lambda x: '' if str(x) == 'nan' else x if x == '' else str(int(x)))

    # 生成买入任务
    buy_task_list = []
    for i in new_plan.index:
        if new_plan.at[i, '策略名称'] == '非策略选股':
            continue
        s_con = ex_api.stg_infos[new_plan.at[i, '策略名称']]
        task = TaskControl(task=f'program.exchange.buy_method.{s_con["buy"][0]}', start='9:15', end='15:00',
                           ex_api=ex_api, rest=['11:30', '13:00'], order_index=i, s_config=s_con, **kwargs)
        buy_task_list.append(task)

    # 保存之前，先把需要保存的数据只保留2位小数
    ex_api.buy['下单金额'] = ex_api.buy['下单金额'].apply(lambda x: round(x, 2))
    # 同步最新的买入计划并保存
    ex_api.save_buy()
    # 记录日志
    Rb.record_log(f'获取到新的交易计划：\n {ex_api.df2txt(new_plan[["策略名称", "证券代码"]])}', send=True)

    # 将新获取到的交易计划也写到已加载的文件里面
    for inx in new_plan.index:
        source_inx = new_plan.loc[inx, 'index']
        if '√' not in str(buy_order.loc[source_inx, '其他']):
            buy_order.loc[source_inx, '其他'] = str(buy_order.loc[source_inx, '其他']) + '√'
    # 保存本地文件
    buy_order.to_csv(buy_order_path, encoding='gbk', index=False)

    # 返回值的第二个元素是list，第三个原始是字符串的"Task"，就会向列表中增加新的任务
    return ex_api, buy_task_list, 'Task'
