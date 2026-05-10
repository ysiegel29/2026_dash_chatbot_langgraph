/*
 * Keyboard shortcuts for the composer textarea.
 *
 * Enter          → click the send button
 * Shift+Enter    → insert newline (default browser behaviour, allowed through)
 *
 * Also auto-resizes the textarea as the user types.
 */
(function () {
  function onKeydown(e) {
    if (e.target.id !== "composer") return;

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      var btn = document.getElementById("send-btn");
      if (btn && !btn.disabled) {
        btn.click();
      }
    }
  }

  function autoResize(e) {
    if (e.target.id !== "composer") return;
    var el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  document.addEventListener("keydown", onKeydown);
  document.addEventListener("input", autoResize);
})();
