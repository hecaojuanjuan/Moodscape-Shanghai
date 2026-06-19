const recommendForm = document.querySelector("#recommendForm");
const generateButton = document.querySelector("#generateButton");
const userText = document.querySelector("#userText");
const results = document.querySelector("#results");
const statusText = document.querySelector("#statusText");
const selectedTagsText = document.querySelector("#selectedTagsText");
const resultTitle = document.querySelector("#resultTitle");
const tagGrid = document.querySelector("#tagGrid");
const mindsetGrid = document.querySelector("#mindsetGrid");

const mindsetTags = [
  { tag: "独处", label: "独处", copy: "适合一个人安静停留，把城市走成自己的背景音。" },
  { tag: "疗愈", label: "疗愈", copy: "适合累了、想放松、想恢复一点能量的时刻。" },
  { tag: "灵感", label: "灵感", copy: "适合看展、观察街区、重新打开感受力。" },
  { tag: "怀旧", label: "怀旧", copy: "适合老建筑、文学街区和旧时光的城市线索。" },
  { tag: "成长", label: "成长", copy: "适合学习、涨见识和带着问题探索城市。" },
  { tag: "浪漫", label: "浪漫", copy: "适合约会、江风、展厅和有氛围的慢步行。" },
  { tag: "探索", label: "探索", copy: "适合冷门角落、城市支线和非标准路线。" },
  { tag: "社交", label: "社交", copy: "适合朋友同行、逛吃聊天和热闹街区。" },
];

const selectedTags = new Set();
const selectedTagLabels = new Map();

loadEmotionTags();
renderMindsetButtons();

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
    renderRecommendation(data.route, data.script, data);
    statusText.textContent = "已生成一条适合当前心情的路线。";
  } catch (error) {
    resultTitle.textContent = "生成失败";
    results.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
    statusText.textContent = "";
  } finally {
    setLoading(false);
  }
});

async function loadEmotionTags() {
  try {
    const response = await fetch("/static/data/tags.json");
    if (!response.ok) {
      throw new Error("标签数据加载失败。");
    }

    const tags = await response.json();
    renderTagButtons(tags);
  } catch (error) {
    tagGrid.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
  }
}

function renderTagButtons(tags) {
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

function renderMindsetButtons() {
  mindsetGrid.innerHTML = mindsetTags
    .map(
      (tag) => `
        <button
          type="button"
          class="tag-button mindset-button"
          data-tag="${escapeHtml(tag.tag)}"
          data-label="${escapeHtml(tag.label)}"
          title="${escapeHtml(tag.copy)}"
          aria-pressed="false"
        >
          ${escapeHtml(tag.label)}
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

function renderRecommendation(route, script, payload = {}) {
  if (!route) {
    resultTitle.textContent = "暂无路线";
    results.innerHTML = '<p class="empty-state">暂时没有可展示的路线。</p>';
    return;
  }

  resultTitle.textContent = route.route_name || "推荐路线";

  const matchedTags = payload.matched_tags || route.matched_tags || [];
  const matchedMindsets = payload.matched_mindsets || route.matched_mindsets || [];
  const matchedLabels = [...matchedTags, ...matchedMindsets];
  const matchedTagsHtml = matchedLabels.length
    ? matchedLabels.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")
    : "<span>默认推荐</span>";

  const spots = payload.spots || route.spots || [];
  const reason = payload.recommendation_reason || route.reason || "这条路线适合此刻的你。";

  const spotsHtml = spots
    .map(
      (spot, index) => `
        <li class="spot-item">
          <div class="spot-index">${index + 1}</div>
          <div>
            <strong>${escapeHtml(spot.name)}</strong>
            <p>${escapeHtml(spot.description)}</p>
            <span>纬度 ${escapeHtml(spot.lat)} / 经度 ${escapeHtml(spot.lng)}</span>
          </div>
        </li>
      `,
    )
    .join("");

  results.innerHTML = `
    <article class="route-card">
      <div class="route-topline">
        <span>${escapeHtml(route.estimated_time)}</span>
        <span>${escapeHtml(route.budget_level)}预算</span>
        <span>匹配分 ${escapeHtml(route.score)}</span>
      </div>

      <div class="matched-tags" aria-label="匹配情绪标签">
        ${matchedTagsHtml}
      </div>

      <section class="route-section">
        <h3>推荐理由</h3>
        <p>${escapeHtml(reason)}</p>
      </section>

      <section class="route-section">
        <h3>点位列表</h3>
        <ol class="spot-list">${spotsHtml}</ol>
      </section>

      <section class="route-section script-box">
        <h3>Mock AI 旅游剧本</h3>
        <p>${escapeHtml(script)}</p>
      </section>

      <section class="map-placeholder" aria-label="地图预留区域">
        <div class="map-grid"></div>
        <div class="map-line"></div>
        <div class="map-pin pin-one"></div>
        <div class="map-pin pin-two"></div>
        <div class="map-pin pin-three"></div>
        <div class="map-copy">
          <h3>地图预留区域</h3>
          <p>后续可在这里接入真实地图 API，展示路线点位与连线。</p>
        </div>
      </section>
    </article>
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
