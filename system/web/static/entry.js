// This relative script also runs when index.html is opened directly from disk.
(() => {
  const localFile = window.location.protocol === "file:";
  document.documentElement.dataset.entry = localFile ? "file" : "http";
  let resourceFailed = false;
  let failure = "";
  let ready = false;
  let timer;
  const render = () => {
    const gate = document.querySelector("#entry-gate");
    if (!gate || localFile || ready) return;
    gate.dataset.state = failure ? "error" : "loading";
    document.querySelector("#entry-title").textContent = failure ? "The workspace couldn’t load" : "Opening your workspace";
    document.querySelector("#entry-copy").textContent = failure || "Connecting to this service and checking your session…";
    document.querySelector("#entry-retry").hidden = false;
    document.querySelector("#entry-retry").textContent = failure ? "Try again" : "Reload page";
    document.querySelector("#entry-service-address").textContent = window.location.origin;
  };
  const fail = (message) => {
    if (localFile || ready) return;
    failure = message;
    clearTimeout(timer);
    render();
  };
  window.EntryGate = {
    ready() {
      if (localFile || resourceFailed) return;
      ready = true;
      clearTimeout(timer);
      document.querySelector("#entry-gate").hidden = true;
      document.body.classList.remove("entry-pending");
    },
    fail,
  };
  if (!localFile) {
    window.addEventListener("error", (event) => {
      const asset = event.target;
      if (ready || !asset?.matches?.('script[src]:not([data-entry-optional]), link[rel="stylesheet"]')) return;
      resourceFailed = true;
      fail("Part of the app didn’t download. Check your connection, then try again. Your project data has not been changed.");
    }, true);
    timer = setTimeout(() => fail("The service is taking longer than expected. Check that it is running, then try again."), 10000);
  }
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#entry-retry").addEventListener("click", () => window.location.reload());
    render();
  });
})();
