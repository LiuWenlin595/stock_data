import pandas as pd


def equal_weight(data, s_config, **kwargs):
    """
    等权计算持仓分配，plan参数为外部传入参数，
    假设，策略今日计划开仓50000元，计划持有3只股票，实际只有2只股票
    True：严格执行计划，每只股票下单金额 = 50000/3
    False：不严格按照计划执行，每只股票下单金额 = 50000/2
    :param data:
    :param s_config:
    :param kwargs:
    :return:
    """
    plan = False
    # 如果选股数量是0，表示是任意选股数量，不能严格模式
    if s_config['select_count'] == 0:
        plan = False
    if len(s_config['stock_weight']) > 1:
        plan = s_config['stock_weight'][1]
    if plan:
        data['股票权重'] = 1 / s_config['select_count']
    else:
        data['选股数量'] = data.groupby('交易日期')['证券代码'].transform('count')
        data['股票权重'] = 1 / data['选股数量']
        del data['选股数量']
    return data
