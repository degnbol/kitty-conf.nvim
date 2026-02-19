-- In-process LSP providing hover for kitty.conf options.
-- No external server — cmd is a Lua function.

local data = require("kitty-conf.data")

local function get_word_at(bufnr, line, col)
    local lines = vim.api.nvim_buf_get_lines(bufnr, line, line + 1, false)
    if #lines == 0 then return nil end
    local text = lines[1]
    local s, e = col + 1, col + 1
    -- Expand to include word chars and hyphens (for --flag-name tokens)
    while s > 1 and text:sub(s - 1, s - 1):match("[%w_-]") do s = s - 1 end
    while e <= #text and text:sub(e, e):match("[%w_-]") do e = e + 1 end
    if s >= e then return nil end
    local word = text:sub(s, e - 1)
    -- If it doesn't start with -- strip leading hyphens (avoid matching e.g. "key-combo")
    if not word:match("^%-%-") then
        word = word:match("[%w_]+")
    end
    return word
end

return {
    cmd = function()
        return {
            request = function(method, params, callback)
                if method == "initialize" then
                    callback(nil, { capabilities = { hoverProvider = true } })
                elseif method == "textDocument/hover" then
                    local d = data.load()
                    if not d then
                        callback(nil, nil)
                        return
                    end
                    local bufnr = vim.uri_to_bufnr(params.textDocument.uri)
                    local word = get_word_at(bufnr, params.position.line, params.position.character)
                    local entry = word and d.by_name[word]
                    if entry then
                        callback(nil, {
                            contents = { kind = "markdown", value = data.format_doc(entry) },
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
