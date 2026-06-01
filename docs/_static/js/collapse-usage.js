// Collapse the "Usage" node in the left sidebar by default. There's no
// per-node config for this, so we strip Shibuya's `_expand` class from that one
// node on load. The chevron still re-expands it, and the `current` class keeps
// it open whenever you're on a page inside Usage.
document.addEventListener("DOMContentLoaded", () => {
  document
    .querySelectorAll('.globaltoc a[href$="guides/usage/index.html"]')
    .forEach((link) => link.closest("li")?.classList.remove("_expand"));
});
