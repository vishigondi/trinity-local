// Trinity Local — popup glue.
//
// The popup is the ONLY extension-specific UI. The extension's own
// duplicate launchpad.html was removed; clicking "Open Trinity
// launchpad" dispatches an `open-launchpad` action via Native Messaging,
// which runs `trinity-local portal-html --open-browser` and opens the
// file:// launchpad in the user's default browser.
//
// "Send to council" launches a council *detached* (Popen + start_new_session
// in capture_host) and returns immediately with a client-generated
// status_token. The popup then polls capture_host's in-process
// `get-council-status` handler every ~1.5s and renders a status panel
// with rotating loading copy + per-member chips + synthesis row, the
// same vocabulary as the launchpad's running surface.
//
// If Native Messaging isn't wired (CLI not installed, manifest not
// registered), we show a friendly setup card instead of cryptic errors.

"use strict";

const $ = (id) => document.getElementById(id);

// Mirrors src/trinity_local/launchpad_data.py:COUNCIL_LOADING_MESSAGES.
// Cycled every 2.5s while the council is running.
const COUNCIL_LOADING_MESSAGES = [
  "Reticulating splines...",
  "Generating witty dialog...",
  "Tokenizing real life...",
  "Convincing AI not to turn evil...",
  "Computing chance of success...",
  "Optimizing the optimizer...",
  "Keeping all the 1's and removing all the 0's...",
  "Pushing pixels...",
];

// Mirrors launchpad_template.py's formatProviderLabel — kept tiny since
// the popup only ever shows our three canonical providers. The slug
// rename (gemini → antigravity) was 2026-05-20; canonical lineup is now
// (claude, codex, antigravity). New councils dispatch through the
// canonical slugs; this popup only shows live councils so no legacy
// normalizer is needed here (unlike launchpad_template.py which reads
// historical outcomes).
const PROVIDER_LABELS = {
  claude: "Claude",
  codex: "Codex",
  antigravity: "Antigravity",
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
};
function providerLabel(p) {
  return PROVIDER_LABELS[p] || (p.charAt(0).toUpperCase() + p.slice(1));
}

function setStatus(text, cls = "") {
  const el = $("status");
  if (!el) return;
  el.textContent = text;
  el.className = "status " + cls;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === "string") node.appendChild(document.createTextNode(child));
    else if (child) node.appendChild(child);
  }
  return node;
}

