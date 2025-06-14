// web/static/js/console.js

let socket;

function connectWebSocket() {
    socket = new WebSocket(`ws://${location.host}/ws/logs`);

    socket.onopen = () => {
        appendLog("🟢 Connected to Developer Console");
    };

    socket.onmessage = (event) => {
        appendLog(event.data);
    };

    socket.onerror = (error) => {
        appendLog("🔴 WebSocket error:", error);
    };

    socket.onclose = () => {
        appendLog("🔴 Disconnected. Retrying in 3s...");
        setTimeout(connectWebSocket, 3000);
    };
}

function appendLog(text) {
    const output = document.getElementById("log-output");
    const line = document.createElement("div");
    line.className = "log-line";
    line.textContent = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
}

function sendCommand() {
    const input = document.getElementById("cmd-input");
    const command = input.value.trim();
    if (!command) return;
    appendLog("▶️ " + command);
    socket.send(JSON.stringify({ type: "cmd", data: command }));
    input.value = "";
}

document.getElementById("cmd-form").addEventListener("submit", (e) => {
    e.preventDefault();
    sendCommand();
});

window.onload = () => {
    connectWebSocket();
    document.getElementById("cmd-input").focus();
};
