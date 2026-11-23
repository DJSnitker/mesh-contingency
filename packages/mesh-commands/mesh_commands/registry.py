"""Finding, configuring and loading commands.

Commands are found through an entry point group the project names (any
installed package can add to it), or named directly in the config:

    [commands.alert]
    permission = "admin"

    [commands.hello]
    handler = "my_commands:hello"   # module:attr, a Command subclass or function
    permission = "public"
    greeting = "hi"                 # anything else is the command's own option

Only commands with a section and a permission other than "disabled" are
imported, so installing a package never enables or runs anything by itself.
"""

import importlib
import inspect
import re
from dataclasses import dataclass, field
from importlib.metadata import entry_points

from .command import DEFAULT_TIMEOUT, Command, Context, FunctionCommand
from .limits import Limits, parse_rate
from .permissions import DISABLED, LEVELS, NO_ROLES

# Keys of a [commands.<name>] section that are for the dispatcher, not the command.
RESERVED_KEYS = {"permission", "handler", "timeout", "rate"}
NAME_RE = re.compile(r"[a-z][a-z0-9_]*")
HANDLER_RE = re.compile(r"[A-Za-z_][\w.]*:[A-Za-z_][\w.]*")


def discover(group):
    """Return {command name: "module:attr"} for every command installed under
    the entry point group.

    Exits if two packages offer the same name with different code, since it
    would be unclear which one runs.
    """
    found = {}
    for ep in entry_points(group=group):
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


class Registry:
    """The commands the config enables, checked before connecting to the radio."""

    def __init__(self, config, group=None, available=None, limits=None, retired=()):
        """Check the config's [commands] sections against the installed
        commands and import the enabled ones.

        The installed commands are `available` ({name: "module:attr"}), or
        those discovered under the entry point `group`. `limits` is the
        default rate for each level (from the config's [limits] if None).
        `retired` names commands the project used to have: a config that still
        lists them gets one warning instead of an error.

        Exits on a config mistake (unknown command or level, bad handler or
        timeout) so a typo can't silently leave a command open or shut. A
        command whose code fails to import is skipped with a warning.
        """
        if available is None:
            available = discover(group) if group else {}
        self.limits = Limits.from_config(config) if limits is None else limits
        sections = dict(config.get("commands", {}))
        self.specs = {}  # name -> CommandSpec, enabled commands only
        self.disabled = []  # names of commands nobody may run
        self.warnings = []  # problems worth printing at startup
        self.factories = {}  # name -> imported Command subclass or function

        old = [name for name, section in sections.items()
               if name in retired and name not in available and not (isinstance(section, dict)
                                                                     and "handler" in section)]
        if old:
            self.warnings.append(f"[commands] lists commands that no longer exist, ignored: {', '.join(old)}. "
                                 "Remove their entries.")
        for name, section in sections.items():
            if name in old:
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

    def build(self, radio=None, roles=NO_ROLES, send=None, extras=None):
        """Create the enabled commands and return them as {name: Command}.

        Each gets a Context with the radio, the roles (who are users and
        admins), send(public key, text) to queue a direct message, and the
        project's `extras`, one dict shared by all. A command that fails to
        start is skipped and added to warnings.
        """
        commands = {}
        extras = {} if extras is None else extras
        for name, spec in self.specs.items():
            factory = self.factories[name]
            ctx = Context(name=name, options=spec.options, radio=radio, commands=commands, roles=roles,
                          extras=extras, **({"send": send} if send else {}))
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
