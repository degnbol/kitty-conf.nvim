"""Tests for generate.py pure functions + generated JSON integrity.

Run: python -m pytest test_generate.py
No kitty dependency needed for unit tests — kitty modules are mocked.
JSON integrity tests require a generated kitty_options.json.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock

# Mock kitty modules before importing generate
sys.modules["kitty"] = MagicMock()
sys.modules["kitty.conf"] = MagicMock()
sys.modules["kitty.conf.utils"] = MagicMock(
    include_keys=["include", "globinclude", "envinclude", "geninclude"]
)
sys.modules["kitty.options"] = MagicMock()
sys.modules["kitty.options.definition"] = MagicMock()

from generate import (
    extract_values,
    is_stub_doc,
    none_is_special_value,
    parse_options_spec,
    strip_rst,
)


# --- strip_rst ---

class TestStripRst:
    def test_plain_text_unchanged(self):
        assert strip_rst("hello world") == "hello world"

    def test_empty(self):
        assert strip_rst("") == ""
        assert strip_rst(None) == ""

    def test_role_content(self):
        assert strip_rst(":opt:`font_size`") == "font_size"

    def test_role_tilde_prefix(self):
        assert strip_rst(":ref:`~some.module`") == "some.module"

    def test_code_role(self):
        assert strip_rst(":code:`yes`") == "yes"

    def test_literal_role(self):
        # Angle-bracket stripping runs after :literal: extraction, so <bar> is stripped.
        # This is a known limitation — :literal: with angle brackets loses them.
        assert strip_rst(":literal:`foo <bar>`") == "foo"

    def test_cross_reference_with_target(self):
        assert strip_rst(":doc:`some doc <path/to/doc>`") == "some doc"

    def test_double_backtick_code(self):
        assert strip_rst("use ``vim.cmd``") == "use vim.cmd"

    def test_rst_ref_underscore(self):
        assert strip_rst("see `my reference`_") == "see my reference"

    def test_note_directive(self):
        assert strip_rst(".. note:: be careful") == "Note: be careful"

    def test_versionadded(self):
        assert strip_rst(".. versionadded:: 0.30") == "(added in 0.30)"

    def test_code_block_removed(self):
        assert strip_rst(".. code-block:: python\n  x = 1") == "x = 1"

    def test_substitution_ref(self):
        assert strip_rst("the |kitty| terminal") == "the kitty terminal"

    def test_literal_block_marker(self):
        assert strip_rst("tasks::") == "tasks:"

    def test_angle_bracket_target_stripped(self):
        assert strip_rst("some text <action-copy_to_clipboard>") == "some text"

    def test_url_preserved(self):
        assert strip_rst("see <https://example.com>") == "see <https://example.com>"

    def test_combined_markup(self):
        text = ":opt:`url_style` can be :code:`curly` or :code:`straight`."
        result = strip_rst(text)
        assert "url_style" in result
        assert "curly" in result
        assert "straight" in result
        assert ":opt:" not in result
        assert ":code:" not in result


# --- extract_values ---

class TestExtractValues:
    def test_basic_extraction(self):
        text = "This can be :code:`left`, :code:`center`, or :code:`right`."
        assert extract_values("align", text) == ["left", "center", "right"]

    def test_one_of(self):
        text = "Must be one of :code:`yes`, :code:`no`."
        assert extract_values("opt", text) == ["yes", "no"]

    def test_no_trigger_phrase(self):
        text = "The :code:`value` is used for something."
        assert extract_values("opt", text) == []

    def test_single_value_skipped(self):
        text = "Can be :code:`only_one`."
        assert extract_values("opt", text) == []

    def test_cross_reference_skipped(self):
        # :opt: must be in the same sentence as the trigger phrase to cause a skip
        text = "This can be :code:`curly` or :code:`straight`, see :opt:`url_style`."
        assert extract_values("url_color", text) == []

    def test_same_opt_reference_allowed(self):
        text = "This can be :code:`a` or :code:`b`. See :opt:`myopt`."
        assert extract_values("myopt", text) == ["a", "b"]

    def test_empty_input(self):
        assert extract_values("opt", "") == []
        assert extract_values("opt", None) == []

    def test_first_paragraph_only(self):
        text = "This can be :code:`a` or :code:`b`.\n\nAnother paragraph :code:`c` :code:`d`."
        assert extract_values("opt", text) == ["a", "b"]

    def test_long_values_skipped(self):
        long = "x" * 31
        text = f"Can be :code:`{long}` or :code:`{long}2`."
        assert extract_values("opt", text) == []

    def test_deduplication(self):
        text = "Can be :code:`a`, :code:`b`, or :code:`a`."
        assert extract_values("opt", text) == ["a", "b"]


# --- none_is_special_value ---

class TestNoneIsSpecialValue:
    def test_basic_detection(self):
        text = "Set to :code:`none` to disable."
        assert none_is_special_value("opt", text) is True

    def test_no_none_mention(self):
        text = "Set to :code:`yes` to enable."
        assert none_is_special_value("opt", text) is False

    def test_different_opt_reference(self):
        text = "The :opt:`other_opt` can be :code:`none`."
        assert none_is_special_value("opt", text) is False

    def test_same_opt_reference(self):
        text = "The :opt:`opt` can be :code:`none`."
        assert none_is_special_value("opt", text) is True

    def test_empty_input(self):
        assert none_is_special_value("opt", "") is False
        assert none_is_special_value("opt", None) is False

    def test_multiple_sentences(self):
        text = "First sentence. Set to :code:`none` to disable. Last sentence."
        assert none_is_special_value("opt", text) is True


# --- is_stub_doc ---

class TestIsStubDoc:
    def test_stub(self):
        assert is_stub_doc("See launch for details.") is True

    def test_stub_with_content(self):
        assert is_stub_doc("See launch for details. x") is True  # < 20 chars after

    def test_real_content(self):
        assert is_stub_doc("See launch for details. This is a long explanation of what the action does.") is False

    def test_no_see_prefix(self):
        assert is_stub_doc("This is normal documentation text.") is False

    def test_empty(self):
        assert is_stub_doc("") is False
        assert is_stub_doc(None) is False


# --- parse_options_spec ---

class TestParseOptionsSpec:
    def test_basic_flag(self):
        spec = "--type\ntype=choices\nchoices=window,tab,os_window\nThe type of thing."
        result = parse_options_spec(spec)
        assert len(result) == 1
        flags, desc = result[0]
        assert "--type" in flags
        assert "window" in flags
        assert "tab" in flags

    def test_multiple_flags(self):
        spec = "--title\nThe window title.\n--type\ntype=choices\nchoices=window,tab\nThe type."
        result = parse_options_spec(spec)
        assert len(result) == 2

    def test_flag_with_default(self):
        spec = "--color\ndefault=red\nThe colour to use."
        result = parse_options_spec(spec)
        assert len(result) == 1
        _, desc = result[0]
        assert "default: red" in desc

    def test_list_type(self):
        spec = "--env\ntype=list\nEnvironment variables."
        result = parse_options_spec(spec)
        flags, _ = result[0]
        assert "(repeatable)" in flags

    def test_empty_spec(self):
        assert parse_options_spec("") == []
        assert parse_options_spec(None) == []

    def test_placeholder_skipped(self):
        spec = "#placeholder_for_formatting#\n--title\nThe title."
        result = parse_options_spec(spec)
        assert len(result) == 1

    def test_synonym_flags(self):
        spec = "--cwd --directory\nThe working directory."
        result = parse_options_spec(spec)
        flags, _ = result[0]
        assert "--cwd" in flags
        assert "--directory" in flags


# --- Generated JSON integrity ---

JSON_PATH = Path(__file__).parent / "lua" / "kitty-conf" / "kitty_options.json"


def _load_json():
    if not JSON_PATH.exists():
        return None
    with open(JSON_PATH) as f:
        return json.load(f)


def _find_dupes(names):
    return {k: v for k, v in Counter(names).items() if v > 1}


class TestJsonNoDuplicates:
    """Ensure the generated JSON has no duplicate entries within each category."""

    data = _load_json()

    def test_option_names_unique(self):
        if not self.data:
            return
        names = [o["name"] for o in self.data["options"]]
        dupes = _find_dupes(names)
        assert not dupes, f"Duplicate options: {dupes}"

    def test_multi_option_names_unique(self):
        if not self.data:
            return
        names = [o["name"] for o in self.data["multi_options"]]
        dupes = _find_dupes(names)
        assert not dupes, f"Duplicate multi_options: {dupes}"

    def test_no_overlap_options_multi_options(self):
        if not self.data:
            return
        opt_names = {o["name"] for o in self.data["options"]}
        multi_names = {o["name"] for o in self.data["multi_options"]}
        overlap = opt_names & multi_names
        assert not overlap, f"Name in both options and multi_options: {overlap}"

    def test_no_overlap_options_directives(self):
        if not self.data:
            return
        opt_names = {o["name"] for o in self.data["options"]}
        multi_names = {o["name"] for o in self.data["multi_options"]}
        dir_names = {d["name"] for d in self.data.get("directives", [])}
        overlap = (opt_names | multi_names) & dir_names
        assert not overlap, f"Directive name collides with option: {overlap}"

    def test_action_names_unique(self):
        if not self.data:
            return
        names = [a["name"] for a in self.data["actions"]]
        dupes = _find_dupes(names)
        assert not dupes, f"Duplicate actions: {dupes}"

    def test_option_choices_unique(self):
        if not self.data:
            return
        for opt in self.data["options"]:
            choices = opt.get("choices", [])
            dupes = _find_dupes(choices)
            assert not dupes, f"Duplicate choices for {opt['name']}: {dupes}"

    def test_key_names_unique(self):
        if not self.data:
            return
        dupes = _find_dupes(self.data.get("key_names", []))
        assert not dupes, f"Duplicate key_names: {dupes}"

    def test_map_flag_names_unique(self):
        if not self.data:
            return
        names = [f["name"] for f in self.data.get("map_flags", [])]
        dupes = _find_dupes(names)
        assert not dupes, f"Duplicate map_flags: {dupes}"

    def test_map_flag_choices_unique(self):
        if not self.data:
            return
        for flag in self.data.get("map_flags", []):
            choices = flag.get("choices", [])
            dupes = _find_dupes(choices)
            assert not dupes, f"Duplicate choices for {flag['name']}: {dupes}"
