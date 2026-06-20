const profileGate = document.querySelector("#profileGate");
const appShell = document.querySelector("#appShell");
const savedProfileActions = document.querySelector("#savedProfileActions");
const useSavedProfileButton = document.querySelector("#useSavedProfileButton");
const restartProfileButton = document.querySelector("#restartProfileButton");
const profileWizard = document.querySelector("#profileWizard");
const profileProgress = document.querySelector("#profileProgress");
const profileQuestionTitle = document.querySelector("#profileQuestionTitle");
const profileOptionList = document.querySelector("#profileOptionList");
const profileStepHint = document.querySelector("#profileStepHint");
const profileBackButton = document.querySelector("#profileBackButton");
const profileSkipButton = document.querySelector("#profileSkipButton");
const profileNextButton = document.querySelector("#profileNextButton");
const editProfileButton = document.querySelector("#editProfileButton");
const profileSummaryText = document.querySelector("#profileSummaryText");
const recommendForm = document.querySelector("#recommendForm");
const generateButton = document.querySelector("#generateButton");
const userText = document.querySelector("#userText");
const results = document.querySelector("#results");
const statusText = document.querySelector("#statusText");
const selectedTagsText = document.querySelector("#selectedTagsText");
const resultTitle = document.querySelector("#resultTitle");
const tagGrid = document.querySelector("#tagGrid");
const mindsetGrid = document.querySelector("#mindsetGrid");
const needsInputMessage = "请在左侧选择标签，或者写入你的心情状态。";
const profileStorageKey = "moodscapeProfileAnswers";

const profileQuestions = [
  {
    id: "pace",
    title: "你平时在城市里最舒服的节奏是？",
    required: true,
    options: [
      { value: "slow_stop", label: "慢慢走，能停就停" },
      { value: "clear_content", label: "有明确目标，想看点有内容的" },
      { value: "loose_surprise", label: "不想安排太满，但希望有惊喜" },
      { value: "lively_food", label: "热闹一点，边逛边吃" },
    ],
  },
  {
    id: "healing_space",
    title: "你更容易被哪种空间治愈？",
    required: true,
    options: [
      { value: "quiet_street", label: "书店、咖啡馆、公园、安静街区" },
      { value: "art_space", label: "美术馆、展览、设计空间" },
      { value: "historic_area", label: "老建筑、弄堂、历史街区" },
      { value: "river_night", label: "江边、夜景、城市地标" },
    ],
  },
  {
    id: "shanghai_style",
    title: "你更想遇见哪种上海？",
    required: true,
    options: [
      { value: "old_shanghai", label: "老上海、烟火气、历史感" },
      { value: "future_city", label: "未来感、高楼、城市震撼" },
      { value: "natural_waterfront", label: "自然水岸、公园、轻松散步" },
      { value: "hidden_corner", label: "小众角落、意外发现" },
    ],
  },
  {
    id: "companion",
    title: "你通常更适合哪种同行状态？",
    required: false,
    options: [
      { value: "solo", label: "一个人" },
      { value: "couple", label: "两个人约会" },
      { value: "family", label: "亲子家庭" },
      { value: "friends", label: "朋友一起" },
    ],
  },
  {
    id: "travel_persona",
    title: "如果用一句话描述你的旅行人格？",
    required: false,
    options: [
      { value: "low_stimulation", label: "低刺激、慢节奏" },
      { value: "inspiration_hunter", label: "灵感猎人" },
      { value: "classic_comfort", label: "经典地标也要舒服" },
      { value: "niche_explorer", label: "越小众越兴奋" },
    ],
  },
];

const selectedTags = new Set();
const selectedTagLabels = new Map();
let currentRoutes = [];
let expandedRouteIndex = null;
let profileAnswers = {};
let profileDraftAnswers = {};
let profileStepIndex = 0;

loadTags();
initProfileGate();

recommendForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const trimmedUserText = userText.value.trim();

  if (selectedTags.size === 0 && trimmedUserText === "") {
    showNeedsInput(needsInputMessage);
    return;
  }

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
        user_text: trimmedUserText,
        profile_answers: collectProfileAnswers(),
      }),
    });

    if (!response.ok) {
      throw new Error("生成接口暂时不可用，请稍后再试。");
    }

    const data = await response.json();
    if (data.needs_input) {
      showNeedsInput(data.message || needsInputMessage);
      return;
    }

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

useSavedProfileButton.addEventListener("click", () => {
  const savedProfile = loadSavedProfileAnswers();
  if (savedProfile) {
    enterAppWithProfile(savedProfile);
  } else {
    restartProfileFlow();
  }
});

restartProfileButton.addEventListener("click", () => restartProfileFlow());
editProfileButton.addEventListener("click", () => restartProfileFlow(profileAnswers));

profileBackButton.addEventListener("click", () => {
  if (profileStepIndex > 0) {
    profileStepIndex -= 1;
    renderProfileStep();
  }
});

