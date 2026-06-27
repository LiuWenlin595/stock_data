import pandas as pd
from program.Config import root_path
import program.Evaluate as Eva
import os
from plotly.io import to_html
import time
import plotly.express as px

'''
功能：
1. 支持单因子参数平原
2. 支持双因子参数热力图
3. 存在2个以上的因子参数遍历时，可以通过con来控制不画图的因子的参数

运行步骤:
对于某个策略，假设你有3个因子需要测试:bias_x,RSI_y,std_z,其中x,y,z分别代表3个因子的参数
第一步：运行3_轮动策略遍历回测.py，指定好x,y,z需要遍历的参数。
第二步：设置好stg_name,period_offset。
第三步：factor_name_dict给出需要画图的参数，字典的key是名字（可以自定义），value是对应的参数位置。
注意：当你有3个参数在遍历，但是只想展示2个参数的热力图时，只需要在factor_name_dict中给出两个因子的参数位置，第三个参数通过con来控制。
第四步：运行该脚本

详细的教程可以看这篇帖子：https://bbs.quantclass.cn/thread/41459
'''

# 需要修改的参数
stg_name = '案例多参数轮动策略'  # 想看的策略名
period_offset = "W_0"  # 想看的周期和offset
factor_name_dict = {'bias': 0}  # 格式： {参数遍历的因子名:参数位置}
con = {}  # 格式： {不画图的因子位置：指定的参数值}   如果为空，value的指定的参数值默认选择最小参数


# ==========以下内容不需要改动==========

