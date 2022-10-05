from gitfive.lib.objects import GitfiveRunner


async def hunt(username: str, runner: GitfiveRunner=None):
    if not runner:
        runner = GitfiveRunner()
        await runner.login()

    data1 = await runner.api.query(f"/search/commits?q=author:{username.lower()}&per_page=100&sort=author-date&order=asc")
    if data1.get("message") == "Validation Failed":
        exit(f'\n[-] User "{username}" not found.')

    results = [data1]
    if data1.get("total_count") > 100:
        data2 = await runner.api.query(f"/search/commits?q=author:{username.lower()}&per_page=100&sort=author-date&order=desc")
        results.append(data2)

    emails = set()
    for data in results:
        for item in data.get("items"):
            email = item.get("commit", {}).get("author", {}).get("email")
            if email and email != "noreply@github.com" and not email.endswith("@users.noreply.github.com"):
                emails.add(email)

    if not emails:
        exit(f"\n[-] No email found for {username}.\nYou should try full search !")
    print(f'\nEmail{"s" if len(emails) > 1 else ""} found for user "{username}" :')
    for email in emails:
        print(f"- {email}")