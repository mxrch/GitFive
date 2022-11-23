from gitfive.lib.objects import GitfiveRunner
from gitfive.lib.utils import is_local_domain, detect_custom_domain, sanatize

import gitfive.config as config

from copy import deepcopy


def generate(runner: GitfiveRunner, custom_domains_list=[], default_domains_list=[], domain_prefixes=[]):
    """
        This function generates all possible email addresses combinations
        using the aggregated target's data.
    """
    fullnames = {x.lower() for x in runner.target.fullnames}
    usernames = {x.lower() for x in runner.target.usernames}
    found_domains = {x.lower() for x in runner.target.domains}

    splitted_names = set()

    custom_domains_list = set(custom_domains_list)
    default_domains_list = set(default_domains_list)
    domains = found_domains.union(default_domains_list).union(custom_domains_list)

    # Using all the previous fetched data about the target
    for _, email_data in runner.target.internal_contribs["all"].items():
        if not is_local_domain(email_data["domain"]):
            extracted_domains = detect_custom_domain(email_data["domain"])
            domains.update(set(extracted_domains))
    for _, email_data in runner.target.internal_contribs["no_github"].items():
        if not (is_local_domain(email_data["domain"]) and email_data["handle"].lower() in config.local_names):
            usernames.add(email_data["handle"].lower())
            usernames.add(email_data["handle"].split("+")[0].lower())
        for name in email_data["names"]:
            if name and not (is_local_domain(email_data["domain"]) and name.lower() in config.local_names):
                if " " in name:
                    fullnames.add(sanatize(name.lower()))
                else:
                    usernames.add(sanatize(name.lower()))

    for _, email_data in runner.target.ext_contribs.items():
        if not (is_local_domain(email_data["domain"]) and email_data["handle"].lower() in config.local_names):
            usernames.add(email_data["handle"].lower())
            usernames.add(email_data["handle"].split("+")[0].lower())
        for name in email_data["names"]:
            if name and not (is_local_domain(email_data["domain"]) and name.lower() in config.local_names):
                if " " in name:
                    fullnames.add(sanatize(name.lower()))
                else:
                    usernames.add(sanatize(name.lower()))

    for name, name_data in runner.target.near_names.items():
        if name:
            if " " in name:
                fullnames.add(sanatize(name.lower()))
            else:
                usernames.add(sanatize(name.lower()))
        for _, email_data in name_data["related_data"].items():
            usernames.add(email_data["handle"].lower())
            usernames.add(email_data["handle"].split("+")[0].lower())
            if not is_local_domain(email_data["domain"]):
                extracted_domains = detect_custom_domain(email_data["domain"])
                domains.update(set(extracted_domains))
            for name2, _ in email_data["names"].items():
                if name2:
                    if " " in name2:
                        fullnames.add(sanatize(name2.lower()))
                    else:
                        usernames.add(sanatize(name2.lower()))

    if fullnames:
        for name in fullnames:
            name_splitted = sanatize(name.lower()).split()
            if len(name_splitted) > 1:
                first_name = name_splitted[0]
                last_name = ''.join(name_splitted[1:])
                splitted_names.add((first_name, last_name))
            else:
                usernames.add(sanatize(name.lower()))

    _usernames = deepcopy(usernames)
    for username in _usernames:
        if "." in username:
            usernames.add(username.replace(".", ""))

    emails = set()
    for domain in domains:
        if not domain.strip():
            continue
        for first_name, last_name in splitted_names:
            if not first_name.strip() and not last_name.strip():
                continue
            for reverse in [False, True]:
                first_pos = last_name if reverse else first_name
                second_pos = first_name if reverse else last_name
                for nb_first in range(0, len(first_name)+1):
                    for nb_second in range(0, len(last_name)+1):
                        total = nb_first + nb_second
                        if not total or (nb_first < 2 and nb_second < 2):
                            continue
                        for dot in ['', '.']:
                            emails.add(f"{first_pos[:nb_first]}{dot}{second_pos[:nb_second]}@{domain}")
                            if not nb_first or not nb_second:
                                break

        for username in usernames:
            if not username.strip():
                continue
            emails.add(f"{username}@{domain}")

    for domain in found_domains:
        if not domain.strip():
            continue
        if domain not in default_domains_list:
            for prefix in domain_prefixes:
                if not prefix.strip():
                    continue
                emails.add(f"{prefix}@{domain}")

    emails = {x for x in emails if x not in runner.spoofed_emails}
    runner.spoofed_emails.update(emails)

    return list(emails)