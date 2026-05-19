// Trinity Local — popup glue.
//
// The popup is the ONLY extension-specific UI. The extension's own
// duplicate launchpad.html was removed (see commit log); clicking
// "Open Trinity launchpad" dispatches an `open-launchpad` action via
// Native Messaging, which runs `trinity-local portal-html
// --open-browser` and opens the file:// launchpad in the user's
// default browser. Single canonical launchpad surface.
//
// Two affordances:
//  1. Type a question + Send to council → fires `launch-council` via
//     Native Messaging.
//  2. Open Trinity launchpad → fires `open-launchpad` → CLI generates
//     + opens the file:// launchpad.
//
// If Native Messaging isn't wired (CLI not installed, manifest not
// registered), show a friendly setup card instead of cryptic errors.

"use strict";

const $ = (id) => document.getElementById(id);

function setStatus(text, cls = "") {
  const el = $("status");
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
  // 320px wide — too narrow for shell commands inline. Solution: a
  // single Copy button that puts both commands on the clipboard.
  const body = document.querySelector("body");
  while (body.firstChild) body.removeChild(body.firstChild);

  const extensionId = chrome.runtime.id;
  const installCmd =
    "curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash";
  const registerCmd = `trinity-local install-extension --extension-id ${extensionId}`;
  const bothCmds = installCmd + "\n" + registerCmd;

  body.appendChild(el("h1", { text: "Trinity Local — setup needed" }));
  body.appendChild(el("p", { class: "setup-reason", text: reason }));

  body.appendChild(el("p", { class: "setup-step", text:
    "Install Trinity's CLI, then register this extension with it. " +
    "Copy both commands and paste them in your terminal:"
  }));

  const copyBtn = el("button", {
    class: "btn",
    id: "copy-setup-cmds",
    text: "Copy install commands",
  });
  body.appendChild(copyBtn);

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(bothCmds);
      copyBtn.textContent = "✓ Copied — paste in terminal";
      copyBtn.disabled = true;
    } catch {
      copyBtn.textContent = "Clipboard blocked — see Setup link below";
    }
  });

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

$("run-btn").addEventListener("click", async () => {
  const task = $("task").value.trim();
  if (!task) {
    setStatus("Type a question first.", "error");
    return;
  }
  setStatus("Sending to council…");
  $("run-btn").disabled = true;
  const response = await dispatch("launch-council", { task });
  $("run-btn").disabled = false;
  if (response.ok) {
    setStatus("Council started. Open the launchpad to see live status.", "ok");
    $("task").value = "";
  } else if (response.error === "native-host-unavailable") {
    showSetupCard("Native Messaging host not found. Trinity's CLI isn't wired to this extension yet.");
  } else if ((response.error || "").includes("CLI not on PATH")) {
    showSetupCard("Trinity's CLI isn't on PATH. Install it via curl-bash, then come back here.");
  } else {
    const err = response.error || response.detail || "unknown error";
    const hint = response.hint ? "\n" + response.hint : "";
    setStatus("Failed: " + err + hint, "error");
  }
});

$("task").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("run-btn").click();
  }
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
    const err = response.error || response.detail || "unknown error";
    setStatus("Failed to open launchpad: " + err, "error");
  }
});
