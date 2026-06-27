import subprocess


def install_package(package_name):
    """
    安装依赖环境
    :param package_name:
    :return:
    """
    # 使用清华源安装需要的包
    pip_command = f"pip install -i https://pypi.tuna.tsinghua.edu.cn/simple {package_name}"

    try:
        subprocess.check_call(pip_command.split())
    except subprocess.CalledProcessError as e:
        print(f"安装{package_name}失败：{e}")
    else:
        print(f"{package_name}已成功安装")


# 调用函数安装我们需要的库
install_package('xbx')
