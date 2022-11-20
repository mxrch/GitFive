from git import Repo
import git
from alive_progress import alive_bar

from typing import *
from pathlib import Path
import concurrent.futures
import re

from gitfive.lib.utils import unicode_patch, is_diff_low, is_local_domain
from gitfive.lib.objects import GitfiveRunner
from gitfive.lib import metamon
from gitfive.lib import commits
from gitfive.lib import github


def get_repo(token: str, target_username: str, target_id: int, repos_folder: Path, repo_details: Dict[str, any]):
    """
        Clones and analyzes a git repository.
        Intended to be used in a multi-processing task.
    """
    results = {
        "repo": repo_details["name"],
        "all_contribs": {},
        "internal_contribs" : {},
        "usernames_history": {}
    }

    repo_id = f'{target_username}/{repo_details["name"]}'
    repo_url = f'https://{token}:x-oauth-basic@github.com/{repo_id}'
    repo_path = repos_folder / repo_details["name"]
    results["repo_path"] = repo_path
    try:
        repo = Repo.clone_from(repo_url, repo_path, multi_options=["--filter=tree:0", "--no-checkout"])
    except git.exc.GitCommandError as e:
        error = e
        if error.status == 128:
            # If a file/folder name is weird, and your OS is Windows, it will produce "invalid path" error.
            # See more => https://confluence.atlassian.com/bitbucketserverkb/error-invalid-path-during-git-clone-to-windows-client-1085186345.html
            # You can disable this by doing `git config --global core.protectNTFS false`, but
            # it will make you vulnerable to CVE-2019-1353.

            # Repo example to git clone : https://github.com/novitae/Aet-s-Tools

            pass # In fact, it fails to checkout but commits are cloned, so we don't care. 💅

        repo = Repo(repo_path)

    if not repo.refs:
        # Empty repo, no branch
        return results

    ### Iterating commits
    external_commits_sha = set()
    for commit in repo.iter_commits():
        committer = commit.committer
        author = commit.author
        for entity in [committer, author]:
            # Getting all emails
            if not entity.email in results["all_contribs"]:
                results["all_contribs"][entity.email] = {
                                                        "names": {},
                                                        "handle": entity.email.split("@")[0],
                                                        "domain": entity.email.split("@")[-1]
                                                      }
            if not entity.name in results["all_contribs"][entity.email]["names"]:
                results["all_contribs"][entity.email]["names"][entity.name] = {"repos": set()}
            results["all_contribs"][entity.email]["names"][entity.name]["repos"].add(repo_id)

            # Getting usernames & names history
            if entity.email.endswith("@users.noreply.github.com"):
                if entity.email.count("+") == 1 and entity.email.startswith(f"{target_id}+"):
                    username = entity.email.split("+")[1].split('@')[0]
                    # if username.lower() != target_username.lower(): # => https://github.com/mxrch/GitFive/issues/16
                    if not username in results["usernames_history"]:
                        results["usernames_history"][username] = {"names": {}}
                    if not entity.name in results["usernames_history"][username]["names"]:
                        name = unicode_patch(entity.name)
                        results["usernames_history"][username]["names"][name] = {"repos": set()}
                    results["usernames_history"][username]["names"][name]["repos"].add(repo_id)

        # Getting internal contributors and UPNs
        if len(commit.parents) > 1:
            merged_commits_sha = re.findall(r'\S{40}', repo.git.log(f"{commit.hexsha}^..{commit.hexsha}"))[1:]
            for sha in merged_commits_sha:
                external_commits_sha.add(sha)
        if commit.hexsha not in external_commits_sha:
            for entity in [committer, author]:
                if entity.email != "noreply@github.com" and not entity.email.endswith("@users.noreply.github.com"):
                    if entity.email not in results["internal_contribs"]:
                        results["internal_contribs"][entity.email] = {
                                                        "names": {},
                                                        "handle": entity.email.split("@")[0],
                                                        "domain": entity.email.split("@")[-1]
                                                      }
                    if not entity.name in results["internal_contribs"][entity.email]["names"]:
                        results["internal_contribs"][entity.email]["names"][entity.name] = {"repos": set()}
                    results["internal_contribs"][entity.email]["names"][entity.name]["repos"].add(repo_id)

    repo.close()

    return results

