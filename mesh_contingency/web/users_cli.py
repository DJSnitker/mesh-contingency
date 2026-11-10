"""mesh-contingency-console user: make and change console users on the bot's
own computer (see console_users.py for what's kept).

    mesh-contingency-console user add sam        # asks for the password twice
    mesh-contingency-console user password sam   # a new password
    mesh-contingency-console user remove sam
    mesh-contingency-console user list

Console users have nothing to do with radios or users.toml. This command
is how the first one is made, and the way back in if every console user is
locked out or forgotten: it works whether or not the bot is running.
Passwords are asked twice and not shown.
"""

import getpass
import time

from . import console_users as store


class Stopped(Exception):
    pass


def ask_secret(prompt):
    try:
        return getpass.getpass(prompt)
    except (EOFError, KeyboardInterrupt):
        raise Stopped from None


def ask_password():
    """A new password, typed twice."""
    while True:
        password = ask_secret("New password: ")
        problem = store.check_password(password)
        if problem:
            print(f"Not used: {problem}.")
            continue
        if ask_secret("Again: ") == password:
            return password
        print("They don't match; again.")


def known(users, name):
    if name not in users:
        raise SystemExit(f"No console user called {name}; see mesh-contingency-console user list.")
    return users[name]


def add(path, name):
    problem = store.check_name(name)
    if problem:
        raise SystemExit(f"Not used: {problem}.")
    if name in store.load(path):
        raise SystemExit(f"There is already a console user called {name}.")
    print(f"A console user {name}: a password of {store.PASSWORD_MIN} or more characters.")
    password = ask_password()
    with store.changing(path) as users:
        if name in users:  # made meanwhile
            raise SystemExit(f"There is already a console user called {name}.")
        users[name] = store.new_user(name, password)
    print(f"Added console user {name}. It's kept in {path}.")


def change_password(path, name):
    known(store.load(path), name)
    password = ask_password()
    with store.changing(path) as users:
        store.set_password(known(users, name), password)
    print(f"New password for {name}; they'll need it at their next login.")


def remove(path, name):
    with store.changing(path) as users:
        known(users, name)
        del users[name]
    print(f"Removed console user {name}.")


def day(seconds):
    return time.strftime("%Y-%m-%d", time.localtime(seconds))


def list_users(path):
    users = store.load(path)
    if not users:
        print("No console users yet; add one with: mesh-contingency-console user add NAME")
        return
    for name, user in sorted(users.items()):
        by = "on the node" if user["created_by"] == store.BY_NODE else f"by {user['created_by']}"
        print(f"  {name:<16} made {day(user['created'])} {by}, password set {day(user['changed'])}")


def add_parser(subparsers):
    """The user subcommand's arguments, under subparsers."""
    user = subparsers.add_parser("user", help="make and change console users",
                                 description="Make and change the people who may log in to the web console. "
                                             "They are separate from radio users and admins.")
    actions = user.add_subparsers(dest="action", required=True, metavar="ACTION")
    for action, text in (("add", "a new console user"), ("password", "set a new password"),
                         ("remove", "remove a console user")):
        actions.add_parser(action, help=text).add_argument("name", type=store.normal_name, help=store.NAME_RULE)
    actions.add_parser("list", help="the console users")


def main(args):
    """Run the user subcommand parsed by add_parser."""
    path = store.users_path(args.config)
    try:
        if args.action == "add":
            add(path, args.name)
        elif args.action == "password":
            change_password(path, args.name)
        elif args.action == "remove":
            remove(path, args.name)
        else:
            list_users(path)
    except store.ConsoleUsersError as e:
        raise SystemExit(f"{path}: {e}") from None
    except Stopped:
        raise SystemExit("\nStopped: nothing changed.") from None
