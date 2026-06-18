const tagButtons = Array.from(document.querySelectorAll(".tag-button"));
const generateButton = document.querySelector("#generateButton");
const userText = document.querySelector("#userText");
const results = document.querySelector("#results");
const statusText = document.querySelector("#statusText");
const selectedTagsText = document.querySelector("#selectedTagsText");

const selectedTags = new Set();

tagButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const tag = button.dataset.tag;

    if (selectedTags.has(tag)) {
      selectedTags.delete(tag);
      button.classList.remove("is-selected");
    } else {
      selectedTags.add(tag);
      button.classList.add("is-selected");
    }

    updateSelectedTagsText();
  });
});

generateButton.addEventListener("click", async () => {
  setLoading(true);
  statusText.textContent = "正在生成路线推荐...";

  try {
    const response = await fetch("/api/recommend-routes", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        selected_tags: Array.from(selectedTags),
        user_text: userText.value.trim(),
      }),
    });

    if (!response.ok) {
      throw new Error("推荐接口暂时不可用");
    }

    const data = await response.json();
    renderRoutes(data.routes || []);
    statusText.textContent = "已根据当前情绪生成推荐。";
  } catch (error) {
    results.innerHTML = '<p class="empty-state">推荐失败，请稍后再试。</p>';
    statusText.textContent = error.message;
  } finally {
    setLoading(false);
  }
});

function updateSelectedTagsText() {
  if (selectedTags.size === 0) {
    selectedTagsText.textContent = "尚未选择标签";
    return;
  }

  selectedTagsText.textContent = Array.from(selectedTags).join(" / ");
}

function renderRoutes(routes) {
  if (routes.length === 0) {
    results.innerHTML = '<p class="empty-state">暂时没有匹配路线，可以换一个标签或补充心情描述。</p>';
    return;
  }

  results.innerHTML = routes.map((route) => createRouteCard(route)).join("");
}

function createRouteCard(route) {
  const spots = (route.spots || [])
    .map(
      (spot) => `
        <li>
          <strong>${escapeHtml(spot.name)}</strong>
          <span>${escapeHtml(spot.description)} (${spot.lat}, ${spot.lng})</span>
        </li>
      `,
    )
    .join("");

  return `
    <article class="route-card">
      <h3>${escapeHtml(route.route_name)}</h3>
      <ul class="route-meta">
        <li>${escapeHtml(route.estimated_time)}</li>
        <li>${escapeHtml(route.budget_level)}</li>
      </ul>
      <p class="route-reason">${escapeHtml(route.reason)}</p>
      <ul class="spot-list">${spots}</ul>
    </article>
  `;
}

function setLoading(isLoading) {
  generateButton.disabled = isLoading;
  generateButton.textContent = isLoading ? "生成中..." : "生成推荐";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
