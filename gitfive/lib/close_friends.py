from gitfive.lib.objects import GitfiveRunner, TMPrinter
from gitfive.lib import pea, social

from typing import *


def update_close_friends(username: str, users: Dict[str, Dict[str, any]], reason):
    if username in users:
        users[username]["points"] += 1
        users[username]["reasons"].append(reason)
    else:
        users[username] = {"points": 1, "reasons": [reason]}
    return users

def is_pea(username: str, pea_cache: Dict[str, bool]):
    return pea_cache[username]

async def guess(runner: GitfiveRunner):
    users = {}
    target = {}

    tmprinter = TMPrinter()
    tmprinter.out("Analyzing if target is PEA...")

    pea_cache = await pea.analyze(runner, [runner.target.username])
    tmprinter.clear()

    target["is_pea"] = is_pea(runner.target.username, pea_cache)
    print(f'Account is PEA : {target["is_pea"]}')

    target["following"] = await social.get_follows(runner, "following")

    if not target["is_pea"] and not target["following"]:
        return {} # Popular but 0 following, nothing to analyze

    target["followers"] = await social.get_follows(runner, "followers")

    if target["is_pea"]:
        usernames = target["following"].union(target["followers"])
    else:
        usernames = target["following"]

    new_pea_cache = await pea.analyze(runner, usernames)
    pea_cache = pea_cache | new_pea_cache

    if target["is_pea"]:
        for username in target["followers"]:
            users = update_close_friends(username, users, "Follower is following PEA")
            if is_pea(username, pea_cache):
                users = update_close_friends(username, users, "Follower is PEA")

    for username in target["following"]:
        if is_pea(username, pea_cache):
            users = update_close_friends(username, users, "Following is PEA")
        if username in target["followers"]:
            users = update_close_friends(username, users, "Follower + Following")

    users = {k: v for k, v in sorted(users.items(), key=lambda item: item[1]["points"], reverse=True)} # Sort by points
    return users

def show(runner: GitfiveRunner):
    users = runner.target.potential_friends
    if users:
        runner.rc.print(f"[+] {len(users)} potential close friend{'s' if len(users) > 1 else ''} found !", style="light_green")

        points = sorted(list(set([x["points"] for x in list(users.values())])), reverse=True)
        for point in points :
            to_show = []
            for username in users:
                if users[username]["points"] == point:
                    to_show.append(username)
            print(f"\nClose friend{'s' if len(to_show) > 1 else ''} with {point} point{'s' if point > 1 else ''} :")
            for username in to_show[:14]:
                print(f"- {username} ({', '.join(users[username]['reasons'])})")
            if len(to_show) > 14:
                print("- [...]")
    else:
        print("[-] No potential close friends were found.")

    print("\n* PEA = Pretty Empty Account")