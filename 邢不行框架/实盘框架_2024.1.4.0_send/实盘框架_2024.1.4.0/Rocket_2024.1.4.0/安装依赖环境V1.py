import subprocess
import sys


def install_package(package_name):
    """
    安装依赖环境
    :param package_name:
    :return:
    """

    # 使用清华源安装需要的包
    if '==' in package_name:
        pip_command = f"pip install -i https://pypi.tuna.tsinghua.edu.cn/simple {package_name} "
    else:
        pip_command = f"pip install -i https://pypi.tuna.tsinghua.edu.cn/simple --upgrade {package_name} "

    try:
        subprocess.check_call(pip_command.split())
    except subprocess.CalledProcessError as e:
        print(f"清华源安装{package_name}失败：{e}"
              f"\n尝试从豆瓣源安装")
        try:
            # 使用豆瓣源安装需要的包
            if '==' in package_name:
                pip_command = f"pip install -i https://pypi.douban.com/simple {package_name}"
            else:
                pip_command = f"pip install -i https://pypi.douban.com/simple --upgrade {package_name}"
            subprocess.check_call(pip_command.split())
        except subprocess.CalledProcessError as e:
            print(f"清华源安装{package_name}失败：{e}")
        else:
            print(f"{package_name}已成功安装")
    else:
        print(f"{package_name}已成功安装")


if __name__ == '__main__':
    # 先检查一下版本对不对
    if ('3.8.10' not in sys.version) and ('3.8.16' not in sys.version):
        print(f'python版本要求为3.8.10或者3.8.16'
              f'\n当前版本为：{sys.version}'
              f'\n请将python版本替换成满足要求的版本。')
        exit()

    # 调用函数安装我们需要的库
    install_package('xbx')

    # 也可以使用这个库帮你安装其他的三方包
    # install_package('pandas')  # 安装最新版本的pandas
    # install_package('pandas==1.5.3')  # 安装指定版本的pandas
