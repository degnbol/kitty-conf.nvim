# kitty-conf.nvim

Neovim plugin providing completion and hover documentation for `kitty.conf`.
Data is extracted from kitty's own Python internals, so it stays accurate across kitty versions.

[blink.cmp](https://github.com/Saghen/blink.cmp) completion source:
- ~438 option names with descriptions, defaults, and group headings
- Enum values after options that accept specific choices (e.g. `cursor_shape` → `block`, `beam`, `underline`)
- ~85 action names after `map`/`mouse_map` key bindings
- Key modifier/name completion in the key combo position (`ctrl`, `alt`, `shift`, `super`, `f1`–`f12`, etc.)

## Install

With [lazy.nvim](https://github.com/folke/lazy.nvim):

```lua
{
    "degnbol/kitty-conf.nvim",
    ft = "kitty",
}
```

### blink.cmp

Add the source to your blink.cmp config:

```lua
sources = {
    per_filetype = {
        kitty = { "kitty", "snippets", "buffer" },
    },
    providers = {
        kitty = {
            name = "kitty",
            module = "kitty-conf",
        },
    },
},
```

## Regenerating the data

The JSON data file is included, currently generated for kitty version 0.45.0. To regenerate it after a kitty update:
```sh
./generate.sh
```
Requires `kitty` to be installed (uses `kitty +runpy` to access kitty's option definitions).

## How it works

`generate.py` runs inside kitty's Python environment via `kitty +runpy` and extracts option metadata from `kitty.options.definition.definition`:
- `iter_all_options()` for options and multi-options (name, default, choices, docs, group)
- `shortcut_map` for action names and descriptions
- Group tree walking for `map`/`mouse_map` directive descriptions

RST markup is stripped to plain text for clean documentation popups. Enum-like values are extracted from doc text when explicit `choices` aren't available.
