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
      // offsetParent is null when the button is hidden (a turn is streaming);
      // don't fire a send in that state.
      if (btn && !btn.disabled && btn.offsetParent !== null) {
        btn.click();
      }
    }
  }

  var MAX_H = 400;

  function autoResize(e) {
    if (e.target.id !== "composer") return;
    var el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, MAX_H) + "px";
    // Only show a scrollbar once the box has hit its max height.
    el.style.overflowY = el.scrollHeight > MAX_H ? "auto" : "hidden";
  }

  document.addEventListener("keydown", onKeydown);
  document.addEventListener("input", autoResize);
})();
