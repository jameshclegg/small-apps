import { createRound, getResult, ROUND_SIZE } from "./quiz.js";

const screens = {
  intro: document.querySelector("#intro-screen"),
  quiz: document.querySelector("#quiz-screen"),
  results: document.querySelector("#results-screen"),
};

const elements = {
  start: document.querySelector("#start-button"),
  replay: document.querySelector("#replay-button"),
  review: document.querySelector("#review-button"),
  questionNumber: document.querySelector("#question-number"),
  score: document.querySelector("#live-score"),
  progress: document.querySelector("#progress-bar"),
  photo: document.querySelector("#face-photo"),
  photoStatus: document.querySelector("#photo-status"),
  photoCredit: document.querySelector("#photo-credit"),
  finalScore: document.querySelector("#final-score"),
  resultTitle: document.querySelector("#result-title"),
  resultCopy: document.querySelector("#result-copy"),
  reviewGrid: document.querySelector("#review-grid"),
  creditsButton: document.querySelector("#credits-button"),
  creditsDialog: document.querySelector("#credits-dialog"),
  closeCredits: document.querySelector("#close-credits"),
  creditsList: document.querySelector("#credits-list"),
};

const answerButtons = [...document.querySelectorAll(".answer-button")];
let library = [];
let round = [];
let answers = [];
let currentIndex = 0;
let score = 0;
let acceptingAnswer = false;

function showScreen(name) {
  Object.entries(screens).forEach(([key, screen]) => {
    screen.classList.toggle("active", key === name);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function startRound() {
  round = createRound(library);
  answers = [];
  currentIndex = 0;
  score = 0;
  elements.score.textContent = "0";
  elements.reviewGrid.hidden = true;
  elements.review.textContent = "Review answers";
  showScreen("quiz");
  renderQuestion();
}

function renderQuestion() {
  const photo = round[currentIndex];
  acceptingAnswer = true;
  elements.questionNumber.textContent = String(currentIndex + 1).padStart(2, "0");
  elements.progress.style.width = `${((currentIndex + 1) / ROUND_SIZE) * 100}%`;
  elements.photo.classList.add("loading");
  elements.photo.src = photo.src;
  elements.photoCredit.href = photo.source;
  elements.photoCredit.textContent = `${photo.artist} · ${photo.license}`;
  elements.photoStatus.className = "photo-status";
  elements.photoStatus.textContent = "";
  answerButtons.forEach((button) => {
    button.disabled = false;
    button.classList.remove("correct", "wrong");
  });
}

function answer(choice) {
  if (!acceptingAnswer) return;
  acceptingAnswer = false;

  const photo = round[currentIndex];
  const correct = choice === photo.person;
  if (correct) score += 1;

  answers.push({ photo, choice, correct });
  elements.score.textContent = String(score);
  elements.photoStatus.textContent = correct ? "CORRECT" : `IT'S ${photo.person.toUpperCase()}`;
  elements.photoStatus.classList.add("visible", correct ? "correct" : "wrong");

  answerButtons.forEach((button) => {
    button.disabled = true;
    if (button.dataset.answer === photo.person) button.classList.add("correct");
    if (button.dataset.answer === choice && !correct) button.classList.add("wrong");
  });

  window.setTimeout(() => {
    currentIndex += 1;
    if (currentIndex < ROUND_SIZE) {
      renderQuestion();
    } else {
      showResults();
    }
  }, 950);
}

function showResults() {
  const result = getResult(score);
  elements.finalScore.textContent = String(score);
  elements.resultTitle.textContent = result.title;
  elements.resultCopy.textContent = result.copy;
  renderReview();
  showScreen("results");
}

function renderReview() {
  elements.reviewGrid.replaceChildren(
    ...answers.map(({ photo, choice, correct }, index) => {
      const item = document.createElement("article");
      const image = document.createElement("img");
      const details = document.createElement("div");
      const status = document.createElement("span");
      const answer = document.createElement("strong");

      item.className = `review-item ${correct ? "correct" : "wrong"}`;
      image.src = photo.src;
      image.alt = `${photo.person} Gallagher`;
      status.textContent = `${String(index + 1).padStart(2, "0")} · ${
        correct ? "Correct" : `You said ${choice}`
      }`;
      answer.textContent = photo.person;
      details.append(status, answer);
      item.append(image, details);
      return item;
    }),
  );
}

function renderCredits() {
  elements.creditsList.replaceChildren(
    ...library.map((photo) => {
      const credit = document.createElement("p");
      const id = document.createElement("strong");
      const title = document.createElement("span");
      const artist = document.createElement("span");
      const license = document.createElement("a");

      id.textContent = photo.id.toUpperCase();
      title.textContent = photo.title;
      artist.textContent = photo.artist;
      license.textContent = photo.license;
      license.href = photo.source;
      license.target = "_blank";
      license.rel = "noreferrer";
      credit.append(id, title, artist, license);
      return credit;
    }),
  );
}

async function loadLibrary() {
  const response = await fetch("photos.json");
  if (!response.ok) throw new Error("Could not load the photo library.");
  library = await response.json();
  renderCredits();
  elements.start.disabled = false;
}

elements.start.disabled = true;
elements.start.addEventListener("click", startRound);
elements.replay.addEventListener("click", startRound);
answerButtons.forEach((button) => {
  button.addEventListener("click", () => answer(button.dataset.answer));
});
elements.photo.addEventListener("load", () => elements.photo.classList.remove("loading"));
elements.review.addEventListener("click", () => {
  elements.reviewGrid.hidden = !elements.reviewGrid.hidden;
  elements.review.textContent = elements.reviewGrid.hidden ? "Review answers" : "Hide answers";
});
elements.creditsButton.addEventListener("click", () => elements.creditsDialog.showModal());
elements.closeCredits.addEventListener("click", () => elements.creditsDialog.close());
elements.creditsDialog.addEventListener("click", (event) => {
  if (event.target === elements.creditsDialog) elements.creditsDialog.close();
});

document.addEventListener("keydown", (event) => {
  if (!screens.quiz.classList.contains("active")) return;
  if (event.key.toLowerCase() === "l") answer("Liam");
  if (event.key.toLowerCase() === "n") answer("Noel");
});

loadLibrary().catch((error) => {
  elements.start.textContent = error.message;
});