def prepare_data(stg_name, period_offset, stats_index, factor_name_dict):
    save_path = os.path.join(root_path, 'data/回测结果/遍历结果.csv')
    df = pd.read_csv(save_path, encoding='gbk')
    if len(df[(df['策略名称'] == stg_name)]) == 0:
        print('传入的策略名称不存在，请检查，程序已退出')
        exit()
    elif len(df[(df['周期&offset'] == period_offset)]) == 0:
        print('传入的周期不存在，请检查，程序已退出')
        exit()
    df = df[(df['策略名称'] == stg_name) & (df['周期&offset'] == period_offset)]

    # 检查同一策略，同一周期，同一参数是否存在多个回测数据
    stg_param_count = df.groupby('策略参数')['策略参数'].count()
    if max(stg_param_count) > 1:
        multi_param = stg_param_count[stg_param_count > 1].index.values
        # 对于重复的参数，只保留最新一条的参数所在行
        df1 = df[~df['策略参数'].isin(multi_param)]
        df2 = df[df['策略参数'].isin(multi_param)]
        df2 = df2.drop_duplicates(subset='策略参数', keep='last')
        df = pd.concat([df1, df2], axis=0)

    # 新增一个判断，解决2024.1.7.3和2024.1.7.4版本的遗留问题
    if ',' in str(df['策略参数'].iloc[0]):
        print(
            '2024.1.7.5版本后不再支持传入的多参数用逗号（,）分隔，请按照4_轮动策略遍历回测.py中的示例传入列表格式的参数。\n如果策略文件中使用逗号拆分多参数，策略文件也要做相应的修改，请修改后再重新运行，程序先退出')
        exit()

    # 检查传入的策略参数用加号分隔的数量是否一致
    df['策略参数'] = df['策略参数'].apply(str)
    df = df[df['策略参数'].apply(lambda x: True if '+' in x else False)]
    if df['策略参数'].apply(lambda x: len(str(x).split('+'))).nunique() != 1:
        print('传入的策略参数用加号（+）分隔的数量不一致，请检查，程序已退出')
        exit()

    # 获取每年收益
    df['开始年份'] = df['年份区间'].apply(lambda x: x.split('_')[0]).astype(int)
    df['结束年份'] = df['年份区间'].apply(lambda x: x.split('_')[1]).astype(int)
    df['历年收益'] = df['历年收益'].apply(lambda x: x.split('+'))
    df['temp_year'] = df['开始年份']

    del_pct_list = ['年化收益', '最大回撤']
    for i in del_pct_list:
        df[i] = df[i].apply(lambda x: x[:-1]).astype(float)

    cal_year = int(df['开始年份'].min())
    # ==检查历年收益字段中列表的长度是否一致
    # 计算每个策略开始年份与cal_year的差
    df['开始年份差'] = df['开始年份'].apply(lambda x: int(x) - cal_year if int(x) > cal_year else 0)
    df['开始年份差_填充值'] = df['开始年份差'].apply(lambda x: ['0%'] * x)
    df['历年收益'] = df['开始年份差_填充值'] + df['历年收益']
    # 计算每个策略结束年份与end_year的差
    end_year = int(df['结束年份'].max())
    df['结束年份差'] = df['结束年份'].apply(lambda x: end_year - int(x) if end_year > int(x) else 0)
    df['结束年份差_填充值'] = df['结束年份差'].apply(lambda x: ['0%'] * x)
    df['历年收益'] = df['历年收益'] + df['结束年份差_填充值']

    # 从df中删除开始年份差、开始年份差_填充值列
    del df['开始年份差'], df['开始年份差_填充值'], df['结束年份差'], df['结束年份差_填充值']

    for i in range(int(df['结束年份'].max()) - int(df['开始年份'].min()) + 1):
        df[f'{cal_year}年收益'] = df['历年收益'].apply(lambda x: x[i][:-1]).astype(float)
        cal_year += 1

    # 历年收益
    if '历年收益' in stats_index:
        stats_index.remove('历年收益')
        stats_index += [f'{i}年收益' for i in range(int(df['开始年份'].min()), int(df['结束年份'].max() + 1))]

    # 拆分参数
    try:
        for key, value in factor_name_dict.items():
            try:
                df[key] = df['策略参数'].apply(lambda x: str(x).split('+')[value]).astype(float)
            except:
                print('传入的参数似乎有不符合浮点数的格式，确定没问题可忽略')
                df[key] = df['策略参数'].apply(lambda x: str(x).split('+')[value])
        df.sort_values(by=list(factor_name_dict.keys()), inplace=True)
    except:
        print('传入的因子列表的长度可能与参数长度不一致，请检查，程序退出')
        exit()

    # 通过con来控制不画图的因子的参数
    param_len = len(str(df['策略参数'].iloc[0]).split('+'))
    df['策略参数列表'] = df['策略参数'].apply(lambda x: str(x).split('+'))
    for param_pos in range(param_len):
        if param_pos in factor_name_dict.values():  # 参数在factor_name_dict中，那么不需要做任何处理
            continue
        elif param_pos in con.keys():  # 参数不在factor_name_dict中，但是在con中指定了，那么选择con中指定的参数
            df = df[df['策略参数列表'].apply(lambda x: x[param_pos]).astype(str) == str(con[param_pos])]
        else:  # 参数不在factor_name_dict中，也没有在con中指定，那么默认选择最小参数
            try:
                print('有参数未指定在factor_name_dict中，也没有在con中指定，会按照浮点数最小值来选择参数')
                df = df[df['策略参数列表'].apply(lambda x: x[param_pos]).astype(float) == min(
                    df['策略参数列表'].apply(lambda x: x[param_pos]).astype(float))]
            except:
                print('参数未指定在factor_name_dict中，也没有在con中指定，且参数不是浮点数，会按照ASCII码最小值来选择参数，如果不符合预期，请检查，符合预期可忽略，程序先暂停5秒')
                time.sleep(5)
                df = df[df['策略参数列表'].apply(lambda x: x[param_pos]) == min(df['策略参数列表'].apply(lambda x: x[param_pos]))]

    show_factor_param_list = [key for key, value in factor_name_dict.items()]

    return df, show_factor_param_list


if __name__ == '__main__':
    stats_index = ['年化收益', '最大回撤', '年化收益/回撤比', '历年收益']
    data, show_factor_param_list = prepare_data(stg_name=stg_name, period_offset=period_offset, stats_index=stats_index,
                                                factor_name_dict=factor_name_dict)

    fig_list = []
    if len(show_factor_param_list) == 1:
        for indicator in stats_index:
            fig = Eva.draw_bar(data=data, factor_name_list=show_factor_param_list, indicator=indicator)
            fig_list.append(fig)
    elif len(show_factor_param_list) == 2:
        for indicator in stats_index:
            fig = Eva.draw_heatmap(data=data, factor_name_list=show_factor_param_list, indicator=indicator)
            fig_list.append(fig)
    else:
        print('画图涉及的因子超过了2个，或者没有一个因子设置为True，需要修改，程序已经退出')
        exit()

    Eva.merge_html(os.path.join(root_path, 'data/绘图信息/热力图'), fig_list, stg_name)
