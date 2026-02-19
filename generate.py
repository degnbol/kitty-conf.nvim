"""Generate kitty_options.json from kitty's Python internals.

Run via: kitty +runpy (see generate.sh)
Requires: kitty
"""

import json
import re
from pathlib import Path

from kitty.conf.utils import include_keys
from kitty.options.definition import definition


def strip_rst(text):
    """Strip RST markup to plain text."""
    if not text:
        return ""
    # :code:`content` and :literal:`content` — keep as-is (may contain literal <angle brackets>)
    text = re.sub(r":(?:code|literal):`([^`]*)`", r"\1", text)
    # :role:`display <target>` — cross-references; keep display text, strip target
    text = re.sub(r":[a-z]+:`([^`]*?)\s*<[^>]+>`", r"\1", text)
    # :role:`value` — inline markup; keep the display text
    text = re.sub(r":[a-z]+:`~?([^`]*)`", r"\1", text)
    # Strip angle-bracket RST targets: "text <target>" -> "text"
    # Handles both inline and line-wrapped cases. Excludes URLs.
    text = re.sub(r"\s*<(?!https?://)(?:[a-z@/][\w. @+=/:-]*)>", "", text)
    # ``code`` -> code
    text = re.sub(r"``([^`]*)``", r"\1", text)
    # `ref`_ -> ref
    text = re.sub(r"`([^`]*)`_", r"\1", text)
    # .. note:: -> Note:
    text = re.sub(r"\.\. note::", "Note:", text)
    text = re.sub(r"\.\. versionadded:: (\S+)", r"(added in \1)", text)
    # .. code-block:: lang -> remove
    text = re.sub(r"\.\. code-block::.*", "", text)
    # |kitty| -> kitty
    text = re.sub(r"\|(\w+)\|", r"\1", text)
    # RST literal block marker "tasks::" -> "tasks:"
    text = re.sub(r"(\w)::", r"\1:", text)
    return text.strip()


def extract_values(opt_name, text):
    """Extract enum-like values from :code: markup in the trigger sentence.

    Skips sentences that reference a different option via :opt:, to avoid
    attributing another option's values to this one (e.g. url_color's doc
    mentions url_style's values).
    """
    if not text:
        return []
    first_para = text.split("\n\n")[0]
    # Find the sentence containing the trigger phrase and extract values from it only
    trigger = re.search(
        r"[^.]*(?:can be|one of|valid values|set to one|allowed values)[^.]*\.",
        first_para,
        re.IGNORECASE,
    )
    if not trigger:
        return []
    # Skip if the sentence describes a different option
    other_opts = re.findall(r":opt:`(\w+)`", trigger.group())
    if any(o != opt_name for o in other_opts):
        return []
    values = list(dict.fromkeys(re.findall(r":code:`([^`]+)`", trigger.group())))
    if len(values) >= 2 and all(len(v) < 30 for v in values):
        return values
    return []


def none_is_special_value(opt_name, raw_doc):
    """Detect if 'none' is a settable value for this option (not another one).

    Looks for :code:`none` in sentences that don't reference a different option
    via :opt:`other_name`.
    """
    if not raw_doc:
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", raw_doc):
        if ":code:`none`" not in sentence:
            continue
        other_opts = re.findall(r":opt:`(\w+)`", sentence)
        if all(o == opt_name for o in other_opts):
            return True
    return False


options = []
multi_options = []

for opt in definition.iter_all_options():
    typ = type(opt).__name__
    doc = strip_rst(opt.long_text) if opt.long_text else ""
    group = opt.group.title if opt.group else ""

    if typ == "Option":
        entry = {"name": opt.name, "default": opt.defval_as_string, "group": group, "doc": doc}
        if opt.choices:
            entry["choices"] = list(opt.choices)
        else:
            vals = extract_values(opt.name, opt.long_text) if opt.long_text else []
            if vals:
                entry["choices"] = vals
        # Infer yes/no choices from default value
        if "choices" not in entry and entry["default"] in ("yes", "no"):
            entry["choices"] = ["yes", "no"]
        # Add 'none' if the parser explicitly accepts it (to_color_or_none),
        # or if the doc text describes it as a settable value for this option
        parser = getattr(opt, "parser_func", None)
        parser_name = getattr(parser, "__name__", "")
        if "none" not in entry.get("choices", []):
            if parser_name == "to_color_or_none" or none_is_special_value(opt.name, opt.long_text or ""):
                entry.setdefault("choices", []).append("none")
        options.append(entry)
    elif typ == "MultiOption":
        entry = {"name": opt.name, "group": group, "doc": doc}
        if opt.items:
            entry["default"] = opt.items[0].defval_as_str
        multi_options.append(entry)

