import sys


def main():
    if (sys.version_info < (3, 10)):
        print('[-] GitFive only works with Python 3.10+.')
        print(f"Your current Python version : {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        sys.exit(1)

    from gitfive.lib.cli import parse_args
    from gitfive.lib.utils import show_banner

    show_banner()
    parse_args()