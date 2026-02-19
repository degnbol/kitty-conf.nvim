-- In-process LSP providing hover for kitty.conf options.
-- No external server — cmd is a Lua function.

local data_cache

local function load_data()
    if data_cache then return data_cache end
    local files = vim.api.nvim_get_runtime_file("lua/kitty-conf/kitty_options.json", false)
    if #files == 0 then return {} end
    local fh = io.open(files[1])
    local raw = vim.json.decode(fh:read("*a"))
    fh:close()
    data_cache = {}
    for _, opt in ipairs(raw.options) do data_cache[opt.name] = opt end
    for _, opt in ipairs(raw.multi_options) do data_cache[opt.name] = opt end
    for _, act in ipairs(raw.actions) do data_cache[act.name] = act end
    for _, dir in ipairs(raw.directives or {}) do data_cache[dir.name] = dir end
    return data_cache
end

local function format_hover(entry)
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

local function get_word_at(bufnr, line, col)
    local lines = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)
    if #lines == 0 then return nil end
    local text = lines[1]
    local s, e = col + 1, col + 1
    while s > 1 and text:sub(s - 1, s - 1):match("[%w_]") do s = s - 1 end
    while e <= #text and text:sub(e, e):match("[%w_]") do e = e + 1 end
    if s >= e then return nil end
    return text:sub(s, e - 1)
end

return {
    cmd = function()
        return {
            request = function(method, params, callback)
                if method == "initialize" then
                    callback(nil, { capabilities = { hoverProvider = true } })
                elseif method == "textDocument/hover" then
                    local data = load_data()
                    local bufnr = vim.uri_to_bufnr(params.textDocument.uri)
                    local word = get_word_at(bufnr, params.position.line, params.position.character)
                    local entry = word and data[word]
                    if entry then
                        callback(nil, {
                            contents = { kind = "markdown", value = format_hover(entry) },
                        })
                    else
                        callback(nil, nil)
                    end
                elseif method == "shutdown" then
                    callback(nil, nil)
                end
            end,
            notify = function() end,
            is_closing = function() return false end,
            terminate = function() end,
        }
    end,
    filetypes = { "kitty" },
}
