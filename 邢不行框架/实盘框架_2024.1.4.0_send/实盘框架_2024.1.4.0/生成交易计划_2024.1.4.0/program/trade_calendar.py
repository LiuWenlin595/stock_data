import os
from py_mini_racer import py_mini_racer
import pandas as pd
import datetime
import requests


# 交易日历
class TradeCalendar(object):
    # 常用的参数，初始化的时候就会生成
    today = None  # 当前交易日期，如果当前非交易日。
    last_trade_date = None  # 上一个交易日
    next_trade_date = None  # 下一个交易日
    market_open = True  # 今日是否交易
    calendar = None  # 完整的交易日历
    _now_date = datetime.date.today()
    period_offset_df = pd.DataFrame()

    def __init__(self, rb, day_win=60):
        """
        构造函数
        :param day_win: 日历长度
        """
        try:
            self.calendar = self.tool_trade_date_hist_sina()
            self.rb = rb
        except Exception as err:
            self.rb.record_log(f'获取交易日历存在错误：{err}', send=True)
            self.calendar = self.create_calendar_offline(day_win=day_win * 1.5)
        # 计算时间差
        self.calendar['from_now'] = self.calendar['trade_date'].apply(lambda x: (x - self._now_date).days)
        # 只保留距指定时间的数据
        self.calendar = self.calendar[abs(self.calendar['from_now']) < day_win]

        # 处理获取的未来日历长度不够的问题
        if self.calendar['from_now'].max() < day_win * 0.95:
            calendar_offline = self.create_calendar_offline(day_win=day_win * 1.5)
            calendar_offline = calendar_offline[calendar_offline['trade_date'] > self.calendar['trade_date'].iloc[-1]]
            self.calendar = pd.concat([self.calendar, calendar_offline], ignore_index=True).sort_values(
                by='trade_date')
            self.calendar['from_now'] = self.calendar['trade_date'].apply(lambda x: (x - self._now_date).days)

        self.calendar['trade_date'] = pd.to_datetime(self.calendar['trade_date'])
        # 获取上一个交易日
        con = self.calendar['from_now'] < 0
        self.last_trade_date = self.calendar[con]['trade_date'].iloc[-1]

        # 获取下一个交易日
        con = self.calendar['from_now'] > 0
        self.next_trade_date = self.calendar[con]['trade_date'].iloc[0]

        # 获取当前日期
        if 0 in self.calendar['from_now'].values:
            self.today = self.calendar[self.calendar['from_now'] == 0]['trade_date'].iloc[0]
        else:
            self.today = self.next_trade_date
            self.market_open = False

        # 计算好一些东西备用
        self.calendar['month'] = self.calendar['trade_date'].apply(lambda x: x.month)
        self.calendar['week'] = self.calendar['trade_date'].apply(lambda x: x.weekofyear)
        for key in ['month', 'week']:
            self.calendar.loc[self.calendar[key] == self.calendar[key].shift(), key] = 0
            self.calendar.loc[self.calendar[key] != 0, key] = 1
            self.calendar[key] = self.calendar[key].cumsum()
        # 计算当前日属于一周的第几天或者一个月的第几天
        self.calendar['week_of'] = self.calendar.groupby('week')['week'].rank(method='first')
        self.calendar['month_of'] = self.calendar.groupby('month')['month'].rank(method='first')

    @staticmethod
    def create_calendar_offline(day_win=84):
        """
        离线创建交易日历
        :param day_win: 日历长度
        :return:
        """
        now_date = datetime.date.today()
        start = now_date - datetime.timedelta(days=day_win)
        end = now_date + datetime.timedelta(days=day_win)
        calendar_offline = pd.DataFrame(pd.date_range(start, end, freq='D'))
        calendar_offline.rename(columns={0: 'trade_date'}, inplace=True)
        # ===== 删除节假日数据的数据
        # 1、标记周末、和日期信息：公历+阴历+节气
        calendar_offline['week'] = calendar_offline['trade_date'].dt.dayofweek + 1
        calendar_offline['date_info'] = calendar_offline['trade_date'].apply(
            lambda x: f'公历{x.month}月{x.day}日' + ' 农历' + Lunar(x).ln_date_str() + Lunar(x).ln_jie())
        # 节日放假信息
        holidays = {'公历1月1日': 3, '公历5月1日': 5, '公历10月1日': 7,
                    '正月初一': 6, '五月初五': 3, '八月十五': 3,
                    '清明': 3}
        for holiday in holidays.keys():
            calendar_offline.loc[calendar_offline['date_info'].str.contains(holiday), 'rest'] = holidays[holiday]

        # 周末默认放假
        calendar_offline.loc[calendar_offline['week'] > 5, 'holiday'] = 1
        # 根据节假日的休息信息判断什么时候放假
        for i in calendar_offline.index[10:-10]:
            if calendar_offline.at[i, 'rest'] > 0:
                # 节日当天肯定是休息的
                calendar_offline.at[i, 'holiday'] = 1
                week = calendar_offline.at[i, 'week']
                rest = calendar_offline.at[i, 'rest']
                # 处理休息三天的情况
                if rest == 3:
                    if week <= 2:
                        calendar_offline.at[i - 1, 'holiday'] = 1
                        calendar_offline.at[i - 2, 'holiday'] = 1
                    elif (week > 3) & (week < 7):
                        calendar_offline.at[i + 1, 'holiday'] = 1
                        calendar_offline.at[i + 2, 'holiday'] = 1
                    else:
                        calendar_offline.at[i + 1, 'holiday'] = 1
                else:
                    for j in range(1, int(rest)):
                        calendar_offline.at[i + j, 'holiday'] = 1
                    # 特殊处理春节,春节有是29开始放假，有的是30开始放假。
                    if rest == 6:
                        calendar_offline.at[i - 1, 'holiday'] = 1

        calendar_offline = calendar_offline[calendar_offline['holiday'] != 1][['trade_date']]
        calendar_offline['trade_date'] = calendar_offline['trade_date'].apply(
            lambda x: datetime.date(year=x.year, month=x.month, day=x.day))
        return calendar_offline

    def cal_day_delta(self, appoint_day, delta):
        """
        根据指定日期计算日期偏差。
        :param appoint_day: 指定日期
        :param delta: 日期偏差，正数表示向前，负数表示向后
        :return:
        """
        try:
            # 时间格式转换
            if isinstance(appoint_day, str):
                appoint_day = pd.to_datetime(appoint_day)
            if delta > 0:
                date = self.calendar[self.calendar['trade_date'] < appoint_day]['trade_date'].iloc[-delta]
            if delta < 0:
                date = self.calendar[self.calendar['trade_date'] >= appoint_day]['trade_date'].iloc[-delta]
            if delta == 0:
                date = pd.to_datetime(appoint_day)
            return date
        except Exception as err:
            self.rb.record_log(f'计算指定交易日日期失败：{appoint_day}偏移{delta}，错误：{err}')
            return -1

    def day_of_period_end(self, period='W', period_delta=0, day_delta=None):
        """
        计算周末或者月末的交易日期
        :param period: 周还是月
        :param period_delta: 间隔周或者月，-1表示下周，0表示当周，1表示上周
        :param day_delta: 针对获取到的末期数据计算便宜
        :return:
        """
        try:
            time_con = self.calendar['from_now'] <= 0
            if period == 'W':
                week = self.calendar[time_con]['week'].iloc[-1]
                con = self.calendar['week'] == (week - period_delta)
            else:
                month = self.calendar[time_con]['month'].iloc[-1]
                con = self.calendar['month'] == (month - period_delta)
            date = self.calendar[con]['trade_date'].iloc[-1]
            if day_delta:
                date = self.cal_day_delta(date, day_delta)
            return date
        except Exception as err:
            self.rb.record_log(f"计算{period}末失败：{err}")
            return -1

    def get_date_by_rule(self, rule, intraday_swap_change=0):
        """
        根据规则获取指定的交易日期，详见使用指南
        :param rule: 规则
        :param intraday_swap_change: 当intraday_swap=1的时候，要传入，这样卖出日会延后一个交易日
        :return:
        """
        sell_date = -1
        if isinstance(rule, int):
            sell_date = self.cal_day_delta(self.today, -abs(rule) + 1)
        elif isinstance(rule, list):
            day_delta = None
            if len(rule) == 3:
                day_delta = -abs(rule[2])
            sell_date = self.day_of_period_end(rule[0], -abs(rule[1]), day_delta)
        elif isinstance(rule, str):
            if (intraday_swap_change == 1) and (self.period_offset_df[rule].min() >= 0):
                df = self.period_offset_df.copy()
                df['下个交易日期'] = df['交易日期'].shift(-1)
                df = df[df[rule] > 0]
                sell_date = df.groupby(rule).agg({'下个交易日期': 'last'})['下个交易日期'].iloc[0]
            else:
                df = self.period_offset_df[self.period_offset_df[rule] > 0]
                sell_date = df.groupby(rule).agg({'交易日期': 'last'})['交易日期'].iloc[0]
        else:
            self.rb.record_log(f"获取卖出日期失败：{rule}")
        return sell_date

    def load_period_offset(self, file_path):
        if os.path.exists(file_path):
            df = pd.read_csv(file_path, encoding='gbk', parse_dates=['交易日期'], skiprows=1)
            self.period_offset_df = df[df['交易日期'] > self.today].copy()

    @staticmethod
    def tool_trade_date_hist_sina() -> pd.DataFrame:
        """
        交易日历-历史数据
        https://finance.sina.com.cn/realstock/company/klc_td_sh.txt
        :return: 交易日历
        :rtype: pandas.DataFrame
        """

        url = "https://finance.sina.com.cn/realstock/company/klc_td_sh.txt"
        r = requests.get(url)
        js_code = py_mini_racer.MiniRacer()
        hk_js_decode = """
        function d(t) {
            var e, i, n, r, a, o, s, l = (arguments,
                    864e5), u = 7657, c = [], h = [], d = ~(3 << 30), f = 1 << 30,
                p = [0, 3, 5, 6, 9, 10, 12, 15, 17, 18, 20, 23, 24, 27, 29, 30], m = Math, g = function () {
                    var l, u;
                    for (l = 0; 64 > l; l++)
                        h[l] = m.pow(2, l),
                        26 > l && (c[l] = v(l + 65),
                            c[l + 26] = v(l + 97),
                        10 > l && (c[l + 52] = v(l + 48)));
                    for (c.push("+", "/"),
                             c = c.join(""),
                             i = t.split(""),
                             n = i.length,
                             l = 0; n > l; l++)
                        i[l] = c.indexOf(i[l]);
                    return r = {},
                        e = o = 0,
                        a = {},
                        u = w([12, 6]),
                        s = 63 ^ u[1],
                    {
                        _1479: T,
                        _136: _,
                        _200: S,
                        _139: k,
                        _197: _mi_run
                    }["_" + u[0]] || function () {
                        return []
                    }
                }, v = String.fromCharCode, b = function (t) {
                    return t === {}._
                }, N = function () {
                    var t, e;
                    for (t = y(),
                             e = 1; ;) {
                        if (!y())
                            return e * (2 * t - 1);
                        e++
                    }
                }, y = function () {
                    var t;
                    return e >= n ? 0 : (t = i[e] & 1 << o,
                        o++,
                    o >= 6 && (o -= 6,
                        e++),
                        !!t)
                }, w = function (t, r, a) {
                    var s, l, u, c, d;
                    for (l = [],
                             u = 0,
                         r || (r = []),
                         a || (a = []),
                             s = 0; s < t.length; s++)
                        if (c = t[s],
                            u = 0,
                            c) {
                            if (e >= n)
                                return l;
                            if (t[s] <= 0)
                                u = 0;
                            else if (t[s] <= 30) {
                                for (; d = 6 - o,
                                           d = c > d ? d : c,
                                           u |= (i[e] >> o & (1 << d) - 1) << t[s] - c,
                                           o += d,
                                       o >= 6 && (o -= 6,
                                           e++),
                                           c -= d,
                                           !(0 >= c);)
                                    ;
                                r[s] && u >= h[t[s] - 1] && (u -= h[t[s]])
                            } else
                                u = w([30, t[s] - 30], [0, r[s]]),
                                a[s] || (u = u[0] + u[1] * h[30]);
                            l[s] = u
                        } else
                            l[s] = 0;
                    return l
                }, x = function (t) {
                    var e, i, n;
                    for (t > 1 && (e = 0),
                             e = 0; t > e; e++)
                        r.d++,
                            n = r.d % 7,
                        (3 == n || 4 == n) && (r.d += 5 - n);
                    return i = new Date,
                        i.setTime((u + r.d) * l),
                        i
                }, S = function () {
                    var t, i, a, o, l;
                    if (s >= 1)
                        return [];
                    for (r.d = w([18], [1])[0] - 1,
                             a = w([3, 3, 30, 6]),
                             r.p = a[0],
                             r.ld = a[1],
                             r.cd = a[2],
                             r.c = a[3],
                             r.m = m.pow(10, r.p),
                             r.pc = r.cd / r.m,
                             i = [],
                             t = 0; o = {
                        d: 1
                    },
                         y() && (a = w([3])[0],
                             0 == a ? o.d = w([6])[0] : 1 == a ? (r.d = w([18])[0],
                                 o.d = 0) : o.d = a),
                             l = {
                                 day: x(o.d)
                             },
                         y() && (r.ld += N()),
                             a = w([3 * r.ld], [1]),
                             r.cd += a[0],
                             l.close = r.cd / r.m,
                             i.push(l),
                         !(e >= n) && (e != n - 1 || 63 & (r.c ^ t + 1)); t++)
                        ;
                    return i[0].prevclose = r.pc,
                        i
                }, _ = function () {
                    var t, i, a, o, l, u, c, h, d, f, p;
                    if (s > 2)
                        return [];
                    for (c = [],
                             d = {
                                 v: "volume",
                                 p: "price",
                                 a: "avg_price"
                             },
                             r.d = w([18], [1])[0] - 1,
                             h = {
                                 day: x(1)
                             },
                             a = w(1 > s ? [3, 3, 4, 1, 1, 1, 5] : [4, 4, 4, 1, 1, 1, 3]),
                             t = 0; 7 > t; t++)
                        r[["la", "lp", "lv", "tv", "rv", "zv", "pp"][t]] = a[t];
                    for (r.m = m.pow(10, r.pp),
                             s >= 1 ? (a = w([3, 3]),
                                 r.c = a[0],
                                 a = a[1]) : (a = 5,
                                 r.c = 2),
                             r.pc = w([6 * a])[0],
                             h.pc = r.pc / r.m,
                             r.cp = r.pc,
                             r.da = 0,
                             r.sa = r.sv = 0,
                             t = 0; !(e >= n) && (e != n - 1 || 7 & (r.c ^ t)); t++) {
                        for (l = {},
                                 o = {},
                                 f = r.tv ? y() : 1,
                                 i = 0; 3 > i; i++)
                            if (p = ["v", "p", "a"][i],
                            (f ? y() : 0) && (a = N(),
                                r["l" + p] += a),
                                u = "v" == p && r.rv ? y() : 1,
                                a = w([3 * r["l" + p] + ("v" == p ? 7 * u : 0)], [!!i])[0] * (u ? 1 : 100),
                                o[p] = a,
                            "v" == p) {
                                if (!(l[d[p]] = a) && (s > 1 || 241 > t) && (r.zv ? !y() : 1)) {
                                    o.p = 0;
                                    break
                                }
                            } else
                                "a" == p && (r.da = (1 > s ? 0 : r.da) + o.a);
                        r.sv += o.v,
                            l[d.p] = (r.cp += o.p) / r.m,
                            r.sa += o.v * r.cp,
                            l[d.a] = b(o.a) ? t ? c[t - 1][d.a] : l[d.p] : r.sv ? ((m.floor((r.sa * (2e3 / r.m) + r.sv) / r.sv) >> 1) + r.da) / 1e3 : l[d.p] + r.da / 1e3,
                            c.push(l)
                    }
                    return c[0].date = h.day,
                        c[0].prevclose = h.pc,
                        c
                }, T = function () {
                    var t, e, i, n, a, o, l;
                    if (s >= 1)
                        return [];
                    for (r.lv = 0,
                             r.ld = 0,
                             r.cd = 0,
                             r.cv = [0, 0],
                             r.p = w([6])[0],
                             r.d = w([18], [1])[0] - 1,
                             r.m = m.pow(10, r.p),
                             a = w([3, 3]),
                             r.md = a[0],
                             r.mv = a[1],
                             t = []; a = w([6]),
                             a.length;) {
                        if (i = {
                            c: a[0]
                        },
                            n = {},
                            i.d = 1,
                        32 & i.c)
                            for (; ;) {
                                if (a = w([6])[0],
                                63 == (16 | a)) {
                                    l = 16 & a ? "x" : "u",
                                        a = w([3, 3]),
                                        i[l + "_d"] = a[0] + r.md,
                                        i[l + "_v"] = a[1] + r.mv;
                                    break
                                }
                                if (32 & a) {
                                    o = 8 & a ? "d" : "v",
                                        l = 16 & a ? "x" : "u",
                                        i[l + "_" + o] = (7 & a) + r["m" + o];
                                    break
                                }
                                if (o = 15 & a,
                                    0 == o ? i.d = w([6])[0] : 1 == o ? (r.d = o = w([18])[0],
                                        i.d = 0) : i.d = o,
                                    !(16 & a))
                                    break
                            }
                        n.date = x(i.d);
                        for (o in {
                            v: 0,
                            d: 0
                        })
                            b(i["x_" + o]) || (r["l" + o] = i["x_" + o]),
                            b(i["u_" + o]) && (i["u_" + o] = r["l" + o]);
                        for (i.l_l = [i.u_d, i.u_d, i.u_d, i.u_d, i.u_v],
                                 l = p[15 & i.c],
                             1 & i.u_v && (l = 31 - l),
                             16 & i.c && (i.l_l[4] += 2),
                                 e = 0; 5 > e; e++)
                            l & 1 << 4 - e && i.l_l[e]++,
                                i.l_l[e] *= 3;
                        i.d_v = w(i.l_l, [1, 0, 0, 1, 1], [0, 0, 0, 0, 1]),
                            o = r.cd + i.d_v[0],
                            n.open = o / r.m,
                            n.high = (o + i.d_v[1]) / r.m,
                            n.low = (o - i.d_v[2]) / r.m,
                            n.close = (o + i.d_v[3]) / r.m,
                            a = i.d_v[4],
                        "number" == typeof a && (a = [a, a >= 0 ? 0 : -1]),
                            r.cd = o + i.d_v[3],
                            l = r.cv[0] + a[0],
                            r.cv = [l & d, r.cv[1] + a[1] + !!((r.cv[0] & d) + (a[0] & d) & f)],
                            n.volume = (r.cv[0] & f - 1) + r.cv[1] * f,
                            t.push(n)
                    }
                    return t
                }, k = function () {
                    var t, e, i, n;
                    if (s > 1)
                        return [];
                    for (r.l = 0,
                             n = -1,
                             r.d = w([18])[0] - 1,
                             i = w([18])[0]; r.d < i;)
                        e = x(1),
                            0 >= n ? (y() && (r.l += N()),
                                n = w([3 * r.l], [0])[0] + 1,
                            t || (t = [e],
                                n--)) : t.push(e),
                            n--;
                    return t
                };
            return _mi_run = function () {
                var t, i, a, o;
                if (s >= 1)
                    return [];
                for (r.f = w([6])[0],
                         r.c = w([6])[0],
                         a = [],
                         r.dv = [],
                         r.dl = [],
                         t = 0; t < r.f; t++)
                    r.dv[t] = 0,
                        r.dl[t] = 0;
                for (t = 0; !(e >= n) && (e != n - 1 || 7 & (r.c ^ t)); t++) {
                    for (o = [],
                             i = 0; i < r.f; i++)
                        y() && (r.dl[i] += N()),
                            r.dv[i] += w([3 * r.dl[i]], [1])[0],
                            o[i] = r.dv[i];
                    a.push(o)
                }
                return a
            }
                ,
                g()()
        }
        """
        js_code.eval(hk_js_decode)
        dict_list = js_code.call(
            "d", r.text.split("=")[1].split(";")[0].replace('"', "")
        )  # 执行js解密代码
        temp_df = pd.DataFrame(dict_list)
        temp_df.columns = ["trade_date"]
        temp_df["trade_date"] = pd.to_datetime(temp_df["trade_date"]).dt.date
        temp_list = temp_df["trade_date"].to_list()
        temp_list.append(datetime.date(1992, 5, 4))  # 是交易日但是交易日历缺失该日期
        temp_list.sort()
        temp_df = pd.DataFrame(temp_list, columns=["trade_date"])
        return temp_df