def near_lookup(runner: GitfiveRunner):
    """
        Search for possible names variations.
    """
    runner.xray_near_iteration += 1

    new_variations = False
    print(f"\n[XRAY] 🥷 Near names iteration n°{runner.xray_near_iteration}")
    print(f"[XRAY] 🥷 Using names {runner.target._possible_names}\n")
    for email, email_data in runner.target.all_contribs.items():
        if email == "noreply@github.com" or email.endswith("@users.noreply.github.com"):
            continue
        if email not in runner.target.all_contribs:
            runner.target.all_contribs[email] = email_data
        for name in email_data["names"]:
            handle = email_data["handle"]
            if any([is_diff_low(x, handle) for x in runner.target._possible_names]):
                if handle not in runner.target.near_names:
                    new_variations = True
                    runner.target.near_names[handle] = {"related_data": {}}
                runner.target.near_names[handle]["related_data"][email] = email_data
            if any([is_diff_low(x, name) for x in runner.target._possible_names]):
                if name not in runner.target.near_names:
                    new_variations = True
                    runner.target.near_names[name] = {"related_data": {}}
                runner.target.near_names[name]["related_data"][email] = email_data

    return new_variations

def near_show(runner: GitfiveRunner):
    """
        Shows the results of the near names analysis.
    """
    found_exact = False
    found_variation = False
    for step in ["exact", "variations"]:
        for name, name_data in runner.target.near_names.items():
            entity_fingerprint = name.lower()+'@'.join(name_data["related_data"].keys())
            # We do a fingerprint of the identity rather than just checking the name,
            # Otherwise we wouldn't print different person's identities if they have the same name.

            if entity_fingerprint in runner.shown_near_names:
                continue
            if step == "exact":
                found_exact = True
                if name.lower() not in runner.target._possible_names:
                    continue
                print(f"[+] Target's {'user' if not ' ' in name else ''}name exact match => 🙍 {name}")
            elif step == "variations":
                found_variation = True
                if name.lower() in runner.target._possible_names:
                    continue
                print(f"[+] Possible {'user' if not ' ' in name else ''}name variation => 🙍 {name}")

            runner.shown_near_names.add(entity_fingerprint)

            print(f"Related email{'s' if len(name_data['related_data']) > 1 else ''} tied to this name :")
            already_shown = False
            for email, email_data in name_data["related_data"].items():
                _checks_str = ""
                if email in runner.emails_accounts:
                    gh_username = runner.emails_accounts[email]['username']
                    _is_target = gh_username == runner.target.username
                    _checks_str += f" [{'italic light_green' if _is_target else 'bold indian_red'}](🐱 Github Account -> @{gh_username})"
                if is_local_domain(email.split("@")[-1]):
                    _checks_str += f" [bold violet](💻 Local identity)"
                runner.rc.print(f"  📮 {email}{_checks_str}")
                if email in runner.shown_emails:
                    runner.rc.print("    [Already shown]\n", style="bright_black")
                    already_shown = True
                    continue
                already_shown = False
                runner.shown_emails.add(email)
                print(f"  Name{'s' if len(email_data['names']) > 1 else ''} tied to this email :")
                for name2, name_data2 in email_data["names"].items():
                    print(f"    🙍 {name2} (found in {len(name_data2['repos'])} repo{'s' if len(name_data2['repos']) > 1 else ''})")
                
                if not (already_shown and email == list(name_data["related_data"].keys())[-1]):
                    print()

        if step == "exact" and not found_exact:
            print("[-] No match found for the name.\n")
        elif step == "variations" and not found_variation:
            print("[-] No possible name variation found.\n")

