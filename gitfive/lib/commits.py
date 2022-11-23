import trio
from bs4 import BeautifulSoup
from alive_progress import alive_bar


from gitfive.lib.utils import *
from gitfive.lib import github
from gitfive.lib.instruments import TrioAliveProgress


async def fetch_avatar(runner: GitfiveRunner, email: str, avatar_link: str, username: str,
                        out: Dict[str, str|bool], check_only: bool):
    async with runner.limiters["commits_fetch_avatar"]:
        is_target = (username.lower() == runner.target.username.lower())
        if check_only:            
            if is_target:
                runner.rc.print(f"[+] [Target's email] 🐱 {email} -> @{username}", style="cyan")

            out[email] = {
                "avatar": avatar_link,
                "username": username,
                "is_target": is_target
            }
        else:
            full_name = await github.fetch_profile_name(runner, username)
            _name_str = ""
            if full_name:
                _name_str = f" [{full_name}]"

            if is_target:
                runner.rc.print(f"[+] [TARGET FOUND] 🐱 {email} -> @{username}{_name_str}", style="green bold")
            else:
                runner.rc.print(f"[+] 🐱 {email} -> @{username}{_name_str}")

            out[email] = {
                "avatar": avatar_link,
                "full_name": full_name,
                "username": username,
                "is_target": is_target
            }

async def fetch_commits(runner: GitfiveRunner, repo_name: str, emails_index: Dict[str, str],
                        last_hash: str, page: int, out: Dict[str, str|bool], check_only: bool):
    async with runner.limiters["commits_scrape"]:
        if page == 0:
            req = await runner.as_client.get(f"https://github.com/{runner.creds.username}/{repo_name}/commits/mirage")
        else:
            req = await runner.as_client.get(f"https://github.com/{runner.creds.username}/{repo_name}/commits/mirage?after={last_hash}+{page}&branch=mirage")

        if req.status_code == 429:
            exit(f'Rate-limit detected, please adjust the CapacityLimiter.\nCurrent CapacityLimiter : {runner.limiters["commits_scrape"]}')
        body = BeautifulSoup(req.text, 'html.parser')

        commits = body.find_all("li", {"class": "js-commits-list-item"})
        
        async with trio.open_nursery() as nursery:
            for commit in commits:
                hexsha = commit.find("a", {"class": "js-navigation-open"}).attrs["href"].split("/")[-1]
                avatar = commit.find("img", {"class": "avatar-user"})
                if not avatar:
                    continue

                email = emails_index[hexsha]
                avatar_link = avatar.get("src")
                username = avatar.get("alt")[1:] # We remove the "@" at the beginning
                
                nursery.start_soon(fetch_avatar, runner, email, avatar_link, username, out, check_only)

async def scrape(runner: GitfiveRunner, repo_name: str, emails_index: Dict[str, str], check_only=False):
    out = {}
    total = 0
    last_hash_trigger = f"/{runner.creds.username}/{repo_name}/tree/"
    last_hash = ""

    req = await runner.as_client.get(f"https://github.com/{runner.creds.username}/{repo_name}")
    body = BeautifulSoup(req.text, 'html.parser')

    if is_repo_empty(body):
        exit("Empty repository.")

    if last_hash_trigger in req.text:
        _, total = await get_commits_count(runner, raw_body=req.text)
        last_hash = [x for x in body.select('a') if x.text.lower() == "permalink"][0].attrs['href'].split('/')[-1]
    else:
        exit("Couldn't fetch the last hash.")

    to_request = [0]+list(range(-1, total-1, 35))[1:]

    with alive_bar(total, receipt=False, enrich_print=False, title="Fetching committers...") as bar:
        instrument = TrioAliveProgress(fetch_commits, 35, bar)

        trio.lowlevel.add_instrument(instrument)

        async with trio.open_nursery() as nursery:
            for page in to_request:
                nursery.start_soon(fetch_commits, runner, repo_name, emails_index, last_hash, page, out, check_only)

        trio.lowlevel.remove_instrument(instrument)

    return out