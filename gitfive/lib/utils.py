import httpx
import Levenshtein
from bs4 import BeautifulSoup
from rich import print as rprint
from rich.console import Console
import imagehash
from PIL import Image
from unidecode import unidecode

import os
import re
import stat
import socket
from pathlib import Path
from dateutil.relativedelta import *
from typing import *
from io import BytesIO
import string
from packaging.version import parse as parse_version
import json

import gitfive.config as config
from gitfive.lib.objects import GitfiveRunner
from gitfive.lib.banner import banner
from gitfive import version as current_version


def is_local_domain(domain: str):
    return not "." in domain or any([domain.endswith(f".{tld}") for tld in config.local_tlds])

def get_image_hash(img: Image):
    """Return the hash of the pixels of an image"""
    hash = str(imagehash.average_hash(img))
    return hash

def fetch_img(url: str):
    """Download an image and return a PIL's Image object."""
    req = httpx.get(url)
    img = Image.open(BytesIO(req.content))
    return img

def extract_domain(url: str, sub_level: int=0):
    if url.startswith('http'):
        return '.'.join(url.split('/')[2].split('.')[-(sub_level+2):])
    return '.'.join(url.split('/')[0].split('.')[-(sub_level+2):])

def detect_custom_domain(link: str):
    link = link.strip('/')
    domains = []
    if "." in link and (link.count('/') >= 2 or '/' not in link):
        nb_of_dots = link.count('.')
        if nb_of_dots > 3: # Avoiding domains with too much subdomains,
                           # so we only extract longest and shortest domain
            domains.append(extract_domain(link, 0))
            domains.append(extract_domain(link, nb_of_dots-1))
        else:
            for sub_level in range(nb_of_dots):
                domain = extract_domain(link, sub_level)
                if not domain.startswith("www.") and not domain.endswith("github.io"):
                    domains.append(domain)
    return domains

def is_diff_low(string1: str, string2: str, limit: int=40):
    """Calculate difference pourcentage between
    two strings with Levenshtein algorithm"""

    diff = Levenshtein.distance(string1, string2)
    first_len = len(string1)
    pourcentage = int(diff/first_len*100)

    if pourcentage <= limit:
        return True
    return False

def is_repo_empty(body: BeautifulSoup):
    if body.h3 and any(['this repository is empty' in x.text.lower() for x in body.find_all("h3")]):
        return True
    return False

def get_link_location(domain: str):
    """If the HTTP redirects to HTTPS, it returns the HTTPS link"""
    http_link = f"http://{domain}"
    https_link = f"https://{domain}"
    req = httpx.head(http_link) # We use HEAD method to optimize speed and not fetching the body
    final_url = req.url.__str__()
    if final_url.startswith((http_link, https_link)):
        return final_url
    else:
        return http_link

def is_ghpages_hosted(domain: str):
    try:
        ip = socket.gethostbyname(domain)
    except Exception:
        return False
    else:
        if ip in config.ghpages_servers:
            return True
        return False

def change_permissions(path: Path|str):
    for root, dirs, files in os.walk(path):  
        for dir in dirs:
            os.chmod(Path(root) / Path(dir), stat.S_IRWXU)
        for file in files:
            os.chmod(Path(root) / Path(file), stat.S_IRWXU)

def show_banner():
    rprint(banner)

async def get_commits_count(runner: GitfiveRunner, repo_url: str="", raw_body: str=""):
    if not raw_body:
        req = await runner.as_client.get(repo_url)
        raw_body = req.text
    # Slightly modified this line to find the correct <span> containing the commit count
    matches = re.findall(r'"commitCount":"(.*?)"', raw_body)
    if not matches:
        return False, 0
    nb_commits_str = matches[0].replace(",", "")

    if nb_commits_str == "∞":
        return True, 50000 # Temporary limit, because GitHub hasn't liked my 70k commits
    nb_commits = int(nb_commits_str)
    return True, nb_commits

def chunks(lst: List[any], n: int):
    """
        Yield successive n-sized chunks from list.
    """
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def humanize_list(array: List[any]):
    """
        Transforms a list to a human sentence.
        Ex : ["reader", "writer", "owner"] -> "reader, writer and owner".
    """
    if len(array) <= 1:
        return ''.join(array)

    final = ""
    for nb, item in enumerate(array):
        if nb == 0:
            final += f"{item}"
        elif nb+1 < len(array):
            final += f", {item}"
        else:
            final += f" and {item}"
    return final

def sanatize(text: str) -> str:
    deaccented = ""
    try:
        deaccented = unidecode(text, "utf-8")
    except Exception:
        pre_sanatize = ''.join([*filter(lambda x:x.isalpha() or x in "-. ", text)]) # kudos to @n1nj4sec
        deaccented = unidecode(pre_sanatize, "utf-8")
    return ''.join([*filter(lambda x:x.lower() in string.ascii_lowercase+" ", deaccented)])

def get_gists_stats(runner: GitfiveRunner):
    req = httpx.get(f"https://gist.github.com/{runner.target.username}/starred")
    body = BeautifulSoup(req.text, 'html.parser')
    stats = [int(x.text) for x in body.select('span.Counter')]
    return {"gists": stats[0], "starred": stats[1]}

async def get_ssh_keys(runner: GitfiveRunner):
    req = await runner.as_client.get(f"https://github.com/{runner.target.username}.keys")
    lines = req.text.strip()
    if lines:
        runner.target.ssh_keys.extend(lines.split("\n"))

def delete_tmp_dir():
    from shutil import rmtree
    cwd_path = Path().home()
    gitfive_folder = cwd_path / ".malfrats/gitfive"
    gitfive_folder.mkdir(parents=True, exist_ok=True)
    
    target_user_folder: Path = gitfive_folder / ".tmp"

    change_permissions(target_user_folder)
    rmtree(target_user_folder)

def unicode_patch(txt: str):
    bad_chars = {
        "é": "e",
        "è": "e",
        "ç": "c",
        "à": "a"
    }
    return txt.replace(''.join([*bad_chars.keys()]), ''.join([*bad_chars.values()]))

def safe_print(txt: str):
    """
        Escape the bad characters to avoid ANSI injections.
        Also works for Rich printers.
    """
    return txt.encode("unicode_escape").decode().replace('[', '\\[')

def show_version():
    new_version, new_metadata = check_new_version()
    co = Console(highlight=False)
    co.print(f"> GitFive {current_version.metadata.get('version', '')} ({current_version.metadata.get('name', '')}) <".center(62), style="bold")
    print()
    if new_version:
        co.print(f"🥳 New version {new_metadata.get('version', '')} ({new_metadata.get('name', '')}) is available !", style="bold red")
        co.print(f"🤗 Run 'pipx upgrade gitfive' to update.", style="bold light_pink3")
    else:
        co.print("🎉 You are up to date !", style="light_pink3")


def check_new_version() -> tuple[bool, dict[str, str]]:
    """
        Checks if there is a new version of GitFive available.
    """
    req = httpx.get("https://raw.githubusercontent.com/mxrch/GitFive/master/gitfive/version.py")
    if req.status_code != 200:
        return False, {}

    raw = req.text.strip().removeprefix("metadata = ")
    data = json.loads(raw)
    new_version = data.get("version", "")
    new_name = data.get("name", "")

    if parse_version(new_version) > parse_version(current_version.metadata.get("version", "")):
        return True, {"version": new_version, "name": new_name}
    return False, {}