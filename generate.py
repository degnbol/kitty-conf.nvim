"""Generate kitty_options.json from kitty's Python internals.

Run via: kitty +runpy (see generate.sh)
Requires: kitty
"""

import json
import re
from pathlib import Path

from kitty.options.definition import definition


def strip_rst(text):
    """Strip RST markup to plain text."""
    if not text:
        return ""
    # :role:`value` -> value
    text = re.sub(r":(?:code|opt|ac|kbd|option|ref|doc|term|envvar|file):`~?([^`]*)`", r"\1", text)
    text = re.sub(r":literal:`([^`]*)`", r"\1", text)
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
    return text.strip()


def extract_values(text):
    """Extract enum-like values from :code: markup in the trigger sentence."""
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
    values = list(dict.fromkeys(re.findall(r":code:`([^`]+)`", trigger.group())))
    if len(values) >= 2 and all(len(v) < 30 for v in values):
        return values
    return []


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
            vals = extract_values(opt.long_text) if opt.long_text else []
            if vals:
                entry["choices"] = vals
        options.append(entry)
    elif typ == "MultiOption":
        entry = {"name": opt.name, "group": group, "doc": doc}
        if opt.items:
            entry["default"] = opt.items[0].defval_as_str
        multi_options.append(entry)

# Actions: unique action names from shortcut_map
actions = []
seen = set()
for name, mappings in definition.shortcut_map.items():
    if name in seen:
        continue
    seen.add(name)
    m = mappings[0]
    actions.append({
        "name": name,
        "short": strip_rst(m.short_text) if m.short_text else "",
        "doc": strip_rst(m.long_text) if m.long_text else "",
    })

actions.sort(key=lambda x: x["name"])

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

data = {"options": options, "multi_options": multi_options, "actions": actions, "directives": directives}

outpath = Path(__file__).parent / "lua" / "kitty-conf" / "kitty_options.json"
with open(outpath, "w") as f:
    json.dump(data, f, indent=2)

print(f"Generated {outpath.name}: {len(options)} options, {len(multi_options)} multi-options, {len(actions)} actions")
