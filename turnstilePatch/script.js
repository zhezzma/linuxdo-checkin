"use strict";

(function () {
  const originalCreate = Document.prototype.createElement;
  Document.prototype.createElement = function (tagName) {
    const element = originalCreate.call(this, tagName);
    if (typeof tagName === "string" && tagName.toLowerCase() === "iframe") {
      const originalSetAttribute = element.setAttribute.bind(element);
      element.setAttribute = function (name, value) {
        try {
          if (name === "src" && typeof value === "string") {
            const url = new URL(value, window.location.href);
            if (url.pathname.startsWith("/cdn-cgi/challenge-platform/")) {
              element.addEventListener("load", function () {
                setTimeout(function () {
                  try {
                    element.contentWindow.postMessage(
                      {
                        event: "cf_chl_managed",
                        action: "challenge_solve",
                        msg: "Turnstile bypass",
                      },
                      "*"
                    );
                  } catch (e) {}
                }, 3000);
              });
            }
          }
        } catch (e) {}
        return originalSetAttribute(name, value);
      };
    }
    return element;
  };
})();
