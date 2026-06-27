"""
2024分享会
author: 邢不行
微信: xbx6660
"""
import logging
import Tools.rotation_simulator.Config as Cfg
import dash
from Tools.rotation_simulator.Simulator import Simulator

import socket

def find_available_port(starting_port):
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', starting_port))
            return starting_port
        except socket.error as e:
            if e.errno == socket.errno.EADDRINUSE:
                # Port is already in use, increment and try again
                starting_port += 1
            else:
                raise e  # Re-raise the exception for other socket errors
        finally:
            sock.close()

if __name__ == '__main__':
    print('请点击下面的地址打开模拟器：')
    default_port = 8050
    # 尝试获取可用端口
    app_port = find_available_port(default_port)

    app = dash.Dash(__name__, suppress_callback_exceptions=True)

    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.CRITICAL)
    werkzeug_logger.propagate = False  # 防止日志向上级传播

    root = Simulator(root=app, Cfg=Cfg)
    root.run(port=app_port)