import trio
from bs4 import BeautifulSoup

from gitfive.lib.objects import GitfiveRunner

from typing import *


async def fetch_follow_page(runner: GitfiveRunner, to_scrape: str, page: int, usernames: Set[str], body: BeautifulSoup=None):
    async with runner.limiters["social_follows"]:
        if page > 1:
            req = await runner.as_client.get(f"https://github.com/{runner.target.username}?page={page}&tab={to_scrape}")
            body = BeautifulSoup(req.text, 'html.parser')

        new_usernames = {x.attrs["href"].strip("/") for x in body.find_all("a", {"data-hovercard-type": "user"}) if x.find('span')}
        usernames.update(new_usernames)

async def get_follows(runner: GitfiveRunner, to_scrape: str):
    req = await runner.as_client.get(f"https://github.com/{runner.target.username}?tab={to_scrape}")
    body = BeautifulSoup(req.text, 'html.parser')

    followers = body.find("a", href=f"https://github.com/{runner.target.username}?tab={to_scrape}")
    followers = int(followers.text.replace('k', '00').replace('.', '').split(' ')[0].strip('\n')) if followers else 0
    to_request = [0]+list(range(50, followers, 50))
    pages = [nb+1 for nb in range(len(to_request))]

    usernames = set()
    async with trio.open_nursery() as nursery:
        for page in pages:
            if page == 1:
                nursery.start_soon(fetch_follow_page, runner, to_scrape, page, usernames, body)
            else:
                nursery.start_soon(fetch_follow_page, runner, to_scrape, page, usernames)

    return usernames
