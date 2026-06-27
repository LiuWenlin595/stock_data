import os
import time
import requests
from program.config import order_exe_path
from retrying import retry

"""
重要提示：
    运行本脚本之前，请先关闭对应券商的迅投软件！！！
    运行本脚本之前，请先关闭对应券商的迅投软件！！！
    运行本脚本之前，请先关闭对应券商的迅投软件！！！
    - 如果同时开了大QMT和小QMT，两个都要关
    
本脚本运行完成后，重启小QMT，并且最好点开行情源，看看行情源是否链接正常。
相关教程：https://bbs.quantclass.cn/thread/18505

exchange_name是本代码唯一需要配置的东西
可以填：  中航    光大     中金上海    中金深圳

是哪家券商的QMT就填哪家的名字，千万不要写错了！！！
是哪家券商的QMT就填哪家的名字，千万不要写错了！！！
是哪家券商的QMT就填哪家的名字，千万不要写错了！！！

如果你是中金
交易的电脑如果离上海近就写  中金上海
交易的电脑如果离深圳近就写  中金深圳

"""

# =====这是你唯一需要配置的东西
exchange_name = ''
# =====这是你唯一需要配置的东西


@retry(stop_max_attempt_number=5)
def update_exchange_address():
    res = requests.get(f'https://api.quantclass.cn/static/qmt/{exchange_name}/xtquoterconfig.xml?_t={int(time.time())}')
    file_path = os.path.join(order_exe_path, 'users', 'xtquoterconfig.xml')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(res.text)


update_exchange_address()
print('行情源更新成功！！！')