function showSetupCard(reason) {
  // Replace the action surface with first-run guidance. The popup is
  // 380px wide — just wide enough for stacked copy + a single button.
  // We collapse the install into one "Copy install commands" button
  // that puts both shell lines on the clipboard.
  stopPolling();
  const body = document.querySelector("body");
  while (body.firstChild) body.removeChild(body.firstChild);

  const extensionId = chrome.runtime.id;
  const installCmd =
    "curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash";
  const registerCmd = `trinity-local install-extension --extension-id ${extensionId}`;

  // Paste-into-agent brief — the primary install path for non-technical
  // users. They open Claude Code (or Claude Desktop), paste this brief,
  // the agent runs all three steps + verifies. No terminal expertise
  // required. The extension ID is auto-filled so the user never has to
  // copy a long opaque string.
  const brief = [
    "Install Trinity Local for me.",
    "",
    "It's a cross-provider memory layer that runs councils across Claude,",
    "Codex, and Gemini and learns my taste. Open source, no API key,",
    "transcripts stay local. https://github.com/vishigondi/trinity-local",
    "",
    "Three steps:",
    `1. ${installCmd}`,
    `2. ${registerCmd}`,
    "3. trinity-local status   (should report MCP wired and extension wired)",
    "",
    "Then reload the Trinity Chrome extension popup. Tell me when done.",
  ].join("\n");

  body.appendChild(el("h1", { text: "Trinity Local — setup needed" }));
  body.appendChild(el("p", { class: "setup-reason", text: reason }));

  body.appendChild(el("p", { class: "setup-step", text:
    "Easiest path: paste the install brief into Claude Code or Claude " +
    "Desktop — the agent runs all the setup for you."
  }));

  const briefBtn = el("button", {
    class: "btn",
    id: "copy-setup-brief",
    text: "Copy install brief",
  });
  body.appendChild(briefBtn);
  briefBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(brief);
      briefBtn.textContent = "✓ Copied — paste into Claude Code / Desktop";
      briefBtn.disabled = true;
    } catch {
      briefBtn.textContent = "Clipboard blocked — see Setup link below";
    }
  });

  // Secondary affordance for terminal-native users — copies just the
  // two shell commands without the agent-targeted preamble.
  body.appendChild(el("p", { class: "setup-step", text:
    "Prefer the terminal? Copy just the shell commands instead:"
  }));

  const cmdsBtn = el("button", {
    class: "btn secondary",
    id: "copy-setup-cmds",
    text: "Copy shell commands",
  });
  body.appendChild(cmdsBtn);
  cmdsBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(installCmd + "\n" + registerCmd);
      cmdsBtn.textContent = "✓ Copied — paste in terminal";
      cmdsBtn.disabled = true;
    } catch {
      cmdsBtn.textContent = "Clipboard blocked — see Setup link below";
    }
  });

  // Per-harness paste-in snippet picker (#166). For users who'd rather
  // drop the MCP config block straight into their harness than run the
  // CLI. Rendered by the pure harness-snippets.js module (no chrome.*),
  // which is the single source of truth for the per-harness config shapes.
  if (typeof renderHarnessPicker === "function") {
    renderHarnessPicker(body);
  }

  body.appendChild(el("p", { class: "setup-step", text:
    "After installing, reload this popup."
  }));

  const footer = el("p", { class: "setup-footer" });
  const link = el("a", {
    href: "https://github.com/vishigondi/trinity-local#install",
    target: "_blank",
    text: "Setup details →",
  });
  footer.appendChild(link);
  body.appendChild(footer);
}

function dispatch(kind, extra = {}) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { type: "action", kind, ...extra },
      (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: "extension-error: " + chrome.runtime.lastError.message });
          return;
        }
        if (!response) {
          resolve({ ok: false, error: "native-host-unavailable" });
          return;
        }
        resolve(response);
      }
    );
  });
}

// Surface a real error string instead of "unknown error". The host
// now returns `error` for non-zero exits (last line of stderr) plus
// `returncode` / `stderr`; pick whichever is most informative.
function extractError(response) {
  if (!response) return "no response";
  const candidates = [
    response.error,
    response.detail,
    response.hint,
    (response.stderr || "").trim().split("\n").pop(),
    response.returncode != null ? `exit code ${response.returncode}` : null,
  ];
  for (const c of candidates) {
    if (c && String(c).trim()) return String(c).trim();
  }
  return "unknown error";
}

// ─── Council polling state ────────────────────────────────────────────

let pollTimer = null;
let rotateTimer = null;
let rotateIndex = 0;
let activeStatusToken = null;
let activeMembers = [];
let activeTask = "";

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (rotateTimer) { clearInterval(rotateTimer); rotateTimer = null; }
  activeStatusToken = null;
}

function newStatusToken() {
  // Same shape as launchpad's: launch_<base36ts>_<rand>. Filename-safe
  // (matches capture_host's _SAFE_ID_RX so the in-process status reader
  // accepts it).
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `launch_${ts}_${rand}`;
}

function showStatusPanel(task, members) {
  activeMembers = members.slice();
  activeTask = task;
  $("compose").style.display = "none";
  const panel = $("status-panel");
  panel.style.display = "block";
  $("panel-title").textContent = "Council running";
  $("panel-tip").textContent = COUNCIL_LOADING_MESSAGES[0];
  // Open/Stop visible while busy; Dismiss hidden until terminal state.
  $("panel-open-btn").style.display = "";
  $("panel-stop-btn").style.display = "";
  $("panel-dismiss-btn").style.display = "none";

  // Pre-render member rows in pending state so the user sees structure
  // before the first status JSON arrives.
  const rows = $("member-rows");
  while (rows.firstChild) rows.removeChild(rows.firstChild);
  for (const p of members) {
    rows.appendChild(memberRow(p, "pending"));
  }
  rows.appendChild(memberRow("__synthesis__", "pending"));
}

