// ==UserScript==
// @name         Iglu Agent 自动化 (A1336)：自动登录 + 申请表单预填
// @namespace    uhomes.sydney
// @version      2.0.0
// @description  1) Iglu 登录页自动填 A1336 并登录；2) 申请页自动填 Agency 信息（首次手动填一次自动记住，之后全自动；手动改过也会记住新值）
// @author       梁赛威 · Murphy
// @match        https://iglu.com.au/iglu-agent-portal-login*
// @match        https://iglu.com.au/apply-online*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  var AGENT_CODE = "A1336";

  // ── 配置区（可选）─────────────────────────────
  // 不填也没关系：第一次在申请页手动填一次 Agency 信息，
  // 脚本会自动记住（存在浏览器 localStorage），之后每次申请自动填好。
  var AGENCY = {
    firstName: "",  // Agency First Name，如 "Sanwei"
    lastName:  "",  // Agency Last Name，如 "Liang"
    email:     "",  // Agency Email，如 "sanwei@uhomes.com"
    phone:     ""   // Agency Phone，如 "13800138000"
  };

  var LS_KEY = "iglu_agency_v1";

  function loadSaved() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (raw) {
        var saved = JSON.parse(raw);
        for (var k in saved) if (saved.hasOwnProperty(k)) AGENCY[k] = saved[k];
      }
    } catch (e) {}
  }
  function saveAgency() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(AGENCY)); } catch (e) {}
  }

  // ── 1) 登录页：自动填 A1336 并提交 ──
  function autoLogin() {
    var tries = 0;
    var timer = setInterval(function () {
      var input = document.getElementById("agent_code");
      var form = document.getElementById("agent_from");
      if (input && form) {
        clearInterval(timer);
        if (input.value.trim() !== "") return;      // 已有输入则不覆盖
        input.value = AGENT_CODE;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        setTimeout(function () {
          if (input.value.trim() !== AGENT_CODE) return;
          var btn = form.querySelector('input[type="submit"], button[type="submit"]');
          if (btn) btn.click();
          else form.submit();
        }, 400);
      } else if (++tries > 10) {
        clearInterval(timer);
      }
    }, 500);
  }

  // ── 2) 申请页：自动填 Agency 信息 ──
  function fillAgency() {
    loadSaved();
    var fields = {
      agency_first_name:  "firstName",
      agency_last_name:   "lastName",
      agency_email:       "email",
      agency_phone:       "phone",
      input_agency_phone: "phone"
    };
    var tries = 0;
    var timer = setInterval(function () {
      var found = false;
      for (var id in fields) {
        var el = document.getElementById(id);
        if (!el) continue;
        found = true;
        var val = AGENCY[fields[id]];
        if (val && el.value !== val) {
          el.value = val;
          el.dispatchEvent(new Event("input", { bubbles: true }));
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
        // 用户手动修改后自动记住（每个字段只绑定一次）
        if (!el.dataset.igluBound) {
          el.dataset.igluBound = "1";
          el.addEventListener("blur", function () {
            AGENCY[fields[this.id]] = this.value;
            saveAgency();
          });
        }
      }
      if (found) clearInterval(timer);
      else if (++tries > 20) clearInterval(timer);   // 最多等 10 秒（表单动态加载）
    }, 500);
  }

  var p = location.pathname;
  if (p.indexOf("iglu-agent-portal-login") >= 0) autoLogin();
  else if (p.indexOf("apply-online") >= 0) fillAgency();
})();
