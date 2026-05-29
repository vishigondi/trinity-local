// Trinity Local — per-harness paste-in snippet generator (#166, Phase A).
//
// Replaces "go run install-mcp in the right CLI" with: pick your harness,
// copy the exact MCP config block, paste it where it says. Solves the
// acquisition friction for non-coder + multi-harness users — they don't
// need to know which CLI they're in, just which app they use.
//
// PURE module: depends only on `document` + `navigator.clipboard`, never on
// the chrome extension runtime — so it loads standalone (independently
// browser-testable) and is
// the SINGLE SOURCE OF TRUTH for the config shapes (mirrors the Python
// `install-mcp` writer in src/trinity_local/commands/install.py, but uvx-
// based: the recommended zero-prereq path that auto-updates per invocation).
//
// Exposed as `globalThis.TRINITY_HARNESS_SNIPPETS` (data) +
// `globalThis.renderHarnessPicker(targetEl)` (UI). popup.js calls the
// renderer inside the setup card.

(function () {
  "use strict";

  // The uvx invocation every harness shares. uvx ships with `uv`; it pulls
  // + runs trinity-local with no prior `pip install`, and re-resolves to the
  // latest on each launch — so "paste this once" stays current.
  var JSON_BLOCK =
    '{\n' +
    '  "mcpServers": {\n' +
    '    "trinity-local": {\n' +
    '      "command": "uvx",\n' +
    '      "args": ["trinity-local", "--mcp"]\n' +
    '    }\n' +
    '  }\n' +
    '}';

  // Codex reads TOML, not JSON. Same command/args, different surface.
  var TOML_BLOCK =
    '[mcp_servers.trinity-local]\n' +
    'command = "uvx"\n' +
    'args = ["trinity-local", "--mcp"]';

  // Each harness: where the block goes + the block itself. `merge` tells the
  // user this is an ADD into an existing object, not a whole-file replace
  // (the #1 paste-in footgun — clobbering a config that already has servers).
  var SNIPPETS = [
    {
      id: "claude-code",
      label: "Claude Code",
      file: "~/.claude.json",
      lang: "json",
      merge: 'merge into the top-level "mcpServers" object',
      snippet: JSON_BLOCK,
    },
    {
      id: "claude-desktop",
      label: "Claude Desktop",
      file: "~/Library/Application Support/Claude/claude_desktop_config.json (macOS) · %APPDATA%\\Claude\\claude_desktop_config.json (Windows)",
      lang: "json",
      merge: 'merge into the top-level "mcpServers" object',
      snippet: JSON_BLOCK,
    },
    {
      id: "codex",
      label: "Codex CLI",
      file: "~/.codex/config.toml",
      lang: "toml",
      merge: "append this table",
      snippet: TOML_BLOCK,
    },
    {
      id: "cursor",
      label: "Cursor",
      file: "~/.cursor/mcp.json",
      lang: "json",
      merge: 'merge into the top-level "mcpServers" object',
      snippet: JSON_BLOCK,
    },
    {
      id: "antigravity",
      label: "Antigravity",
      file: "~/.gemini/settings.json",
      lang: "json",
      merge: 'merge into the "mcpServers" key',
      snippet: JSON_BLOCK,
    },
    {
      id: "cline",
      label: "Cline (VS Code)",
      file: "Cline → MCP Servers → Configure (cline_mcp_settings.json)",
      lang: "json",
      merge: 'merge into the top-level "mcpServers" object',
      snippet: JSON_BLOCK,
    },
  ];

  function snippetFor(id) {
    for (var i = 0; i < SNIPPETS.length; i++) {
      if (SNIPPETS[i].id === id) return SNIPPETS[i];
    }
    return null;
  }

  // Build the picker DOM: a row of harness pills, a detail area that shows
  // the target file + the copyable config block. Pure DOM, no extension APIs.
  function renderHarnessPicker(targetEl) {
    var doc = targetEl.ownerDocument || document;

    var wrap = doc.createElement("div");
    wrap.className = "harness-picker";

    var heading = doc.createElement("p");
    heading.className = "setup-step";
    heading.textContent = "Or paste the config straight into your harness:";
    wrap.appendChild(heading);

    var pillRow = doc.createElement("div");
    pillRow.className = "harness-pills";
    wrap.appendChild(pillRow);

    var detail = doc.createElement("div");
    detail.className = "harness-detail";
    detail.style.display = "none";
    wrap.appendChild(detail);

    var fileLine = doc.createElement("p");
    fileLine.className = "harness-file";
    detail.appendChild(fileLine);

    var pre = doc.createElement("pre");
    pre.className = "harness-snippet";
    var code = doc.createElement("code");
    pre.appendChild(code);
    detail.appendChild(pre);

    var copyBtn = doc.createElement("button");
    copyBtn.className = "btn";
    copyBtn.id = "copy-harness-snippet";
    copyBtn.textContent = "Copy config block";
    detail.appendChild(copyBtn);

    var selected = null;
    var pills = [];

    function select(spec, pill) {
      selected = spec;
      for (var i = 0; i < pills.length; i++) {
        pills[i].classList.toggle("active", pills[i] === pill);
      }
      fileLine.textContent = "Paste into " + spec.file + " — " + spec.merge + ".";
      code.textContent = spec.snippet;
      copyBtn.textContent = "Copy config block";
      copyBtn.disabled = false;
      detail.style.display = "block";
    }

    SNIPPETS.forEach(function (spec) {
      var pill = doc.createElement("button");
      pill.className = "harness-pill";
      pill.type = "button";
      pill.dataset.harness = spec.id;
      pill.textContent = spec.label;
      pill.addEventListener("click", function () { select(spec, pill); });
      pillRow.appendChild(pill);
      pills.push(pill);
    });

    copyBtn.addEventListener("click", function () {
      if (!selected) return;
      var nav = (typeof navigator !== "undefined") ? navigator : null;
      if (nav && nav.clipboard && nav.clipboard.writeText) {
        nav.clipboard.writeText(selected.snippet).then(function () {
          copyBtn.textContent = "✓ Copied — paste into " + selected.label;
          copyBtn.disabled = true;
        }, function () {
          copyBtn.textContent = "Clipboard blocked — select + copy manually";
        });
      } else {
        copyBtn.textContent = "Clipboard unavailable — select + copy manually";
      }
    });

    targetEl.appendChild(wrap);
    return wrap;
  }

  var root = (typeof globalThis !== "undefined") ? globalThis : window;
  root.TRINITY_HARNESS_SNIPPETS = SNIPPETS;
  root.trinitySnippetFor = snippetFor;
  root.renderHarnessPicker = renderHarnessPicker;
})();