# Actions: merge kitty.actions.get_all_actions() with shortcut_map
try:
    from kitty.actions import get_all_actions
except ImportError:
    get_all_actions = None


def is_stub_doc(text):
    """Check if doc is just a 'See X for details' reference with no real content."""
    if not text:
        return False
    # Strip the "See ... for details" prefix and check if anything substantial remains
    stripped = re.sub(r"^See\b.*?\bfor details\.?\s*", "", text, count=1)
    return len(stripped.strip()) < 20


def parse_options_spec(spec):
    """Parse kitty options_spec format into a list of flag summaries.

    Returns [(flags, description), ...] where flags is e.g. '--type=window|tab|...'
    and description is the first sentence/paragraph.
    """
    if not spec:
        return []
    entries = []
    current_flags = None
    current_meta = {}
    current_desc_lines = []

    def flush():
        if current_flags is None:
            return
        desc = strip_rst("\n".join(current_desc_lines).strip())
        # Take the first paragraph, join into one line
        first_para = desc.split("\n\n")[0].strip() if desc else ""
        first_para = " ".join(first_para.split())
        # Trim to first sentence if it's long
        if len(first_para) > 120:
            m = re.match(r"([^.]+\.)\s", first_para)
            if m:
                first_para = m.group(1)
        flag_str = current_flags
        if current_meta.get("choices"):
            flag_str += "=" + "|".join(current_meta["choices"].split(","))
        elif current_meta.get("type") == "list":
            flag_str += " (repeatable)"
        if current_meta.get("default"):
            first_para += f" (default: {current_meta['default']})"
        entries.append((flag_str, first_para))

    for line in spec.split("\n"):
        if line.strip() == "#placeholder_for_formatting#":
            continue
        if line.startswith("--"):
            flush()
            # Parse flag names, separating synonyms: "--long -s" -> "--long, -s"
            current_flags = ", ".join(line.split())
            current_meta = {}
            current_desc_lines = []
        elif current_flags is not None and re.match(r"^(type|default|choices|completion)=", line.strip()):
            key, _, val = line.strip().partition("=")
            current_meta[key] = val
        elif current_flags is not None:
            current_desc_lines.append(line)
    flush()
    return entries


def format_flags_doc(entries):
    """Format parsed flag entries into readable text."""
    lines = []
    for flags, desc in entries:
        lines.append(f"  {flags}")
        if desc:
            lines.append(f"    {desc}")
    return "\n".join(lines)


def enrich_stub_actions(action_map):
    """Replace stub docs with richer content from kitty internals."""
    # launch: use kitty.launch.options_spec() for flag documentation
    if "launch" in action_map and is_stub_doc(action_map["launch"]["doc"]):
        try:
            from kitty.launch import options_spec
            entries = parse_options_spec(options_spec())
            if entries:
                action_map["launch"]["doc"] = "Flags:\n" + format_flags_doc(entries)
        except Exception:
            pass

    # shortcut_map has richer docs for some actions (e.g. send_text)
    for name, mappings in definition.shortcut_map.items():
        if name in action_map and is_stub_doc(action_map[name]["doc"]):
            m = mappings[0]
            if m.long_text and not is_stub_doc(m.long_text):
                action_map[name]["doc"] = strip_rst(m.long_text)

    # Remote control commands have descriptions for remaining stubs
    try:
        from kitty.rc.base import command_for_name
    except ImportError:
        command_for_name = None
    rc_name_map = {
        "disable_ligatures_in": "disable_ligatures",
        "start_resizing_window": "resize_window",
    }
    if command_for_name is not None:
        for name, entry in action_map.items():
            if not is_stub_doc(entry["doc"]):
                continue
            rc_name = rc_name_map.get(name, name)
            try:
                cmd = command_for_name(rc_name)
                entry["doc"] = strip_rst(cmd.desc)
            except Exception:
                pass

    # Strip "See X" references — useless in hover (not a link).
    see_re = r"\.?\s*See\s+.+$"
    for entry in action_map.values():
        # Trailing "See X" / "See X." in short
        entry["short"] = re.sub(see_re, "", entry["short"]).strip()
        # Leading "See X for details" in doc — keep any content after the prefix
        if entry["doc"] and re.match(r"^See\b", entry["doc"]):
            entry["doc"] = re.sub(r"^See\b.*?\bfor details\.?\s*", "", entry["doc"], count=1).strip()


