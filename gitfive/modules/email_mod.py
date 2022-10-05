from gitfive.lib import metamon, commits
from gitfive.lib.objects import GitfiveRunner

from pathlib import Path


async def hunt(email: str, json_file="", runner: GitfiveRunner = None):
    if not runner:
        runner = GitfiveRunner()
        await runner.login()

    if json_file and not (parent := Path(json_file).parent).is_dir():
        exit(f"[-] The directory {parent} can't be found.")

    temp_repo_name, emails_index = await metamon.start(runner, [email])
    emails_accounts = await commits.scrape(runner, temp_repo_name, emails_index)
    if emails_accounts:
        print("[+] Target found !")
        
        from gitfive.modules import username_mod
        username = [*emails_accounts.values()][0]["username"]
        await username_mod.hunt(username, json_file, runner)
    else:
        print("[-] Email isn't linked to a GitHub account.")
        runner.tmprinter.out("Deleting temp folder...")
        from gitfive.lib.utils import delete_tmp_dir; delete_tmp_dir()
        runner.tmprinter.clear()
    
    # Delete
    from gitfive.lib import github
    await github.delete_repo(runner, temp_repo_name)