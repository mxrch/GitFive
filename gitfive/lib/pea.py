import trio
from bs4 import BeautifulSoup
from alive_progress import alive_bar

from base64 import b64encode
from urllib.parse import quote_plus
from typing import *

from gitfive.lib.instruments import TrioAliveProgress
from gitfive.lib.objects import GitfiveRunner


# PEA means Pretty Empty Account


async def analyze(runner: GitfiveRunner, usernames: set):
    usernames = [*usernames]
    users = {x:None for x in usernames}

    if len(users) > 1:
        with alive_bar(len(users), receipt=False, enrich_print=False, title="Analyzing following & followers...") as bar:
            instrument = TrioAliveProgress(is_pea, 1, bar)
            trio.lowlevel.add_instrument(instrument)

            async with trio.open_nursery() as nursery:
                for username in users:
                    nursery.start_soon(is_pea, runner, username, users)

            trio.lowlevel.remove_instrument(instrument)

    else:
        if usernames:
            await is_pea(runner, usernames[0], users)

    return users

async def is_pea(runner: GitfiveRunner, username: str, users: Dict[str, bool]):
    if not await has_many_stars_or_repos(runner, username) and \
        not await is_followed_or_following_a_lot(runner, username):
        users[username] = True
    else:
        users[username] = False

async def is_followed_or_following_a_lot(runner: GitfiveRunner, username: str):
    """
    Check if the target has >= 20 followers or is
    following >= 50 people (more risk of follow-back)
    """
    async with runner.limiters["pea_followers"]:
        req = await runner.as_client.get(f"https://github.com/{username}")
        body = BeautifulSoup(req.text, 'html.parser')

        followers_html = body.find("a", href=f"/{username}?tab=followers") or ''
        followers_count = (followers_html and followers_html.text).replace('k', '00').replace('.', '').split(' ')[0].strip('\n')
        followers = int(followers_count) if followers_count else 0

        following_html = body.find("a", href=f"/{username}?tab=following") or ''
        following_count = (following_html and following_html.text).replace('k', '00').replace('.', '').split(' ')[0].strip('\n')
        following = int(following_count) if following_count else 0
        
        if followers >= 20 or following >= 50:
            return True
        return False

async def has_many_stars_or_repos(runner: GitfiveRunner, username: str):
    """
    Return False if 0 public repos or < 2 total stars (apart from the author)
    """
    async with runner.limiters["pea_repos_search"]:
        req = await runner.as_client.get(f"https://github.com/{username}?language=&q=stars:>0&tab=repositories")
        body = BeautifulSoup(req.text, 'html.parser')
        if not body.find("a", itemprop = "name codeRepository"): # If there is no repos with > 0 stars
            return False

        req = await runner.as_client.get(f"https://github.com/{username}?language=&q=stars:>=3&tab=repositories")
        _body = BeautifulSoup(req.text, 'html.parser')
        if _body.find("a", itemprop = "name codeRepository"): # If there is at least one repo with >= 3 stars
            return True

    # 3 stagazers means 2 persons + potentially the author, so we avoid unecessary requests
    # instead of always fetching the stargazers and verify

    # Otherwise, we fallback on fetching all the repos with >0 stars and extract stargazers
    # If there is at least 2 differents stargazers (without the author), return True

    stargazers = await launch_repo_queries(runner, username, body)

    if len(stargazers) >= 2:
        return True
    return False

async def launch_repo_queries(runner: GitfiveRunner, username: str, body: BeautifulSoup):
    async with runner.limiters["pea_repos"]: # x10 tasks max
        repos_page_limiter = trio.CapacityLimiter(5) # spawning x5 task max per child task
        
        total_repos = int(body.find("div", "user-repo-search-results-summary").text.replace('\n', '').replace(',', '').split()[0])
        if not total_repos:
            return False

        to_request = ([0]+list(range(30, total_repos, 30)))[:33]
            # Can't go higher than 960 cursor v1 pagination (so 990 repos)
            # => https://github.community/t/github-cursor-v1-for-repos-pagination-is-broken/160025

        stargazers = set()
        async with trio.open_nursery() as nursery:
            for page in to_request:
                if page == 0:
                    nursery.start_soon(fetch_repos_page, runner, username, page, stargazers, repos_page_limiter, body)
                else:
                    nursery.start_soon(fetch_repos_page, runner, username, page, stargazers, repos_page_limiter)

        return stargazers

async def fetch_repos_page(runner: GitfiveRunner, username: str, page: int, stargazers: Set[str],
                            repos_page_limiter: trio.CapacityLimiter, body: BeautifulSoup=None):
    async with repos_page_limiter: # x5 max 
        if len(stargazers) >= 2:
            return True

        if page > 0:
            page_code = b64encode(f'cursor:{page}'.encode()).decode()
            req = await runner.as_client.get(f"https://github.com/{username}?after={quote_plus(page_code)}&language=&q=stars:>0&tab=repositories")

            body = BeautifulSoup(req.text, 'html.parser')

        repos_list = body.find('div', id='user-repositories-list').find_all('li')

        for repo in repos_list:
            name = repo.find("a", itemprop="name codeRepository").text.strip()
            stars = repo.find("a", href=f"/{username}/{name}/stargazers")
            stars = int(stars.text.strip().replace(',', '')) if stars else 0

            new_stargazers = await extract_first_stargazers(runner, username, name)
            stargazers.update(new_stargazers)

async def extract_first_stargazers(runner: GitfiveRunner, username: str, repo_name: str):
    """
        Extracts the first stargazers page
    """
    req = await runner.as_client.get(f"https://github.com/{username}/{repo_name}/stargazers")
    body = BeautifulSoup(req.text, 'html.parser')

    stargazers_list = body.find_all('li', 'follow-list-item')
    stargazers = {sg for x in stargazers_list if (sg := x.find('h3', 'follow-list-name').text.lower()) != username.lower()}
    return stargazers
