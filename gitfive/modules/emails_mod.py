from gitfive.lib import metamon, commits
from gitfive.lib.objects import GitfiveRunner


async def hunt(emails_file: str, json_file="", target="", runner: GitfiveRunner = None):
    from pathlib import Path
    if not Path(emails_file).is_file():
        exit(f"[-] The specified file {emails_file} can't be found.")

    if json_file and not (parent := Path(json_file).parent).is_dir():
        exit(f"[-] The directory {parent} can't be found.")

    if not runner:
        runner = GitfiveRunner()
        await runner.login()

    with open(emails_file, "r", encoding="utf8") as f:
        emails = [y for x in f.readlines() if (y := x.strip())]

    if target:
        runner.target.username = target

    temp_repo_name, emails_index = await metamon.start(runner, emails)
    emails_accounts = await commits.scrape(runner, temp_repo_name, emails_index)
    if not emails_accounts:
        print("No email linked to a Github account !")

    # Delete
    runner.rc.print("\n[+] Deleted the remote repo", style="italic")
    from gitfive.lib import github
    await github.delete_repo(runner, temp_repo_name)

    if json_file:
        import json
        with open(json_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(emails_accounts, indent=4))
        runner.rc.print(f"[+] JSON output wrote to {json_file} !", style="italic")

    runner.tmprinter.out("Deleting temp folder...")
    from gitfive.lib.utils import delete_tmp_dir; delete_tmp_dir()
    runner.tmprinter.clear()