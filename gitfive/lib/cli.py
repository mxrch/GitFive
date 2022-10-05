import argparse
import sys


def parse_args():
    parser = argparse.ArgumentParser('gitfive')
    subparsers = parser.add_subparsers(dest='command')

    login_parser = subparsers.add_parser('login', help='Let GitFive authenticate to GitHub.')
    login_parser.add_argument('--clean', action='store_true', help="Clear credentials and session local files.")

    user_parser = subparsers.add_parser('user', help='Track down a GitHub user by its username.')
    user_parser.add_argument(dest="username",
                            action='store',
                            type=str,
                            help="GitHub's username of the target")
    user_parser.add_argument('--json', type=str, help="File to write the JSON output to")

    email_parser = subparsers.add_parser('email', help='Track down a GitHub user by its email address.')
    email_parser.add_argument(dest="email_address",
                            action='store',
                            type=str,
                            help="GitHub's email address of the target")
    email_parser.add_argument('--json', type=str, help="File to write the JSON output to")

    emails_parser = subparsers.add_parser('emails', help='Find GitHub usernames of a given list of email addresses.')
    emails_parser.add_argument(dest="emails_file",
                                action='store',
                                type=str,
                                help="File containing a list of email adresses")
    emails_parser.add_argument('--json', type=str, help="File to write the JSON output to")
    emails_parser.add_argument('-t', type=str, help="GitHub's username of the target")

    light_parser = subparsers.add_parser('light', help='Quickly find emails addresses from a GitHub username.')
    light_parser.add_argument(dest="username",
                                action='store',
                                type=str,
                                help="GitHub's username of the target")

    args = parser.parse_args(args=None if sys.argv[1:] else ['--help'])

    import trio
    match args.command:
        case "login":
            from gitfive.modules import login_mod
            trio.run(login_mod.check_and_login, args.clean)
        case "user":
            from gitfive.modules import username_mod
            if not args.username:
                exit("[-] Please give a valid username.\nExample : gitfive user mxrch")
            trio.run(username_mod.hunt, args.username, args.json)
        case "email":
            from gitfive.modules import email_mod
            if not args.email_address:
                exit("[-] Please give a valid email address.\nExample : gitfive email <email_address>")
            trio.run(email_mod.hunt, args.email_address, args.json)
        case "emails":
            from gitfive.modules import emails_mod
            if not args.emails_file:
                exit("[-] Please give a valid file.\nExample : gitfive emails ~/Desktop/my_emails_list.txt")
            trio.run(emails_mod.hunt, args.emails_file, args.json, args.t)
        case "light":
            from gitfive.modules import light_mod
            if not args.username:
                exit("[-] Please give a valid username.\nExample : gitfive light mxrch")
            trio.run(light_mod.hunt, args.username)