function memberRow(provider, status, detail) {
  const isSynth = provider === "__synthesis__";
  const label = isSynth ? "Chairman synthesis" : providerLabel(provider);
  const statusLabel = (
    status === "done" ? "Done" :
    status === "failed" ? "Failed" :
    status === "running" ? "Running" : "Queued"
  );
  const row = el("div", { class: "member-row" });
  row.dataset.provider = provider;
  row.appendChild(el("div", { class: "dot " + status }));
  row.appendChild(el("div", { class: "name", text: label }));
  row.appendChild(el("div", { class: "pill " + status, text: statusLabel }));
  return row;
}

function updateMemberRow(provider, status) {
  const rows = $("member-rows");
  const existing = Array.from(rows.children).find((c) => c.dataset.provider === provider);
  if (!existing) {
    rows.appendChild(memberRow(provider, status));
    return;
  }
  const dot = existing.querySelector(".dot");
  const pill = existing.querySelector(".pill");
  if (dot) dot.className = "dot " + status;
  if (pill) {
    pill.className = "pill " + status;
    pill.textContent = (
      status === "done" ? "Done" :
      status === "failed" ? "Failed" :
      status === "running" ? "Running" : "Queued"
    );
  }
}

function rotateTip() {
  rotateIndex = (rotateIndex + 1) % COUNCIL_LOADING_MESSAGES.length;
  const tip = $("panel-tip");
  if (tip) tip.textContent = COUNCIL_LOADING_MESSAGES[rotateIndex];
}

function startPolling(statusToken, members) {
  stopPolling();
  activeStatusToken = statusToken;
  rotateIndex = 0;
  rotateTimer = setInterval(rotateTip, 2500);

  const check = async () => {
    if (statusToken !== activeStatusToken) return;
    const r = await dispatch("get-council-status", { status_token: statusToken });
    if (!r || !r.ok) {
      // Treat transient read failure as just "no status yet" — the
      // runner may not have written the first record. Don't bail.
      return;
    }
    const status = r.status;
    if (!status) return;  // pre-write window — keep cycling tips

    // Member updates
    const memberMap = status.members || {};
    for (const p of members) {
      const m = memberMap[p] || {};
      updateMemberRow(p, m.status || "pending");
    }
    // Synthesis row
    const synth = status.synthesis || {};
    updateMemberRow("__synthesis__", synth.status || "pending");

    // Synthesis tip overrides rotating copy while chairman runs.
    const tip = $("panel-tip");
    if (tip) {
      if (synth.status === "running") {
        tip.textContent = "Synthesizing the strongest answer...";
      } else {
        const activeProvider = Object.entries(memberMap)
          .find(([, v]) => (v || {}).status === "running");
        if (activeProvider) {
          tip.textContent = `${providerLabel(activeProvider[0])}: ${COUNCIL_LOADING_MESSAGES[rotateIndex]}`;
        }
      }
    }

    if (status.status === "completed") {
      $("panel-title").textContent = "Council ready";
      if (tip) tip.textContent = "Open the council page to pick a winner.";
      stopPolling();
      enterTerminalState();
      // Auto-open the council page for THIS council — not the launchpad.
      // The user just asked a specific question; landing them on the
      // launchpad would be a step backwards.
      await dispatch("open-council-page", {
        status_token: statusToken,
        task: activeTask,
        members: activeMembers,
      });
    } else if (status.status === "failed") {
      $("panel-title").textContent = "Council failed";
      if (tip) tip.textContent = status.error || "The council runner exited with an error.";
      stopPolling();
      enterTerminalState();
    } else if (status.status === "canceled") {
      $("panel-title").textContent = "Council stopped";
      if (tip) tip.textContent = status.error || "Run was canceled.";
      stopPolling();
      enterTerminalState();
    }
  };

  // Fire immediately so the first status JSON shows up as soon as the
  // runner writes it (typically <500ms after Popen).
  check();
  pollTimer = setInterval(check, 1500);
}