# 计算农历节假日，copy的代码

class Lunar(object):
    # ******************************************************************************
    # 下面为阴历计算所需的数据,为节省存储空间,所以采用下面比较变态的存储方法.
    # ******************************************************************************
    # 数组g_lunar_month_day存入阴历1901年到2050年每年中的月天数信息，
    # 阴历每月只能是29或30天，一年用12（或13）个二进制位表示，对应位为1表30天，否则为29天
    g_lunar_month_day = [
        0x4ae0, 0xa570, 0x5268, 0xd260, 0xd950, 0x6aa8, 0x56a0, 0x9ad0, 0x4ae8, 0x4ae0,  # 1910
        0xa4d8, 0xa4d0, 0xd250, 0xd548, 0xb550, 0x56a0, 0x96d0, 0x95b0, 0x49b8, 0x49b0,  # 1920
        0xa4b0, 0xb258, 0x6a50, 0x6d40, 0xada8, 0x2b60, 0x9570, 0x4978, 0x4970, 0x64b0,  # 1930
        0xd4a0, 0xea50, 0x6d48, 0x5ad0, 0x2b60, 0x9370, 0x92e0, 0xc968, 0xc950, 0xd4a0,  # 1940
        0xda50, 0xb550, 0x56a0, 0xaad8, 0x25d0, 0x92d0, 0xc958, 0xa950, 0xb4a8, 0x6ca0,  # 1950
        0xb550, 0x55a8, 0x4da0, 0xa5b0, 0x52b8, 0x52b0, 0xa950, 0xe950, 0x6aa0, 0xad50,  # 1960
        0xab50, 0x4b60, 0xa570, 0xa570, 0x5260, 0xe930, 0xd950, 0x5aa8, 0x56a0, 0x96d0,  # 1970
        0x4ae8, 0x4ad0, 0xa4d0, 0xd268, 0xd250, 0xd528, 0xb540, 0xb6a0, 0x96d0, 0x95b0,  # 1980
        0x49b0, 0xa4b8, 0xa4b0, 0xb258, 0x6a50, 0x6d40, 0xada0, 0xab60, 0x9370, 0x4978,  # 1990
        0x4970, 0x64b0, 0x6a50, 0xea50, 0x6b28, 0x5ac0, 0xab60, 0x9368, 0x92e0, 0xc960,  # 2000
        0xd4a8, 0xd4a0, 0xda50, 0x5aa8, 0x56a0, 0xaad8, 0x25d0, 0x92d0, 0xc958, 0xa950,  # 2010
        0xb4a0, 0xb550, 0xb550, 0x55a8, 0x4ba0, 0xa5b0, 0x52b8, 0x52b0, 0xa930, 0x74a8,  # 2020
        0x6aa0, 0xad50, 0x4da8, 0x4b60, 0x9570, 0xa4e0, 0xd260, 0xe930, 0xd530, 0x5aa0,  # 2030
        0x6b50, 0x96d0, 0x4ae8, 0x4ad0, 0xa4d0, 0xd258, 0xd250, 0xd520, 0xdaa0, 0xb5a0,  # 2040
        0x56d0, 0x4ad8, 0x49b0, 0xa4b8, 0xa4b0, 0xaa50, 0xb528, 0x6d20, 0xada0, 0x55b0,  # 2050
    ]

    # 数组gLanarMonth存放阴历1901年到2050年闰月的月份，如没有则为0，每字节存两年
    g_lunar_month = [
        0x00, 0x50, 0x04, 0x00, 0x20,  # 1910
        0x60, 0x05, 0x00, 0x20, 0x70,  # 1920
        0x05, 0x00, 0x40, 0x02, 0x06,  # 1930
        0x00, 0x50, 0x03, 0x07, 0x00,  # 1940
        0x60, 0x04, 0x00, 0x20, 0x70,  # 1950
        0x05, 0x00, 0x30, 0x80, 0x06,  # 1960
        0x00, 0x40, 0x03, 0x07, 0x00,  # 1970
        0x50, 0x04, 0x08, 0x00, 0x60,  # 1980
        0x04, 0x0a, 0x00, 0x60, 0x05,  # 1990
        0x00, 0x30, 0x80, 0x05, 0x00,  # 2000
        0x40, 0x02, 0x07, 0x00, 0x50,  # 2010
        0x04, 0x09, 0x00, 0x60, 0x04,  # 2020
        0x00, 0x20, 0x60, 0x05, 0x00,  # 2030
        0x30, 0xb0, 0x06, 0x00, 0x50,  # 2040
        0x02, 0x07, 0x00, 0x50, 0x03  # 2050
    ]

    START_YEAR = 1901

    # 天干
    gan = '甲乙丙丁戊己庚辛壬癸'
    # 地支
    zhi = '子丑寅卯辰巳午未申酉戌亥'
    # 生肖
    xiao = '鼠牛虎兔龙蛇马羊猴鸡狗猪'
    # 月份
    lm = '正二三四五六七八九十冬腊'
    # 日份
    ld = '初一初二初三初四初五初六初七初八初九初十十一十二十三十四十五十六十七十八十九二十廿一廿二廿三廿四廿五廿六廿七廿八廿九三十'
    # 节气
    jie = '小寒大寒立春雨水惊蛰春分清明谷雨立夏小满芒种夏至小暑大暑立秋处暑白露秋分寒露霜降立冬小雪大雪冬至'

    def __init__(self, dt=None):
        '''初始化：参数为datetime.datetime类实例，默认当前时间'''
        self.localtime = dt if dt else datetime.datetime.today()

    def sx_year(self):  # 返回生肖年
        ct = self.localtime  # 取当前时间

        year = self.ln_year() - 3 - 1  # 农历年份减3 （说明：补减1）
        year = year % 12  # 模12，得到地支数
        return self.xiao[year]

    def gz_year(self):  # 返回干支纪年
        ct = self.localtime  # 取当前时间
        year = self.ln_year() - 3 - 1  # 农历年份减3 （说明：补减1）
        G = year % 10  # 模10，得到天干数
        Z = year % 12  # 模12，得到地支数
        return self.gan[G] + self.zhi[Z]

    def gz_month(self):  # 返回干支纪月（未实现）
        pass

    def gz_day(self):  # 返回干支纪日
        ct = self.localtime  # 取当前时间
        C = ct.year // 100  # 取世纪数，减一
        y = ct.year % 100  # 取年份后两位（若为1月、2月则当前年份减一）
        y = y - 1 if ct.month == 1 or ct.month == 2 else y
        M = ct.month  # 取月份（若为1月、2月则分别按13、14来计算）
        M = M + 12 if ct.month == 1 or ct.month == 2 else M
        d = ct.day  # 取日数
        i = 0 if ct.month % 2 == 1 else 6  # 取i （奇数月i=0，偶数月i=6）

        # 下面两个是网上的公式
        # http://baike.baidu.com/link?url=MbTKmhrTHTOAz735gi37tEtwd29zqE9GJ92cZQZd0X8uFO5XgmyMKQru6aetzcGadqekzKd3nZHVS99rewya6q
        # 计算干（说明：补减1）
        G = 4 * C + C // 4 + 5 * y + y // 4 + 3 * (M + 1) // 5 + d - 3 - 1
        G = G % 10
        # 计算支（说明：补减1）
        Z = 8 * C + C // 4 + 5 * y + y // 4 + 3 * (M + 1) // 5 + d + 7 + i - 1
        Z = Z % 12

        # 返回 干支纪日
        return self.gan[G] + self.zhi[Z]

    def gz_hour(self):  # 返回干支纪时（时辰）
        ct = self.localtime  # 取当前时间
        # 计算支
        Z = round((ct.hour / 2) + 0.1) % 12  # 之所以加0.1是因为round的bug!!

        # 返回 干支纪时（时辰）
        return self.zhi[Z]

    def ln_year(self):  # 返回农历年
        year, _, _ = self.ln_date()
        return year

    def ln_month(self):  # 返回农历月
        _, month, _ = self.ln_date()
        return month

    def ln_day(self):  # 返回农历日
        _, _, day = self.ln_date()
        return day

    def ln_date(self):  # 返回农历日期整数元组（年、月、日）（查表法）
        delta_days = self._date_diff()

        # 阳历1901年2月19日为阴历1901年正月初一
        # 阳历1901年1月1日到2月19日共有49天
        if (delta_days < 49):
            year = self.START_YEAR - 1
            if (delta_days < 19):
                month = 11;
                day = 11 + delta_days
            else:
                month = 12;
                day = delta_days - 18
            return (year, month, day)

        # 下面从阴历1901年正月初一算起
        delta_days -= 49
        year, month, day = self.START_YEAR, 1, 1
        # 计算年
        tmp = self._lunar_year_days(year)
        while delta_days >= tmp:
            delta_days -= tmp
            year += 1
            tmp = self._lunar_year_days(year)

        # 计算月
        (foo, tmp) = self._lunar_month_days(year, month)
        while delta_days >= tmp:
            delta_days -= tmp
            if (month == self._get_leap_month(year)):
                (tmp, foo) = self._lunar_month_days(year, month)
                if (delta_days < tmp):
                    return (0, 0, 0)
                delta_days -= tmp
            month += 1
            (foo, tmp) = self._lunar_month_days(year, month)

        # 计算日
        day += delta_days
        return (year, month, day)

    def ln_date_str(self):  # 返回农历日期字符串，形如：农历正月初九
        _, month, day = self.ln_date()
        return '{}月{}'.format(self.lm[month - 1], self.ld[(day - 1) * 2:day * 2])

    def ln_jie(self):  # 返回农历节气
        ct = self.localtime  # 取当前时间
        year = ct.year
        for i in range(24):
            # 因为两个都是浮点数，不能用相等表示
            delta = self._julian_day() - self._julian_day_of_ln_jie(year, i)
            if -.5 <= delta <= .5:
                return self.jie[i * 2:(i + 1) * 2]
        return ''

    # 显示日历
    def calendar(self):
        pass

    #######################################################
    #            下面皆为私有函数
    #######################################################

    def _date_diff(self):
        '''返回基于1901/01/01日差数'''
        return (self.localtime - datetime.datetime(1901, 1, 1)).days

    def _get_leap_month(self, lunar_year):
        flag = self.g_lunar_month[(lunar_year - self.START_YEAR) // 2]
        if (lunar_year - self.START_YEAR) % 2:
            return flag & 0x0f
        else:
            return flag >> 4

    def _lunar_month_days(self, lunar_year, lunar_month):
        if (lunar_year < self.START_YEAR):
            return 30

        high, low = 0, 29
        iBit = 16 - lunar_month;

        if (lunar_month > self._get_leap_month(lunar_year) and self._get_leap_month(lunar_year)):
            iBit -= 1

        if (self.g_lunar_month_day[lunar_year - self.START_YEAR] & (1 << iBit)):
            low += 1

        if (lunar_month == self._get_leap_month(lunar_year)):
            if (self.g_lunar_month_day[lunar_year - self.START_YEAR] & (1 << (iBit - 1))):
                high = 30
            else:
                high = 29

        return (high, low)

    def _lunar_year_days(self, year):
        days = 0
        for i in range(1, 13):
            (high, low) = self._lunar_month_days(year, i)
            days += high
            days += low
        return days

    # 返回指定公历日期的儒略日（http://blog.csdn.net/orbit/article/details/9210413）
    def _julian_day(self):
        ct = self.localtime  # 取当前时间
        year = ct.year
        month = ct.month
        day = ct.day

        if month <= 2:
            month += 12
            year -= 1

        B = year / 100
        B = 2 - B + year / 400

        dd = day + 0.5000115740  # 本日12:00后才是儒略日的开始(过一秒钟)*/
        return int(365.25 * (year + 4716) + 0.01) + int(30.60001 * (month + 1)) + dd + B - 1524.5

    # 返回指定年份的节气的儒略日数（http://blog.csdn.net/orbit/article/details/9210413）
    def _julian_day_of_ln_jie(self, year, st):
        s_stAccInfo = [
            0.00, 1272494.40, 2548020.60, 3830143.80, 5120226.60, 6420865.80,
            7732018.80, 9055272.60, 10388958.00, 11733065.40, 13084292.40, 14441592.00,
            15800560.80, 17159347.20, 18513766.20, 19862002.20, 21201005.40, 22529659.80,
            23846845.20, 25152606.00, 26447687.40, 27733451.40, 29011921.20, 30285477.60]

        # 已知1900年小寒时刻为1月6日02:05:00
        base1900_SlightColdJD = 2415025.5868055555

        if (st < 0) or (st > 24):
            return 0.0

        stJd = 365.24219878 * (year - 1900) + s_stAccInfo[st] / 86400.0

        return base1900_SlightColdJD + stJd
