// ==UserScript==
// @name         Iglu Agent Portal 自动登录 (A1336)
// @namespace    uhomes.sydney
// @version      1.0.0
// @description  打开 Iglu Agent 登录页时自动填入 Agent Code A1336 并提交，免去每次手动输入。若已手动输入其他 Code 则不会覆盖、不会自动提交。
// @author       梁赛威 · Murphy
// @match        https://iglu.com.au/iglu-agent-portal-login*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  var CODE = "A1336";
  var tries = 0;

  var timer = setInterval(function () {
    var input = document.getElementById("agent_code");
    var form = document.getElementById("agent_from");
    if (input && form) {
      clearInterval(timer);
      // 用户已手动输入其他 Code 时，不覆盖、不自动提交
      if (input.value.trim() !== "") return;

      input.value = CODE;
      input.dispatchEvent(new Event("input", { bubbles: true }));

      setTimeout(function () {
        // 提交前再校验一次，避免覆盖用户刚输入的内容
        if (input.value.trim() !== CODE) return;
        var btn = form.querySelector('input[type="submit"], button[type="submit"]');
        if (btn) btn.click();
        else form.submit();
      }, 400);
    } else if (++tries > 10) {
      clearInterval(timer);
    }
  }, 500);
})();
