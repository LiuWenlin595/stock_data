"""
2024分享会
author: 邢不行
微信: xbx6660
选股策略框架
"""
import os
import sys
from program.Functions import get_file_in_folder, list_to_str
from program.Config import root_path
from joblib import Parallel, delayed

python_exe = sys.executable

# 需要遍历的策略的范围，如果不写任何一个策略，默认跑【program/选股策略】下所有的策略
stg_file = []

# 默认的参数是[[0]]，表示不传入任何参数，如果有参数需要自行修改一下（实盘默认是没任何参数的）。
# 例如：stg_param = [[1,2,3,4],[5,6,7,8]]
# 甚至可以写个函数帮批量生成函数
stg_param = [[0]]

# 是否是实盘模式，如果是实盘模式只会运行当前的offset
trading_mode = False

# 是否是无参数模式，如果是：stg_param = [[0]]，实盘模式默认是无参数模式
no_param = True

# 是否要保存每日选股结果，遍历参数的情况下不建议保存，但是实盘模式是一定要保存的
save_result = True

# 用多少个CPU来回测策略，不建议设置的太高，因为你的内存可能不够大。
cpu_count = 5

# =====以下代码不需要做调整=====
# 如果有外部的参数，以外部的参数为主
if len(sys.argv) > 1:
    trading_mode = True if sys.argv[1] == 'True' else False
    no_param = True if sys.argv[2] == 'True' else False
    save_result = True if sys.argv[3] == 'True' else False

# 交易模式一定是无参数的，且一定是所有的策略
if trading_mode:
    no_param = True
    save_result = True
    stg_file = []
# 无参数模式下，stg_param = [[0]]
if no_param:
    stg_param = [[0]]

# 是否需要多线程处理，True表示多线程，False表示单线程
multiple_process = True if cpu_count > 1 else False

# 如果没有指定策略，则意味着要跑所有的策略
if len(stg_file) == 0:
    stg_path = os.path.join(root_path, 'program/选股策略/')
    stg_file = get_file_in_folder(stg_path, '.py', filters=['_init_'], drop_type=True)

# 生成遍历所需要的参数合集
ergodic_list = []
for file in stg_file:
    for param in stg_param:
        ergodic_list.append([file, trading_mode, list_to_str(param)])

print(f'需要遍历：{len(ergodic_list)}组集合')


# 运行的函数
def run(run_info):
    _file = run_info[0]
    _trading_mode = run_info[1]
    _param = run_info[2]
    os.system(f'{python_exe} {root_path}/program/2_选股.py {_file} {_trading_mode} {_param} True')


# 是否多线程运行
if multiple_process:
    df_list = Parallel(cpu_count)(delayed(run)(info) for info in ergodic_list)
else:
    for info in ergodic_list:
        run(info)
