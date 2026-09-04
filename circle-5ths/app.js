import {
  MAJOR_KEYS,
  MINOR_KEYS,
  ROMANS,
  answersMatch,
  circleFrom,
  degreeAnswer,
  median,
  normalizeNote,
  pitchClass,
  randomItem,
  splitAnswer,
} from "./music.js";

const STORAGE_KEY = "orbit-circle-fifths-v1";
const state = {
  page: "practice",
  mode: "circle",
  level: "major",
  startedAt: 0,
  timerId: null,
  currentCircle: null,
  questions: [],
  questionIndex: 0,
  questionStartedAt: 0,
  answers: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function loadData() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || { attempts: [], gaps: {} };
  } catch {
    return { attempts: [], gaps: {} };
  }
}

function saveData(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function localDate(timestamp = Date.now()) {
  const date = new Date(timestamp);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatTime(milliseconds) {
  const totalTenths = Math.round(milliseconds / 100);
  const minutes = Math.floor(totalTenths / 600);
  const seconds = Math.floor((totalTenths % 600) / 10);
  const tenths = totalTenths % 10;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

function showPage(page) {
  state.page = page;
  $$(".page").forEach((element) => element.classList.toggle("active", element.id === `${page}-page`));
  $$(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
  if (page === "results") renderResults();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showTrainerView(view) {
  ["setup", "circle", "degree", "complete"].forEach((name) => {
    $(`#${name}-view`).hidden = name !== view;
  });
}

function selectMode(mode) {
  state.mode = mode;
  $$(".mode-tab").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  $("#circle-levels").hidden = mode !== "circle";
  $("#degree-options").hidden = mode !== "degrees";
  $("#weak-options").hidden = mode !== "weak";
  $("#setup-kicker").textContent =
    mode === "circle" ? "Circle sprint" : mode === "degrees" ? "Degree drill" : "Adaptive practice";
  $("#setup-title").textContent =
    mode === "circle" ? "Choose your level" : mode === "degrees" ? "Set your distance" : "Train your weak spots";
  $("#start-button").disabled = mode === "weak" && Object.keys(loadData().gaps).length === 0;
  showTrainerView("setup");
}

function startTimer(element) {
  clearInterval(state.timerId);
  state.startedAt = performance.now();
  const update = () => {
    element.textContent = formatTime(performance.now() - state.startedAt);
  };
  update();
  state.timerId = setInterval(update, 100);
}

function stopTimer() {
  clearInterval(state.timerId);
  return performance.now() - state.startedAt;
}

function startCircle() {
  const type = state.level === "mixed" ? randomItem(["major", "minor"]) : state.level;
  const direction = randomItem(["fifths", "fourths"]);
  const key = randomItem(type === "major" ? MAJOR_KEYS : MINOR_KEYS);
  state.currentCircle = { key, type, direction, answer: circleFrom(key, direction, type) };
  $("#circle-key-type").textContent = `${type === "major" ? "Major" : "Minor"} key`;
  $("#circle-start").textContent = key;
  $("#circle-direction").textContent = direction === "fifths" ? "↗ Up in fifths" : "↖ Up in fourths";
  $("#circle-answer").value = "";
  $("#circle-error").textContent = "";
  showTrainerView("circle");
  startTimer($("#circle-timer"));
  requestAnimationFrame(() => $("#circle-answer").focus());
}

function gapKey(key, degreeIndex) {
  return `${key}|${degreeIndex}`;
}

function createQuestion(sourceMode) {
  const data = loadData();
  if (sourceMode === "weak" && Object.keys(data.gaps).length) {
    const weighted = Object.entries(data.gaps).flatMap(([key, score]) =>
      Array.from({ length: Math.max(1, Math.ceil(score)) }, () => key),
    );
    const [key, degree] = randomItem(weighted).split("|");
    return { key, degreeIndex: Number(degree) };
  }
  return {
    key: randomItem(MAJOR_KEYS),
    degreeIndex: Math.floor(Math.random() * ROMANS.length),
  };
}

function startDegrees() {
  const count = state.mode === "weak" ? 10 : Number($("#question-count").value);
  state.questions = Array.from({ length: count }, () => createQuestion(state.mode));
  state.questionIndex = 0;
  state.answers = [];
  showTrainerView("degree");
  startTimer($("#degree-timer"));
  showQuestion();
}

function showQuestion() {
  const question = state.questions[state.questionIndex];
  $("#degree-progress").textContent = `${state.questionIndex + 1} / ${state.questions.length}`;
  $("#progress-bar").style.width = `${(state.questionIndex / state.questions.length) * 100}%`;
  $("#degree-roman").textContent = ROMANS[question.degreeIndex];
  $("#degree-key").textContent = question.key;
  $("#degree-answer").value = "";
  $("#degree-error").textContent = "";
  state.questionStartedAt = performance.now();
  requestAnimationFrame(() => $("#degree-answer").focus());
}

function recordAttempt(attempt) {
  const data = loadData();
  data.attempts.push({ id: crypto.randomUUID(), timestamp: Date.now(), ...attempt });
  saveData(data);
  refreshSummary();
}

function completeAttempt(attempt) {
  recordAttempt(attempt);
  $("#complete-time").textContent = formatTime(attempt.duration);
  const personalAttempts = loadData().attempts.filter((item) => item.mode === attempt.mode);
  const isBest = attempt.duration === Math.min(...personalAttempts.map((item) => item.duration));
  $("#complete-summary").textContent = isBest
    ? "That’s your fastest run yet."
    : "Clean repetition builds automatic recall.";
  $("#completion-stats").innerHTML =
    attempt.mode === "circle"
      ? `<span><strong>12</strong> keys recalled</span><span><strong>${attempt.level}</strong> level</span>`
      : `<span><strong>${attempt.correct}/${attempt.questions}</strong> correct</span><span><strong>${formatTime(attempt.duration / attempt.questions)}</strong> avg.</span>`;
  showTrainerView("complete");
}

function submitCircle(event) {
  event.preventDefault();
  const actual = splitAnswer($("#circle-answer").value);
  if (actual.length !== 12) {
    $("#circle-error").textContent = `You have ${actual.length} of 12 keys. Keep going.`;
    return;
  }
  if (!answersMatch(actual, state.currentCircle.answer)) {
    const mismatch = actual.findIndex((value, index) => !answersMatch([value], [state.currentCircle.answer[index]]));
    $("#circle-error").textContent = `Check position ${mismatch + 1}. The sequence breaks after ${mismatch ? actual[mismatch - 1] : "the start"}.`;
    return;
  }
  const duration = stopTimer();
  completeAttempt({
    mode: "circle",
    level: state.level,
    duration,
    questions: 12,
    correct: 12,
  });
}

function degreeMatches(actual, expected) {
  const a = pitchClass(normalizeNote(actual));
  const e = pitchClass(expected);
  return a.pitch !== undefined &&
    a.pitch === e.pitch &&
    a.minor === e.minor &&
    a.diminished === e.diminished;
}

function updateGap(question, correct, elapsed) {
  const data = loadData();
  const key = gapKey(question.key, question.degreeIndex);
  const previous = data.gaps[key] || 0;
  if (!correct) data.gaps[key] = Math.min(10, previous + 2);
  else if (elapsed > 4500) data.gaps[key] = Math.min(10, previous + 0.75);
  else if (previous > 0) data.gaps[key] = Math.max(0, previous - 1);
  if (data.gaps[key] === 0) delete data.gaps[key];
  saveData(data);
}

function submitDegree(event) {
  event.preventDefault();
  const answer = $("#degree-answer").value.trim();
  if (!answer) return;
  const question = state.questions[state.questionIndex];
  const expected = degreeAnswer(question.key, question.degreeIndex);
  const elapsed = performance.now() - state.questionStartedAt;
  const correct = degreeMatches(answer, expected);
  state.answers.push({ ...question, answer, expected, correct, elapsed });
  updateGap(question, correct, elapsed);

  if (!correct) {
    $("#degree-error").textContent = `Not quite — the answer is ${expected}.`;
    $("#degree-answer").select();
    setTimeout(() => advanceDegree(), 850);
  } else {
    advanceDegree();
  }
}

function advanceDegree() {
  state.questionIndex += 1;
  if (state.questionIndex < state.questions.length) {
    showQuestion();
    return;
  }
  const duration = stopTimer();
  const correct = state.answers.filter((answer) => answer.correct).length;
  completeAttempt({
    mode: state.mode,
    level: "major",
    duration,
    questions: state.questions.length,
    correct,
  });
  refreshWeakSpots();
}

function startCurrentMode() {
  if (state.mode === "circle") startCircle();
  else startDegrees();
}

function quitQuiz() {
  clearInterval(state.timerId);
  showTrainerView("setup");
}

function refreshWeakSpots() {
  const gaps = Object.entries(loadData().gaps).sort((a, b) => b[1] - a[1]);
  $("#weak-count").textContent = gaps.length;
  $("#weak-summary").textContent = gaps.length
    ? `${gaps.length} recall gap${gaps.length === 1 ? "" : "s"} queued. The weakest combinations will appear most often.`
    : "No active gaps. Complete a degree drill to calibrate your recall.";
  if (state.mode === "weak") $("#start-button").disabled = gaps.length === 0;
}

function getStreak(attempts) {
  const days = new Set(attempts.map((attempt) => localDate(attempt.timestamp)));
  let streak = 0;
  const cursor = new Date();
  if (!days.has(localDate(cursor))) cursor.setDate(cursor.getDate() - 1);
  while (days.has(localDate(cursor))) {
    streak += 1;
    cursor.setDate(cursor.getDate() - 1);
  }
  return streak;
}

function refreshSummary() {
  const data = loadData();
  const today = data.attempts.filter((attempt) => localDate(attempt.timestamp) === localDate());
  const bestFor = (mode) => {
    const values = today.filter((attempt) => attempt.mode === mode).map((attempt) => attempt.duration);
    return values.length ? formatTime(Math.min(...values)) : "—";
  };
  $("#today-sessions").textContent = `${today.length} sprint${today.length === 1 ? "" : "s"}`;
  $("#today-circle").textContent = bestFor("circle");
  const degreeValues = today.filter((attempt) => ["degrees", "weak"].includes(attempt.mode));
  $("#today-degrees").textContent = degreeValues.length
    ? formatTime(Math.min(...degreeValues.map((attempt) => attempt.duration)))
    : "—";
  const gapCount = Object.keys(data.gaps).length;
  $("#recall-health").textContent = gapCount === 0 ? "Fresh" : gapCount < 5 ? "Strong" : "Training";
  const streak = getStreak(data.attempts);
  $("#streak").textContent = `${streak} day streak`;
}

function filteredAttempts() {
  const filter = $("#results-filter").value;
  const attempts = loadData().attempts;
  return filter === "all" ? attempts : attempts.filter((attempt) => attempt.mode === filter);
}

function renderChart(attempts) {
  const canvas = $("#results-chart");
  const groups = Object.groupBy(attempts, (attempt) => localDate(attempt.timestamp));
  const points = Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([date, items]) => {
      const values = items.map((item) => item.duration);
      return { date, best: Math.min(...values), median: median(values), worst: Math.max(...values) };
    });
  $("#chart-empty").hidden = points.length > 0;
  canvas.hidden = points.length === 0;
  if (!points.length) return;

  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const context = canvas.getContext("2d");
  context.scale(ratio, ratio);
  context.clearRect(0, 0, width, height);
  const padding = { top: 20, right: 18, bottom: 38, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const max = Math.max(...points.map((point) => point.worst), 1000) * 1.12;

  context.font = "12px Inter, system-ui";
  context.fillStyle = "#7d7d88";
  context.strokeStyle = "rgba(255,255,255,.08)";
  context.lineWidth = 1;
  for (let index = 0; index <= 4; index += 1) {
    const y = padding.top + (plotHeight / 4) * index;
    context.beginPath();
    context.moveTo(padding.left, y);
    context.lineTo(width - padding.right, y);
    context.stroke();
    context.fillText(formatTime(max * (1 - index / 4)), 0, y + 4);
  }

  const x = (index) =>
    padding.left + (points.length === 1 ? plotWidth / 2 : (plotWidth * index) / (points.length - 1));
  const y = (value) => padding.top + plotHeight - (value / max) * plotHeight;
  [
    ["worst", "#6c6878", 1.5],
    ["median", "#f2ad5e", 2],
    ["best", "#dbff64", 3],
  ].forEach(([field, color, lineWidth]) => {
    context.beginPath();
    context.strokeStyle = color;
    context.lineWidth = lineWidth;
    context.lineJoin = "round";
    points.forEach((point, index) => {
      const method = index ? "lineTo" : "moveTo";
      context[method](x(index), y(point[field]));
    });
    context.stroke();
  });
  points.forEach((point, index) => {
    const date = new Date(`${point.date}T12:00:00`);
    context.fillStyle = "#7d7d88";
    context.textAlign = "center";
    context.fillText(`${date.getMonth() + 1}/${date.getDate()}`, x(index), height - 12);
  });
  context.textAlign = "start";
}

function modeLabel(mode) {
  return mode === "circle" ? "Circle sprint" : mode === "weak" ? "Weak spots" : "Degree drill";
}

function renderResults() {
  const attempts = filteredAttempts();
  const allAttempts = loadData().attempts;
  $("#stat-best").textContent = attempts.length
    ? formatTime(Math.min(...attempts.map((attempt) => attempt.duration)))
    : "—";
  $("#stat-total").textContent = attempts.length;
  $("#stat-answers").textContent = attempts.reduce((total, attempt) => total + attempt.questions, 0);
  $("#stat-streak").textContent = `${getStreak(allAttempts)} days`;
  $("#history-list").innerHTML = attempts.length
    ? [...attempts]
        .reverse()
        .slice(0, 20)
        .map((attempt) => {
          const date = new Date(attempt.timestamp);
          const accuracy = attempt.mode === "circle" ? "Perfect" : `${attempt.correct}/${attempt.questions}`;
          return `<article class="history-row">
            <div class="history-icon">${attempt.mode === "circle" ? "○" : "Ⅲ"}</div>
            <div><strong>${modeLabel(attempt.mode)}</strong><small>${date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })} · ${date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}</small></div>
            <span>${accuracy}</span><strong>${formatTime(attempt.duration)}</strong>
          </article>`;
        })
        .join("")
    : '<div class="empty-history">No attempts yet.</div>';
  renderChart(attempts);
}

$$(".nav-link").forEach((button) => button.addEventListener("click", () => showPage(button.dataset.page)));
$$(".mode-tab").forEach((button) => button.addEventListener("click", () => selectMode(button.dataset.mode)));
$$(".level-card").forEach((button) =>
  button.addEventListener("click", () => {
    state.level = button.dataset.level;
    $$(".level-card").forEach((item) => item.classList.toggle("selected", item === button));
  }),
);
$$("[data-action='quit']").forEach((button) => button.addEventListener("click", quitQuiz));
$("#start-button").addEventListener("click", startCurrentMode);
$("#circle-form").addEventListener("submit", submitCircle);
$("#degree-form").addEventListener("submit", submitDegree);
$("#again-button").addEventListener("click", startCurrentMode);
$("#view-results").addEventListener("click", () => showPage("results"));
$("#results-filter").addEventListener("change", renderResults);
$("#clear-results").addEventListener("click", () => {
  if (confirm("Clear all saved attempts and weak-spot data?")) {
    saveData({ attempts: [], gaps: {} });
    renderResults();
    refreshSummary();
    refreshWeakSpots();
  }
});
window.addEventListener("resize", () => state.page === "results" && renderChart(filteredAttempts()));
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !$("#setup-view").hidden && event.target.tagName !== "SELECT") {
    event.preventDefault();
    startCurrentMode();
  }
});

refreshSummary();
refreshWeakSpots();
