const recommendForm = document.querySelector("#recommendForm");
const generateButton = document.querySelector("#generateButton");
const userText = document.querySelector("#userText");
const results = document.querySelector("#results");
const statusText = document.querySelector("#statusText");
const selectedTagsText = document.querySelector("#selectedTagsText");
const resultTitle = document.querySelector("#resultTitle");
const tagGrid = document.querySelector("#tagGrid");
const mindsetGrid = document.querySelector("#mindsetGrid");

const selectedTags = new Set();
const selectedTagLabels = new Map();
let currentRoutes = [];
let expandedRouteIndex = null;

loadTags();

recommendForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  setLoading(true);
  statusText.textContent = "正在生成路线和城市剧本...";

  try {
    const response = await fetch("/api/generate-script", {
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
      throw new Error("生成接口暂时不可用，请稍后再试。");
    }

    const data = await response.json();
    currentRoutes = data.routes || [];
    expandedRouteIndex = null;
    renderRouteOptions(currentRoutes);
    statusText.textContent = "已生成候选路线。";
  } catch (error) {
    resultTitle.textContent = "生成失败";
    results.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
    statusText.textContent = "";
  } finally {
    setLoading(false);
  }
});

async function loadTags() {
  try {
    const response = await fetch("/api/tags");
    if (!response.ok) {
      throw new Error("标签数据加载失败。");
    }

    const data = await response.json();
    renderExperienceTagButtons(data.experience_tags || []);
    renderMindsetButtons(data.mindset_tags || []);
  } catch (error) {
    tagGrid.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
    mindsetGrid.innerHTML = "";
  }
}

function renderExperienceTagButtons(tags) {
  tagGrid.innerHTML = tags
    .map(
      (tag) => `
        <button
          type="button"
          class="tag-button"
          data-tag="${escapeHtml(tag.emotion_tag)}"
          data-label="${escapeHtml(tag.user_button_text)}"
          title="${escapeHtml(tag.website_display_copy)}"
          aria-pressed="false"
        >
          ${escapeHtml(tag.user_button_text)}
        </button>
      `,
    )
    .join("");

  tagGrid.querySelectorAll(".tag-button").forEach((button) => {
    button.addEventListener("click", () => toggleTag(button));
  });
}

function renderMindsetButtons(tags) {
  mindsetGrid.innerHTML = tags
    .map(
      (tag) => `
        <button
          type="button"
          class="tag-button mindset-button"
          data-tag="${escapeHtml(tag)}"
          data-label="${escapeHtml(tag)}"
          aria-pressed="false"
        >
          ${escapeHtml(tag)}
        </button>
      `,
    )
    .join("");

  mindsetGrid.querySelectorAll(".tag-button").forEach((button) => {
    button.addEventListener("click", () => toggleTag(button));
  });
}

function toggleTag(button) {
  const tag = button.dataset.tag;
  const label = button.dataset.label || tag;

  if (selectedTags.has(tag)) {
    selectedTags.delete(tag);
    selectedTagLabels.delete(tag);
    button.classList.remove("is-selected");
    button.setAttribute("aria-pressed", "false");
  } else {
    selectedTags.add(tag);
    selectedTagLabels.set(tag, label);
    button.classList.add("is-selected");
    button.setAttribute("aria-pressed", "true");
  }

  updateSelectedTagsText();
}

function updateSelectedTagsText() {
  if (selectedTags.size === 0) {
    selectedTagsText.textContent = "未选择标签";
    return;
  }

  selectedTagsText.textContent = Array.from(selectedTags)
    .map((tag) => selectedTagLabels.get(tag) || tag)
    .join(" / ");
}

function renderRouteOptions(routes) {
  if (!routes.length) {
    resultTitle.textContent = "暂无路线";
    results.innerHTML = '<p class="empty-state">暂时没有可展示的路线。</p>';
    return;
  }

  resultTitle.textContent = "候选路线";
  results.innerHTML = routes
    .map((route, index) => renderRouteOption(route, index, index === expandedRouteIndex))
    .join("");

  results.querySelectorAll(".route-option").forEach((button) => {
    button.addEventListener("click", () => toggleRouteDetail(Number(button.dataset.index)));
  });

  results.querySelectorAll(".route-close-button").forEach((button) => {
    button.addEventListener("click", closeRouteDetail);
  });
}

function renderRouteOption(route, index, isExpanded) {
  const labels = [...(route.matched_tags || []), ...(route.matched_mindsets || [])];
  const labelsHtml = labels.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");

  return `
    <article class="route-card ${isExpanded ? "is-expanded" : ""}">
      <button class="route-option" type="button" data-index="${index}" aria-expanded="${isExpanded}">
        <div>
          <strong>${escapeHtml(route.route_name)}</strong>
          <p>${escapeHtml(route.suggested_card_copy || route.match_reason || route.route_intro_user_facing)}</p>
        </div>
        <span>${escapeHtml(route.match_percent)}%</span>
      </button>
      <div class="route-topline">
        <span>${escapeHtml(route.estimated_time)}</span>
        <span>${escapeHtml(route.budget_level)}预算</span>
        <span>匹配度 ${escapeHtml(route.match_percent)}%</span>
      </div>
      <div class="matched-tags" aria-label="匹配标签">
        ${labelsHtml}
      </div>
      ${isExpanded ? renderRouteDetail(route, index) : ""}
    </article>
  `;
}

function toggleRouteDetail(index) {
  expandedRouteIndex = expandedRouteIndex === index ? null : index;
  renderRouteOptions(currentRoutes);
}

function closeRouteDetail(event) {
  event.stopPropagation();
  expandedRouteIndex = null;
  renderRouteOptions(currentRoutes);
}

function renderRouteDetail(route, index) {
  const spotsHtml = (route.spots || [])
    .map(
      (spot, index) => `
        <li class="spot-item">
          <div class="spot-index">${index + 1}</div>
          <div>
            <strong>${escapeHtml(spot.name)}</strong>
            <p>${escapeHtml(spot.description)}</p>
            <span>${escapeHtml(spot.open_time)} / ${escapeHtml(spot.ticket_reservation)}</span>
            <span>${escapeHtml(spot.address)}</span>
          </div>
        </li>
      `,
    )
    .join("");

  return `
    <div class="route-detail">
      <button
        class="route-close-button"
        type="button"
        data-index="${index}"
        aria-label="关闭路线详情"
        title="关闭路线详情"
      >
        ×
      </button>

      <section class="route-section">
        <h3>推荐理由</h3>
        <p>${escapeHtml(route.match_reason)}</p>
      </section>

      <section class="route-section">
        <h3>点位列表</h3>
        <ol class="spot-list">${spotsHtml}</ol>
      </section>

      <section class="route-section script-box">
        <h3>Mock AI 旅游剧本</h3>
        <p>${escapeHtml(route.script)}</p>
      </section>

      <section class="map-placeholder" aria-label="地图预留区域">
        <div class="map-grid"></div>
        <div class="map-line"></div>
        <div class="map-pin pin-one"></div>
        <div class="map-pin pin-two"></div>
        <div class="map-pin pin-three"></div>
        <div class="map-copy">
          <h3>地图预留区域</h3>
        </div>
      </section>
    </div>
  `;
}

function setLoading(isLoading) {
  generateButton.disabled = isLoading;
  generateButton.textContent = isLoading ? "生成中..." : "生成路线剧本";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
