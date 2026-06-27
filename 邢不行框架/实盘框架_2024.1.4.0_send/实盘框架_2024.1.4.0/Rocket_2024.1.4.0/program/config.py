import os

# 根目录的地址
_ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
root_path = os.path.abspath(os.path.join(_, ''))

# ===== 常用的配置：需要酌情修改 =====
# QMT的安装位置中极简版的目录
order_exe_path = 'D:\\xx证券QMT交易端\\userdata_mini'

# 券商账户号，不清楚的话可以问一下券商的客户经理哦
account = ''

# 默认的配置是58610端口，如果一台电脑只跑一个QMT，保持默认就好，这是最优的。
# 如果你想在一台电脑上使用多个券商的QMT，就需要配置port
# 例如券商A 端口58610，券商B端口58611，券商C端口58612
#   千万不要重复！！！千万不要重复！！！千万不要重复！！！
port = 58610

# 企业微信机器人配置，支持配置3个机器人，让它们负责推送不同类别的消息（也可以三个配置都指向同一个机器人）
# 相关配置教程：https://bbs.quantclass.cn/thread/10975
robot_api = {'info': '',
             'warning': '',
             'news': ''}

# 周期和offset预运算数据位置，全量数据下载链接：https://www.quantclass.cn/data/stock/stock-period-offset
period_offset_path = 'D:/Data/stock_data/period_offset.csv'

# 策略配置信息，此部分配置运行《生成交易计划》项目中的【2_生成交易计划.py】会自动生成推荐的配置，针对配置酌情修改即可。
# 每个参数的详细说明可以查看本项目中的《Rocket食用指南.pdf》
stg_infos = {}

# ===== 不常用的配置：非必要不修改，保持默认即可 =====
# 针对单一股票的委托次数限制，默认50次，如果有需要可以调高次数
# 监管新规下，如果频繁买卖可能会被交易所警告
# 注意：程序重启之后，order_limit会重新从0开始计数
order_limit = 50

# 代理信息，一般只有你开了代理才需要用
proxies = {}
# 相同提醒消息发送冷却时间，单位秒
same_msg_interval = 5
# 总仓位控制
position_control = 1

# ===== 以下内容无需修改，也无需配置 =====
# 日内调仓买卖对冲标志读取,0表示不进行日内调仓的买卖对冲；1表示买入日早盘；2表示卖出日尾盘。
intraday_swap_dict = {}
for s in stg_infos:
    if 'intraday_swap' in stg_infos[s].keys():
        intraday_swap_dict[s] = stg_infos[s]['intraday_swap']
    else:
        intraday_swap_dict[s] = 0

# 仓位控制，避免设置错误导致整体的仓位超过100%
pos_sum = 0
for key in stg_infos.keys():
    pos_sum += stg_infos[key]['strategy_weight']
    stg_infos[key]['strategy_weight'] *= position_control
if round(pos_sum, 8) > 1:
    print('整体仓位设置超过1，将对比例进行归一化处理')  # 仓位不为1时，会有问题
    for key in stg_infos.keys():
        stg_infos[key]['strategy_weight'] = stg_infos[key]['strategy_weight'] / pos_sum
