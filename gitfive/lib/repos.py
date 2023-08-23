from gitfive.lib.objects import GitfiveRunner
from gitfive.lib.utils import *
from gitfive.lib.instruments import TrioAliveProgress
import trio
from bs4 import BeautifulSoup
from alive_progress import alive_bar

from math import ceil


async def fetch_repos_page(runner: GitfiveRunner, page: int, repos: List[Dict[str, any]], body: BeautifulSoup=None):
    async with runner.limiters["repos_list"]:
        if page > 1:
            req = await runner.as_client.get(f"https://github.com/{runner.target.username}?page={page}&tab=repositories")
            body = BeautifulSoup(req.text, 'html.parser')

        repos_list = body.find('div', id='user-repositories-list').find_all('li')

        for repo in repos_list:
            name = repo.find("a", itemprop="name codeRepository").text.strip()
            main_language = repo.find("span", itemprop="programmingLanguage")
            main_language = main_language.text if main_language else None
            stars = repo.find("a", href=f"/{runner.target.username}/{name}/stargazers")
            stars = int(stars.text.strip().replace(',', '')) if stars else 0
            forks = repo.find("a", href=f"/{runner.target.username}/{name}/network/members")
            forks = int(forks.text.strip().replace(',', '')) if forks else 0

            is_fork = 'fork' in repo.attrs['class']
            is_mirror = 'mirror' in repo.attrs['class']
            is_source = 'source' in repo.attrs['class']
            is_archived = 'archived' in repo.attrs['class']
            is_private = 'public' not in repo.attrs['class'] # Only useful for people using the tool against themselves
            is_empty = is_repo_empty(body)

            details = {
                "name": name,
                "main_language": main_language,
                "stars": stars,
                "forks": forks,
                "is_empty": is_empty,
                "is_fork": is_fork,
                "is_mirror": is_mirror,
                "is_source": is_source,
                "is_archived": is_archived,
                "is_private": is_private,
            }

            repos.append(details)


async def get_list(runner: GitfiveRunner):
    req = await runner.as_client.get(f"https://github.com/{runner.target.username}?tab=repositories")

    body = BeautifulSoup(req.text, 'html.parser')
    total_repos = int(body.find("a", {"data-tab-item": "repositories"}).find("span", {"class": "Counter"}).attrs["title"])

    to_request = range(1, ceil(total_repos/30)+1)

    with alive_bar(total_repos, receipt=False, enrich_print=False, title="Fetching repos...") as bar:
        instrument = TrioAliveProgress(fetch_repos_page, 30, bar)
        trio.lowlevel.add_instrument(instrument)

        repos = []
        async with trio.open_nursery() as nursery:
            for page in to_request:
                if page == 1:
                    nursery.start_soon(fetch_repos_page, runner, page, repos, body)
                else:
                    nursery.start_soon(fetch_repos_page, runner, page, repos)

        trio.lowlevel.remove_instrument(instrument)

    main_languages = [x["main_language"] for x in repos]
    languages_stats = {x:round(main_languages.count(x) / len(main_languages) * 100, 2) for x in main_languages}

    runner.target.repos = repos
    runner.target.languages_stats = dict(sorted(languages_stats.items(), key=lambda item: item[1], reverse=True))

def show(runner: GitfiveRunner):
    if not runner.target.repos:
        print("[-] No repositories found.")
        return False

    source_repos_nb = len([x for x in runner.target.repos if x['is_source']])
    fork_repos_nb = len([x for x in runner.target.repos if x['is_fork']])

    runner.rc.print(f"[+] {len(runner.target.repos)} repositor{'ies' if len(runner.target.repos) > 1 else 'y'} scraped !", style="light_green", end="")
    runner.rc.print(f" ({source_repos_nb} source{'s' if source_repos_nb > 1 else ''}, {fork_repos_nb} fork{'s' if fork_repos_nb > 1 else ''})", style="light_green italic")

    languages_stats = list(runner.target.languages_stats.items())[:4]
    print("\n[+] Languages stats :")
    for language,percentages in languages_stats:
        print(f"- {language} ({percentages}%)")