action_map = {}

# Primary source: get_all_actions() (has launch, combine, kitten, etc.)
if get_all_actions is not None:
    for group_actions in get_all_actions().values():
        for a in group_actions:
            action_map[a.name] = {
                "name": a.name,
                "short": strip_rst(a.short_help) if a.short_help else "",
                "doc": strip_rst(a.long_help) if a.long_help else "",
            }

# Supplement from shortcut_map (has aliases like clear_screen, decrease_font_size)
for name, mappings in definition.shortcut_map.items():
    if name not in action_map:
        m = mappings[0]
        action_map[name] = {
            "name": name,
            "short": strip_rst(m.short_text) if m.short_text else "",
            "doc": strip_rst(m.long_text) if m.long_text else "",
        }

enrich_stub_actions(action_map)
actions = sorted(action_map.values(), key=lambda x: x["name"])

# Directives: map and mouse_map (not in iter_all_options, doc from group start_text)
directives = []
for group in definition.root_group.items:
    if hasattr(group, "name") and group.name == "shortcuts" and group.start_text:
        directives.append({"name": "map", "doc": strip_rst(group.start_text)})
        break
# mouse_map: find its group description by walking the group tree
def find_group(group, target_name):
    if hasattr(group, "name") and group.name == target_name:
        return group
    if hasattr(group, "items"):
        for child in group.items:
            found = find_group(child, target_name)
            if found:
                return found
    return None

mm_group = find_group(definition.root_group, "mouse.mousemap")
if mm_group and mm_group.start_text:
    directives.append({"name": "mouse_map", "doc": strip_rst(mm_group.start_text)})

# Include directives (config parser syntax, no docs available via definition)
for key in include_keys:
    directives.append({"name": key})

# Map flags: --when-focus-on, --mode, --new-mode, --on-unknown, --on-action
map_flags = []
try:
    import dataclasses
    from kitty.options.utils import KeyMapOptions
    for field in dataclasses.fields(KeyMapOptions):
        flag_name = "--" + field.name.replace("_", "-")
        entry = {"name": flag_name}
        # Extract choices from Literal types
        origin = getattr(field.type, "__origin__", None)
        if origin is not None:
            # LiteralField[Literal['beep', 'end', ...]] -> dig out the Literal args
            for arg in getattr(field.type, "__args__", ()):
                literals = getattr(arg, "__args__", None)
                if literals:
                    entry["choices"] = list(literals)
                    break
        if field.default != "":
            entry["default"] = field.default
        map_flags.append(entry)
except Exception:
    pass

# Key modifiers and names for map key combo completions
key_names = [
    "ctrl", "alt", "shift", "super", "cmd", "opt", "kitty_mod",
    "left", "right", "up", "down", "home", "end",
    "page_up", "page_down", "insert", "delete", "backspace",
    "enter", "return", "escape", "tab", "space",
    "f1", "f2", "f3", "f4", "f5", "f6",
    "f7", "f8", "f9", "f10", "f11", "f12",
]

data = {"options": options, "multi_options": multi_options, "actions": actions, "directives": directives, "map_flags": map_flags, "key_names": key_names}

outpath = Path(__file__).parent / "lua" / "kitty-conf" / "kitty_options.json"
with open(outpath, "w") as f:
    json.dump(data, f, indent=2)

print(f"Generated {outpath.name}: {len(options)} options, {len(multi_options)} multi-options, {len(actions)} actions")
