"""Finding, configuring and loading mesh commands.

Commands are found through the "mesh_contingency.commands" entry point group,
which every installed package can add to (this one registers the built-in
commands the same way), or named directly in the config:

    [commands.wx]
    permission = "public"

    [commands.hello]
    handler = "my_commands:hello"   # module:attr, a Command subclass or function
    permission = "user"
    greeting = "hi"                 # anything else is the command's own option

Only commands with a section and a permission other than "disabled" are
imported, so installing a package never enables or runs anything by itself.
"""

import importlib
import inspect
import re
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from .api import DEFAULT_TIMEOUT, DISABLED, LEVELS, Command, Context, FunctionCommand
from .limits import Limits, parse_rate
from .state import State

ENTRY_POINT_GROUP = "mesh_contingency.commands"
# Keys of a [commands.<name>] section that are for the bot, not the command.
RESERVED_KEYS = {"permission", "handler", "timeout", "rate"}
NAME_RE = re.compile(r"[a-z][a-z0-9_]*")
HANDLER_RE = re.compile(r"[A-Za-z_][\w.]*:[A-Za-z_][\w.]*")


def discover():
    """Return {command name: "module:attr"} for every installed command.

    Exits if two packages offer the same name with different code, since it
    would be unclear which one runs.
    """
    found = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if found.get(ep.name, ep.value) != ep.value:
            raise SystemExit(f"Two installed packages provide the command '{ep.name}': "
                             f"{found[ep.name]} and {ep.value}. Uninstall one, or pick one "
                             f"with handler = in [commands.{ep.name}].")
        found[ep.name] = ep.value
    return found


def resolve(handler):
    """Import "module:attr" and return the Command subclass or function it names."""
    module, _, attr = handler.partition(":")
    obj = importlib.import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part)
    if inspect.isclass(obj):
        if not issubclass(obj, Command):
            raise TypeError(f"{handler} is a class but not a Command subclass")
    elif not callable(obj):
        raise TypeError(f"{handler} is not a Command subclass or function")
    return obj


@dataclass
class CommandSpec:
    """One enabled command, as configured."""

    name: str
    handler: str  # "module:attr"
    permission: str
    timeout: float
    options: dict = field(default_factory=dict)
    rate: tuple | None = None  # (count, seconds) per sender, or None for no limit

# Commands that used to exist, and why they went: a config that still lists
# one gets a warning rather than failing to start.
RETIRED = {
    "rename": "names are now the radios' names, kept up to date by the bot",
}
# Commands that were renamed: an old config's section is used for the new
# name, with a warning, so an upgraded node keeps working.
RENAMED = {"quickim": "qm", "setquickim": "setqm"}


class Registry:
    """The commands the config enables, checked before connecting to the radio."""

    def __init__(self, config, available=None):
        """Check the config's [commands] sections against the installed
        commands (`available`, {name: "module:attr"}; discovered if None) and
        import the enabled ones.

        Exits on a config mistake (unknown command or level, bad handler or
        timeout) so a typo can't silently leave a command open or shut. A
        command whose code fails to import is skipped with a warning.
        """
        if "permissions" in config:
            raise SystemExit("The [permissions] table is replaced by one [commands.<name>] section "
                             "per command, e.g. [commands.wx] permission = \"public\"; "
                             "see config.example.toml.")
        available = discover() if available is None else available
        self.limits = Limits.from_config(config)
        sections = dict(config.get("commands", {}))
        renamed = []  # warnings about old command names
        for old, new in RENAMED.items():
            if old not in sections or old in available:
                continue
            if new in sections:
                renamed.append(f"[commands.{old}] is now [commands.{new}], which is also there; remove "
                               f"[commands.{old}] from the config.")
            else:
                renamed.append(f"{old} is now called {new}; rename [commands.{old}] to [commands.{new}] in the "
                               f"config. Using it for {new} meanwhile.")
                sections[new] = sections[old]
            del sections[old]
        self.specs = {}  # name -> CommandSpec, enabled commands only
        self.disabled = []  # names of commands nobody may run
        self.warnings = []  # problems worth printing at startup
        self.factories = {}  # name -> imported Command subclass or function
        self.warnings += renamed

        for name, section in sections.items():
            if name in RETIRED and name not in available and not (isinstance(section, dict) and "handler" in section):
                self.warnings.append(f"{name} no longer exists ({RETIRED[name]}); remove [commands.{name}] "
                                     f"from the config.")
                continue
            spec = self._check(name, section, available, self.limits)
            if spec is None:
                self.disabled.append(name)
            else:
                self.specs[name] = spec
        for name in available:
            if name not in sections:
                self.disabled.append(name)
                self.warnings.append(f"{name} has no [commands.{name}] section; disabled.")

        for name, spec in list(self.specs.items()):
            try:
                self.factories[name] = resolve(spec.handler)
            except Exception as e:
                del self.specs[name]
                self.warnings.append(f"Could not load {name} ({spec.handler}): {e}; skipped.")

    @staticmethod
    def _check(name, section, available, limits):
        """Return the CommandSpec for a config section, or None if disabled."""
        where = f"[commands.{name}]"
        if not NAME_RE.fullmatch(name):
            raise SystemExit(f"Bad command name '{name}' in [commands]; "
                             "use lowercase letters, digits and _, starting with a letter.")
        if not isinstance(section, dict):
            raise SystemExit(f"{where} must be a table, e.g. {name} = {{ permission = \"public\" }}.")
        permission = section.get("permission")
        if permission not in LEVELS:
            problem = "needs a permission" if permission is None else f"has unknown permission '{permission}'"
            raise SystemExit(f"{where} {problem}; use one of: {', '.join(LEVELS)}.")
        handler = section.get("handler", available.get(name))
        if handler is None:
            raise SystemExit(f"Unknown command '{name}' in [commands]; installed commands are: "
                             f"{', '.join(available) or 'none'}. To use your own code, "
                             f"set handler = \"module:attr\" in {where}.")
        if not isinstance(handler, str) or not HANDLER_RE.fullmatch(handler):
            raise SystemExit(f"{where} handler must look like \"package.module:attr\", not {handler!r}.")
        timeout = section.get("timeout", DEFAULT_TIMEOUT)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise SystemExit(f"{where} timeout must be a positive number of seconds, not {timeout!r}.")
        if permission == DISABLED:
            return None
        rate = parse_rate(section["rate"], where) if "rate" in section else limits.rates[permission]
        options = {k: v for k, v in section.items() if k not in RESERVED_KEYS}
        return CommandSpec(name, handler, permission, timeout, options, rate)

    def build(self, directory, radio, state=None, send=None):
        """Create the enabled commands, sharing one State, and return them as
        {name: Command}. send(public key, text) queues a direct message.

        A command that fails to start is skipped and added to warnings.
        """
        commands = {}
        state = state or State()
        for name, spec in self.specs.items():
            factory = self.factories[name]
            ctx = Context(name=name, options=spec.options, directory=directory, radio=radio, commands=commands,
                          state=state, limits=self.limits, **({"send": send} if send else {}))
            try:
                cmd = factory(ctx) if inspect.isclass(factory) else FunctionCommand(ctx, factory)
            except Exception as e:
                self.warnings.append(f"Could not start {name}: {e}; skipped.")
                continue
            cmd.permission = spec.permission
            cmd.timeout = spec.timeout
            cmd.rate = spec.rate
            commands[name] = cmd
        return commands
