import httpx
from git import Repo
from alive_progress import alive_bar

import uuid
from pathlib import Path
import time
from time import sleep
import concurrent.futures
from gitfive.lib.objects import GitfiveRunner

from gitfive.lib.utils import *
from gitfive.lib import github


# メタモン (Metamon)
# EN: Ditto
# N° 132


def do_chunk(repo: Repo, genesis_hash: str, genesis_tree_hash: str, emails_chunk: List[str]):
    """
        Adds commits to a repo.
        Intended to be used inside of a multi-processing task.
    """
    new_indexes = {}
    for email in emails_chunk:
        commit_hash = repo.git.commit_tree(genesis_tree_hash, '-m', f'Impersonating: {email}\r\n\r\nCo-authored-by: target <{email}>', '-p', genesis_hash)

        new_indexes[commit_hash] = email
    
    return len(emails_chunk), new_indexes

def do_chunk_merge(runner: GitfiveRunner, repo: Repo, genesis_tree_hash: str, all_commits: str, total=0):
    """
        Recursively merging commits that haven't a parent.
    """
    if not all_commits:
        runner.tmprinter.clear()
        exit("[-] No commits given to merge.")
    if len(all_commits) == 1:
        runner.tmprinter.clear()
        return all_commits[0]
    remaining_hashes = []
    for hashs_chunk in chunks(all_commits, 200):
        total += len(hashs_chunk)
        runner.tmprinter.out(f"[~] 🐙 Merged {total} commits...")
        args = []
        for hash in hashs_chunk:
            args.append("-p")
            args.append(hash)
        commit_hash = repo.git.commit_tree(genesis_tree_hash, '-m', 'CLOSING', *args)
        remaining_hashes.append(commit_hash)
    return do_chunk_merge(runner, repo, genesis_tree_hash, remaining_hashes, total)

async def start(runner: GitfiveRunner, emails: List[str]):
    temp_repo_name = "GitFive-"+uuid.uuid4().hex[:20]

    # Create
    runner.tmprinter.out("[METAMON] 🐙 Creating repo...")
    await github.create_repo(runner, temp_repo_name)

    cwd_path = Path().home()
    gitfive_folder = cwd_path / ".malfrats/gitfive"
    gitfive_folder.mkdir(parents=True, exist_ok=True)
    
    if not runner.target.username:
        temp_folder = "temp-"+uuid.uuid4().hex[:20]
        target_user_folder: Path = gitfive_folder / ".tmp" / temp_folder
    else:
        target_user_folder: Path = gitfive_folder / ".tmp" / runner.target.username
    fake_folder = (target_user_folder / "fake")
    fake_folder.mkdir(parents=True, exist_ok=True)
    repo_path = fake_folder / temp_repo_name

    repo_url = f"https://{runner.creds.token}:x-oauth-basic@github.com/{runner.creds.username}/{temp_repo_name}"
    repo = Repo.init(repo_path, initial_branch='mirage')
    repo.create_remote('origin', repo_url)

    # To avoid conflits in the commits parsing, we set an unusable "email" for the committer
    # but only in the scope of the repo
    repo.config_writer().set_value("user", "email", "gitfive_lock").release()
    repo.config_writer().set_value("user", "name", "gitfive_hunter").release()

    dummy_file_name = "dummy.txt"
    dummy_file_path = repo_path / dummy_file_name

    # Creating genesis commit
    with open(dummy_file_path, "w", encoding="utf-8") as f:
        f.write("GENESIS")

    genesis_blob_hash = repo.git.hash_object(dummy_file_name, "-w")
    repo.git.update_index("--add", "--cacheinfo", "100644", genesis_blob_hash, dummy_file_name)

    genesis_tree_hash = repo.git.write_tree()
    repo.git.commit('-m', 'GENESIS')
    genesis_hash = repo.active_branch.commit.hexsha

    emails_index = {}

    futures = set()
    part_start = time.time()
    with concurrent.futures.ProcessPoolExecutor() as executor:
        for chunk in chunks(emails, 10):
            future = executor.submit(do_chunk, repo, genesis_hash, genesis_tree_hash, chunk)
            futures.add(future)

        with alive_bar(len(emails), receipt=False, enrich_print=False, title="[METAMON] 🐙 Spoofing commits...") as bar:
            for future in concurrent.futures.as_completed(futures):
                chunk_len, new_indexes = future.result()
                bar(chunk_len)
                emails_index |= new_indexes

    if emails_index:
        runner.tmprinter.out(f"[METAMON] 🐙 Recursive merge...")
        last_commit_hash = do_chunk_merge(runner, repo, genesis_tree_hash, list(emails_index.keys()))

        commit = repo.commit(last_commit_hash)
        repo.head.set_commit(commit)

        total_commits_count = int(repo.git.rev_list('--count', 'HEAD'))

        runner.tmprinter.clear()
        print(f"[METAMON] 🐙 Added commits in {round(time.time() - part_start, 2)}s !\n")

        # Checking if repo is created
        # If error 500, prints short summary. Need to test to determine "HTML response text" and exclude it w/ testing.
        # Also implements a 5s retry-after instead of default 1s by prepending 4s wait.
        while True:
            req = await runner.as_client.get(f"https://github.com/{runner.creds.username}/{temp_repo_name}/settings")
            if req.status_code == 200:
                break
            elif req.status_code == 500:
                print("[METAMON] 🐙 Error 500: retrying after 5s.")
                sleep(4)
            sleep(1)

        runner.tmprinter.out("[METAMON] 🐙 Pushing...")
        repo.git.push('--set-upstream', repo.remote().name, 'mirage')
    else:
        print("[METAMON] 🐙 No email found in commits.\n")

    repo.close()

    if emails_index:
        # Checking if commits have been pushed
        while True:
            found, nb_commits = await get_commits_count(runner, repo_url=f"https://github.com/{runner.creds.username}/{temp_repo_name}")
            if found and nb_commits == total_commits_count:
                break
            sleep(1)

    runner.tmprinter.clear()

    return temp_repo_name, emails_index