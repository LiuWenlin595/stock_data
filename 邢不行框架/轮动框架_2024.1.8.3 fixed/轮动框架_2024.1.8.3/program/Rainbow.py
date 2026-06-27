import os
import time
import requests
import logging as log
import datetime
import json
import traceback

_ = os.path.abspath(os.path.dirname(__file__))  # 返回当前文件路径
root_path = os.path.abspath(os.path.join(_, '..'))  # 返回根目录文件夹

log_path = os.path.join(root_path, 'data/系统日志/')
os.makedirs(log_path, exist_ok=True)
log.basicConfig(filename=os.path.join(log_path, f'{datetime.datetime.now().strftime("%Y-%m-%d")}_日志.log'),
                level=log.INFO)

err_set_path = os.path.join(root_path, 'data/err_set.json')
err_set_name = 'lundong'
err_set = []


# region 错题集相关代码

def update_err_set():
    """
    更新错题集
    :return:
    """
    try:
        global err_set
        update = False
        # 如果文件不存在，需要更新
        if not os.path.exists(err_set_path):
            update = True
        # 如果文件不是最新的，也需要更新（每天更新一次）
        else:
            modify_time = os.path.getmtime(err_set_path)
            modify_time_readable = time.strftime('%Y-%m-%d', time.localtime(modify_time))
            today = datetime.datetime.today().strftime('%Y-%m-%d')
            if modify_time_readable != today:
                update = True
            # 如果错题集文件过小也需要更新
            else:
                with open(err_set_path, 'r', encoding='utf-8') as f:
                    err_set = json.load(f)
                if len(err_set) == 0:
                    update = True

        if update:
            url = f'https://api.quantclass.cn/api/data/framework/solution/version/{err_set_name}'
            res = requests.get(url)
            if res.status_code == 200:
                file_res = requests.get(res.json()['data']['solutions'])
                if file_res.status_code == 200:
                    record_log(f'错题集更新成功，当前版本号：{res.json()["data"]["version"]}')
                    json_text = file_res.text
                else:
                    json_text = '[]'
            else:
                json_text = '[]'

            # 如果获取失败了
            if json_text == '[]':
                record_log('更新错题集出现了一点小问题，不要慌，可以忽略的~~')
                if os.path.exists(err_set_path):
                    return
            err_set = eval(json_text)
            with open(err_set_path, 'w', encoding='utf-8') as f:
                json.dump(err_set, f, ensure_ascii=False, indent=4)
        else:
            record_log('当前错题集状态正常，无需更新~~')
    except Exception as err:
        err_txt = traceback.format_exc()
        record_log(f'错题集更新失败，程序继续运行，错误信息:{err_txt}~~')
        json_text = '[]'
        if os.path.exists(err_set_path):
            return
        err_set = eval(json_text)
        with open(err_set_path, 'w', encoding='utf-8') as f:
            json.dump(err_set, f, ensure_ascii=False, indent=4)


def check_strings_in_text(string_list, text):
    """
    判断目标文本中是否包含list中所有的字符元素
    :param string_list:
    :param text:
    :return:
    """
    # 遍历列表中的每个字符串
    for string in string_list:
        # 如果字符串不在文本中，则返回False
        if string not in text:
            return False
    # 如果所有字符串都在文本中出现过，遍历结束后返回True
    return True


def match_solution(err_text, _print=True):
    """
    根据err信息匹配对应的解决方案
    :param err_text:
    :param _print:
    :return:
    """
    global err_set
    hit = False
    for err in err_set:
        hit = check_strings_in_text(err['keywords'], err_text)
        if hit:
            reason = err['reason']
            solution = err['solution']
            res = f'==问题原因：\n{reason}\n\n==解决方案：\n{solution}'
            err_text += '\n' + res
            break
    if not hit:
        res = '未在错题集里面找到对应的答案，如果自己搞不定的话，及时找助教帮忙哦~'
        err_text += '\n' + res
    record_log(err_text, _print)
    return err_text


# endregion

# region 记录日志相关的代码
def record_log(msg, _print=True):
    """
    记录日志
    :param msg:日志信息
    :param _print:是否要打印
    :return:
    """
    now_time = datetime.datetime.now()
    time_str = datetime.datetime.strftime(now_time, "%H:%M:%S")
    log_msg = time_str + ' --> ' + msg

    try:
        if _print:
            print(log_msg)
        log.info(msg=log_msg)
    except Exception as err:
        log.info(msg=f'记录日志错误{err}')


# endregion

update_err_set()
if __name__ == '__main__':
    while True:
        ipt = input('请把你的报错信息复制过来，然后敲回车。\n')
        _res = match_solution(ipt)
        print(_res, '\n')
