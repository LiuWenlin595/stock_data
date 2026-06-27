import pandas as pd

import program.config as cfg
from program.exchange.exchange_api import *
from program.utils.functions import *
from program.utils.task_control import *
from program.utils.user_task import *
import time
import traceback
import warnings
import program.RainbowV1 as Rb

Rb.robot_api = cfg.robot_api
Rb.proxies = cfg.proxies
Rb.same_msg_interval = cfg.same_msg_interval

warnings.filterwarnings('ignore')
pd.set_option('expand_frame_repr', False)  # 当列太多时不换行
pd.set_option('display.max_rows', 5000)  # 最多显示数据的行数

if __name__ == '__main__':
    # 初始化一些变量
    tc = TradeCalendar(Rb, 60)  # 交易日期
    pre_other_task_list = []  # 其他任务（在buy和sell等之前先去加载已报的订单）
    buy_task_list = []  # 买入任务列表
    sell_task_list = []  # 卖出任务列表
    risk_task_list = []  # 风控列表
    other_task_list = []  # 其他任务列表
    task_list = []
    ex_api = None  # 交易接口
    # 构建交易日才执行的任务
    if tc.market_open:
        try:
            # 初始化交易对象
            ex_api = ExchangeAPI(user=cfg.account, exe_path=cfg.order_exe_path, stg_infos=cfg.stg_infos, port=cfg.port,
                                 rb=Rb)
            # 校验持仓信息
            ex_api.compare_hold_and_position()
            # 检查持仓计划是否正确
            ex_api.check_hold_plan(cfg.period_offset_path)
            # 读取订单数据
            if ex_api.create_order(ex_api.trader_calendar.today):
                # 根据下单信息、持仓记录、策略配置，计算开仓金额
                ex_api = cal_allocation_of_cap(ex_api)
                # 日内调仓买卖对冲调整
                ex_api.intraday_swap_process(cfg.intraday_swap_dict)
        except Exception as err:
            Rb.record_log(f'初始化失败，程序退出,请手动干预\n{err}\n{traceback.format_exc()}', send=True)
            exit()
        Rb.record_log('=====买入计划=====\n' + ex_api.df2txt(ex_api.buy[['策略名称', '证券代码', '下单金额', '其他']],
                                                         float_cols=['下单金额']), True)
        Rb.record_log('=====卖出计划=====\n' + ex_api.df2txt(ex_api.sell[['策略名称', '证券代码', '持仓量', '其他']]
                                                         , float_cols=['持仓量']), True)
        # 检查是否存在下单金额不足的情况。
        order_check(ex_api)
        console_check('请检查买入&卖出计划，以及持仓文件,确认无误后输入y继续执行下一步。')
        # ====交易任务，生成任务列表
        ex_api, buy_task_list = create_buy_tasks(ex_api)  # 买入任务列表
        ex_api, sell_task_list = create_sell_tasks(ex_api)  # 卖出任务列表
        ex_api, risk_task_list = create_risk_tasks(ex_api)  # 风控任务列表
        # 盘中刷新委托信息
        refresh_entrusts_task = TaskControl(task='ex_api.refresh_entrusts', start='9:00', end='20:01', api_task=True,
                                            ex_api=ex_api, rest=['11:31', '12:59'])
        pre_other_task_list.append(refresh_entrusts_task)
        # 每隔5分钟读取一次交易计划，将新增的买入任务添加到列表中。
        load_trade_plan_task = TaskControl(task='program.utils.user_task.load_trade_plan', start='9:30', end='15:00',
                                           interval=1, ex_api=ex_api)
        other_task_list.append(load_trade_plan_task)
        # 盘尾用剩余的资金购买逆回购
        reverse_repo = TaskControl(task='program.utils.user_task.reverse_repo', start='15:05', end='15:30', interval=30,
                                   ex_api=ex_api, keep=1000)
        other_task_list.append(reverse_repo)
        # 盘中更新北向数据（选择性开启）
        # north_fund_task = TaskControl(task='program.utils.user_task.get_north_fund', start='9:01', end='15:05',
        #                               interval=5, control_info=True, recoder_last_res=True)
        # other_task_list.append(north_fund_task)
        # 推送成交信息
        buy_info_task = TaskControl(task='program.utils.user_task.send_buy_info', start='9:30', end='15:00',
                                    interval=3, ex_api=ex_api, strategy_filter=['kepler'])
        other_task_list.append(buy_info_task)

        # 早晚各记录一次账户信息，为分析做准备（选择性开启，不开启无法使用实盘查看器或功能受限）
        recoder_task_morning = TaskControl(task='ex_api.recoder', start='9:10', api_task=True, ex_api=ex_api)
        recoder_task_afternoon = TaskControl(task='ex_api.recoder', start='15:10', api_task=True, ex_api=ex_api)
        other_task_list.append(recoder_task_morning)
        other_task_list.append(recoder_task_afternoon)
        # 盘后记录一下当日所有订单，备份一下当前持仓。为分析做准备（选择性开启，不开启无法使用实盘查看器或功能受限）
        save_ent_pos_task = TaskControl(task='ex_api.save_entrusts_backup_pos', start='15:10',
                                        api_task=True, ex_api=ex_api)
        other_task_list.append(save_ent_pos_task)

    else:
        print('友情提示：今天不是交易日，程序不会下单，有可能不执行任何任务。')

    # 构建非交易日也要运行的事件
    # 推送市场热点新闻（选择性开启）
    # news_task = TaskControl(task='program.utils.user_task.get_news', start='9:01', end='21:05', interval=5,
    #                         control_info=True)
    # other_task_list.append(news_task)

    # 主程序终止时间
    end_time = datetime.datetime.strptime((datetime.datetime.now().strftime('%Y-%m-%d') + ' 15:30'), "%Y-%m-%d %H:%M")
    task_list = pre_other_task_list + buy_task_list + sell_task_list + risk_task_list + other_task_list
    recoder_time = datetime.datetime.now()
    while True:
        for task in task_list:
            res = task.run()
            if res[0] == 0:
                Rb.match_solution(str(task.task) + '运行失败' + '\n' + res[1], send=True)
            elif res[0] == 1:
                if isinstance(res[1], ExchangeAPI):
                    ex_api = res[1]
                # 添加新的任务到任务列表里面
                if isinstance(res[1], tuple):
                    if isinstance(res[1][0], ExchangeAPI):
                        ex_api = res[1][0]
                    if len(res[1]) >= 3:
                        if res[1][2] == 'Task':
                            task_list += res[1][1]
                # 运行成功的消息每30秒记录一次，避免记录太多内容
                if datetime.datetime.now() > recoder_time:
                    Rb.record_log(str(task.task) + '运行成功')
                    recoder_time += pd.to_timedelta('30s')
            if task.is_finish:
                task_list.remove(task)
        time.sleep(1)
        # 判断是否达到计划的停止时间
        if datetime.datetime.now() > end_time:
            if tc.market_open:
                ex_api.compare_hold_and_position()
            os._exit(0)
