import datetime
import traceback
import copy
import importlib


# 任务控制器
class TaskControl(object):
    last_run_time = None  # 任务上次运行时间
    is_finish = False  # 任务是否完成
    once = True  # 任务是否为单次执行的任务

    def __init__(self, task, start, end=None, interval=0, control_info=False, recoder_last_res=False, api_task=False,
                 rest=[], **kwargs):
        """
        定期执行任务，如果只给start，意味着只执行一次，start和end都给表示在这个区间内循环执行。
        默认没有运行的时间间隔，如果设置的话，运行的时间单位是min
        :param task:任务函数的名称
        :param start:任务起始时间
        :param end:任务结束时间
        :param interval:任务运行间隔,对于需要每日都运行一次的任务，一定要加
        :param control_info:是否需要获取控制器的信息
        :param rest:给一个时间区间，在这个时间区间内，程序将不运行
        :param **kwargs:task需要的参数
        """
        self.task = task
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        self.start = datetime.datetime.strptime((today + ' ' + start), "%Y-%m-%d %H:%M")
        if end:
            self.end = datetime.datetime.strptime((today + ' ' + end), "%Y-%m-%d %H:%M")
        else:
            self.end = None
        self.interval = interval
        self.last_run_time = datetime.datetime.now() - datetime.timedelta(minutes=self.interval)
        self.kwargs = kwargs
        self.once = False if end else True
        self.control_info = control_info
        self.recoder = recoder_last_res
        if len(rest) > 1:
            self.rest_start = datetime.datetime.strptime((today + ' ' + rest[0]), "%Y-%m-%d %H:%M")
            self.rest_end = datetime.datetime.strptime((today + ' ' + rest[1]), "%Y-%m-%d %H:%M")
            self.rest = True
        else:
            self.rest = False
        self.last_fun_res = None
        self.is_finish = False
        self.api_task = api_task

    def _get_control_info(self):
        self.kwargs['task'] = self.task
        self.kwargs['start'] = self.start
        self.kwargs['end'] = self.end
        self.kwargs['interval'] = self.interval
        self.kwargs['last_run_time'] = self.last_run_time
        self.kwargs['once'] = self.once
        self.kwargs['is_finish'] = self.is_finish
        self.kwargs['last_fun_res'] = self.last_fun_res

    def run(self):
        """
        运行任务
        :return:
        """
        res = 2  # 0表示错误，1表示满足条件且正常执行，2表示未满足执行条件
        func_res = '未满足执行条件'
        try:
            if self.is_finish:
                return res, '任务已完成'
            now_time = datetime.datetime.now()
            con = now_time >= self.start
            if self.end:
                con &= now_time <= self.end
            if self.interval > 0:
                con &= now_time >= self.last_run_time + datetime.timedelta(minutes=self.interval)
            if self.rest:
                is_rest = (self.rest_start <= now_time) and (now_time <= self.rest_end)
                con &= (not is_rest)
            if con:
                if self.control_info:
                    self._get_control_info()
                paras = ''
                if self.api_task:
                    for k in self.kwargs.keys():
                        if k == 'ex_api':
                            continue
                        # paras += '%s=self.kwargs[\'%s\'],' % (k, k)
                        paras += f"{k}=self.kwargs['{k}'],"
                    func_name = self.task[self.task.rfind('.'):]
                    # func_res = eval('self.kwargs[\'ex_api\']%s(%s)' % (func_name, paras))
                    func_res = eval(f"self.kwargs['ex_api']{func_name}({paras})")
                    func_res = (self.kwargs['ex_api'], func_res)
                else:
                    for k in self.kwargs.keys():
                        # paras += '%s=self.kwargs[\'%s\'],' % (k, k)
                        paras += f"{k}=self.kwargs['{k}'],"
                    mode_name = self.task[:self.task.rfind('.')]
                    func_name = self.task[self.task.rfind('.'):]
                    # func_res = eval('importlib.import_module(\'%s\')%s(%s)' % (mode_name, func_name, paras))
                    func_res = eval(f"importlib.import_module('{mode_name}'){func_name}({paras})")
                if self.recoder:
                    self.last_fun_res = copy.deepcopy(func_res)
                res = 1
                self.last_run_time = now_time
                if isinstance(func_res, tuple):
                    if isinstance(func_res[-1], str):
                        if func_res[-1] == 'Finish':
                            self.is_finish = True
                            return res, func_res[:-1]
                        elif func_res[-1] == 'Pass':
                            return 2, '未满足执行条件'
                elif func_res == 'Finish':
                    self.is_finish = True
                elif func_res == 'Pass':
                    return 2, '未满足执行条件'
                if self.once:
                    self.is_finish = True
            return res, func_res

        except Exception as err:
            res = 0
            return res, traceback.format_exc() + str(err)
