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
const appConfig = window.MOODSCAPE_CONFIG || {};

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
let amapLoadPromise = null;
let activeMap = null;
let activeMapRenderId = 0;

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

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    if (!response.ok || data.error) {
      throw new Error(data.message || "生成接口暂时不可用，请稍后再试。");
    }
    if (data.needs_input) {
      showNeedsInput(data.message || needsInputMessage);
      return;
    }

    currentRoutes = data.routes || [];
    destroyActiveMap();
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

  if (expandedRouteIndex !== null && routes[expandedRouteIndex]) {
    renderRouteMap(routes[expandedRouteIndex], expandedRouteIndex);
  }
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
  destroyActiveMap();
  expandedRouteIndex = expandedRouteIndex === index ? null : index;
  renderRouteOptions(currentRoutes);
}

function closeRouteDetail(event) {
  event.stopPropagation();
  destroyActiveMap();
  expandedRouteIndex = null;
  renderRouteOptions(currentRoutes);
}

function renderRouteDetail(route, index) {
  const routeFacts = [
    ["预计时间", route.estimated_time],
    ["预算", `${route.budget_level || ""}预算`.trim()],
    ["匹配度", `${route.match_percent}%`],
  ].filter(([, value]) => value && value !== "预算");
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
        <h3>必要信息</h3>
        <dl class="route-fact-grid">
          ${routeFacts.map(([label, value]) => `
            <div>
              <dt>${escapeHtml(label)}</dt>
              <dd>${escapeHtml(value)}</dd>
            </div>
          `).join("")}
        </dl>
        <div class="route-info-note">
          <strong>推荐理由</strong>
          <p>${escapeHtml(route.match_reason)}</p>
        </div>
        <ol class="spot-list">${spotsHtml}</ol>
        <div class="route-map-panel" aria-label="真实步行路线">
          <div class="map-heading">
            <div>
              <h3>真实步行路线</h3>
              <p id="routeMapStatus-${index}" aria-live="polite">正在加载高德地图...</p>
            </div>
          </div>
          <div class="route-map" id="routeMap-${index}"></div>
        </div>
      </section>

      <section class="route-section script-box">
        <div class="section-heading-row">
          <h3>分幕剧本</h3>
        </div>
        ${renderScriptContent(route)}
      </section>
    </div>
  `;
}

function renderScriptContent(route) {
  const sections = Array.isArray(route.script_sections)
    ? route.script_sections.filter((section) => section && section.type === "spot" && section.title && section.text)
    : [];
  const scriptTitle = route.script_title || "沉浸式城市剧本";
  const sourceBadge = getScriptSourceBadge(route);
  const sourceMessage = route.script_source === "fallback"
    ? route.script_source_message || "千问未成功返回，当前为本地模板。"
    : "";

  if (!sections.length) {
    return `<p>${escapeHtml(route.script)}</p>`;
  }

  return `
    <div class="script-story">
      <div class="script-story-heading">
        <h4 class="script-story-title">${escapeHtml(scriptTitle)}</h4>
        ${sourceBadge}
      </div>
      ${sourceMessage ? `<p class="script-source-note">${escapeHtml(sourceMessage)}</p>` : ""}
      <div class="script-section-list script-scene-list">
        ${sections.map((section, index) => renderScriptScene(section, index)).join("")}
      </div>
    </div>
  `;
}

function getScriptSourceBadge(route) {
  if (route.script_source === "qwen") {
    return '<span class="script-source-badge">来自千问</span>';
  }
  if (route.script_source === "fallback") {
    return '<span class="script-source-badge is-fallback">本地模板</span>';
  }
  return "";
}

function renderScriptScene(section, index) {
  const paragraphs = getScriptParagraphs(section);

  return `
    <article class="script-section script-section-spot">
      <div class="script-section-header">
        <strong>${escapeHtml(section.title || `第${index + 1}幕`)}</strong>
      </div>
      ${paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
    </article>
  `;
}

function getScriptParagraphs(section) {
  if (Array.isArray(section.paragraphs)) {
    const paragraphs = section.paragraphs
      .map((paragraph) => String(paragraph || "").trim())
      .filter(Boolean);
    if (paragraphs.length) {
      return paragraphs;
    }
  }

  return String(section.text || "")
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

async function renderRouteMap(route, index) {
  const mapContainer = document.querySelector(`#routeMap-${index}`);
  const mapStatus = document.querySelector(`#routeMapStatus-${index}`);
  if (!mapContainer || !mapStatus) {
    return;
  }

  const spotsWithCoordinates = (route.spots || []).filter(
    (spot) => Number.isFinite(spot.lng) && Number.isFinite(spot.lat),
  );
  if (spotsWithCoordinates.length < 2) {
    mapStatus.textContent = "有效坐标不足，暂时无法规划步行路线。";
    mapContainer.classList.add("has-map-error");
    return;
  }
  if (!appConfig.amapJsKey) {
    mapStatus.textContent = "尚未配置高德地图 Key，请在 .env 中填写 AMAP_JS_KEY。";
    mapContainer.classList.add("has-map-error");
    return;
  }

  const renderId = ++activeMapRenderId;
  try {
    const AMap = await loadAmapScript();
    if (renderId !== activeMapRenderId) {
      return;
    }

    const sourcePositions = spotsWithCoordinates.map((spot) => [spot.lng, spot.lat]);
    const positions = await convertWgs84Positions(AMap, sourcePositions);
    if (renderId !== activeMapRenderId) {
      return;
    }

    activeMap = new AMap.Map(mapContainer, {
      zoom: 13,
      viewMode: "2D",
      mapStyle: "amap://styles/normal",
    });
    addNumberedMarkers(AMap, activeMap, spotsWithCoordinates, positions);

    let totalDistance = 0;
    let totalDuration = 0;
    let failedSegments = 0;
    for (let segmentIndex = 0; segmentIndex < positions.length - 1; segmentIndex += 1) {
      const start = positions[segmentIndex];
      const end = positions[segmentIndex + 1];
      try {
        const segment = await planWalkingSegment(AMap, start, end);
        if (renderId !== activeMapRenderId) {
          return;
        }
        totalDistance += segment.distance;
        totalDuration += segment.duration;
        drawRouteLine(AMap, activeMap, segment.path, false);
      } catch (error) {
        if (renderId !== activeMapRenderId) {
          return;
        }
        failedSegments += 1;
        drawRouteLine(AMap, activeMap, [start, end], true);
      }
    }

    activeMap.setFitView();
    const missingCoordinates = (route.spots || []).length - spotsWithCoordinates.length;
    const statusParts = [];
    if (totalDistance > 0) {
      statusParts.push(`步行约 ${(totalDistance / 1000).toFixed(1)} 公里`);
    }
    if (totalDuration > 0) {
      statusParts.push(`约 ${Math.max(1, Math.round(totalDuration / 60))} 分钟`);
    }
    if (failedSegments > 0) {
      statusParts.push(`${failedSegments} 段未获取道路规划，已用虚线连接`);
    }
    if (missingCoordinates > 0) {
      statusParts.push(`${missingCoordinates} 个点位缺少坐标`);
    }
    mapStatus.textContent = statusParts.join(" · ") || "已显示路线点位。";
  } catch (error) {
    if (renderId !== activeMapRenderId) {
      return;
    }
    mapStatus.textContent = `地图暂时无法加载：${error.message}`;
    mapContainer.classList.add("has-map-error");
  }
}

function loadAmapScript() {
  if (window.AMap) {
    return Promise.resolve(window.AMap);
  }
  if (amapLoadPromise) {
    return amapLoadPromise;
  }
  if (!appConfig.amapJsKey) {
    return Promise.reject(new Error("缺少 AMAP_JS_KEY"));
  }

  window._AMapSecurityConfig = {
    securityJsCode: appConfig.amapSecurityJsCode || "",
  };
  amapLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(appConfig.amapJsKey)}&plugin=AMap.Walking`;
    script.async = true;
    script.onload = () => resolve(window.AMap);
    script.onerror = () => {
      amapLoadPromise = null;
      reject(new Error("高德地图脚本加载失败"));
    };
    document.head.appendChild(script);
  });
  return amapLoadPromise;
}

function convertWgs84Positions(AMap, positions) {
  return new Promise((resolve, reject) => {
    AMap.convertFrom(positions, "gps", (status, result) => {
      if (status === "complete" && result.info === "ok" && result.locations?.length) {
        resolve(result.locations);
        return;
      }
      reject(new Error("点位坐标转换失败"));
    });
  });
}

function addNumberedMarkers(AMap, map, spots, positions) {
  positions.forEach((position, index) => {
    const marker = new AMap.Marker({
      map,
      position,
      title: spots[index].name,
      content: `<div class="amap-number-marker">${index + 1}</div>`,
      offset: new AMap.Pixel(-15, -15),
    });
    marker.setMap(map);
  });
}

function planWalkingSegment(AMap, start, end) {
  return new Promise((resolve, reject) => {
    const walking = new AMap.Walking({
      hideMarkers: true,
      autoFitView: false,
    });
    walking.search(start, end, (status, result) => {
      const route = result?.routes?.[0];
      if (status !== "complete" || !route) {
        reject(new Error("步行路线规划失败"));
        return;
      }

      const path = [];
      (route.steps || []).forEach((step) => {
        (step.path || []).forEach((point) => path.push(point));
      });
      resolve({
        distance: Number(route.distance) || 0,
        duration: Number(route.time) || 0,
        path: path.length ? path : [start, end],
      });
    });
  });
}

function drawRouteLine(AMap, map, path, isFallback) {
  const lineOptions = {
    map,
    path,
    strokeColor: isFallback ? "#be496d" : "#0f766e",
    strokeOpacity: 0.85,
    strokeWeight: isFallback ? 5 : 7,
    lineJoin: "round",
  };
  if (isFallback) {
    lineOptions.strokeStyle = "dashed";
    lineOptions.strokeDasharray = [10, 8];
  } else {
    lineOptions.strokeStyle = "solid";
  }
  return new AMap.Polyline(lineOptions);
}

function destroyActiveMap() {
  activeMapRenderId += 1;
  if (activeMap) {
    activeMap.destroy();
    activeMap = null;
  }
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
