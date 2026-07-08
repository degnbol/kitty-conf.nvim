-- In-process LSP providing hover for kitty.conf options. Thin protocol shim;
-- resolution + formatting live in kitty-conf.data.

return require("kitty-conf.lsp").hover_server {
    filetypes = { "kitty" },
    hover = function(bufnr, row, col)
        return require("kitty-conf.data").hover(bufnr, row, col)
    end,
}
