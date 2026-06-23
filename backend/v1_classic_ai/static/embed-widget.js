(function () {
  var API = "{{API_BASE}}";
  var BOT_ID = "{{BOT_ID}}";
  var BOT_NAME = "{{BOT_NAME}}";
  var userId = "web-" + Math.random().toString(36).slice(2, 10);

  var style = document.createElement("style");
  style.textContent = `
    #v1cb-launcher {
      position: fixed; bottom: 20px; right: 20px; z-index: 99999;
      width: 56px; height: 56px; border-radius: 50%; border: none;
      background: #2563eb; color: #fff; font-size: 24px; cursor: pointer;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    #v1cb-panel {
      display: none; position: fixed; bottom: 88px; right: 20px; z-index: 99999;
      width: 360px; max-width: calc(100vw - 40px); height: 480px;
      background: #fff; border-radius: 14px; box-shadow: 0 8px 40px rgba(0,0,0,0.2);
      flex-direction: column; overflow: hidden; font-family: system-ui, sans-serif;
    }
    #v1cb-panel.open { display: flex; }
    #v1cb-head { padding: 12px 14px; background: #2563eb; color: #fff; font-weight: 600; font-size: 14px; }
    #v1cb-msgs { flex: 1; overflow-y: auto; padding: 10px; background: #f8fafc; }
    #v1cb-msgs .u { text-align: right; margin: 6px 0; }
    #v1cb-msgs .u span { background: #2563eb; color: #fff; padding: 8px 12px; border-radius: 12px; display: inline-block; max-width: 85%; font-size: 13px; }
    #v1cb-msgs .b { text-align: left; margin: 6px 0; }
    #v1cb-msgs .b span { background: #e2e8f0; color: #1e293b; padding: 8px 12px; border-radius: 12px; display: inline-block; max-width: 85%; font-size: 13px; }
    #v1cb-foot { display: flex; border-top: 1px solid #e2e8f0; }
    #v1cb-input { flex: 1; border: none; padding: 12px; outline: none; font-size: 14px; }
    #v1cb-send { border: none; background: #2563eb; color: #fff; padding: 0 16px; cursor: pointer; font-weight: 600; }
  `;
  document.head.appendChild(style);

  var panel = document.createElement("div");
  panel.id = "v1cb-panel";
  panel.innerHTML =
    '<div id="v1cb-head">' + BOT_NAME + '</div>' +
    '<div id="v1cb-msgs"></div>' +
    '<div id="v1cb-foot"><input id="v1cb-input" placeholder="Ask a question..." /><button id="v1cb-send">Send</button></div>';
  document.body.appendChild(panel);

  var btn = document.createElement("button");
  btn.id = "v1cb-launcher";
  btn.textContent = "💬";
  btn.title = "Chat with us";
  document.body.appendChild(btn);

  btn.onclick = function () {
    panel.classList.toggle("open");
    if (panel.classList.contains("open") && !panel.dataset.greeted) {
      panel.dataset.greeted = "1";
      addBot("Hello! How can I help you today?");
    }
  };

  function addUser(t) {
    var d = document.createElement("div");
    d.className = "u";
    d.innerHTML = "<span></span>";
    d.querySelector("span").textContent = t;
    document.getElementById("v1cb-msgs").appendChild(d);
    scroll();
  }

  function addBot(t) {
    var d = document.createElement("div");
    d.className = "b";
    d.innerHTML = "<span></span>";
    d.querySelector("span").textContent = t;
    document.getElementById("v1cb-msgs").appendChild(d);
    scroll();
  }

  function scroll() {
    var m = document.getElementById("v1cb-msgs");
    m.scrollTop = m.scrollHeight;
  }

  async function send() {
    var input = document.getElementById("v1cb-input");
    var msg = input.value.trim();
    if (!msg) return;
    input.value = "";
    addUser(msg);
    addBot("...");
    try {
      var res = await fetch(API + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_id: BOT_ID, user_id: userId, message: msg }),
      });
      var data = await res.json();
      var msgs = document.getElementById("v1cb-msgs");
      msgs.removeChild(msgs.lastChild);
      addBot(data.response || "Sorry, something went wrong.");
    } catch (e) {
      var msgs = document.getElementById("v1cb-msgs");
      msgs.removeChild(msgs.lastChild);
      addBot("Cannot reach chat server. Is the API running?");
    }
  }

  document.getElementById("v1cb-send").onclick = send;
  document.getElementById("v1cb-input").onkeydown = function (e) {
    if (e.key === "Enter") send();
  };
})();
