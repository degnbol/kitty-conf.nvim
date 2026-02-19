
local async = require "blink.cmp.lib.async"
local Kind = vim.lsp.protocol.CompletionItemKind

local M = {}

function M.new()
    local self = setmetatable({}, { __index = M })
    self.is_cached = false
    self.option_items = {}
    self.action_items = {}
    self.key_items = {}    -- key modifiers/names for map key combo position
    self.value_map = {}    -- option_name -> list of value completion items
    self:_load_async()
    return self
end

function M:_load()
    local files = vim.api.nvim_get_runtime_file("lua/kitty-conf/kitty_options.json", false)
    if #files == 0 then
        print("kitty_options.json not found")
        return
    end
    local fh = io.open(files[1])
    local data = vim.json.decode(fh:read("*a"))
    fh:close()

    -- Build option completion items
    for _, opt in ipairs(data.options) do
        local doc_parts = {}
        if opt.group ~= "" then table.insert(doc_parts, "**" .. opt.group .. "**") end
        if opt.doc ~= "" then table.insert(doc_parts, opt.doc) end
        if opt.default then table.insert(doc_parts, "Default: `" .. opt.default .. "`") end
        if opt.choices then
            table.insert(doc_parts, "Values: " .. table.concat(opt.choices, ", "))
        end

        table.insert(self.option_items, {
            label = opt.name,
            insertText = opt.name,
            kind = Kind.Property,
            source = "kitty",
            documentation = { kind = "markdown", value = table.concat(doc_parts, "\n\n") },
        })

        -- Build value map for options with known values
        if opt.choices and #opt.choices > 0 then
            local values = {}
            for _, v in ipairs(opt.choices) do
                table.insert(values, {
                    label = v,
                    kind = Kind.EnumMember,
                    source = "kitty",
                })
            end
            self.value_map[opt.name] = values
        end
    end

    -- Multi-options
    for _, opt in ipairs(data.multi_options) do
        local doc_parts = {}
        if opt.group ~= "" then table.insert(doc_parts, "**" .. opt.group .. "**") end
        if opt.doc ~= "" then table.insert(doc_parts, opt.doc) end
        if opt.default then table.insert(doc_parts, "Default: `" .. opt.default .. "`") end

        table.insert(self.option_items, {
            label = opt.name,
            insertText = opt.name,
            kind = Kind.Property,
            source = "kitty",
            documentation = { kind = "markdown", value = table.concat(doc_parts, "\n\n") },
        })
    end

    -- Directives (map, mouse_map) — not in iter_all_options()
    for _, dir in ipairs(data.directives or {}) do
        table.insert(self.option_items, {
            label = dir.name,
            kind = Kind.Keyword,
            source = "kitty",
            documentation = { kind = "markdown", value = dir.doc },
        })
    end

    -- Key modifiers/names for map key combo position
    local key_names = {
        "ctrl", "alt", "shift", "super", "cmd", "opt", "kitty_mod",
        "left", "right", "up", "down", "home", "end",
        "page_up", "page_down", "insert", "delete", "backspace",
        "enter", "return", "escape", "tab", "space",
        "f1", "f2", "f3", "f4", "f5", "f6",
        "f7", "f8", "f9", "f10", "f11", "f12",
    }
    for _, name in ipairs(key_names) do
        table.insert(self.key_items, {
            label = name,
            kind = Kind.Keyword,
            source = "kitty",
        })
    end

    -- Action completion items
    for _, act in ipairs(data.actions) do
        local doc_parts = {}
        if act.short ~= "" then table.insert(doc_parts, act.short) end
        if act.doc ~= "" then table.insert(doc_parts, act.doc) end

        table.insert(self.action_items, {
            label = act.name,
            kind = Kind.Function,
            source = "kitty",
            documentation = { kind = "markdown", value = table.concat(doc_parts, "\n\n") },
        })
    end

    self.is_cached = true
end

function M:_load_async()
    async.task.new(function(resolve)
        resolve(self:_load())
    end)
end

local empty = { is_incomplete_forward = true, is_incomplete_backward = true, items = {} }

function M:get_completions(_, callback)
    if not self.is_cached then
        callback(empty)
        return function() end
    end

    local line = vim.api.nvim_get_current_line()
    local col = vim.api.nvim_win_get_cursor(0)[2]
    local before = line:sub(1, col)

    -- Comments
    if before:match("^%s*#") then
        callback(empty)
        return function() end
    end

    -- Key combo context: after map/mouse_map, typing the key combination
    if before:match("^%s*map%s+") and not before:match("^%s*map%s+%S+%s+") then
        callback({ is_incomplete_forward = false, is_incomplete_backward = false, items = self.key_items })
        return function() end
    end

    -- map/mouse_map context: complete action names
    if before:match("^%s*map%s+%S+%s+") or before:match("^%s*mouse_map%s+%S+%s+%S+%s+%S+%s+") then
        callback({ is_incomplete_forward = false, is_incomplete_backward = false, items = self.action_items })
        return function() end
    end

    -- Value context: option name followed by space, cursor in value position
    local opt_name = before:match("^%s*(%S+)%s+")
    if opt_name and self.value_map[opt_name] then
        callback({ is_incomplete_forward = false, is_incomplete_backward = false, items = self.value_map[opt_name] })
        return function() end
    end

    -- Default: option names
    callback({ is_incomplete_forward = false, is_incomplete_backward = false, items = self.option_items })
    return function() end
end

return M
