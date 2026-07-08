-- Helpers for in-process LSP servers (`cmd` is a Lua function, no external
-- process). See `:h vim.lsp.Config`; usage in lsp/kitty_conf.lua.

local M = {}

--- Build an in-process LSP server config that answers `textDocument/hover`
--- from a Lua callback. Register the returned table as `lsp/<name>.lua` (or via
--- `vim.lsp.config`) and turn it on with `vim.lsp.enable("<name>")`. It joins
--- the standard multi-client hover (`vim.lsp.buf.hover`), so it patches/extends
--- whatever a real language server returns rather than overriding `K`.
---
--- @param opts { filetypes: string[], hover: fun(bufnr: integer, row: integer, col: integer): string|nil }
--- `hover` gets a 0-based row/col (LSP position) and returns markdown to show,
--- or nil to defer to other clients. `filetypes` gates which buffers attach.
--- @return vim.lsp.Config
function M.hover_server(opts)
    --- @type vim.lsp.Config
    local config = {
        cmd = function()
            return {
                request = function(method, params, callback)
                    if method == "initialize" then
                        callback(nil, { capabilities = { hoverProvider = true } })
                    elseif method == "textDocument/hover" then
                        local bufnr = vim.uri_to_bufnr(params.textDocument.uri)
                        local markdown = opts.hover(bufnr, params.position.line, params.position.character)
                        if markdown then
                            callback(nil, { contents = { kind = "markdown", value = markdown } })
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
        filetypes = opts.filetypes,
    }
    return config
end

return M
