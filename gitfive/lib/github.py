from bs4 import BeautifulSoup

import re
import gitfive.config

from gitfive.lib.objects import GitfiveRunner


async def create_repo(runner: GitfiveRunner, repo_name: str):
    # Slightly modified the form_data so that they will be sent as multipart/form-data
    form_data = {
        "template_repository_id": (None, b"", None),
        "owner": (None, runner.creds.username.encode(), None),
        "include_all_branches": (None, b"0", None),
        "repository[name]": (None, repo_name.encode(), None),
        "repository[description]": (None, b"", None),
        "repository[visibility]": (None, b"private", None),
        "repository[auto_init]": (None, b"0", None),
        "repository[gitignore_template]": (None, b"", None),
        "repository[license_template]": (None, b"", None)
    }

    # Adding some headers that are now required to create a repository
    updated_headers = gitfive.config.headers
    updated_headers["Github-Verified-Fetch"] = "true"
    updated_headers["Origin"] = "https://github.com"

    # Sending the form data as "files" to produce a multipart/form-data POST request
    req = await runner.as_client.post("https://github.com/repositories", files=form_data, headers=updated_headers)
    if req.status_code in [200, 302]:
        return True
    exit(f'Couldn\'t create repo "{repo_name}".\nResponse code : {req.status_code}\nResponse text : {req.text}')


async def delete_repo(runner: GitfiveRunner, repo_name: str):
    req = await runner.as_client.get(f"https://github.com/{runner.creds.username}/{repo_name}/settings")

    body = BeautifulSoup(req.text, 'html.parser')
    form = body.find('form', action=f'/{runner.creds.username}/{repo_name}/settings/delete')
    if not form:
        exit(f'Couldn\'t find the form to delete the repo "{repo_name}".')

    authenticity_token = [x for x in form.find_all('input') if "name" in x.attrs and x.attrs["name"] == "authenticity_token"][0].attrs["value"]
    form_data = {
        "_method": "delete",
        "authenticity_token": authenticity_token,
        "repository": repo_name,
        "sudo_referrer": f"https://github.com/{runner.creds.username}/{repo_name}/settings",
        "user_id": runner.creds.username,
        "verify": f"{runner.creds.username}/{repo_name}",
        "sudo_password": runner.creds.password
    }

    req = await runner.as_client.post(f"https://github.com/{runner.creds.username}/{repo_name}/settings/delete", data=form_data)
    if req.status_code in [200, 302]:
        return True

    exit(f'Couldn\'t delete repo "{repo_name}".\nResponse code : {req.status_code}\nResponse text : {req.text}')

async def fetch_profile_name(runner: GitfiveRunner, username: str):
    """
    Uses the Github hovercards to quickly fetch the name of an username.
    """

    headers = {"X-Requested-With": "XMLHttpRequest", **runner.as_client.headers}
    req = await runner.as_client.get(f"https://github.com/users/{username}/hovercard", headers=headers)
    body = BeautifulSoup(req.text, 'html.parser')

    fields = [x.text.strip() for x in body.find("section", {"aria-label": "user login and name"}).find_all("a")]
    if len(fields) < 2:
        return False

    return fields[1]

async def get_original_branch_from_commit(runner: GitfiveRunner, commit: str, username: str, repo_name: str):
    req = await runner.as_client.get(f"https://github.com/{username}/{repo_name}/branch_commits/{commit}")
    body = BeautifulSoup(req.text, 'html.parser')
    branch = body.find("li", "branch").text.strip()
    if branch:
        return branch
    exit(f"[-] Error : branch not found for this repo and commit : {username}/{repo_name} - {commit}")

async def get_commits_history_from_blob(runner: GitfiveRunner, blob_url: str):
    res = re.compile(r"github\.com\/(.*?)\/(.*?)\/blob\/(.{40})\/(.*?)$").findall(blob_url)
    if not res:
        exit(f"[-] Error : cannot get the details from this blob_url : {blob_url}")

    username, repo_name, commit, filename = res[0]
    branch = await get_original_branch_from_commit(runner, commit, username, repo_name)
    # Keeping this function to get CNAME commits history, in the future
