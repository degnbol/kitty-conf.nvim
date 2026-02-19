#!/bin/zsh
# Generate kitty_options.json from kitty's Python internals.
# Requires: kitty
cd "${0:A:h}"
kitty +runpy "import runpy; runpy.run_path('${0:A:h}/generate.py')"
