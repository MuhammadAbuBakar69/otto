/* Page behaviour that has nothing to do with the demo:
 * sticky header, mobile menu, copy buttons, footer year.
 * FAQ is a native <details>, so it needs no script at all.
 */
(function () {
  "use strict";

  var header = document.getElementById("site-header");
  var toggle = document.getElementById("nav-toggle");
  var nav = document.getElementById("nav");

  if (header && toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = header.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    nav.addEventListener("click", function (event) {
      if (event.target.tagName === "A") {
        header.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  if (header) {
    var onScroll = function () {
      header.classList.toggle("is-stuck", window.scrollY > 8);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* copy buttons */

  function toast(message) {
    var node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("is-visible");
    window.clearTimeout(toast._timer);
    toast._timer = window.setTimeout(function () {
      node.classList.remove("is-visible");
    }, 2200);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    /* older browsers, and plain http origins where clipboard is blocked */
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy") ? resolve() : reject(new Error("copy failed"));
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(area);
      }
    });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy]");
    if (!button) return;
    var source = document.querySelector(button.getAttribute("data-copy"));
    if (!source) return;
    var text = source.textContent.trim();
    var original = button.textContent;
    copyText(text).then(
      function () {
        button.textContent = "Copied";
        toast("Copied to clipboard");
        window.setTimeout(function () { button.textContent = original; }, 1600);
      },
      function () {
        button.textContent = "Select it";
        window.setTimeout(function () { button.textContent = original; }, 1600);
      }
    );
  });

  /* current year in the footer */

  var year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());
})();
