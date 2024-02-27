import sys


def main():
    version = sys.version_info
    if (version < (3, 10)):
        print('[-] GitFive only works with Python 3.10+.')
        print(f'Your current Python version : {version.major}.{version.minor}.{version.micro}')
        sys.exit(1)

    from gitfive.lib.cli import parse_args
    from gitfive.lib.utils import show_banner, show_version

    show_banner()
    show_version()
    print()
    parse_args()
