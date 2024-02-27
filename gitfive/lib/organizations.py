from gitfive.lib.instruments import TrioAliveProgress
from gitfive.lib.utils import *

import trio
from bs4 import BeautifulSoup
from alive_progress import alive_bar

from base64 import b64decode


def show(runner: GitfiveRunner):
    if not runner.target.orgs:
        print("[-] No organizations found.")
        return False

    print(f"[+] {len(runner.target.orgs)} organization{'s' if len(runner.target.orgs) > 1 else ''} found !\n")

    for nb,org in enumerate(runner.target.orgs):
        print(f'Handle : {org["handle"]}')
        if org["name"]:
            print(f'Name : {org["name"]}')
        if org["website"]["link"]:
            print(f'Website : {org["website"]["link"]}{" (Hosted on Github Pages !)" if org["website"]["ghpages_hosted"] else ""}')
        if org["website_on_main_repo"]["link"]:
            print(f'Website on main repo : {org["website_on_main_repo"]["link"]}{" (Hosted on Github Pages !)" if org["website_on_main_repo"]["ghpages_hosted"] else ""}')
        if org["email"]:
            print(f'Email : {org["email"]}')
        print(f'GH Pages : {"Found" if org["github_pages"]["activated"] else "Not found"}')
        if org["github_pages"]["link"]:
            print(f'GH Pages link : {org["github_pages"]["link"]}')
        if org["github_pages"]["cname"]:
            print(f'GH Pages CNAME : {org["github_pages"]["cname"]}')
        if nb != len(runner.target.orgs)-1:
            print()

async def github_pages_check(runner: GitfiveRunner, github_pages: Dict[str, any], req: httpx.Response,
                                body: BeautifulSoup, repo_name: str, org_name: str):
    if req.status_code == 200:
        if repo_name != org_name:
            github_pages["activated"] = True
            github_pages["link"] = repo_name
        if not is_repo_empty(body):
            default_branch_matches = re.findall(r',"defaultBranch":"(.*?)","', req.text)
            default_branch = default_branch_matches[0]
            cname_file = f"https://raw.githubusercontent.com/{org_name}/{repo_name}/{default_branch}/CNAME"
            req = await runner.as_client.get(cname_file)
            if req.status_code == 200:
                if repo_name == org_name:
                    github_pages["activated"] = True
                domain = req.text.strip()
                sanitized_domains = detect_custom_domain(domain)
                if sanitized_domains:
                    github_pages["cname"] = sanitized_domains[-1] # The last domain is the domain with the more subdomains detected
                    if repo_name == org_name:
                        github_pages["link"] = sanitized_domains[-1]
        return github_pages
    return False

async def fetch_org(runner: GitfiveRunner, org_name: str, out: List[Dict[str, any]]):
    async with runner.limiters["orgs_list"]:
        organization = {
            "handle": org_name
        }
        req = await runner.as_client.get(f"https://github.com/{org_name}")
        body = BeautifulSoup(req.text, 'html.parser')
        name = body.find("h1")
        organization["name"] = name.text.strip() if name else ""
        website_link = body.find("a", {"itemprop": "url"})
        website_link = website_link.text.strip() if website_link else ""
        website_domains = detect_custom_domain(website_link)
        organization["website_domains"] = website_domains or []

        website_ghpages_hosted = is_ghpages_hosted(website_domains[-1]) if website_domains else False
        organization["website"] = {"link": website_link, "ghpages_hosted": website_ghpages_hosted}
        
        email = body.find("a", {"itemprop": "email"})
        organization["email"] = email.text.strip() if email else ""

        # Fetch website on org/org repo
        req_1 = await runner.as_client.get(f"https://github.com/{org_name}/{org_name}")
        body_1 = BeautifulSoup(req_1.text, 'html.parser')
        repo_website_link = body_1.find("a", {"role": "link"})
        repo_website_link = repo_website_link.text if repo_website_link else ""

        repo_website_domains = detect_custom_domain(website_link)
        repo_website_ghpages_hosted = is_ghpages_hosted(repo_website_domains[-1]) if repo_website_domains else False

        organization["website_on_main_repo"] = {"link": repo_website_link, "ghpages_hosted": repo_website_ghpages_hosted}

        # Check if the org has a Github Pages
        req_2 = await runner.as_client.get(f"https://github.com/{org_name}/{org_name}.github.io")
        body_2 = BeautifulSoup(req_2.text, 'html.parser')
        
        # We first check the repo org/org, and fallback org.github.io if needed
        gh_pages_default_result = {
            "activated": False,
            "link": "",
            "cname": ""
        }

        gh_pages_result = await github_pages_check(runner, gh_pages_default_result, req_1, body_1, org_name, org_name)
        if not gh_pages_result:
            gh_pages_result = await github_pages_check(runner, gh_pages_default_result, req_2, body_2, f"{org_name}.github.io", org_name)
            if not gh_pages_result:
                gh_pages_result = gh_pages_default_result

        organization["github_pages"] = gh_pages_result

        out.append(organization)

async def scrape(runner: GitfiveRunner):
    out = []
    req = await runner.as_client.get(f"https://github.com/{runner.target.username}")
    body = BeautifulSoup(req.text, 'html.parser')
    orgs = [x.attrs["aria-label"] for x in body.find_all("a", {"class": "avatar-group-item", "data-hovercard-type": "organization"}) if "itemprop" in x.attrs]
    orgs = [x for x in orgs if x]

    with alive_bar(len(orgs), receipt=False, enrich_print=False, title="Fetching organizations...") as bar:
        instrument = TrioAliveProgress(fetch_org, 1, bar)

        trio.lowlevel.add_instrument(instrument)

        async with trio.open_nursery() as nursery:
            for org in orgs:
                nursery.start_soon(fetch_org, runner, org, out)

        trio.lowlevel.remove_instrument(instrument)
    runner.target.orgs = out