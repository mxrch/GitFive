from gitfive.lib.objects import GitfiveRunner
from gitfive.lib.utils import unicode_patch


async def hunt(target_username: str, target_id: str, runner: GitfiveRunner=None):
    if not runner:
        runner = GitfiveRunner()
        await runner.login()

    data1 = await runner.api.query(f"/search/commits?q=author:{target_username.lower()} -user:{target_username.lower()}&per_page=100&sort=author-date&order=asc")
    if data1.get("message") == "Validation Failed":
        exit(f'\n[-] User "{target_username}" not found.')

    total_count = data1.get("total_count")
    runner.target.nb_ext_contribs = total_count

    results = [data1]
    if total_count > 100:
        data2 = await runner.api.query(f"/search/commits?q=author:{target_username.lower()} -user:{target_username.lower()}&per_page=100&sort=author-date&order=desc")
        results.append(data2)

    if total_count > 200:
        from math import ceil
        middle_page = ceil(ceil(total_count/100)/2)
        data3 = await runner.api.query(f"/search/commits?q=author:{target_username.lower()} -user:{target_username.lower()}&per_page=100&sort=author-date&order=asc&page={middle_page}")
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
                if email.count("+") == 1 and email.startswith(f"{target_id}+"):
                    username: str = email.split("+")[1].split('@')[0]
                    if username.lower() != target_username.lower():
                        username = unicode_patch(username)
                        name = unicode_patch(name)
                        if not username in runner.target.usernames_history:
                            runner.target._add_name(username) # Previous usernames are valid informations (unless target spoof it)
                            runner.target.usernames_history[username] = {"names": {}}
                        if not name in runner.target.usernames_history[username]["names"]:
                            runner.target._add_name(name) # Previous names are valid informations (unless target spoof it)
                            runner.target.usernames_history[username]["names"][name] = {"repos": set()}
                        runner.target.usernames_history[username]["names"][name]["repos"].add(repo_name)