async def analyze(runner: GitfiveRunner):
    cwd_path = Path().home()
    gitfive_folder = cwd_path / ".malfrats/gitfive"
    gitfive_folder.mkdir(parents=True, exist_ok=True)
    
    target_user_folder: Path = gitfive_folder / ".tmp" / runner.target.username
    repos_folder = target_user_folder / "repos"
    repos_folder.mkdir(parents=True, exist_ok=True)

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = []
        total = 0
        for repo_details in runner.target.repos:
            if repo_details["is_source"]:
                total += 1
                # The object Runner cannot be given to a process, because concurrent.futures tries to pickle args, and throws this error :
                # TypeError: cannot pickle '_thread.RLock' object (Because of the Console from rich.console in runner.rc using an RLock)
                # So we give the token, username and id args individually
                future = executor.submit(get_repo, runner.creds.token, runner.target.username, runner.target.id, repos_folder, repo_details)
                futures.append(future)
        
        with alive_bar(total, receipt=False, dual_line=True, enrich_print=False, title="[XRAY] 🥷 Dumping and analyzing repos...") as bar:
            for future in concurrent.futures.as_completed(futures):
                results = future.result()
                bar()
                repo_name = results["repo"]
                #runner.tmprinter.out(f"[XRAY] 🃏 Finished {repo_name} ({nb}/{total})")
                bar.text = f"-> 🪅 Finished {repo_name}..."
                # Merging results
                for username, username_data in results["usernames_history"].items():
                    runner.target._add_name(username) # Previous usernames are valid informations (unless target spoof it)
                    if username not in runner.target.usernames_history:
                        username = unicode_patch(username)
                        runner.target.usernames_history[username] = username_data
                    for name, name_data in username_data["names"].items():
                        runner.target._add_name(name) # Previous names are valid informations (unless target spoof it)
                        if name not in runner.target.usernames_history[username]["names"]:
                            runner.target.usernames_history[username]["names"][name] = name_data
                        runner.target.usernames_history[username]["names"][name]["repos"].update(name_data["repos"])

                for email, email_data in results["all_contribs"].items():
                    if email not in runner.target.all_contribs:
                        runner.target.all_contribs[email] = email_data
                    for name, name_data in email_data["names"].items():
                        if name not in runner.target.all_contribs[email]["names"]:
                            runner.target.all_contribs[email]["names"][name] = name_data
                        runner.target.all_contribs[email]["names"][name]["repos"].update(name_data["repos"])

                for email, email_data in results["internal_contribs"].items():
                    if email not in runner.target.internal_contribs["all"]:
                        runner.target.internal_contribs["all"][email] = email_data

                    for name, name_data in email_data["names"].items():
                        if name not in runner.target.internal_contribs["all"][email]["names"]:
                            runner.target.internal_contribs["all"][email]["names"][name] = name_data
                        runner.target.internal_contribs["all"][email]["names"][name]["repos"].update(name_data["repos"])

    print("[XRAY] 🎭 Impersonating users got in dumped commits...")
    emails_candidates = [x for x in runner.target.all_contribs.keys() if x != "noreply@github.com" and not x.endswith("@users.noreply.github.com")]
    temp_repo_name, emails_index = await metamon.start(runner, emails_candidates)
    if emails_index:
        # Commits scrape
        runner.emails_accounts = await commits.scrape(runner, temp_repo_name, emails_index, check_only=True)
    # Delete
    runner.rc.print("[+] Deleted the remote repo", style="italic")
    await github.delete_repo(runner, temp_repo_name)

    # Filter internal contributors by those having a github account and aren't tied to the target
    no_github_accounts = runner.target.internal_contribs["all"]
    for email, results in runner.emails_accounts.items():
        if email in runner.target.internal_contribs["all"]:
            del no_github_accounts[email]

        if results["is_target"]:
            runner.target._add_name(email.split("@")[0])
            runner.target._add_name(email.split("@")[0].split("+")[0])

    runner.target.internal_contribs["no_github"] = no_github_accounts
    runner.analyzed_usernames = runner.target._possible_names

    near_lookup(runner)
    near_show(runner)

    # Show usernames history
    for username, username_data in runner.target.usernames_history.items():
        if (username.lower() == runner.target.username.lower() and len(username_data["names"]) < 1) or \
            (username.lower() == runner.target.username.lower() and len(username_data["names"]) == 1 and \
            [*username_data["names"].keys()][0].lower() == runner.target.name.lower()):
            continue # Skipping showing default values
        if username.lower() == runner.target.username.lower():
            print(f"[~] Current username -> 🙍 {username}")
        else:
            print(f"[+] Previous username -> 🙍 {username}")
        print(f"Names history tied to this username :")
        for name, name_data in username_data["names"].items():
            print(f"  🙍 {name} (found in {len(name_data['repos'])} repo{'s' if len(name_data['repos']) > 1 else ''})")
        print()
    if not runner.target.usernames_history:
        print("[-] No previous usernames / names found.\n")

    # Show internal contributors
    for email, email_data in runner.target.internal_contribs["no_github"].items():
        _checks_str = ""
        if is_local_domain(email.split("@")[-1]):
            _checks_str += f" [bold violet](💻 Local identity)"
        runner.rc.print(f"[+] Internal contributor email -> 📮 {email}{_checks_str}")
        if email in runner.shown_emails:
            runner.rc.print("    [Already shown]\n", style="bright_black")
            continue
        runner.shown_emails.add(email)
        print(f"Name{'s' if len(email_data['names']) > 1 else ''} tied to this email :")
        for name, name_data in email_data["names"].items():
            print(f"  🙍 {name} (found in {len(name_data['repos'])} repo{'s' if len(name_data['repos']) > 1 else ''})")
        print()
    if not runner.target.internal_contribs:
        print("[-] No internal contributor identity found.\n")

