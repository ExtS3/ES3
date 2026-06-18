const approveBtn = document.getElementById("approve_btn");
const rejectBtn = document.getElementById("reject_btn");

const params = new URLSearchParams(window.location.search);
const id = params.get("id");
const app_name = params.get("name");
const app_browser = params.get("browser");
const version = params.get("version");
const source_path = (params.get("source_path") || "").replace(/^\/+/, "");
const payload = { id, app_name, app_browser, browser: app_browser, version, source_path };

async function sendDecision(url, successMessage) {
    try {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const result = await response.json();

        if (!response.ok || !result.success) {
            throw new Error(result.detail || result.message || "처리 중 오류가 발생했습니다.");
        }

        alert(successMessage);
        location.href = "/admin";
    } catch (error) {
        console.error("Decision request failed:", error);
        alert(error.message);
    }
}

approveBtn.addEventListener("click", () => {
    sendDecision("/api/decision/approve", "승인 처리되었습니다.");
});

rejectBtn.addEventListener("click", () => {
    sendDecision("/api/decision/reject", "거부 처리되었습니다.");
});
