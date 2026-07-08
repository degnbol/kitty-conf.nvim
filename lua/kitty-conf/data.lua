-- Shared data loading and formatting for kitty-conf.nvim.
-- Used by both the LSP server and the blink.cmp completion source.

local M = {}

local cache

--- Load and cache kitty_options.json.
--- Returns { raw = <decoded JSON>, by_name = <name → entry lookup> }, or nil.
function M.load()
    if cache then return cache end
    local files = vim.api.nvim_get_runtime_file("lua/kitty-conf/kitty_options.json", false)
    if #files == 0 then return nil end
    local fh = io.open(files[1])
    if not fh then return nil end
    local raw = vim.json.decode(fh:read("*a"))
    fh:close()
    local by_name = {}
    for _, opt in ipairs(raw.options) do by_name[opt.name] = opt end
    for _, opt in ipairs(raw.multi_options) do by_name[opt.name] = opt end
    for _, act in ipairs(raw.actions) do by_name[act.name] = act end
    for _, dir in ipairs(raw.directives or {}) do by_name[dir.name] = dir end
    for _, flag in ipairs(raw.map_flags or {}) do by_name[flag.name] = flag end
    cache = { raw = raw, by_name = by_name }
    return cache
end

--- Word at a 0-based (row, col), expanded over `[%w_-]`; non-flag tokens are
--- trimmed back to `[%w_]` so e.g. "key-combo" doesn't match a hyphenated half.
--- @return string|nil
local function word_at(bufnr, row, col)
    local lines = vim.api.nvim_buf_get_lines(bufnr, row, row + 1, false)
    if #lines == 0 then return nil end
    local text = lines[1]
    local s, e = col + 1, col + 1
    while s > 1 and text:sub(s - 1, s - 1):match("[%w_-]") do s = s - 1 end
    while e <= #text and text:sub(e, e):match("[%w_-]") do e = e + 1 end
    if s >= e then return nil end
    local word = text:sub(s, e - 1)
    if not word:match("^%-%-") then
        word = word:match("[%w_]+")
    end
    return word
end

--- Hover markdown for the kitty.conf token at a 0-based (row, col), or nil when
--- there's no recognised option/action/directive/flag there.
--- @return string|nil
function M.hover(bufnr, row, col)
    local d = M.load()
    if not d then return nil end
    local word = word_at(bufnr, row, col)
    local entry = word and d.by_name[word]
    return entry and M.format_doc(entry) or nil
end

--- Format an entry's documentation as markdown.
--- Works for options, actions, directives, and map flags.
function M.format_doc(entry)
    local parts = {}
    if entry.group and entry.group ~= "" then
        table.insert(parts, "**" .. entry.group .. "**")
    end
    if entry.short and entry.short ~= "" then
        table.insert(parts, entry.short)
    end
    if entry.doc and entry.doc ~= "" then
        table.insert(parts, entry.doc)
    end
    if entry.default then
        table.insert(parts, "Default: `" .. entry.default .. "`")
    end
    if entry.choices then
        table.insert(parts, "Values: " .. table.concat(entry.choices, ", "))
    end
    return table.concat(parts, "\n\n")
end

return M
