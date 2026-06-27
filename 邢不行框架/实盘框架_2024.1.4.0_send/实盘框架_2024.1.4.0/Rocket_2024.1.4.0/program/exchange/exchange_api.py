import datetime
import math
import os
import random
import json
from decimal import Decimal, ROUND_HALF_UP
import shutil
import time
import pandas as pd
import requests
from retrying import retry
from xtquant import xtconstant, xtdata
from xtquant.xttrader import XtQuantTrader
from xtquant.xttype import StockAccount
from program.utils.trade_calendar import TradeCalendar

import warnings

warnings.filterwarnings('ignore')

_ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_path = os.path.abspath(os.path.join(_, '../'))


class Rb(object):
    # 这个类主要是做容错用的，没有实际意义
    def record_log(self, msg, _print=True, send=False, robot_type='info'):
        pass


class ExchangeAPI(object):
    account = {}  # 账户资金数据
    position = pd.DataFrame(
        columns=['证券代码', '成交均价', '持仓量', '在途量', '可用量', '冻结量', '昨日持仓量', '市值'])  # 持仓数据
    entrusts = pd.DataFrame(
        columns=['证券代码', '下单价格', '下单量', '订单状态', '订单标记', '委托编号', '成交均价', '成交量', '下单时间',
                 '下单类型', '价格类型'])  # 委托数据
    hold = pd.DataFrame(
        columns=['策略名称', '证券代码', '持仓量', '交易日期', '计划卖出日期', '订单标记', '上笔委托编号', '上笔成交量',
                 '成交均价', '其他'])  # 持仓数据
    buy = pd.DataFrame(
        columns=['交易日期', '策略名称', '证券代码', '下单金额', '委托编号', '开盘价', '成交均价',
                 '订单标记', '持仓计划', '其他'])  # 下单买入的数据
    sell = pd.DataFrame(
        columns=['买入日期', '计划卖出日期', '策略名称', '证券代码', '持仓量', '委托编号', '订单标记',
                 '其他'])  # 下单卖出的数据
    match = pd.DataFrame(columns=['委托编号', '订单标记'])
    security_detail = {}  # 证券的一些基础数据
    subscribe = {}  # 订阅的证券信息
    buffer = {}  # 缓存其他数据用的

    rb = Rb()

    @retry(stop_max_attempt_number=5)
    def __init__(self, user, rb=None, exe_path='D:\\中航证券QMT实盘-交易端\\userdata_mini',
                 session_id=123456 + random.randint(0, 1000), port=58610,
                 recoder_path=root_path + '/data/账户信息/', day_win=60, stg_infos={}, order_limit=50):

        # 配置端口文件
        self.port = port
        # 高风险操作，只有当端口不是58610的时候才需要重置端口
        self.set_port(exe_path)
        # 下单次数限制
        self.order_limit = order_limit
        # 记录日志的模块
        if rb:
            self.rb = rb

        self.exchange = XtQuantTrader(exe_path, session_id)
        self.user = StockAccount(user, 'STOCK')
        self.exchange.start()
        connect_res = self.exchange.connect()
        if connect_res != 0:
            raise Exception('建立交易连接错误')
        subscribe_res = self.exchange.subscribe(self.user)
        if subscribe_res != 0:
            raise Exception('对交易回调进行订阅时发生错误')
        self.recoder_path = recoder_path  # 记录账户信息的路径
        self.trader_calendar = TradeCalendar(rb, day_win)  # 交易日历
        self.remove_trade_plan()
        self.refresh_entrusts()  # 初始化时加载一下当前订单（其实也可以不加，等task刷新）
        # 将策略信息放到ex_api中
        self.stg_infos = stg_infos
        self.buffer['订单状态'] = {}
        self.buffer['下单次数'] = {}
        self.buffer['股票状态'] = {}
        # 初始化订单配置信息

    # region 账户相关函数

    def get_account(self):
        account = self.exchange.query_stock_asset(self.user)
        self.account = {'总资产': account.total_asset, '持仓市值': account.market_value,
                        '可用资金': account.cash, '冻结资金': account.frozen_cash}
        self.rb.record_log(f'查询账户持仓：{str(self.account)}')
        return self.account

    @retry(stop_max_attempt_number=5)
    def single_order(self, code, price, direction, order_remark, volume=0, amount=None, price_clamp=False,
                     test=False, price_type=xtconstant.FIX_PRICE):
        """
        下单函数，amount和volume参数必须填一个。
        :param code:证券代码 600000.SH
        :param price: 下单价格
        :param direction: 下单方向｛BUY，SELL｝
        :param order_remark: 订单标记
        :param amount:下单金额，按照金额下单
        :param volume:下单量，按照下单量下单
        :param price_clamp:是否要添加盘口下单限制
        :param test:测试模式，不下单
        :param price_type:价格类型，详细参考一下迅投文档。
        :return:
        正常情况：返回订单号
        异常情况1：返回-1，表示后续还可以继续下单
        异常情况2：返回-2，表示这笔交易终止
        """

        # 先判断下单次数会不会超过限制
        if code in self.buffer['下单次数'].keys():
            if self.buffer['下单次数'][code] > 50:
                self.rb.record_log(f'下单次数超过限制，不下单，下单代码：{code}')
                return -2
            self.buffer['下单次数'][code] += 1
        else:
            self.buffer['下单次数'][code] = 1

        code2 = self.trans_code(code)
        is_star = 'sh68' in code2
        is_bond = code[:2] in ['11', '12', '18']
        is_bj = 'bj' in code2
        not_star_and_bond = not (is_star or is_bond)
        ins_detail = self.get_security_detail(code)
        if len(ins_detail) == 0:
            ins_detail['价格精度'] = 0.02
            ins_detail['跌停价'] = 0
            ins_detail['涨停价'] = 99999
            price_clamp = True
        # 处理下单价格
        price = self.del_price(price, ins_detail['价格精度'])
        price = self.clamp(price, ins_detail['跌停价'], ins_detail['涨停价'])
        if price_clamp:
            now_price = self.get_now_price(code)
            if 'BUY' in direction:
                price = min(price, self.del_price(now_price * 1.02, ins_detail['价格精度']))  # 连续竞价期间，买单的挂单价不能超过当前价上浮2%
            elif 'SELL' in direction:
                price = max(price, self.del_price(now_price * 0.98, ins_detail['价格精度']))  # 连续竞价期间，卖单的挂单价不能超过当前价下浮2%
        # 处理下单量
        if amount:
            if is_bond:  # 处理可转债
                volume = amount / price
                volume = volume - volume % 10
            else:
                volume = amount / price
                volume = int(volume) if (is_star or is_bj) else volume - volume % 100
        volume = int(volume)
        if volume <= 0:
            msg = f'下单失败，下单量必须大于0 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
            self.rb.record_log(msg, send=True)
            return -1

        if 'BUY' in direction:
            msg = ''
            if is_star and (volume < 200):
                msg = f'买入失败，科创板最低下单量为200 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
            elif is_bond and (volume < 10):
                msg = f'买入失败，可转债最低下单量为10 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
            elif not_star_and_bond and (volume < 100):
                msg = f'买入失败，常规标的最低下单量为100 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
            if len(msg) > 0:
                self.rb.record_log(msg, send=True)
                return -1
        elif '国债逆回购' not in order_remark:  # 卖单 且 不是国债逆回购
            if (is_star and (volume < 200)) or (is_bond and (volume < 10)) or (not_star_and_bond and (volume < 100)):
                self.get_position(save_log=False)
                inx = self.position[self.position['证券代码'] == code].index.min()
                if pd.isnull(inx):
                    self.rb.record_log(f'{order_remark}持仓不存在，可能已经卖出。', send=True)
                    return -1
                if self.position.loc[inx, '可用量'] != volume:
                    if is_star:
                        msg = f'卖出失败，科创板最低下单量为200 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
                    elif is_bond:
                        msg = f'卖出失败，可转债最低下单量为10 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
                    else:
                        msg = f'卖出失败，常规标的最低下单量为100 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume}'
                    self.rb.record_log(msg, send=True)
                    return -1
        # 下单
        bs = {'BUY': xtconstant.STOCK_BUY, 'SELL': xtconstant.STOCK_SELL}[direction]
        if test:
            order_id = '测试下单'
        else:
            order_id = self.exchange.order_stock(self.user, code, bs, volume, price_type, price, '', '')
            self.add_match(order_id, order_remark)
        msg = f'下单成功 {order_remark} {code} {direction} 下单价格：{price} 下单量：{volume} 委托编号：{order_id}'
        self.rb.record_log(msg, send=True)
        return order_id

    @retry(stop_max_attempt_number=5)
    def get_position(self, save_log=True):
        """
        获取账户持仓信息
        :param: save_log 是否写入日志，因为get_position会在single_order里调用，此时写入会有点浪费资源
        :return:
        """
        positions = self.exchange.query_stock_positions(self.user)
        if len(positions) > 0:
            pos_list = []
            for pos in positions:
                pos_info = {'证券代码': pos.stock_code, '成交均价': pos.open_price, '持仓量': pos.volume,
                            '在途量': pos.on_road_volume,
                            '可用量': pos.can_use_volume, '冻结量': pos.frozen_volume,
                            '昨日持仓量': pos.yesterday_volume,
                            '市值': pos.market_value}
                pos_list.append(pos_info)
            pos_df = pd.DataFrame(pos_list)
            pos_df = pos_df[pos_df['持仓量'] > 0].reset_index(drop=True)
            self.position = pos_df
        else:
            self.position = pd.DataFrame(
                columns=['证券代码', '成交均价', '持仓量', '在途量', '可用量', '冻结量', '昨日持仓量', '市值'])
        if save_log:
            self.rb.record_log(f'查询持仓：\n {str(self.position)}')
        return self.position

    def refresh_entrusts(self):
        orders = self.exchange.query_stock_orders(self.user)
        if len(orders) > 0:
            order_list = []
            for order in orders:
                order_info = {'证券代码': order.stock_code, '下单价格': order.price, '下单量': order.order_volume,
                              '订单状态': order.order_status,
                              '委托编号': order.order_id,
                              '成交均价': order.traded_price, '成交量': order.traded_volume,
                              '下单时间': order.order_time,
                              '下单类型': order.order_type, '价格类型': order.price_type}
                order_list.append(order_info)
            order_df = pd.DataFrame(order_list)
            order_df = order_df[order_df['价格类型'].isin([49, 50, 51])].reset_index(drop=True)
            if order_df.empty:
                self.entrusts = pd.DataFrame(
                    columns=['证券代码', '下单价格', '下单量', '订单状态', '订单标记', '委托编号', '成交均价', '成交量',
                             '下单时间', '下单类型', '价格类型'])
            else:
                order_df = pd.merge(order_df, self.match, 'left', ['委托编号'])
                order_df['订单状态'] = order_df['订单状态'].apply(self.del_order_status)
                order_df['下单类型'] = order_df['下单类型'].apply(self.del_order_type)
                order_df['价格类型'] = order_df['价格类型'].apply(self.del_price_type)
                order_df['下单时间'] = order_df['下单时间'].apply(self.stamp2time)
                self.entrusts = order_df
        else:
            self.entrusts = pd.DataFrame(
                columns=['证券代码', '下单价格', '下单量', '订单状态', '订单标记', '委托编号', '成交均价', '成交量',
                         '下单时间', '下单类型', '价格类型'])
        add_row = {'委托编号': 888888, '订单状态': '已成', '下单类型': '买入'}
        self.entrusts.loc[len(self.entrusts)] = add_row
        return self.entrusts

    def query_order(self, order_id):
        order_id = int(order_id)
        if order_id in self.entrusts['委托编号'].to_list():
            state = self.entrusts[self.entrusts['委托编号'] == order_id]['订单状态'].iloc[0]
            if order_id not in self.buffer['订单状态'].keys():
                self.buffer['订单状态'][order_id] = state
                self.rb.record_log(f'查询订单：{order_id}  状态：{state}')
            else:
                if state != self.buffer['订单状态'][order_id]:
                    self.rb.record_log(f'查询订单：{order_id}  状态：{state}')
                    self.buffer['订单状态'][order_id] = state
            return state
        else:
            return '废单'

    @retry(stop_max_attempt_number=5)
    def cancel_order(self, order_id, try_times=10):
        order_id = int(order_id)
        res = -1
        for i in range(0, try_times):
            res = self.exchange.cancel_order_stock(self.user, order_id)
            if res != 0:
                raise Exception(f'撤单发生错误{order_id}')
            time.sleep(0.05)
            self.refresh_entrusts()
            state = self.query_order(order_id)
            self.rb.record_log(f'撤销订单：{order_id}  状态：{state}')
            if (state == '已撤') or (state == '部撤'):
                self.rb.record_log(f'撤单成功:{order_id}', send=True)
                return res, state
            if state in ['已成', '废单']:
                self.rb.record_log(f'撤单失败:{order_id}，订单状态{state}！！！')
                return res, state
        state = self.query_order(order_id)
        self.rb.record_log(f'撤单失败:{order_id}，请手动确认！！！', send=True)
        return res, state

    def del_buy_amount(self):
        """
        将已完成订单的剩余金额分配给未完成的订单
        :return:
        """
        buy_df = self.buy.copy()

    # endregion

    # region 获取数据相关的函数

    @retry(stop_max_attempt_number=5)
    def get_security_detail(self, security):
        if ((security not in self.security_detail.keys()) or
                (self.security_detail[security]['记录时间'] <= self.get_time('9:15:05'))):
            res = xtdata.get_instrument_detail(security)
            rename_dict = {'InstrumentName': '证券名称', 'OpenDate': '上市日期', 'PreClose': '前收盘价',
                           'UpStopPrice': '涨停价', 'DownStopPrice': '跌停价', 'InstrumentStatus': '停牌状态',
                           'PriceTick': '价格精度'}
            ins_detail = {'记录时间': datetime.datetime.now()}  # 防止启动时QMT还没做日切,从而导致涨跌停价不准
            if pd.notnull(res):
                for key, value in rename_dict.items():
                    if value in ['涨停价', '跌停价', '前收盘价']:
                        ins_detail[value] = self.del_price(res[key], str(res['PriceTick']))
                    elif value == '价格精度':
                        ins_detail[value] = str(res[key])
                    else:
                        ins_detail[value] = res[key]
                self.security_detail[security] = ins_detail
                return self.security_detail[security]
            else:
                self.rb.record_log(f'{security}未查询到证券明细')
                return {}
        if security in self.security_detail.keys():
            return self.security_detail[security]

    @retry(stop_max_attempt_number=5)
    def get_tick(self, code_list):
        if not isinstance(code_list, list):
            code_list = [code_list]
        res = xtdata.get_full_tick(code_list)
        ticks = {}
        for code, item in res.items():
            tick = {}
            rename_dict = {'timetag': '时间', 'lastPrice': '最新价', 'open': '开盘价', 'high': '最高价',
                           'low': '最低价',
                           'lastClose': '前收盘价', 'amount': '成交额', 'volume': '成交量', 'stockStatus': '状态',
                           'askPrice': '委卖价', 'bidPrice': '委买价', 'askVol': '委卖量', 'bidVol': '委买量'}
            for key, value in rename_dict.items():
                tick[value] = item[key]
            ticks[code] = tick
        # 检查最新价是不是None 或 NaN 或 0
        now_time = datetime.datetime.now()
        if now_time > now_time.replace(hour=9, minute=30, second=15, microsecond=0):
            for each_code in code_list:
                if len(ticks) > 0:
                    if ('最新价' not in ticks[each_code].keys()) or pd.isnull(ticks[each_code]['最新价']) or (
                            not float(ticks[each_code]['最新价']) > 0):
                        self.rb.record_log('行情源疑似异常，建议检查行情源。\n'
                                           '可参考论坛内容https://bbs.quantclass.cn/thread/18505', send=True)
                    break
                else:
                    self.rb.record_log('行情源疑似异常，建议检查行情源。\n'
                                       '可参考论坛内容https://bbs.quantclass.cn/thread/18505', send=True)
        if len(ticks) == 1:
            ticks = ticks[code_list[0]]
        return ticks

    def on_data(self, data):
        pass

    @retry(stop_max_attempt_number=5)
    def subscribe_security(self, code):
        sub_no = xtdata.subscribe_quote(code, 'tick', callback=self.on_data)
        start = datetime.date.today().strftime('%Y%m%d') + '091500'
        end = datetime.date.today().strftime('%Y%m%d') + '153000'
        xtdata.download_history_data(code, period='tick', start_time=start, end_time=end)
        self.subscribe[code] = sub_no

    def unsubscribe_security(self, code):
        xtdata.unsubscribe_quote(self.subscribe[code])
        self.subscribe.pop(code)

    @retry(stop_max_attempt_number=5)
    def get_market_data(self, code, period, before_open=False, drop_0=True):
        if code not in self.subscribe.keys():
            self.subscribe_security(code)
        if before_open:
            start = datetime.date.today().strftime('%Y%m%d') + '091500'
        else:
            start = datetime.date.today().strftime('%Y%m%d') + '093000'
        end = datetime.date.today().strftime('%Y%m%d') + '153000'
        mkt_data = pd.DataFrame(xtdata.get_market_data([], [code], period='tick', start_time=start, end_time=end)[code])
        rename_dict = {'time': '时间', 'lastPrice': '最新价', 'open': '开盘价', 'high': '最高价', 'low': '最低价',
                       'lastClose': '前收盘价', 'amount': '成交额', 'volume': '成交量', 'askPrice': '委卖价',
                       'bidPrice': '委买价',
                       'askVol': '委卖量', 'bidVol': '委买量'}
        mkt_data = mkt_data[list(rename_dict.keys())].rename(columns=rename_dict)
        mkt_data['时间'] = mkt_data['时间'].apply(self.stamp2time)

        if drop_0:  # 处理没有成交记录的情况
            mkt_data = mkt_data[mkt_data['成交额'] > 0].reset_index(drop=True)
        if mkt_data.empty:
            if datetime.datetime.now() > self.get_time('9:30:15'):
                self.rb.record_log('行情源疑似异常，建议检查行情源。\n'
                                   '可参考论坛内容https://bbs.quantclass.cn/thread/18505', send=True)
            return mkt_data
        if period != 'tick':
            if period == 'open2now':
                mkt_data = {'时间': mkt_data['时间'].iloc[-1],
                            '最新价': mkt_data['最新价'].iloc[-1],
                            '开盘价': mkt_data['开盘价'].iloc[0],
                            '最高价': mkt_data['最高价'].max(),
                            '最低价': mkt_data['最低价'].min(),
                            '前收盘价': mkt_data['前收盘价'].iloc[0],
                            '成交额': mkt_data['成交额'].iloc[-1],
                            '成交量': mkt_data['成交量'].iloc[-1]}
            else:
                resample_dict = {'时间': 'first', '最新价': 'last', '开盘价': 'first', '最高价': 'max', '最低价': 'min',
                                 '成交额': 'last', '成交量': 'last'}
                mkt_data = mkt_data.resample(rule=period, on='时间').agg(resample_dict).reset_index(drop=True)
        return mkt_data

    @retry(stop_max_attempt_number=5)
    def get_now_price(self, code):
        """
        qmt有得时候拿不到价格，在这里用这个接口拿
        :param code:
        :return:
        """
        # 优先相信QMT，先从QMT尝试拿最新价（不同券商的QMT情况不一样，有些QMT在盘前也有最新价数据）
        price = self.get_tick(code)
        price = price['最新价'] if '最新价' in price.keys() else None
        # qmt拿不到数据就从腾讯的接口拿数据
        if pd.isnull(price) or (not float(price) > 0):
            self.rb.record_log(f'{code}从QMT没拿到数据，转腾讯接口')
        else:
            return float(price)
        # QMT未果后，尝试从腾讯、东财、新浪拿数据
        code = self.trans_code(code)

        # 先从第一个腾讯拿数据：腾讯接口在盘前会返回前收盘价，在集合竞价期间会返回集合竞价最新价，目前看来没有问题
        url = f'https://web.sqt.gtimg.cn/q={code}'
        res = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36'
        })
        # """
        # v_sz000001="51~平安银行~000001~11.20~11.17~11.19~520697~270394~250303~11.20~4819~11.19~9416~11.18~15317~11.17~6513~11.16~12080~11.21~4801~11.22~4529~11.23~12281~11.24~9825~11.25~11389~~20230928161424~0.03~0.27~11.24~11.18~11.20/520697/583649730~520697~58365~0.27~4.45~~11.24~11.18~0.54~2173.42~2173.46~0.57~12.29~10.05~0.75~5320~11.21~4.28~4.78~~~1.46~58364.9730~0.0000~0~ ~GP-A~-13.01~1.36~2.54~10.80~0.89~15.46~9.94~-0.80~0.63~-0.36~19405546950~19405918198~5.85~-20.20~19405546950~~~-5.29~0.00~~CNY~0~";
        # """
        res_data = res.text.split('~')
        try:
            now_price = float(res_data[3])
            if now_price > 0:
                time.sleep(0.5)  # 从接口返回的都等0.5s防ban
                return now_price
            else:
                self.rb.record_log(f'{code} 从腾讯获取最新价为0')
        except Exception as e:
            self.rb.record_log(f'{code} 从腾讯获取价格报错{e}')

        # 返回错误从第二个东财接口拿数据：9点15前都会返回-，9点15后正常
        url = (f'http://push2.eastmoney.com/api/qt/stock/get?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2'
               f'&fields=f43,f57,f58&secid={code.replace("sz", "0.").replace("sh", "1.")}&'
               f'cb=jQuery1124032118142796370974_{int(time.time() * 1000000)}&_={int(time.time() * 1000000)}')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
        }
        resp = requests.get(url=url, headers=headers)
        ####
        # jQuery1124032118142796370974_1643266439913({"rc": 0, "rt": 4, "svr": 2887036676, "lt": 1, "full": 1, "dlmkts": "","data": {"f43": "-", "f57": "688138", "f58": "清溢光电"}});
        ####
        try:
            content = resp.content.decode('utf-8')
            res_data = json.loads(content.split(sep='(', maxsplit=1)[1].rsplit(sep=')', maxsplit=1)[0])['data']
            now_price = res_data['f43'].replace('-', '0')
            if float(now_price) > 0:
                time.sleep(0.5)  # 从接口返回的都等0.5s防ban
                return float(now_price)
            else:
                self.rb.record_log(f'{code} 从东财获取最新价为0')
        except Exception as e:
            self.rb.record_log(f'{code} 从东财获取价格报错{e}')

        # 返回错误从第三个新浪拿数据：新浪接口对于SZ在9点25分前返回0，SH会返回前收盘价
        url = f'https://hq.sinajs.cn/list={code}'
        headers = {
            'Referer': 'http://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36 Edg/97.0.1072.62'
        }
        res = requests.get(url, headers=headers)
        # """
        # var hq_str_sz000001="平安银行,11.190,11.170,11.200,11.240,11.180,11.200,11.210,52069678,583649730.000,481927,11.200,941600,11.190,1531700,11.180,651300,11.170,1208000,11.160,480100,11.210,452900,11.220,1228106,11.230,982500,11.240,1138900,11.250,2023-09-28,15:00:03,00";
        # """
        res_data = res.text.split(',')
        try:
            now_price = float(res_data[3])  # 最新价
            last_price = float(res_data[2])  # 前收盘价
            if now_price > 0:
                time.sleep(0.5)  # 从接口返回的都等0.5s防ban
                return now_price
            else:
                if last_price > 0:
                    time.sleep(0.5)  # 从接口返回的都等0.5s防ban
                    return last_price
                else:
                    self.rb.record_log(f'{code} 从新浪获取最新价为0')
        except Exception as e:
            self.rb.record_log(f'{code} 从新浪获取价格报错{e}')
        self.rb.record_log(f'从所有渠道尝试获取{code}最新价格均报错，建议检查', send=True)
        return self.get_security_detail(self.trans_code(code))['前收盘价']

    @staticmethod
    def get_days_price(code_list, start_day, end_day):
        start = (start_day - pd.to_timedelta('11d')).strftime('%Y%m%d') + '091500'
        end = end_day.strftime('%Y%m%d') + '153000'
        for code in code_list:
            xtdata.download_history_data(code, period='1d', start_time=start, end_time=end)
        mkt = xtdata.get_market_data([], code_list, period='1d', start_time=start, end_time=end)
        open_df = mkt['open'].melt(var_name='交易日期', value_name='开盘价', ignore_index=False)
        open_df.reset_index(inplace=True)
        open_df.rename(columns={'index': '证券代码'}, inplace=True)
        close_df = mkt['close'].melt(var_name='交易日期', value_name='收盘价', ignore_index=False)
        close_df.reset_index(inplace=True)
        close_df.rename(columns={'index': '证券代码'}, inplace=True)
        mkt_df = pd.merge(left=open_df, right=close_df, on=['证券代码', '交易日期'], how='outer')
        for k, v in {'preClose': '前收盘价', 'high': '最高价', 'low': '最低价'}.items():
            _df = mkt[k].melt(var_name='交易日期', value_name=v, ignore_index=False)
            _df.reset_index(inplace=True)
            _df.rename(columns={'index': '证券代码'}, inplace=True)
            mkt_df = pd.merge(left=mkt_df, right=_df, on=['证券代码', '交易日期'], how='outer')
        mkt_df['交易日期'] = pd.to_datetime(mkt_df['交易日期'])
        mkt_df = mkt_df[mkt_df['交易日期'] >= start_day]
        return mkt_df

    def price_limit_state(self, code):
        price = self.get_now_price(code)
        detail = self.get_security_detail(code)
        res = '未知'
        if len(detail) > 0:
            price = self.del_price(price, detail['价格精度'])
            detail['涨停价'] = self.del_price(detail['涨停价'], detail['价格精度'])
            detail['跌停价'] = self.del_price(detail['跌停价'], detail['价格精度'])
            if price == detail['涨停价']:
                res = '涨停'
            elif price == detail['跌停价']:
                res = '跌停'
            else:
                res = '正常'
        self.rb.record_log(f'查询到{code}当前价格状态为{res}')
        return res

    # endregion

    # region 其他函数
    def remove_trade_plan(self):
        file_list = os.listdir(self.recoder_path)
        today = self.trader_calendar.today
        file_list = [file for file in file_list if f'{today.year}_{today.month}_{today.day}' not in file]

        buy_plan_list = [file for file in file_list if '买入计划' in file]
        sell_plan_list = [file for file in file_list if '卖出计划' in file]

        for file in buy_plan_list:
            shutil.move(self.recoder_path + file,
                        self.recoder_path.replace('账户信息', '历史信息') + '买入计划/' + file)
        for file in sell_plan_list:
            shutil.move(self.recoder_path + file,
                        self.recoder_path.replace('账户信息', '历史信息') + '卖出计划/' + file)

    @staticmethod
    def trans_code(code):
        if code[-3] == '.':
            return code[-2:].lower() + code[:-3]
        else:
            return code[2:] + '.' + code[:2].upper()

    @staticmethod
    def get_time(time_str):
        """
        输入时间字符串，返该时间字符串的今日时间。
        :param time_str:
        :return:
        """
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        if len(time_str) >= 7:  # 10:50:00
            target_time = datetime.datetime.strptime(f'{today} {time_str}', "%Y-%m-%d %H:%M:%S")
        else:  # 10:50
            target_time = datetime.datetime.strptime(f'{today} {time_str}', "%Y-%m-%d %H:%M")
        return target_time

    @staticmethod
    def del_price(price, accuracy='0.01'):
        if pd.isnull(accuracy):
            accuracy = '0.01'
        if pd.isnull(price):
            return None
        return float(Decimal(price).quantize(Decimal(str(accuracy)), rounding=ROUND_HALF_UP))

    @staticmethod
    def clamp(num, min_num, max_num):
        num = min(num, max_num)
        num = max(min_num, num)
        return num

    @staticmethod
    def key_value_link(ipt, query_dict):
        if isinstance(ipt, int):
            return query_dict[ipt] if ipt in query_dict.keys() else ipt
        elif isinstance(ipt, str):
            for key in query_dict.keys():
                if query_dict[key] == ipt:
                    return key
            return ipt

    def del_order_status(self, status):
        status_dict = {48: '未报', 49: '待报', 50: '已报', 51: '已报待撤', 52: '部成待撤', 53: '部撤', 54: '已撤',
                       55: '部成', 56: '已成', 57: '废单', 255: '未知'}
        return self.key_value_link(status, status_dict)

    def del_order_type(self, order_type):
        type_dict = {23: '证券买入', 24: '证券卖出', 27: '融资买入', 28: '融券卖出', 29: '买券还券', 30: '直接还券',
                     31: '卖券还款', 32: '直接还款'}
        return self.key_value_link(order_type, type_dict)

    def del_price_type(self, price_type):
        type_dict = {49: '市价', 50: '限价', 51: '最优价', 52: '配股', 53: '转托', 54: '申购', 55: '回购', 56: '配售',
                     57: '指定',
                     58: '转股', 59: '回售', 60: '股息', 68: '深圳配售确认', 69: '配售放弃', 70: '无冻质押'}
        return self.key_value_link(price_type, type_dict)

    @staticmethod
    def stamp2time(stamp, utc=True):
        stamp_len = len(str(stamp))
        unit = {10: 's', 13: 'ms', 19: 'ns'}[stamp_len]
        if utc:
            local_time = pd.to_datetime(stamp, unit=unit) + pd.to_timedelta('8H')
        else:
            local_time = pd.to_datetime(stamp, unit=unit)
        return local_time

    def _ini_hold_file(self):
        # 初始化记录持仓的文件
        hold_df = self.position[['证券代码', '持仓量', '成交均价']].copy()
        hold_df['策略名称'] = '非策略选股'
        hold_df['交易日期'] = self.trader_calendar.today  # 默认是今天下单的
        hold_df['计划卖出日期'] = self.trader_calendar.today + datetime.timedelta(days=10000)  # 默认1万天后卖出
        hold_df['订单标记'] = hold_df.index
        hold_df['订单标记'] = hold_df['订单标记'].apply(lambda x: '非策略选股+' + str(x))
        hold_df['上笔委托编号'] = 0
        hold_df['上笔成交量'] = 0
        hold_df['其他'] = ''
        self.hold = hold_df[
            ['策略名称', '证券代码', '持仓量', '交易日期', '计划卖出日期', '订单标记', '上笔委托编号', '上笔成交量',
             '成交均价', '其他']]
        # 让今日需要卖出的排在后面，这样防止卖出标的后导致的hold行数调整引发risk函数异常。
        self.hold.sort_values(by=['计划卖出日期', '交易日期'], ascending=[False, False], inplace=True)
        self.save_hold()
        return self.hold

    def compare_change(self, name):
        """
        找到文件的变更点
        :param name:
        :return:
        """
        if name == 'hold':
            if '历史持仓' in self.buffer.keys():
                old_df = self.buffer['历史持仓'].copy()
            else:
                old_df = pd.DataFrame()
            new_df = self.hold.copy()
            self.buffer['历史持仓'] = new_df.copy()
        elif name == 'buy':
            if '历史买入' in self.buffer.keys():
                old_df = self.buffer['历史买入'].copy()
            else:
                old_df = pd.DataFrame()
            new_df = self.buy.copy()
            self.buffer['历史买入'] = new_df.copy()
        elif name == 'sell':
            if '历史卖出' in self.buffer.keys():
                old_df = self.buffer['历史卖出'].copy()
            else:
                old_df = pd.DataFrame()
            new_df = self.sell.copy()
            self.buffer['历史卖出'] = new_df.copy()

        if old_df.empty:
            txt = str(new_df)
        else:
            common_cols = ['策略名称', '证券代码', '订单标记']
            com_df = pd.merge(old_df, new_df, how='outer', on=common_cols, suffixes=('_old', '_new'), indicator=True)

            txt = ''
            # 找到新增的行数
            add_df = com_df[com_df['_merge'] == 'right_only']
            if add_df.shape[0] > 0:
                new_cols = [col for col in com_df.columns if '_new' in col]
                txt += '新增数据：\n' + str(add_df[common_cols + new_cols]) + '\n'

            # 找到删除的行数
            del_df = com_df[com_df['_merge'] == 'left_only']
            old_cols = [col for col in com_df.columns if '_old' in col]
            if del_df.shape[0] > 0:
                txt += '\n删除数据：\n' + str(del_df[common_cols + old_cols]) + '\n'

            # 找到有变更的数据
            both_df = com_df[com_df['_merge'] == 'both']
            both_df['其他_old'].fillna(value='', inplace=True)
            both_df['其他_new'].fillna(value='', inplace=True)
            for col in old_cols:
                both_df[col.replace('_old', '_cp')] = both_df[col] == both_df[col.replace('_old', '_new')]
            cp_cols = [col for col in both_df.columns if '_cp' in col]
            change_df = both_df[both_df[cp_cols].sum(axis=1) < len(cp_cols)]
            if change_df.shape[0] > 0:
                txt += '\n数据变更：\n'
                for i in change_df.index:
                    txt += f'策略名称：{change_df.loc[i, "策略名称"]}, 证券代码：{change_df.loc[i, "证券代码"]}, 订单标记：{change_df.loc[i, "订单标记"]}'
                    for col in cp_cols:
                        if change_df.loc[i, col] == False:
                            txt += f', {col.replace("_cp", "")}：{change_df.loc[i, col.replace("_cp", "_old")]} -> {change_df.loc[i, col.replace("_cp", "_new")]} '
                    txt += '\n'
            if txt == '':
                txt = '无变更'
        return txt

    # 保存记录持仓的文件
    def save_hold(self):
        hold_path = self.recoder_path + '当前持仓.csv'
        self.hold.to_csv(hold_path, encoding='gbk', index=False)
        txt = self.compare_change('hold')
        self.rb.record_log(f'保存持仓：\n {txt}')

    # 保存记录今日买单的文件
    def save_buy(self):
        today = self.trader_calendar.today
        buy_path = self.recoder_path + f'{today.year}_{today.month}_{today.day}买入计划.csv'
        self.buy.to_csv(buy_path, encoding='gbk', index=False)
        txt = self.compare_change('buy')
        self.rb.record_log(f'保存买入计划：\n {txt}')

    # 保存记录今日卖单的文件
    def save_sell(self):
        today = self.trader_calendar.today
        sell_path = self.recoder_path + f'{today.year}_{today.month}_{today.day}卖出计划.csv'
        self.sell.to_csv(sell_path, encoding='gbk', index=False)
        txt = self.compare_change('sell')
        self.rb.record_log(f'保存卖出计划：\n {txt}')

    # 初始化今日订单匹配的文件
    def ini_match(self):
        # 当天的订单信息汇总
        math_path = root_path + '/data/历史信息/当日订单匹配信息.csv'
        if not os.path.exists(math_path):
            self.match.to_csv(math_path, encoding='gbk', index=False)
        else:
            # 如果不今天的文件也新建一个
            if datetime.datetime.fromtimestamp(os.stat(math_path).st_ctime).date() < self.trader_calendar.today:
                self.match.to_csv(math_path, encoding='gbk', index=False)
            else:  # 如果是今天的文件，从本地读一下
                self.match = pd.read_csv(math_path, encoding='gbk')

    def add_match(self, order_id, remark):
        max_inx = 0 if self.match.empty else self.match.index.max() + 1
        self.match.loc[max_inx, '委托编号'] = order_id
        self.match.loc[max_inx, '订单标记'] = remark
        self.save_match()

    def save_match(self):
        # 当天的订单信息汇总
        math_path = root_path + '/data/历史信息/当日订单匹配信息.csv'
        self.match.to_csv(math_path, encoding='gbk', index=False)

    # 对比本地记录的持仓和线上持仓的区别
    def compare_hold_and_position(self):
        hold_path = self.recoder_path + '当前持仓.csv'
        self.get_position()
        self.rb.record_log(f'获取到线上持仓信息：\n {str(self.position)}')
        if not os.path.exists(hold_path):
            self._ini_hold_file()
        else:
            if self.hold.empty:
                self.hold = pd.read_csv(hold_path, encoding='gbk', parse_dates=['计划卖出日期'])
                # 补充一下后面添加的两个字段
                if '上笔委托编号' not in self.hold.columns:
                    self.hold['上笔委托编号'] = 0
                if '上笔成交量' not in self.hold.columns:
                    self.hold['上笔成交量'] = 0
                # 保持列名顺序统一
                self.hold = self.hold[['策略名称', '证券代码', '持仓量', '交易日期', '计划卖出日期', '订单标记',
                                       '上笔委托编号', '上笔成交量', '成交均价', '其他']]
            # 如果本地持仓不为空，但是线上持仓为空，需要人为确认
            if self.position.empty and (not self.hold.empty):
                txt = '本地持仓不为空，但是线上持仓为空。可能原因是：' \
                      '\n1、获取线上持仓失败，若继续运行会丢失持仓信息。建议重启电脑检查qmt行情源' \
                      '\n2、本地持仓文件是错误的，比如是历史的旧文件或者其他地方拷贝过来的' \
                      '\n请人工介入判断，若确认无误，在程序页面输入y后程序将继续执行'
                self.rb.record_log(txt, _print=False, send=True)
                input_msg = input(txt)
                if not input_msg.lower() == 'y':
                    self.rb.record_log('程序终止', _print=False, send=True)
                    raise Exception('人为终止程序')
                else:
                    self.rb.record_log('已输入y，程序将继续执行', send=True)
            self.hold['交易日期'] = pd.to_datetime(self.hold['交易日期'])
            self.rb.record_log(f'本地持仓信息：\n {str(self.hold)}')
            hold_list = self.hold['证券代码'].unique().tolist()
            pos_list = self.position['证券代码'].unique().tolist()
            # 先找出实际持仓有，但是记录里面没有到股票（意料之外的股票）
            unknown_list = [i for i in pos_list if i not in hold_list]
            for code in unknown_list:
                if self.hold.empty:
                    inx = 0
                else:
                    inx = self.hold.index.max() + 1
                self.hold.loc[inx, '策略名称'] = '非策略选股'
                self.hold.loc[inx, '证券代码'] = code
                self.hold.loc[inx, '持仓量'] = self.position[self.position['证券代码'] == code]['持仓量'].iloc[0]
                self.hold.loc[inx, '交易日期'] = self.trader_calendar.today
                self.hold.loc[inx, '成交均价'] = self.position[self.position['证券代码'] == code]['成交均价'].iloc[0]
                self.hold.loc[inx, '计划卖出日期'] = self.trader_calendar.today + datetime.timedelta(days=10000)  # 1万天后卖出
                self.hold.loc[inx, '订单标记'] = '非策略选股+' + str(inx)
                self.hold.loc[inx, '上笔委托编号'] = 0
                self.hold.loc[inx, '上笔成交量'] = 0
            for code in list(set(pos_list).union(set(hold_list))):
                if code not in self.position['证券代码'].tolist():  # 处理特殊情况，持仓量不含该股票
                    self.hold = self.hold[self.hold['证券代码'] != code]
                    continue
                hold_sum = self.hold[self.hold['证券代码'] == code]['持仓量'].sum()
                pos_sum = self.position[self.position['证券代码'] == code]['持仓量'].iloc[0]
                diff = hold_sum - pos_sum
                # 如果记录的数据比实际持有的多，说明被意外平掉了一部分，按照计划平仓日期由近到远依次减去
                if diff > 0:
                    self.hold = self.hold.sort_values(by=['计划卖出日期'], ascending=True).reset_index(drop=True)
                    # 优先在非策略选股上扣掉平仓的部分
                    i_hold = self.hold[
                        (self.hold['策略名称'] == '非策略选股') & (self.hold['证券代码'] == code)].index.min()
                    if pd.notnull(i_hold):
                        if self.hold.at[i_hold, '策略名称'] == '非策略选股':
                            qty_reduce = min(self.hold.at[i_hold, '持仓量'], diff)
                            self.hold.at[i_hold, '持仓量'] -= qty_reduce
                            diff -= qty_reduce
                    if diff > 0:
                        for i in self.hold.index:
                            if self.hold.at[i, '证券代码'] == code:
                                qty_reduce = min(self.hold.at[i, '持仓量'], diff)
                                self.hold.at[i, '持仓量'] -= qty_reduce
                                diff -= qty_reduce
                                if diff <= 0:
                                    break
                # 如果记录的数据比实际持有的少，说明超额加仓了，在最后的一个计划持仓日一并卖出
                elif diff < 0:
                    self.hold = self.hold.sort_values(by=['计划卖出日期'], ascending=True).reset_index(drop=True)
                    for i in range(self.hold.index.max(), -1, -1):
                        if self.hold.at[i, '证券代码'] == code:
                            self.hold.at[i, '持仓量'] -= diff  # diff是负值，-就是加
                            break

            # 删除持仓为0的数据
            self.hold = self.hold[self.hold['持仓量'] > 0]
            self.hold['交易日期'] = pd.to_datetime(self.hold['交易日期'])  # 数据格式转换

            if datetime.datetime.now() >= self.get_time('15:00:03'):
                # 订单标记后面带_temp的，需要合并
                if any(self.hold['订单标记'].str.endswith('_temp')):
                    hold = self.hold.copy()
                    hold['temp'] = 0
                    hold.loc[hold['订单标记'].str.endswith('_temp'), 'temp'] = 1
                    hold.sort_values(by='temp', ascending=True, inplace=True)
                    hold['订单标记'] = hold['订单标记'].apply(lambda x: x.strip('_temp'))
                    hold['持仓金额'] = hold['持仓量'] * hold['成交均价']
                    agg_dict = {'策略名称': 'first', '证券代码': 'first', '持仓量': 'sum',
                                '交易日期': 'first', '计划卖出日期': 'first', '上笔委托编号': 'first',
                                '上笔成交量': 'first', '成交均价': 'first', '其他': 'first',
                                '持仓金额': 'sum', 'temp': 'sum'}
                    hold_groupby = hold.groupby(['订单标记']).agg(agg_dict).reset_index(drop=False)
                    hold_groupby.loc[hold_groupby['temp'] > 0, '成交均价'] = hold_groupby['持仓金额'] / hold_groupby[
                        '持仓量']
                    self.hold = hold_groupby[['策略名称', '证券代码', '持仓量', '交易日期', '计划卖出日期', '订单标记',
                                              '上笔委托编号', '上笔成交量', '成交均价', '其他']].copy()

            # 让今日需要卖出的排在后面，这样防止卖出标的后导致的hold行数调整引发risk函数异常。
            self.hold.sort_values(by=['计划卖出日期', '交易日期'], ascending=[False, False], inplace=True)
            self.save_hold()
            self.rb.record_log(f'更新本地持仓信息：\n {str(self.hold)}')
            return self.hold

    # 加载下单数据
    def create_order(self, order_date):
        today = self.trader_calendar.today
        buy_path = self.recoder_path + f'{today.year}_{today.month}_{today.day}买入计划.csv'
        sell_path = self.recoder_path + f'{today.year}_{today.month}_{today.day}卖出计划.csv'
        today_first = True
        if not os.path.exists(buy_path):
            # 买入订单:从交易计划中读取信息
            buy_order_path = self.recoder_path + '交易计划.csv'
            if os.path.exists(buy_order_path):
                buy_order = pd.read_csv(buy_order_path, encoding='gbk', parse_dates=['交易日期'])
            else:
                buy_order = pd.DataFrame(columns=['交易日期', '策略名称', '证券代码', '持仓计划', '其他'])
            # 条件1：交易日期是今天的股票
            con1 = buy_order['交易日期'] == order_date
            # 条件2：删除股票代码是empty的内容
            con2 = buy_order['证券代码'] != 'empty'
            today_buy_order = buy_order[con1 & con2].reset_index()
            today_buy_order['证券代码'] = today_buy_order['证券代码'].apply(self.trans_code)
            time_str = order_date.strftime('%y%m%d')
            for i in today_buy_order.index:
                # 如果没有填写持仓计划，先看看这个策略有没有今天的开仓的offset，有的话就取第一个，没有的话取配置的offset的第一个
                if (today_buy_order.loc[i, '持仓计划'] == ' ') or pd.isnull(today_buy_order.loc[i, '持仓计划']):
                    if len(self.stg_infos[today_buy_order.loc[i, '策略名称']]['open_offset']) > 0:
                        today_buy_order.loc[i, '持仓计划'] = self.stg_infos[today_buy_order.loc[i, '策略名称']]['open_offset'][
                            0]
                    else:
                        today_buy_order.loc[i, '持仓计划'] = self.stg_infos[today_buy_order.loc[i, '策略名称']]['hold_plan'][0]

                for col in ['交易日期', '策略名称', '证券代码', '持仓计划', '其他']:
                    self.buy.loc[i, col] = today_buy_order.loc[i, col]
                self.buy.loc[i, '订单标记'] = f'{today_buy_order.loc[i, "策略名称"]}+{time_str}_{i}'

                # 已经加载过的订单在原来的订单中加入标记
                inx = today_buy_order.loc[i, 'index']
                if pd.isnull(buy_order.loc[inx, '其他']):
                    buy_order.loc[inx, '其他'] = '√'
                elif '√' not in str(buy_order.loc[inx, '其他']):
                    buy_order.loc[inx, '其他'] = str(buy_order.loc[inx, '其他']) + '√'

            # 保存买入信息
            self.save_buy()
            # 保存一下交易计划
            buy_order.to_csv(buy_order_path, encoding='gbk', index=False)

        else:
            self.buy = pd.read_csv(buy_path, encoding='gbk', parse_dates=['交易日期'])
            today_first = False
        if not os.path.exists(sell_path):
            # 卖出计划从当前持仓中生成
            if self.hold.empty:
                hold_path = self.recoder_path + '当前持仓.csv'
                self.hold = pd.read_csv(hold_path, encoding='gbk', parse_dates=['计划卖出日期'])
            sell_order = self.hold[self.hold['计划卖出日期'] <= self.trader_calendar.today].copy()
            sell_order.reset_index(drop=True, inplace=True)
            for i in sell_order.index:
                for col in ['策略名称', '证券代码', '持仓量', '计划卖出日期', '订单标记', '其他']:
                    self.sell.loc[i, col] = sell_order.loc[i, col]
                self.sell.loc[i, '买入日期'] = sell_order.loc[i, '交易日期']
            # 保存卖出信息
            self.save_sell()
        else:
            self.sell = pd.read_csv(sell_path, encoding='gbk', parse_dates=['买入日期'])
            today_first = False
        return today_first

    def load_orders(self):
        today = self.trader_calendar.today
        buy_path = self.recoder_path + f'{today.year}_{today.month}_{today.day}买入计划.csv'
        sell_path = self.recoder_path + f'{today.year}_{today.month}_{today.day}卖出计划.csv'
        self.buy = pd.read_csv(buy_path, encoding='gbk', parse_dates=['交易日期'])
        self.buy['委托编号'] = self.buy['委托编号'].apply(lambda x: '' if str(x) == 'nan' else str(int(x)))
        self.sell = pd.read_csv(sell_path, encoding='gbk', parse_dates=['买入日期'])
        self.sell['委托编号'] = self.sell['委托编号'].apply(lambda x: '' if str(x) == 'nan' else str(int(x)))
        self.rb.record_log('=====下单前买入计划=====\n' + self.df2txt(self.buy, float_cols=['下单金额']), True)
        self.rb.record_log('=====下单前卖出计划=====\n' + self.df2txt(self.sell, float_cols=['持仓量']), True)

    # 将成交信息同步到hold上
    def syn_hod(self, order_remark, order_id, s_config):
        temp_ent = self.entrusts[self.entrusts['委托编号'] == int(order_id)].copy()
        # 因为废单等原因，这笔订单不一定查的到
        if temp_ent.empty:
            return
        else:
            direction = temp_ent['下单类型'].iloc[0]
            state = temp_ent['订单状态'].iloc[0]
            volume = temp_ent['成交量'].iloc[0]
            price = temp_ent['成交均价'].iloc[0]

        if ('买入' in direction) and (int(order_id) != 888888):
            if order_remark in self.hold['订单标记'].to_list():
                inx = self.hold[self.hold['订单标记'] == order_remark].index.min()
            else:
                if self.hold.index.max() >= 0:
                    inx = self.hold.index.max() + 1
                else:
                    inx = 0
            temp_buy = self.buy[self.buy['订单标记'] == order_remark].copy()
            self.hold.loc[inx, '策略名称'] = temp_buy['策略名称'].iloc[0]
            self.hold.loc[inx, '证券代码'] = temp_buy['证券代码'].iloc[0]
            # 如果上次订单ID是空的，说明第一次同步，加一下新的订单
            last_order_id = self.hold.loc[inx, '上笔委托编号']
            last_ap = self.hold.loc[inx, '成交均价']
            if (pd.isnull(last_order_id) and pd.isnull(last_ap)) or (last_order_id == 0 and pd.isnull(last_ap)):
                self.hold.loc[inx, '持仓量'] = volume
                self.hold.loc[inx, '成交均价'] = price
                # 第一次记录的时候还需要多记录一些东西
                self.hold.loc[inx, '交易日期'] = temp_buy['交易日期'].iloc[0]
                if ('intraday_swap' in s_config.keys()) and s_config['intraday_swap'] == 1:
                    self.hold.loc[inx, '计划卖出日期'] = self.trader_calendar.get_date_by_rule(temp_buy['持仓计划'].iloc[0], 1)
                else:
                    self.hold.loc[inx, '计划卖出日期'] = self.trader_calendar.get_date_by_rule(temp_buy['持仓计划'].iloc[0])
                self.hold.loc[inx, '订单标记'] = order_remark
                self.hold.loc[inx, '其他'] = temp_buy['其他'].iloc[0]
                # 更新数据供下次同步使用
                self.hold.loc[inx, '上笔委托编号'] = order_id
                self.hold.loc[inx, '上笔成交量'] = volume
            # 如果当前ID和上一次ID是一样的
            elif int(last_order_id) == int(order_id):
                # 上笔查询到的订单成交量
                last_volume = 0 if pd.isnull(self.hold.loc[inx, '上笔成交量']) else self.hold.loc[inx, '上笔成交量']
                # 当前这笔订单的成交量
                order_volume = 0 if pd.isnull(volume) else volume
                # 如果当前订单和上一笔订单的成交量不一样，需要更新一下成交均价
                if last_volume != order_volume:
                    # 累计成交额 = (当前记录的持仓量 - 上笔查询到的持仓量) x 记录的均价 + 当前成交量 x 当前成交均价
                    # 成交均价 = 累计成交额 / (当前记录的持仓量 - 上笔查询到的持仓量 + 当前成交量)
                    hist_hold = 0 if pd.isnull(self.hold.loc[inx, '持仓量']) else self.hold.loc[inx, '持仓量']
                    hist_avg_price = 0 if pd.isnull(self.hold.loc[inx, '成交均价']) else self.hold.loc[inx, '成交均价']
                    order_avg_price = 0 if pd.isnull(price) else price
                    total_amount = (hist_hold - last_volume) * hist_avg_price + order_volume * order_avg_price
                    total_volume = hist_hold - last_volume + order_volume
                    self.hold.loc[inx, '成交均价'] = total_amount / total_volume if total_volume > 0 else 0
                    # 持仓量 = 当前记录的持仓量 - 上笔查询到的持仓量 + 当前成交量
                    self.hold.loc[inx, '持仓量'] = hist_hold - last_volume + order_volume
                    # 更新数据供下次同步使用
                    self.hold.loc[inx, '上笔委托编号'] = order_id
                    self.hold.loc[inx, '上笔成交量'] = order_volume

            # 如果和上次的不同
            elif int(last_order_id) != int(order_id):
                # 当前这笔订单的成交量
                order_volume = 0 if pd.isnull(volume) else volume
                order_avg_price = 0 if pd.isnull(price) else price
                hist_hold = 0 if pd.isnull(self.hold.loc[inx, '持仓量']) else self.hold.loc[inx, '持仓量']
                hist_avg_price = 0 if pd.isnull(self.hold.loc[inx, '成交均价']) else self.hold.loc[inx, '成交均价']

                total_amount = hist_hold * hist_avg_price + order_volume * order_avg_price
                total_volume = hist_hold + order_volume
                # 持仓量 = 历史持仓量 + 最新持仓量
                self.hold.loc[inx, '持仓量'] = total_volume
                # 持仓均价 = （历史持仓量 x 历史均价 + 当前持仓量x当前均价）/(历史持仓量 + 当前持仓量)
                self.hold.loc[inx, '成交均价'] = total_amount / total_volume if total_volume > 0 else 0
                # 更新数据供下次同步使用
                self.hold.loc[inx, '上笔委托编号'] = order_id
                self.hold.loc[inx, '上笔成交量'] = order_volume

            if state == '已成':
                self.buy.loc[self.buy['订单标记'] == order_remark, '成交均价'] = self.hold.loc[inx, '成交均价']
                try:
                    self.buy.loc[self.buy['订单标记'] == order_remark, '开盘价'] = \
                        self.get_tick(self.hold.loc[inx, '证券代码'])['开盘价']
                except:
                    self.rb.record_log(f'{order_remark} 完成交易写入开盘价时异常,暂不写入开盘价.')
                self.save_buy()
        elif '卖出' in direction:
            inx = self.hold.loc[(self.hold['订单标记'] == order_remark)].index.min()
            if pd.isnull(inx):
                self.rb.record_log(f'{order_remark}持仓不存在，可能已经卖出。')
            else:
                # 如果是废单，不要同步
                if state != '废单':
                    sell_inx = self.sell[self.sell['委托编号'] == order_id].index.min()
                    if pd.isnull(sell_inx):
                        self.rb.record_log(f'未在卖出计划中找到订单{order_id}', send=True)
                        return
                    if '卖单信息' not in self.buffer.keys():
                        self.buffer['卖单信息'] = {}
                    if order_remark not in self.buffer['卖单信息'].keys():
                        self.buffer['卖单信息'][order_remark] = {'订单号': order_id, '成交量': 0}
                    if order_id == self.buffer['卖单信息'][order_remark]['订单号']:
                        if self.buffer['卖单信息'][order_remark]['成交量'] != volume:
                            diff_volume = volume - self.buffer['卖单信息'][order_remark]['成交量']
                            hold = self.sell.loc[sell_inx, '持仓量'] - diff_volume
                            self.sell.loc[sell_inx, '持仓量'] = hold
                            self.hold.loc[inx, '持仓量'] = hold
                            self.hold = self.hold[
                                self.hold['持仓量'] > 0]  # .reset_index(drop=True)不重置index,因为risk_method的问题
                            self.save_sell()
                            self.buffer['卖单信息'][order_remark] = {'订单号': order_id, '成交量': volume}
                    else:
                        hold = self.sell.loc[sell_inx, '持仓量'] - volume
                        self.sell.loc[sell_inx, '持仓量'] = hold
                        self.hold.loc[inx, '持仓量'] = hold
                        self.hold = self.hold[self.hold['持仓量'] > 0]  # .reset_index(drop=True)不重置index,因为risk_method的问题
                        self.save_sell()
                        self.buffer['卖单信息'][order_remark] = {'订单号': order_id, '成交量': volume}
        self.save_hold()

    # 日内换仓专用的成交信息同步
    def syn_hod_buy_swap(self, order_remark, volume, avg_price, order_id, intraday_swap):
        if order_remark in self.hold['订单标记'].to_list():
            inx = self.hold[self.hold['订单标记'] == order_remark].index.min()
        else:
            if self.hold.index.max() >= 0:
                inx = self.hold.index.max() + 1
            else:
                inx = 0
        temp_buy = self.buy[self.buy['订单标记'] == order_remark].copy()
        self.hold.loc[inx, '策略名称'] = temp_buy['策略名称'].iloc[0]
        self.hold.loc[inx, '证券代码'] = temp_buy['证券代码'].iloc[0]
        # 如果上次订单ID是空的，说明第一次同步，加一下新的订单
        last_order_id = self.hold.loc[inx, '上笔委托编号']
        if (pd.isnull(last_order_id)) or (last_order_id == 0):
            self.hold.loc[inx, '持仓量'] = volume
            self.hold.loc[inx, '成交均价'] = avg_price
            # 第一次记录的时候还需要多记录一些东西
            self.hold.loc[inx, '交易日期'] = temp_buy['交易日期'].iloc[0]
            if intraday_swap == 1:
                self.hold.loc[inx, '计划卖出日期'] = self.trader_calendar.get_date_by_rule(temp_buy['持仓计划'].iloc[0], 1)
            else:
                self.hold.loc[inx, '计划卖出日期'] = self.trader_calendar.get_date_by_rule(temp_buy['持仓计划'].iloc[0])
            self.hold.loc[inx, '订单标记'] = order_remark + '_temp'
            self.hold.loc[inx, '其他'] = temp_buy['其他'].iloc[0]
            # 更新数据供下次同步使用
            self.hold.loc[inx, '上笔委托编号'] = order_id
            self.hold.loc[inx, '上笔成交量'] = volume

        # 已经有过订单信息，需要直接在新的订单上更新就好
        else:
            # 当前这笔订单的成交量
            order_volume = volume
            order_avg_price = avg_price
            hist_hold = 0 if pd.isnull(self.hold.loc[inx, '持仓量']) else self.hold.loc[inx, '持仓量']
            hist_avg_price = 0 if pd.isnull(self.hold.loc[inx, '成交均价']) else self.hold.loc[inx, '成交均价']

            total_amount = hist_hold * hist_avg_price + order_volume * order_avg_price
            total_volume = hist_hold + order_volume
            # 持仓量 = 历史持仓量 + 最新持仓量
            self.hold.loc[inx, '持仓量'] = total_volume
            # 持仓均价 = （历史持仓量 x 历史均价 + 当前持仓量x当前均价）/(历史持仓量 + 当前持仓量)
            self.hold.loc[inx, '成交均价'] = total_amount / total_volume if total_volume > 0 else 0
            # 更新数据供下次同步使用
            self.hold.loc[inx, '上笔委托编号'] = order_id
            self.hold.loc[inx, '上笔成交量'] = order_volume

        # # 向买入计划同步一下订单信息
        # self.buy.loc[self.buy['订单标记'] == order_remark, '成交均价'] = self.hold.loc[inx, '成交均价']
        try:
            self.buy.loc[self.buy['订单标记'] == order_remark, '开盘价'] = \
                self.get_tick(self.hold.loc[inx, '证券代码'])['开盘价']
        except:
            self.rb.record_log(f'{order_remark} 完成交易写入开盘价时异常,暂不写入开盘价.')
        self.save_buy()
        self.save_hold()

    def _ini_account_file(self, now_time):
        ant_df = pd.DataFrame()
        ant_df.loc[0, '记录时间'] = now_time.strftime("%Y-%m-%d %H:%M")
        ant_df.loc[0, '总资产'] = self.account['总资产']
        ant_df.loc[0, '资金划转'] = 0.0
        ant_df.loc[0, '份额'] = self.account['总资产']
        ant_df.loc[0, '净值'] = 1.0
        return ant_df

    def recoder(self):
        """
        记录每日净值以及持仓。
        记录净值只在每日9点13之前和每日3点之后各计算一次净值，
        银证转账请在9点--9点10之间完成，否则计算净值会存在失误。
        持仓只在3点后计算。
        :return:
        """
        ant_path = self.recoder_path + 'account.csv'
        pos_path = self.recoder_path + 'position.csv'
        now_time = datetime.datetime.now()
        today = now_time.strftime('%Y-%m-%d')
        time_con1 = now_time < datetime.datetime.strptime((today + ' ' + '9:13'), "%Y-%m-%d %H:%M")
        time_con2 = now_time > datetime.datetime.strptime((today + ' ' + '15:00'), "%Y-%m-%d %H:%M")
        ant_df = pd.DataFrame()
        if time_con1 or time_con2:
            self.get_account()
            # 如果是第一次记录资金曲线，初始化一个表格。
            if not os.path.exists(ant_path):
                ant_df = self._ini_account_file(now_time)
            else:
                ant_df = pd.read_csv(ant_path, encoding='gbk')
                inx = ant_df.index.max() + 1
                ant_df.loc[inx, '记录时间'] = now_time.strftime("%Y-%m-%d %H:%M")
                ant_df.loc[inx, '总资产'] = self.account['总资产']
                if time_con1:  # 早上记录净值时
                    # 发生资金划转，改变份额，不改变净值
                    if ant_df.loc[inx - 1, '总资产'] != self.account['总资产']:
                        transfer = self.account['总资产'] - ant_df.loc[inx - 1, '总资产']
                        transfer = round(transfer, 2)
                        ant_df.loc[inx, '资金划转'] = transfer
                        ant_df.loc[inx, '份额'] = round(
                            ant_df.loc[inx - 1, '份额'] + transfer / ant_df.loc[inx - 1, '净值'],
                            4)
                        ant_df.loc[inx, '净值'] = ant_df.loc[inx - 1, '净值']
                    else:  # 未发生资金划转，改变净值不改变份额
                        ant_df.loc[inx, '资金划转'] = 0.0
                        ant_df.loc[inx, '份额'] = round(ant_df.loc[inx - 1, '份额'], 4)
                        ant_df.loc[inx, '净值'] = round(ant_df.loc[inx - 1, '净值'], 7)
                if time_con2:
                    ant_df.loc[inx, '资金划转'] = round(self.account['总资产'] - ant_df.loc[inx - 1, '总资产'], 2)
                    ant_df.loc[inx, '份额'] = round(ant_df.loc[inx - 1, '份额'], 4)
                    ant_df.loc[inx, '净值'] = round(self.account['总资产'] / ant_df.loc[inx - 1, '份额'], 7)
                    self.get_position()
                    pos_df = self.position.copy()
                    pos_df['记录时间'] = today
                    if os.path.exists(pos_path):
                        pos_df.to_csv(pos_path, encoding='gbk', index=False, header=False, mode='a')
                    else:
                        pos_df.to_csv(pos_path, encoding='gbk', index=False)
            if not ant_df.empty:
                ant_df.to_csv(ant_path, encoding='gbk', index=False)
        return ant_df

    def save_entrusts_backup_pos(self):
        entrusts_path = self.recoder_path.replace('账户信息', '历史信息') + '订单信息/'
        if not os.path.exists(entrusts_path):
            os.mkdir(entrusts_path)
        entrusts_path += datetime.datetime.now().strftime('%Y-%m-%d') + '_订单.csv'
        self.refresh_entrusts()
        self.entrusts = self.entrusts[self.entrusts['委托编号'] != 888888]  # 有一个人为定义的888888订单需要去掉
        self.entrusts.to_csv(entrusts_path, encoding='gbk', index=False)
        self.compare_hold_and_position()
        pos_path = self.recoder_path.replace('账户信息', '历史信息') + '持仓信息/'
        if not os.path.exists(pos_path):
            os.mkdir(pos_path)
        pos_path += datetime.datetime.now().strftime('%Y-%m-%d') + '_持仓.csv'
        shutil.copy2(self.recoder_path + '当前持仓.csv', pos_path)

    @staticmethod
    def df2txt(msg_df, float_cols=[]):
        """
        将DF格式的数据转为txt格式
        :param msg_df:
        :param float_cols:
        :return:
        """
        try:
            df = msg_df.copy()
            msg = ''
            for inx in df.index:
                for col in df.columns:
                    if col in float_cols:
                        msg += f'{col}:{round(df.loc[inx, col], 3)}\n'
                    else:
                        msg += f'{col}:{df.loc[inx, col]}\n'
                msg += '\n'
            msg = msg.strip()
            return msg
        except Exception as err:
            return 'df2txt发生错误' + str(err)

    def intraday_swap_process(self, id_swap_dict, source_buy_df=pd.DataFrame(columns=['策略名称', '证券代码', '下单金额', '订单标记']),
                              startup_time=1):
        # 第一步：记录一下json里是不是有策略需要做日内调仓合并对冲的，没有就不去玩后面这堆流程了，直接下去做买入的行为了。
        if startup_time == 1:
            source_buy_df = self.buy.copy()
        if any(id_swap_dict.values()) and (not source_buy_df.empty):
            # json里存在需要买卖对冲合并的策略才去判断buy和sell里有没有需要合并的
            sell_df = self.sell.copy()

            # 如果买入计划为空，则直接结束
            if sell_df.empty:
                return source_buy_df
            buy_df = source_buy_df.copy()

            # 买入只保留有实际下单金额，并且是需要日内调仓的个股
            buy_df = buy_df[buy_df['下单金额'] > 0]
            buy_df = buy_df[buy_df['策略名称'].apply(lambda x: id_swap_dict[x] > 0)]
            buy_df['标签'] = buy_df['策略名称'] + '+' + buy_df['证券代码']

            # 只保留需要日内调仓的个股
            sell_df = sell_df[sell_df['策略名称'].apply(lambda x: id_swap_dict[x] > 0)]
            sell_df['标签'] = sell_df['策略名称'] + '+' + sell_df['证券代码']

            # 寻找两边可以合并的部分
            need_swap = list(set(buy_df['标签'].unique().tolist()).intersection(set(sell_df['标签'].unique().tolist())))
            need_swap = sorted(need_swap)
            # 只保留需要合并的部分
            buy_df = buy_df[buy_df['标签'].isin(need_swap)]
            sell_df = sell_df[sell_df['标签'].isin(need_swap)]

            # 遍历每一组交易，计算到底需要怎么计算
            for tag in need_swap:
                stg = tag.split('+')[0]
                code = tag.split('+')[1]
                # 获取一下最新价格
                price = self.get_now_price(code)
                # 拿到这组策略需要交易的信息
                temp_buy = buy_df[buy_df['标签'] == tag].copy()
                temp_sell = sell_df[sell_df['标签'] == tag].copy()
                # 计算卖出部分对应的市值
                temp_sell['持仓市值'] = temp_sell['持仓量'] * price
                for s_inx in temp_sell.index:
                    self.rb.record_log(f'处理卖出对冲交易：\n {str(temp_sell[temp_sell.index == s_inx])}')
                    # 如果卖出单正在挂单，需要先撤销
                    sell_order_id = temp_sell.loc[s_inx, '委托编号']
                    if (not pd.isnull(sell_order_id)) and (str(sell_order_id) not in ['', 'nan']):
                        state = self.cancel_order(sell_order_id)[1]
                        if state == ' 已成':  # 已经成交的单子直接跳过
                            continue
                        if state == '部成':
                            sell_order_remark = temp_sell.loc[s_inx, '订单标记']
                            s_con = self.stg_infos[temp_sell.loc[s_inx, '策略名称']]
                            self.syn_hod(sell_order_remark, sell_order_id, s_con)
                            temp_sell.loc[s_inx, '持仓量'] = self.sell.loc[s_inx, '持仓量']
                            temp_sell.loc[s_inx, '持仓市值'] = self.sell.loc[s_inx, '持仓量'] * price
                        self.sell.loc[s_inx, '委托编号'] = ''  # 撤单之后需要初始化订单
                        self.save_sell()

                    for b_inx in temp_buy.index:
                        self.rb.record_log(f'处理买入对冲交易：\n {str(temp_buy[temp_buy.index == b_inx])}')
                        buy_amt = temp_buy['下单金额'].at[b_inx]
                        sell_amt = temp_sell['持仓市值'].at[s_inx]

                        # 如果已经买完了那直接跳过
                        if (buy_amt == 0) or (sell_amt == 0):
                            continue

                        # 如果买单>=卖单，卖单将全部被消化
                        if buy_amt >= sell_amt:
                            # 获取当前订单的信息
                            volume = temp_sell.loc[s_inx, '持仓量']

                            # 清空临时文件的持仓信息
                            temp_sell.loc[s_inx, '持仓量'] = 0
                            temp_sell.loc[s_inx, '持仓市值'] = 0
                            # 清空底层文件的持仓信息
                            self.sell.loc[s_inx, '持仓量'] = 0
                            self.sell.loc[s_inx, '委托编号'] = '888888'

                            # 需要再当前持仓的文件里面
                            sell_remark = temp_sell.loc[s_inx, '订单标记']
                            self.hold = self.hold[self.hold['订单标记'] != sell_remark]

                            # 买的下单金额要降低
                            temp_buy.loc[b_inx, '下单金额'] -= sell_amt
                            buy_df.loc[b_inx, '下单金额'] -= sell_amt
                            source_buy_df.loc[b_inx, '下单金额'] -= sell_amt
                            self.buy.loc[b_inx, '下单金额'] -= sell_amt
                            buy_remark = temp_buy.loc[b_inx, '订单标记']

                            # 同步买入订单
                            self.syn_hod_buy_swap(buy_remark, volume, price, '888888', id_swap_dict[stg])

                        # 如果买单<卖单，买单将全部被消化
                        else:
                            # 获取当前下单金额对应的volume
                            buy_volume = int(temp_buy.loc[b_inx, '下单金额'] / price)
                            hold_volume = temp_sell.loc[s_inx, '持仓量']
                            code2 = self.trans_code(code)
                            is_star = 'sh68' in code2
                            is_bond = code[:2] in ['11', '12', '18']
                            is_bj = 'bj' in code2

                            # 计算买入可以下单的实际下单量
                            if is_bond:  # 处理北交所
                                buy_volume = buy_volume - buy_volume % 10
                            elif is_star:  # 处理科创板
                                buy_volume = buy_volume if buy_volume >= 200 else 0
                            elif is_bj:
                                buy_volume = buy_volume if buy_volume >= 100 else 0
                            else:  # 处理正常的股票
                                buy_volume = buy_volume - buy_volume % 100

                            # 计算买入之后剩余量
                            surplus = hold_volume - buy_volume

                            # 判断剩余量是否满足卖出的条件，如果不满足，需要对下单金额做处理
                            if is_bond:  # 债券
                                # 如果余量不足不能被10整除，那么把零头划过去
                                if surplus % 10 != 0:
                                    buy_volume += surplus % 10
                            elif is_star:  # 科创板
                                # 如果余量不够200，直接并过去
                                if surplus < 200:
                                    buy_volume += surplus
                            elif is_bj:
                                # 如果余量不够100，直接并过去
                                if surplus < 100:
                                    buy_volume += surplus
                            else:  # 正常股票
                                # 如果余量不足不能被100整除，那么把零头划过去
                                if surplus % 100 != 0:
                                    buy_volume += surplus % 100
                            # 重新计算余量
                            surplus = hold_volume - buy_volume

                            # 减少临时文件中的数据
                            temp_sell.loc[s_inx, '持仓量'] = surplus
                            temp_sell.loc[s_inx, '持仓市值'] = surplus * price
                            # 减少底层文件的持仓
                            self.sell.loc[s_inx, '持仓量'] = surplus

                            # 修改持仓文件
                            sell_remark = temp_sell.loc[s_inx, '订单标记']
                            hold_inx = self.hold[self.hold['订单标记'] == sell_remark].index.min()
                            self.hold.loc[hold_inx, '持仓量'] = surplus

                            # 此笔买单已完成
                            temp_buy.loc[b_inx, '下单金额'] = 0
                            buy_df.loc[b_inx, '下单金额'] = 0
                            source_buy_df.loc[b_inx, '下单金额'] = 0
                            self.buy.loc[b_inx, '下单金额'] = 0
                            buy_remark = temp_buy.loc[b_inx, '订单标记']
                            # 同步买入订单
                            self.syn_hod_buy_swap(buy_remark, buy_volume, price, '888888', id_swap_dict[stg])

                        # 保存信息  这些到时候需要取消注释
                        self.save_buy()
                        self.save_sell()
                        self.save_hold()
        return source_buy_df

    def check_hold_plan(self, po_path):
        # 读取period_offset.csv
        po_df = pd.read_csv(po_path, encoding='gbk', parse_dates=['交易日期'], skiprows=1)

        # period_offset 所有的列
        plan_cols = list(po_df.columns)

        # period_offset 今天需要开仓的列
        today_inx = po_df[po_df['交易日期'] == self.trader_calendar.today].index.min()
        open_cols = []
        for col in plan_cols:
            if po_df[col].iloc[today_inx] != po_df[col].iloc[today_inx - 1]:
                open_cols.append(col)

        for stg in self.stg_infos.keys():
            self.stg_infos[stg]['open_offset'] = []
            for plan in self.stg_infos[stg]['hold_plan']:
                if plan not in plan_cols:
                    self.rb.record_log(f'{stg} 的持仓计划 {plan} 不合规，该列不在period_offset.csv的列中，请检查。')
                    raise Exception(f'{stg} 的持仓计划 {plan} 不合规，该列不在period_offset.csv的列中，请检查。')

                # 针对当天需要开仓的策略，保留一下
                if plan in open_cols:
                    self.stg_infos[stg]['open_offset'].append(plan)

    def set_port(self, exe_path):
        port_path = os.path.join(os.path.dirname(exe_path), 'config/xtminiquote.lua')
        if os.path.exists(port_path):
            with open(port_path, 'r', encoding='gbk') as f:
                lua_content = f.read()

            # 找到端口所在
            port = int(lua_content.split('address = "0.0.0.0:')[1].split('"')[0])
            if port != self.port:
                lua_content = lua_content.replace(f'address = "0.0.0.0:{port}', f'address = "0.0.0.0:{self.port}')
                # 保存数据
                with open(port_path, 'w', encoding='gbk') as f:
                    f.write(lua_content)
                # 有的版本可能没有reconnect函数，需要兼容一下
                try:
                    xtdata.reconnect(port=self.port)
                except:
                    self.rb.record_log('当前xtquant版本可能较旧，请及时更新。\n'
                                       '更新方法参考这个帖子的前言部分：https://bbs.quantclass.cn/thread/37779\n'
                                       '这只是一个提示，不要慌，不更新也没啥\n\n'
                                       '端口发生了变化，请重启迅投软件，代码已退出')
                    os._exit(0)

    # endregion