profileSkipButton.addEventListener("click", () => {
  const question = profileQuestions[profileStepIndex];
  delete profileDraftAnswers[question.id];
  goToNextProfileStep();
});

profileNextButton.addEventListener("click", () => {
  const question = profileQuestions[profileStepIndex];
  if (question.required && !profileDraftAnswers[question.id]) {
    return;
  }
  goToNextProfileStep();
});

function initProfileGate() {
  const savedProfile = loadSavedProfileAnswers();
  if (hasCompletedCoreProfile(savedProfile)) {
    showSavedProfileChoice();
    return;
  }

  restartProfileFlow();
}

function showSavedProfileChoice() {
  profileGate.classList.remove("is-hidden");
  appShell.classList.add("is-hidden");
  savedProfileActions.classList.remove("is-hidden");
  profileWizard.classList.add("is-hidden");
}

function restartProfileFlow(initialAnswers = {}) {
  profileDraftAnswers = { ...initialAnswers };
  profileStepIndex = 0;
  profileGate.classList.remove("is-hidden");
  appShell.classList.add("is-hidden");
  savedProfileActions.classList.add("is-hidden");
  profileWizard.classList.remove("is-hidden");
  renderProfileStep();
}

function renderProfileStep() {
  const question = profileQuestions[profileStepIndex];
  const selectedValue = profileDraftAnswers[question.id] || "";
  const isLastQuestion = profileStepIndex === profileQuestions.length - 1;

  profileProgress.textContent = `${profileStepIndex + 1} / ${profileQuestions.length}`;
  profileQuestionTitle.textContent = question.title;
  profileStepHint.textContent = question.required ? "请选择一个答案" : "这题可以跳过";
  profileBackButton.disabled = profileStepIndex === 0;
  profileSkipButton.classList.toggle("is-hidden", question.required);
  profileNextButton.disabled = question.required && !selectedValue;
  profileNextButton.textContent = isLastQuestion ? "进入网站" : "下一题";

  profileOptionList.innerHTML = question.options
    .map(
      (option) => `
        <button
          type="button"
          class="profile-option-button ${option.value === selectedValue ? "is-selected" : ""}"
          data-value="${escapeHtml(option.value)}"
        >
          ${escapeHtml(option.label)}
        </button>
      `,
    )
    .join("");

  profileOptionList.querySelectorAll(".profile-option-button").forEach((button) => {
    button.addEventListener("click", () => {
      profileDraftAnswers[question.id] = button.dataset.value;
      renderProfileStep();
    });
  });
}

function goToNextProfileStep() {
  if (profileStepIndex === profileQuestions.length - 1) {
    enterAppWithProfile(profileDraftAnswers);
    return;
  }

  profileStepIndex += 1;
  renderProfileStep();
}

function enterAppWithProfile(answers) {
  profileAnswers = sanitizeProfileAnswers(answers);
  saveProfileAnswers(profileAnswers);
  profileGate.classList.add("is-hidden");
  appShell.classList.remove("is-hidden");
  updateProfileSummary();
}

function saveProfileAnswers(answers) {
  try {
    localStorage.setItem(profileStorageKey, JSON.stringify(answers));
  } catch (error) {
    return;
  }
}

function loadSavedProfileAnswers() {
  try {
    const rawProfile = localStorage.getItem(profileStorageKey);
    if (!rawProfile) {
      return null;
    }
    return sanitizeProfileAnswers(JSON.parse(rawProfile));
  } catch (error) {
    return null;
  }
}

function sanitizeProfileAnswers(answers) {
  if (!answers || typeof answers !== "object") {
    return {};
  }

  const cleanAnswers = {};
  profileQuestions.forEach((question) => {
    const value = answers[question.id];
    if (question.options.some((option) => option.value === value)) {
      cleanAnswers[question.id] = value;
    }
  });
  return cleanAnswers;
}

function hasCompletedCoreProfile(answers) {
  return profileQuestions
    .filter((question) => question.required)
    .every((question) => answers && answers[question.id]);
}

function updateProfileSummary() {
  const labels = profileQuestions
    .map((question) => question.options.find((option) => option.value === profileAnswers[question.id])?.label)
    .filter(Boolean);

  profileSummaryText.textContent = labels.length ? labels.join(" / ") : "已建立画像";
}

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

function collectProfileAnswers() {
  return { ...profileAnswers };
}

function showNeedsInput(message) {
  window.alert(message);
  resultTitle.textContent = "需要更多信息";
  results.innerHTML = `<p class="empty-state">${escapeHtml(message)}</p>`;
  statusText.textContent = "";
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
  const labels = uniqueLabels([
    ...(route.matched_tags || []),
    ...(route.matched_mindsets || []),
    ...(route.matched_profile_traits || []),
  ]);
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

function uniqueLabels(labels) {
  return labels.filter((label, index) => label && labels.indexOf(label) === index);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
