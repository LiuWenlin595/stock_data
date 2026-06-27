"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import os
import program.Config as Cfg

# 感谢瓜大仙老板的启发：https://bbs.quantclass.cn/thread/36224
# 感谢请叫我小锅和白驹过隙老板提供的思路：https://bbs.quantclass.cn/thread/40148
# 感谢白驹过隙老板提供的思路：https://bbs.quantclass.cn/thread/40067
# 感谢时间的复利老板提供了指数K线图的思路：https://bbs.quantclass.cn/thread/40151

# 需要修改的参数
shift_bt_file_name = '大小市值轮动策略_W_0_30_1.csv'  # 策略回测的文件名
factor_cols = ['bias_20', '价格分位数_250']  # 要看的因子，需要先跑1_策略数据整理.py算出策略的因子

show_stock_return = True  # 是否显示当期选中轮动策略中的个股或币的前3/后3的收益率信息,如果选股数量不足6个，会自适应减少，但至少要选2只股票，否则不显示
extra_sft_file_list = []  # 需要与基准轮动策略进行对比的策略曲线列表，可为空

# ==========以下内容几乎不需要改动==========
period_count = 25  # 需要展示的周期数
window_width = 1300  # 界面窗口大小

# 获取回测结果文件夹
sft_bt_folder = os.path.join(Cfg.root_path, 'data/回测结果/轮动策略')
# 获取轮动策略的回测结果路径
sft_bt_path = os.path.join(sft_bt_folder, shift_bt_file_name)
# 获取额外的轮动资金曲线路径
if len(extra_sft_file_list) >= 1:
    extra_sft_path_list = [os.path.join(sft_bt_folder, i) for i in extra_sft_file_list]
else:
    extra_sft_path_list = []
# 获取选股策略的回测结果路径
slt_bt_path = os.path.join(Cfg.select_program_path, 'data/回测结果/选股策略')
split_list = shift_bt_file_name.split('_')
per_oft_cnt = str(split_list[-4]) + '_' + str(split_list[-3]) + '_' + str(split_list[-2])  # period_offset信息
shift_ftr_path = os.path.join(Cfg.root_path,
                              f'data/数据整理/all_strategy_data_{per_oft_cnt}.pkl')  # 轮动策略整理的数据文件，运行1_策略数据整理.py可以得到
index_path = Cfg.index_path  # 指数路径
stock_data_path = os.path.join(Cfg.factor_path, '日频数据/基础数据')
# 多线程的CPU参与计算的数量
n_jobs = min(60, os.cpu_count() - 1)  # 多线程的最大数量，未修改的joblib在windows环境下只支持最高63
# 如果模拟器要展示的因子数量大于5，会报错，需要减少因子数量
if len(factor_cols) > 5:
    print('因子数量太多了，减少一点因子数量')
    exit()
