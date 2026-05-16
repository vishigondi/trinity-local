// Trinity Local — bundled launchpad glue. Phase 3.
//
// Wires the three action cards to chrome.runtime.sendMessage so the
// service worker (background.js) can forward via Native Messaging to
// capture_host.py, which runs the corresponding trinity-local CLI.
//
// Buttons use data-action="<kind>" — kind must be in capture_host's
// ACTION_ALLOWLIST. Current allowlist: launch-council, ingest-recent.
//
// Status pills are written to <div data-status-for="<kind>"> next to
// each button (or the next sibling .status if no explicit attribute).

"use strict";

function statusEl(kind) {
  return document.querySelector(`[data-status-for="${kind}"]`);
}

function setStatus(kind, text, cls = "") {
  const el = statusEl(kind);
  if (!el) return;
  el.textContent = text;
  el.className = "status " + cls;
}

function payloadFor(kind) {
  if (kind === "launch-council") {
    const task = document.getElementById("council-task").value.trim();
    if (!task) {
      setStatus(kind, "Type a question first.", "error");
      return null;
    }
    return { type: "action", kind, task };
  }
  if (kind === "ingest-recent") {
    return { type: "action", kind };
  }
  return null;
}

function dispatch(kind, btn) {
  const payload = payloadFor(kind);
  if (!payload) return;

  setStatus(kind, "Dispatching to local CLI…");
  btn.disabled = true;

  chrome.runtime.sendMessage(payload, (response) => {
    btn.disabled = false;

    if (chrome.runtime.lastError) {
      setStatus(kind, "Extension error: " + chrome.runtime.lastError.message, "error");
      return;
    }
    if (!response) {
      setStatus(kind, "No response from native host. Run trinity-local install-extension to register the manifest.", "error");
      return;
    }
    if (response.ok) {
      const detail = response.stdout ? response.stdout.split("\n")[0].slice(0, 120) : "";
      setStatus(kind, "Done. " + detail, "ok");
      if (kind === "launch-council") {
        document.getElementById("council-task").value = "";
      }
    } else {
      const err = response.error || response.detail || "unknown error";
      const hint = response.hint ? " — " + response.hint : "";
      setStatus(kind, "Failed: " + err + hint, "error");
    }
  });
}

document.querySelectorAll("button[data-action]").forEach((btn) => {
  const kind = btn.getAttribute("data-action");
  btn.addEventListener("click", () => dispatch(kind, btn));
});

const taskInput = document.getElementById("council-task");
if (taskInput) {
  taskInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const btn = document.querySelector('button[data-action="launch-council"]');
      if (btn) btn.click();
    }
  });
}

const openFileBtn = document.getElementById("open-file-launchpad");
if (openFileBtn) {
  openFileBtn.addEventListener("click", () => {
    // The file:// launchpad lives at a known absolute path; we can't
    // resolve $HOME from the extension, so we hand the user the path
    // to paste/click. chrome.tabs.create on file:// works when the
    // extension has the matching host_permissions, but Chrome blocks
    // file:// from extensions by default unless the user toggles it.
    // Safer: copy the path to the clipboard and surface the hint.
    const path = "file:///~/.trinity/portal_pages/launchpad.html";
    navigator.clipboard.writeText(path.replace("~", "")).catch(() => {});
    const status = document.createElement("div");
    status.className = "status ok";
    status.textContent = "Path copied. Paste into address bar: " + path;
    openFileBtn.parentElement.parentElement.appendChild(status);
  });
}