async def analyze_ext_contribs(runner: GitfiveRunner):
    """
        Fetch external commits (outside target's repositories) and
        analyze these commits, to get emails and usernames / names history.
    """
    data1 = await runner.api.query(f"/search/commits?q=author:{runner.target.username.lower()} -user:{runner.target.username.lower()}&per_page=100&sort=author-date&order=asc")
    #if data1.get("message") == "Validation Failed":
    #    exit(f'\n[-] User "{runner.target.username}" not found.')

    total_count = data1.get("total_count")
    runner.target.nb_ext_contribs = total_count

    results = [data1]
    if total_count > 100:
        data2 = await runner.api.query(f"/search/commits?q=author:{runner.target.username.lower()} -user:{runner.target.username.lower()}&per_page=100&sort=author-date&order=desc")
        results.append(data2)

    if total_count > 200:
        from math import ceil
        middle_page = ceil(ceil(total_count/100)/2)
        data3 = await runner.api.query(f"/search/commits?q=author:{runner.target.username.lower()} -user:{runner.target.username.lower()}&per_page=100&sort=author-date&order=asc&page={middle_page}")
        results.append(data3)

    for data in results:
        for item in data.get("items"):
            email: str = item.get("commit", {}).get("author", {}).get("email")
            if email == "noreply@github.com": # Should never happen
                continue
            name: str = item.get("commit", {}).get("author", {}).get("name")
            repo_name: str = item.get("repository", {}).get("full_name", {})

            if not email in runner.target.ext_contribs:
                runner.target.ext_contribs[email] = {"names": {}}
            if not name in runner.target.ext_contribs[email]["names"]:
                runner.target.ext_contribs[email]["names"][name] = {"repos": set()}
            runner.target.ext_contribs[email]["names"][name]["repos"].add(repo_name)

            # Getting usernames history
            if email.endswith("@users.noreply.github.com"):
                if email.count("+") == 1 and email.startswith(f"{runner.target.id}+"):
                    username: str = email.split("+")[1].split('@')[0]
                    # if username.lower() != target_username.lower(): # => https://github.com/mxrch/GitFive/issues/16
                    username = unicode_patch(username)
                    name = unicode_patch(name)
                    if not username in runner.target.usernames_history:
                        runner.target._add_name(username) # Previous usernames are valid informations (unless target spoof it)
                        runner.target.usernames_history[username] = {"names": {}}
                    if not name in runner.target.usernames_history[username]["names"]:
                        runner.target._add_name(name) # Previous names are valid informations (unless target spoof it)
                        runner.target.usernames_history[username]["names"][name] = {"repos": set()}
                    runner.target.usernames_history[username]["names"][name]["repos"].add(repo_name)