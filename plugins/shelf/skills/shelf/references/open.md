# open — open the library UI

Thin wrapper around `shelf open`. Triggered by "open my shelf", "show me the
shelf UI", "browse my library".

## Drive pattern

- **Enhanced mode (default):** `shelf open` starts a lightweight local server and
  opens the browser to `http://localhost:<port>`. This mode adds **copy
  contents** and inline HTML rendering (the page can fetch document files over
  HTTP).
- **Core mode:** `shelf open --static` opens the generated `index.html` directly
  over `file://` — search, browse, and **copy absolute path** work with no
  server, but copy-contents is disabled (browsers block `file://` fetches).

Pick enhanced unless the user specifically wants the no-server file. Report the
URL (or file path) it opened.

Run `shelf open --help` for the authoritative flags.