// Once a council reaches completed / failed / canceled, swap Open + Stop
// for a single Dismiss button — mirrors the launchpad's v-if logic.
function enterTerminalState() {
  $("panel-stop-btn").style.display = "none";
  $("panel-dismiss-btn").style.display = "";
}

// ─── Wire UI ──────────────────────────────────────────────────────────

$("run-btn").addEventListener("click", async () => {
  const task = $("task").value.trim();
  if (!task) {
    setStatus("Type a question first.", "error");
    return;
  }
  const statusToken = newStatusToken();
  const members = ["claude", "codex", "antigravity"];
  showStatusPanel(task, members);

  const response = await dispatch("launch-council", {
    task,
    status_token: statusToken,
  });

  if (response.ok && response.detached) {
    // Council is running headless; start polling.
    startPolling(statusToken, members);
    return;
  }
  // Backward-compat: if the host runs synchronously (older capture_host),
  // we still get here with the full result. Re-show compose + a real error.
  $("status-panel").style.display = "none";
  $("compose").style.display = "block";
  if (response.error === "native-host-unavailable") {
    showSetupCard("Native Messaging host not found. Trinity's CLI isn't wired to this extension yet.");
  } else if ((response.error || "").includes("CLI not on PATH")) {
    showSetupCard("Trinity's CLI isn't on PATH. Install it via curl-bash, then come back here.");
  } else {
    setStatus("Failed: " + extractError(response), "error");
  }
});

$("task").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
    e.preventDefault();
    $("run-btn").click();
  }
});

$("panel-open-btn").addEventListener("click", async () => {
  // Open THIS council's live page (not the launchpad). Same shape as
  // the launchpad's `<a :href="liveCouncilUrl">Open council page</a>`.
  const r = await dispatch("open-council-page", {
    status_token: activeStatusToken,
    task: activeTask,
    members: activeMembers,
  });
  if (r.ok) window.close();
});

$("panel-stop-btn").addEventListener("click", async () => {
  // Mirrors launchpad's stopCurrentCouncil — fires the real stop-council
  // action (NOT just hiding the popup). The runner sees SIGTERM and
  // writes status=canceled before exiting.
  if (!activeStatusToken) return;
  $("panel-stop-btn").disabled = true;
  await dispatch("stop-council", { status_token: activeStatusToken });
  // Let the next poll tick render the canceled state — don't bail
  // early in case the stop fails.
});

$("panel-dismiss-btn").addEventListener("click", () => {
  // Terminal-state dismiss — return to compose for the next question.
  stopPolling();
  $("status-panel").style.display = "none";
  $("compose").style.display = "block";
  setStatus("");
});

$("panel-close-btn").addEventListener("click", () => {
  // ✕ — closes the popup without stopping the council (it keeps
  // running headless since we Popen'd with start_new_session). User
  // can reopen the popup or use the launchpad to find it again.
  stopPolling();
  window.close();
});

$("open-launchpad-btn").addEventListener("click", async () => {
  setStatus("Opening launchpad…");
  $("open-launchpad-btn").disabled = true;
  const response = await dispatch("open-launchpad");
  $("open-launchpad-btn").disabled = false;
  if (response.ok) {
    setStatus("Launchpad opened in your default browser.", "ok");
    setTimeout(() => window.close(), 600);
  } else if (response.error === "native-host-unavailable") {
    showSetupCard("Native Messaging host not found. Trinity's CLI isn't wired to this extension yet.");
  } else if ((response.error || "").includes("CLI not on PATH")) {
    showSetupCard("Trinity's CLI isn't on PATH. Install it via curl-bash, then come back here.");
  } else {
    setStatus("Failed to open launchpad: " + extractError(response), "error");
  }
});
