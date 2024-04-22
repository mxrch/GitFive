from typing import *
import json
import base64
from pathlib import Path
from time import sleep
from datetime import datetime

from rich.console import Console
from rich import print as rprint
import httpx
from bs4 import BeautifulSoup as bs
from pwinput import pwinput
import trio

import gitfive.config as config


class TMPrinter():
    """
        Print temporary text, on the same line.
    """
    def __init__(self, rc: Console=Console()):
        self.max_len = 0
        self.rc = rc

    def out(self, text: str):
        if len(text) > self.max_len:
            self.max_len = len(text)
        else:
            text += (" " * (self.max_len - len(text)))
        self.rc.print(text, end='\r')
    def clear(self):
        self.rc.print(" " * self.max_len, end="\r")

# import logging

# class TwoFactorAuthentication:
#     def __init__(self, client):
#         self.client = client  
#         self.logger = logging.getLogger(__name__)

#     async def fetch_2fa_form(self, url):
#         try:
#             response = await self.client.get(url)
#             response.raise_for_status()
#             return response.text
#         except httpx.HTTPStatusError as e:
#             self.logger.error(f"HTTP error occurred: {e}")
#             raise
#         except httpx.RequestError as e:
#             self.logger.error(f"Request error occurred: {e}")
#             raise

#     def parse_form(self, html_content):
#         soup = bs(html_content, 'html.parser')
#         form = soup.find("form", {"action": "/sessions/two-factor"})
#         if form is None:
#             self.logger.warning("The form with action '/sessions/two-factor' was not found.")
#             raise ValueError("The form with action '/sessions/two-factor' was not found in the HTML content.")

#         authenticity_token_input = form.find("input", {"name": "authenticity_token"})
#         if authenticity_token_input is None:
#             self.logger.warning("Authenticity token input not found.")
#             raise ValueError("The input field with name 'authenticity_token' was not found in the form.")

#         return authenticity_token_input.attrs["value"]

#     async def submit_2fa_code(self, authenticity_token, code):
#         data = {
#             "authenticity_token": authenticity_token,
#             "otp": code  # might need to be changed depending on the form's requirements
#         }
#         try:
#             response = await self.client.post("https://github.com/sessions/two-factor", data=data)
#             response.raise_for_status()
#             if "logged_in" in response.cookies and response.cookies["logged_in"] == "yes":
#                 return True
#             else:
#                 return False
#         except httpx.HTTPStatusError as e:
#             self.logger.error(f"Failed to submit 2FA code, HTTP error: {e}")
#             raise
#         except httpx.RequestError as e:
#             self.logger.error(f"Network error when submitting 2FA code: {e}")
#             raise

