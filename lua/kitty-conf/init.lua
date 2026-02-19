
local Kind = vim.lsp.protocol.CompletionItemKind
local data = require("kitty-conf.data")

local M = {}

function M.new()
    local self = setmetatable({}, { __index = M })
    self.is_cached = false
    self.option_items = {}
    self.action_items = {}
    self.key_items = {}        -- key modifiers/names for map key combo position
    self.value_map = {}        -- option_name -> list of value completion items
    self.map_flag_items = {}   -- --when-focus-on, --mode, etc.
    self.map_flag_set = {}     -- set of flag names for quick lookup
    self.map_flag_values = {}  -- flag_name -> list of value items
    self:_load()
    return self
end

function M:_load()
    local d = data.load()
    if not d then return end
    local raw = d.raw

    -- Build option completion items
    for _, opt in ipairs(raw.options) do
        table.insert(self.option_items, {
            label = opt.name,
            kind = Kind.Property,
            source = "kitty",
            documentation = { kind = "markdown", value = data.format_doc(opt) },
        })

        -- Build value map: choices + default value
        local seen = {}
        local values = {}
        for _, v in ipairs(opt.choices or {}) do
            seen[v] = true
            local item = { label = v, kind = Kind.EnumMember, source = "kitty" }
            if v == opt.default then
                item.labelDetails = { description = "default" }
                item.documentation = { kind = "markdown", value = "Default value for `" .. opt.name .. "`" }
            end
            table.insert(values, item)
        end
        if opt.default and not seen[opt.default] then
            table.insert(values, {
                label = opt.default, kind = Kind.Value, source = "kitty",
                labelDetails = { description = "default" },
                documentation = { kind = "markdown", value = "Default value for `" .. opt.name .. "`" },
            })
        end
        if #values > 0 then
            self.value_map[opt.name] = values
        end
    end

    -- Multi-options
    for _, opt in ipairs(raw.multi_options) do
        table.insert(self.option_items, {
            label = opt.name,
            kind = Kind.Property,
            source = "kitty",
            documentation = { kind = "markdown", value = data.format_doc(opt) },
        })
    end

    -- Directives (map, mouse_map, include, etc.) — not in iter_all_options()
    for _, dir in ipairs(raw.directives or {}) do
        local item = { label = dir.name, kind = Kind.Keyword, source = "kitty" }
        if dir.doc and dir.doc ~= "" then
            item.documentation = { kind = "markdown", value = dir.doc }
        end
        table.insert(self.option_items, item)
    end

    -- Key modifiers/names for map key combo position
    for _, name in ipairs(raw.key_names or {}) do
        table.insert(self.key_items, {
            label = name,
            kind = Kind.Keyword,
            source = "kitty",
        })
    end

    -- Action completion items
    for _, act in ipairs(raw.actions) do
        table.insert(self.action_items, {
            label = act.name,
            kind = Kind.Function,
            source = "kitty",
            documentation = { kind = "markdown", value = data.format_doc(act) },
        })
    end

    -- Map flags (--when-focus-on, --mode, --new-mode, --on-unknown, --on-action)
    for _, flag in ipairs(raw.map_flags or {}) do
        local item = {
            label = flag.name,
            kind = Kind.Property,
            source = "kitty",
        }
        local doc = data.format_doc(flag)
        if doc ~= "" then
            item.documentation = { kind = "markdown", value = doc }
        end
        table.insert(self.map_flag_items, item)
        self.map_flag_set[flag.name] = true
        if flag.choices then
            local values = {}
            for _, v in ipairs(flag.choices) do
                table.insert(values, { label = v, kind = Kind.EnumMember, source = "kitty" })
            end
            self.map_flag_values[flag.name] = values
        end
    end

    self.is_cached = true
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

    -- map line: skip --flag value pairs, then key combo, then action
    local map_rest = before:match("^%s*map%s+(.*)")
    if map_rest then
        -- Skip --flag value pairs
        local rest = map_rest
        while true do
            local flag, after = rest:match("^(%-%-[%w-]+)%s+(.*)")
            if flag and self.map_flag_set[flag] then
                -- Skip the value after the flag (if present)
                local after_val = after:match("^%S+%s+(.*)")
                if after_val then
                    rest = after_val
                else
                    -- Cursor is at the flag's value position
                    local items = self.map_flag_values[flag]
                    if items then
                        callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = items })
                    else
                        callback(empty)
                    end
                    return function() end
                end
            else
                break
            end
        end
        -- Cursor at a --flag or key combo position
        if rest:match("^%-%-") then
            -- User typed "--": strip prefix from insertText so blink doesn't double it
            local items = {}
            for _, item in ipairs(self.map_flag_items) do
                items[#items + 1] = vim.tbl_extend("force", item, {
                    insertText = item.label:sub(3),  -- strip "--"
                })
            end
            callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = items })
            return function() end
        end
        if not rest:match("%S") then
            -- Nothing typed yet: offer flags (with full --) and key names
            local items = vim.list_extend(vim.list_extend({}, self.map_flag_items), self.key_items)
            callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = items })
            return function() end
        end
        -- Key combo present, cursor at action position
        if rest:match("^%S+%s+") and not rest:match("^%S+%s+%S+%s+") then
            callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = self.action_items })
            return function() end
        end
        -- Past the action — no completions from us
        if rest:match("^%S+%s+%S+%s+") then
            callback(empty)
            return function() end
        end
        -- Just the key combo, no space after yet
        callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = self.key_items })
        return function() end
    end

    -- mouse_map: button event mode [filter] action
    if before:match("^%s*mouse_map%s+%S+%s+%S+%s+%S+%s+") and not before:match("^%s*mouse_map%s+%S+%s+%S+%s+%S+%s+%S+%s+") then
        callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = self.action_items })
        return function() end
    end

    -- Value context: option name followed by space, cursor in value position
    local opt_name = before:match("^%s*(%S+)%s+")
    if opt_name and self.value_map[opt_name] then
        callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = self.value_map[opt_name] })
        return function() end
    end

    -- Default: option names
    callback({ is_incomplete_forward = true, is_incomplete_backward = true, items = self.option_items })
    return function() end
end

return M
