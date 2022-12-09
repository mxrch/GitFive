from gitfive.lib.objects import Credentials


async def check_and_login(clean=False):
    creds = Credentials()
    if clean:
        if creds.creds_path.is_file():
            creds.creds_path.unlink()
            print(f"[+] Credentials file at {creds.creds_path} deleted !")
        else:
            print(f"Credentials file at {creds.creds_path} doesn't exist, no need to delete.")

        if creds.session_path.is_file():
            creds.session_path.unlink()
            print(f"[+] Session file at {creds.session_path} deleted !")
        else:
            print(f"Session file at {creds.session_path} doesn't exist, no need to delete.")
        exit()

    creds.load_creds()
    is_session_valid = await creds.check_session()
    if is_session_valid:
        print("[+] Creds are working !")
        choice = ""
        while choice.lower() not in ["y", "n"]:
            choice = input("Do you want to re-login anyway ? (Y/n) : ")
            if not choice: # default choice
                choice = "y"
        if choice == "y":
            print()
            creds.__init__()
            await creds.login(force=True)
        else:
            exit("\nBye !")
    else:
        print("[-] Creds aren't active anymore. Relogin...")
        await creds.login()