class Credentials():
    """
        Manages GitHub authentication.
    """
    def __init__(self):
        cwd_path = Path().home()
        gitfive_folder = cwd_path / ".malfrats/gitfive"
        if not gitfive_folder.is_dir():
            gitfive_folder.mkdir(parents=True, exist_ok=True)
        self.creds_path = gitfive_folder / "creds.m"
        self.session_path = gitfive_folder / "session.m"

        self.username = ""
        self.password = ""
        self.token = ""

        self.session: Dict[str, str] = {}

        self._as_client = httpx.AsyncClient(
            # headers=config.headers, timeout=config.timeout, proxies="http://127.0.0.1:8282", verify=False
            headers=config.headers, timeout=config.timeout

        # self.async_client = async_client
        # self.twofa_handler = TwoFactorAuthentication(self.async_client)
        )
        
    def load_creds(self):
        creds = self.parse(self.creds_path)
        if creds:
            self.username = creds["username"]
            self.password = creds["password"]
            self.token = creds["token"]

        session = self.parse(self.session_path) # Cookies
        if session:
            self.session = session
            self._as_client.cookies.update(self.session)

    def save_creds(self):
        self.save(self.creds_path, {
            "username": self.username,
            "password": self.password,
            "token": self.token
        })

        self.save(self.session_path, self.session)

    def parse(self, path: Path):
        if not path.is_file():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(base64.b64decode(raw).decode())
            return data
        except Exception:
            return None

    def save(self, path, data: Dict[str, str]):
        with open(path, "w", encoding="utf-8") as f:
            f.write(base64.b64encode(json.dumps(data, indent=2).encode()).decode())

    def are_creds_loaded(self) -> bool:
        return all([self.username, self.password, self.token])

    def prompt_creds(self):
        while not self.username:
            self.username = input("Username => ")
        while not self.password:
            self.password = pwinput("🔒 Password => ")
        print('\nThe API token requires the "repo" and "delete_repo" scopes.')
        rprint("[italic]See : https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token")
        while not self.token:
            self.token = pwinput("🔒 API Token => ")
        print()

    def check_token(self):
        print("Checking API token validity...")
        headers = {"Authorization": f"Bearer {self.token}"}
        req = httpx.get("https://api.github.com/user", headers=headers)
        if req.status_code == 401:
            exit("[-] Token seems invalid.")
        if req.status_code != 200:
            exit(f"[-] GitHub API is returning an unexpected status code ({req.status_code}). Is your token correct ?") # Shouldn't happend (🤞)
        data = json.loads(req.text)
        token_owner: str = data["login"]
        if token_owner.lower() != self.username.lower():
            exit(f"[-] Token's owner ({token_owner}) doesn't match logged user ({self.username}). 🫥")
        if (raw_scopes := req.headers.get("x-oauth-scopes")):
            from gitfive.lib.utils import humanize_list
            requirements = {"repo", "delete_repo"}
            scopes = [x.strip() for x in raw_scopes.split(",")]
            required_scopes = set()
            excessive_scopes = set()
            for scope in scopes:
                if scope in requirements:
                    required_scopes.add(scope)
                else:
                    excessive_scopes.add(scope)
            if requirements == required_scopes:
                print(f"[+] Token valid ! (scopes : {humanize_list(required_scopes)})")
            else:
                exit(f"[-] Token does not have sufficient scopes. (current scopes : {humanize_list(scopes)})")

            if excessive_scopes:
                print(f"[!] Your token has excessive scopes (scopes : {humanize_list(excessive_scopes)}).")
                print("These scopes are not needed by GitFive, so be sure to keep it secure, or generate a new one.")
            
            print()

        else:
            exit("[-] Your token seems invalid.")

    async def login(self, force=False):
        """
        To avoid login everytime, we save the cookie
        user_session so we can check it later.
        """
        tmprinter = TMPrinter()

        if not force:
            if self.are_creds_loaded():
                print("[+] Credentials found !\n")
            else:
                print("[-] No saved credentials found\n")
                self.prompt_creds()
        else:
            self.prompt_creds()

        self.check_token()

        req = await self._as_client.get("https://github.com/login")

        body = bs(req.text, 'html.parser')
        authenticity_token = body.find("form", {"action": "/session"}).find("input", {"name": "authenticity_token"}).attrs["value"]

        data = {
            "commit": "Sign+in",
            "authenticity_token": authenticity_token,
            "login": self.username,
            "password": self.password
        }

        req = await self._as_client.post("https://github.com/session", data=data, follow_redirects=False)
        if req.status_code == 302:
            if req.cookies.get("logged_in") == "yes":
                self.session = {
                        "user_session": req.cookies["user_session"],
                        "__Host-user_session_same_site": req.cookies["__Host-user_session_same_site"],
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                self.save_creds()
                print("[+] Logged in !")
                rprint(f"[italic][+] Credentials saved in {self.creds_path}")
                rprint(f"[italic][+] Session saved in {self.session_path}")
            elif req.headers["location"] == "https://github.com/sessions/verified-device":
                print("[*] Additional check")
                self.session = {
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                self.save_creds()   # We need to save the _device_id, otherwise, if user provide wrong OTP code,
                                    # it exits and at next login, Github will say that the credentials are wrong,
                                    # unless we provide the same device_id that initiated 2FA procedure.
                req = await self._as_client.get("https://github.com/sessions/verified-device", follow_redirects=False)
                body = bs(req.text, 'html.parser')
                authenticity_token = body.find("form", {"action": "/sessions/verified-device"}).find("input", {"name": "authenticity_token"}).attrs["value"]
                msg = body.find("div", {"id": "device-verification-prompt"}).text
                rprint(f'[bold]🗨️ Github :[/bold] [italic]"{msg}"')
                otp = pwinput("📱 Code => ")
                data = {
                    "authenticity_token": authenticity_token,
                    "otp": otp
                }
                req = await self._as_client.post("https://github.com/sessions/verified-device", data=data)
                if req.cookies.get("logged_in") == "yes":
                    self.session = {
                        "user_session": req.cookies["user_session"],
                        "__Host-user_session_same_site": req.cookies["__Host-user_session_same_site"],
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                    self.save_creds()
                    print("\n[+] Logged in !")
                    rprint(f"[italic][+] Credentials saved in {self.creds_path}")
                    rprint(f"[italic][+] Session saved in {self.session_path}")
                else:
                    exit("\n[-] Wrong code, please retry.")
            elif req.headers["location"] == "https://github.com/sessions/two-factor/app":
                print("[*] Additional check (TOTP)")
                self.session = {
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                self.save_creds()   # We need to save the _device_id, otherwise, if user provide wrong OTP code,
                                    # it exits and at next login, Github will say that the credentials are wrong,
                                    # unless we provide the same device_id that initiated 2FA procedure.
                req = await self._as_client.get("https://github.com/sessions/two-factor/app", follow_redirects=False)
                body = bs(req.text, 'html.parser')
                form = body.find("form", {"action": "/sessions/two-factor"})
                authenticity_token = form.find("input", {"name": "authenticity_token"}).attrs["value"]
                msg = form.find("div", {"class": "mt-3"}).text
                rprint(f'[bold]🗨️ Github :[/bold] [italic]"{msg}"')
                app_otp = pwinput("📱 Code => ")
                data = {
                    "authenticity_token": authenticity_token,
                    "app_otp": app_otp
                }
                req = await self._as_client.post("https://github.com/sessions/two-factor", data=data)
                if req.cookies.get("logged_in") == "yes":
                    self.session = {
                        "user_session": req.cookies["user_session"],
                        "__Host-user_session_same_site": req.cookies["__Host-user_session_same_site"],
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                    self.save_creds()
                    print("\n[+] Logged in !")
                    rprint(f"[italic][+] Credentials saved in {self.creds_path}")
                    rprint(f"[italic][+] Session saved in {self.session_path}")
                else:
                    exit("\n[-] Wrong code, please retry.")
            elif req.headers["location"].startswith("https://github.com/sessions/two-factor/mobile"):
                print("[*] 2FA detected (Github App)")
                self.session = {
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                self.save_creds()   # We need to save the _device_id, otherwise, if user provide wrong OTP code,
                                    # it exits and at next login, Github will say that the credentials are wrong,
                                    # unless we provide the same device_id that initiated 2FA procedure.
                req = await self._as_client.get("https://github.com/sessions/two-factor/mobile?auto=true", follow_redirects=False)
                if req.status_code == 302:
                    exit("[-] You're temporary limited, please wait a minute. Chill and relax ☕")
                body = bs(req.text, 'html.parser')
                authenticity_token = body.find("form", {"action": "/sessions/two-factor/mobile_poll"}).find("input", {"name": "authenticity_token"}).attrs["value"]
                msg = body.find("p", {"data-target": "sudo-credential-options.githubMobileChallengeMessage"}).text.strip()
                number = body.find("h1", {"data-target": "sudo-credential-options.githubMobileChallengeValue"}).text.strip()
                rprint(f'[bold]🗨️ Github :[/bold] [italic]"{msg}"')
                rprint(f"[bold]🎲 Digits : {number}\n")
                tmprinter.out("Waiting for user confirmation...")

                headers = {**self._as_client.headers, "X-Requested-With": "XMLHttpRequest"}
                data = {"authenticity_token": authenticity_token}

                while True:
                    sleep(2)
                    req = await self._as_client.post("https://github.com/sessions/two-factor/mobile_poll", headers=headers, data=data, follow_redirects=False)
                    res = json.loads(req.text)
                    match res["status"]:
                        case 'STATUS_ACTIVE':
                            pass # Waiting
                        case 'STATUS_EXPIRED' :
                            tmprinter.clear()
                            exit("[-] 2FA expired.")
                        case 'STATUS_NOT_FOUND':
                            tmprinter.clear()
                            exit("[-] Request rejected.")
                        case 'STATUS_APPROVED':
                            break
                tmprinter.clear()
                print("[+] Got confirmation !")

                self.session = {
                    "user_session": req.cookies["user_session"],
                    "__Host-user_session_same_site": req.cookies["__Host-user_session_same_site"],
                    "_device_id": self._as_client.cookies["_device_id"]
                }
                self.save_creds()
                rprint(f"[italic][+] Credentials saved in {self.creds_path}")
                rprint(f"[italic][+] Session saved in {self.session_path}")
            elif req.headers["location"].startswith("https://github.com/sessions/two-factor"):
                print("[*] 2FA")
                self.session = {
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                self.save_creds()   # We need to save the _device_id, otherwise, if user provide wrong OTP code,
                                    # it exits and at next login, Github will say that the credentials are wrong,
                                    # unless we provide the same device_id that initiated 2FA procedure.
                req = await self._as_client.get("https://github.com/sessions/two-factor")
                body = bs(req.text, 'html.parser')

                #authenticity_token = body.find("form", {"action": "/sessions/two-factor"}).find("input", {"name": "authenticity_token"}).attrs["value"]
                
                form = body.find("form", {"action": "/sessions/two-factor"})
                if form is None:
                    # Handle the absence of the expected form in the HTML
                    # This could involve logging an error or raising an exception
                    raise ValueError("The form with action '/sessions/two-factor' was not found in the HTML content.")

                authenticity_token_input = form.find("input", {"name": "authenticity_token"})
                if authenticity_token_input is None:
                    # Handle the absence of the input field within the form
                    # This could involve logging an error or raising an exception
                    raise ValueError("The input field with name 'authenticity_token' was not found in the form.")

                authenticity_token = authenticity_token_input.attrs["value"]
                
                
                msg = body.find("form", {"action": "/sessions/two-factor"}).find("div", {"class": "mt-3"}).text.strip().split("\n")[0]
                rprint(f'[bold]🗨️ Github :[/bold] [italic]"{msg}"')
                otp = pwinput("📱 Code => ")
                data = {
                    "authenticity_token": authenticity_token,
                    "otp": otp
                }
                req = await self._as_client.post("https://github.com/sessions/two-factor", data=data)
                if req.cookies.get("logged_in") == "yes":
                    self.session = {
                        "user_session": req.cookies["user_session"],
                        "__Host-user_session_same_site": req.cookies["__Host-user_session_same_site"],
                        "_device_id": self._as_client.cookies["_device_id"]
                    }
                    self.save_creds()
                    print("\n[+] Logged in !")
                    rprint(f"[italic][+] Credentials saved in {self.creds_path}")
                    rprint(f"[italic][+] Session saved in {self.session_path}")
                else:
                    exit("\n[-] Wrong code, please retry.")
            else:
                exit("[-] Unrecognized security step.\nPlease try login in the browser, or with another account.")
        else:
            exit("[-] Login failed.\nVerify your credentials.")

    async def check_session(self):

        req = await self._as_client.get("https://github.com/settings/profile", follow_redirects=False)
        return req.status_code == 200

    async def check_and_login(self):
        is_session_valid = await self.check_session()
        if not is_session_valid:
            print("[DEBUG] Cookies no more active, I re-login...")
            await self.login()
            print("[DEBUG] Cookies re-generated and valid !")
        else:
            print("[DEBUG] Cookies valid !")

class TargetEncoder(json.JSONEncoder):
    """
        Converts non-default types when exporting to JSON.
    """
    def default(self, o: object) -> dict:
        if isinstance(o, Target):
            return o.__dict__
        elif isinstance(o, set):
            return list(o)
        elif isinstance(o, datetime):
            return f"{o.strftime('%Y/%m/%d %H:%M:%S')} (UTC)"

class Target():
    """
        Manages all the target's data during GitFive's run.
    """
    def __init__(self):
        self.username = ""
        self.name = ""
        self.id = ""
        self.is_site_admin = False
        self.is_hireable = False
        self.company = ""
        self.blog = ""
        self.location = ""
        self.bio = ""
        self.twitter = ""
        self.nb_public_repos = 0
        self.nb_followers = 0
        self.nb_following = 0
        self.created_at: datetime = None
        self.updated_at: datetime = None
        self.avatar_url = ""
        self.is_default_avatar = True
        self.nb_ext_contribs = 0

        self.potential_friends: Dict[str, Dict[str, int|bool]] = {}
        self.repos: List[Dict[str, any]] = []
        self.languages_stats: Dict[str, float] = {}
        self.orgs: List[Dict[str, any]]

        self.usernames = set()
        self.fullnames = set()
        self.domains = set()

        self.ssh_keys: List[str] = []

        self.all_contribs: Dict[str, Dict[str, Dict[str, Dict[str, Set[str]]]]] = {}
        self.ext_contribs: Dict[str, Dict[str, Dict[str, Dict[str, Set[str]]]]] = {}
        self.internal_contribs: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Set[str]]]]]] = {"all": {}, "no_github": {}}
        self.usernames_history: Dict[str, Dict[str, Dict[str, Dict[str, Set[str]]]]] = {}
        self.near_names: Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Dict[str, Set[str]]]]]]] = {}

        self.emails = set()
        self.generated_emails = set()
        self.registered_emails: Dict[str, any] = {}

    def export_json(self):
        return json.dumps(self, cls=TargetEncoder, indent=4)

    @property
    def _possible_names(self) -> Set[str]:
        return {x.lower() for x in self.usernames.union(self.fullnames)}

    def _add_name(self, name: str):
        if name:
            if " " in name:
                self.fullnames.add(name)
            else:
                self.usernames.add(name)

    def _scrape(self, data: Dict[str, any]):
        self.username = data["login"] # We use the username from this field because it can have uppercase letters
        from gitfive.lib.utils import unicode_patch
        self.name = unicode_patch(data["name"]) if data["name"] else ""
        self.id = data["id"]
        self.type = data["type"]
        self.is_site_admin = data["site_admin"]
        self.hireable = data["hireable"]
        self.company = data["company"]
        self.blog = data["blog"]
        self.location = data["location"]
        self.bio = data["bio"]
        self.twitter = data["twitter_username"]
        self.nb_public_repos = data["public_repos"]
        self.nb_followers = data["followers"]
        self.nb_following = data["following"]
        self.created_at = datetime.strptime(data["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        self.updated_at = datetime.strptime(data["updated_at"], "%Y-%m-%dT%H:%M:%SZ")

        # Profile pic
        from gitfive.lib.utils import get_image_hash, fetch_img
        self.avatar_url = data["avatar_url"].split('?')[0]
        avatar = fetch_img(self.avatar_url)
        avatar_hash = get_image_hash(avatar)

        identicon = fetch_img(f'https://github.com/identicons/{self.username}.png')
        identicon_hash = get_image_hash(identicon)

        if avatar_hash != identicon_hash:
            self.is_default_avatar = False

class GitfiveRunner():
    """
        Centralizes common informations and functions needed during GitFive's run.
    """
    def __init__(self):
        from gitfive.lib.api import APIInterface
        self.rc = Console(highlight=False) # To print with colors
        self.tmprinter = TMPrinter(self.rc)
        self.creds = Credentials()
        self.target: Target = Target()
        self.as_client = self.creds._as_client
        self.api: APIInterface = None
        
        self.limiters: Dict[str, trio.CapacityLimiter] = {
            "pea_repos": trio.CapacityLimiter(10),
            "pea_repos_search": trio.CapacityLimiter(10),
            "pea_followers": trio.CapacityLimiter(10),
            "social_follows": trio.CapacityLimiter(50),
            "repos_list": trio.CapacityLimiter(50),
            "commits_scrape": trio.CapacityLimiter(50),
            "commits_fetch_avatar": trio.CapacityLimiter(1), # https://github.com/mxrch/GitFive/issues/3#issuecomment-1321260050
            "orgs_list": trio.CapacityLimiter(50)
        }

        self.xray_near_iteration = 0
        self.emails_accounts: Dict[str, Dict[str, any]] = {}
        self.shown_emails = set()
        self.shown_near_names = set()

        self.spoofed_emails = set()
        self.analyzed_usernames = set()

    async def login(self):
        """
            Interacts with the Credentials class to automatically
            login to GitHub and load API Interface.
        """
        from gitfive.lib.api import APIInterface
        self.creds.load_creds()
        await self.creds.check_and_login()
        self.api = APIInterface(self.creds)
