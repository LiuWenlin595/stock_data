from tools.functions_analyze import *
from program.config import root_path
import warnings

warnings.filterwarnings('ignore')
pd.set_option('expand_frame_repr', False)  # 当列太多时不换行
pd.set_option('display.max_rows', 5000)  # 最多显示数据的行数
# print输出中文表头对齐
pd.set_option('display.unicode.ambiguous_as_wide', True)
pd.set_option('display.unicode.east_asian_width', True)

if __name__ == '__main__':
    # ===以下是按需修改的配置
    start_date = '2023-08-01'  # 分析的开始时间
    end_date = '2023-09-28'  # 分析的结束时间
    ent_path = root_path + '/data/历史信息/订单信息/'  # 历史订单的路径，一般是不需要配置的
    stock_data_path = 'D:/data/stock_data/stock-trading-data-pro/'  # 股票全息日线数据
    bond_data_path = 'D:/data/stock_data/stock-basic-bond/'  # 可转债日线数据
    index_path = 'D:/data/stock_data/index/sh000001.csv'  # 指数数据
    is_have_not_stg = False  # 滑点分析是否包含非策略选股，一般是不需要配置的
    # ===以上是按需修改的配置

    fig_list = []
    # ==== 滑点分析
    # 判断一下有没有要载入的数据，创建一下分析目录
    save_path, ent_file_list = check_analyze_path(ent_path, start=start_date, end=end_date)

    # 载入所有订单数据，拼一下开盘收盘价，算一下每个成交的滑点
    print(f'载入每日交易文件，合计{len(ent_file_list)}天，载入中...')
    trade_df_list = []
    for each_file in ent_file_list:
        # 载入后先groupby，因为可能存在拆单的标的
        trade_daily_df = load_ent_file(ent_path, each_file)
        trade_df_list.append(trade_daily_df)
    trade_df = pd.concat(trade_df_list, ignore_index=True)
    trade_df.sort_values(by=['交易日期', '买卖', '订单标记', '首次下单时间', '成交额'], ascending=[True, True, True, True, False],
                         inplace=True)
    trade_df = trade_df[['交易日期', '策略名称', '证券代码', '订单标记', '首次下单时间', '买卖', '下单计数', '有成交计数', '成交额',
                         '成交量', '下单额', '下单量', '成交均价', '下单均价']]
    print(f'正在加载每日开收盘价...')
    days_price_df = get_days_price(trade_df['证券代码'].unique().tolist(), stock_data_path, bond_data_path,
                                   trade_df['交易日期'].min(), trade_df['交易日期'].max())
    if days_price_df.empty:
        print('载入本地数据存在异常，检查后重新运行')
        exit()

    print('滑点计算中...')
    trade_df = pd.merge(left=trade_df, right=days_price_df, on=['证券代码', '交易日期'], how='left')
    trade_df.loc[trade_df['买卖'] == '买入', '滑点'] = trade_df['成交均价'] / trade_df['开盘价'] - 1
    trade_df.loc[trade_df['买卖'] == '卖出', '滑点'] = 1 - trade_df['成交均价'] / trade_df['收盘价']
    # 如果有标的拿不到开收盘价，则直接定义滑点为0，补全一下开收和名称
    trade_df['滑点'].fillna(value=0, inplace=True)
    trade_df['开盘价'].fillna(trade_df['成交均价'], inplace=True)
    trade_df['收盘价'].fillna(trade_df['成交均价'], inplace=True)
    trade_df['股票名称'].fillna(value='未载入数据', inplace=True)
    # 用更少钱买就是正收益
    trade_df.loc[trade_df['买卖'] == '买入', '滑点收益'] = trade_df['开盘价'] * trade_df['成交量'] - trade_df['成交额']
    # 卖到更多的钱就是正收益
    trade_df.loc[trade_df['买卖'] == '卖出', '滑点收益'] = trade_df['成交额'] - trade_df['收盘价'] * trade_df['成交量']
    # 至此所有交易处理完毕，存一下，自己看excel也方便。
    trade_df.to_csv(save_path + '0_交易详情整理.csv', encoding='gbk', index=False)

    if not is_have_not_stg:
        # 不包含非策略选股
        trade_df = trade_df[trade_df['策略名称'] != '非策略选股']

    # 获取一下交易日,算日均和画图都要用
    index_trade_df = pd.read_csv(index_path, encoding='gbk', parse_dates=['candle_end_time'])
    index_trade_df = index_trade_df[(index_trade_df['candle_end_time'] >= trade_df['交易日期'].min()) & (
            index_trade_df['candle_end_time'] <= trade_df['交易日期'].max())]

    # 按日分策略、按日不分策略、按策略算滑点
    daily_strategy_df, daily_df, strategy_df = calc_mean_slip(trade_df, index_trade_df)

    # 滑点分析的作图
    fig_list += daily_slip_pic(daily_df)
    fig_list += daily_slip_pic(daily_strategy_df)

    # 滑点分析结果文件存储
    format_col(strategy_df).to_csv(save_path + '1_滑点分析(按策略).csv', encoding='gbk', index=False)
    print(strategy_df.to_string(index=False))
    format_col(daily_df).to_csv(save_path + '2_滑点分析(按日期).csv', encoding='gbk', index=False)
    format_col(daily_strategy_df).to_csv(save_path + '3_滑点分析(按日期分策略).csv', encoding='gbk', index=False)

    # ==== 盈利分析（仅通过订单）
    print(f'盈利分析中...')
    match_stock_df, match_strategy_df, unmatch_trade_df, info_text = basic_earnings_analysis(trade_df)
    print(info_text)
    # 盈利分析作图
    fig_list += strategy_profit_pic(match_strategy_df, info_text)

    # 盈利分析保存
    format_col(match_stock_df).to_csv(save_path + '4_配对交易盈亏情况(按标的).csv', encoding='gbk', index=False)
    format_col(match_strategy_df).to_csv(save_path + '5_配对交易盈亏情况(按策略).csv', encoding='gbk', index=False)
    print(match_strategy_df.to_string(index=False))
    unmatch_trade_df.to_csv(save_path + '6_未配对交易.csv', encoding='gbk', index=False)

    merge_html(save_path, fig_list, start_date, end_date)
