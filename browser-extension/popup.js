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
  // Replace the action surface with first-run guidance. Build via
  // safe DOM construction (no innerHTML) so the chrome.runtime.id
  // string can never be interpolated as markup.
  const body = document.querySelector("body");
  while (body.firstChild) body.removeChild(body.firstChild);

  const extensionId = chrome.runtime.id;
  const installCmd = "curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash";
  const registerCmd = `trinity-local install-extension --extension-id ${extensionId}`;

  body.appendChild(el("h1", { text: "Trinity Local — setup needed" }));
  body.appendChild(el("p", { class: "setup-reason", text: reason }));

  body.appendChild(el("p", { class: "setup-step" },
    el("strong", { text: "1." }), " Install Trinity Local:"));
  body.appendChild(el("pre", { class: "setup-cmd", text: installCmd }));

  body.appendChild(el("p", { class: "setup-step" },
    el("strong", { text: "2." }), " Register this Chrome extension with the local host:"));
  body.appendChild(el("pre", { class: "setup-cmd", text: registerCmd }));

  body.appendChild(el("p", { class: "setup-step" },
    el("strong", { text: "3." }), " Reload this popup. The launchpad opens after that."));

  const footer = el("p", { class: "setup-footer" });
  footer.appendChild(document.createTextNode(
    "Trinity is local-first — the extension dispatches to a CLI on your " +
    "machine via Native Messaging. No server, no listening port. See "
  ));
  const link = el("a", {
    href: "https://github.com/vishigondi/trinity-local#install",
    target: "_blank",
    text: "README",
  });
  footer.appendChild(link);
  footer.appendChild(document.createTextNode(" for the full flow."));
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
