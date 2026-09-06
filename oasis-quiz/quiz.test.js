import assert from "node:assert/strict";
import test from "node:test";
import { createRound, getResult, shuffle } from "./quiz.js";

const photos = [
  ...Array.from({ length: 30 }, (_, index) => ({ id: `liam-${index}`, person: "Liam" })),
  ...Array.from({ length: 30 }, (_, index) => ({ id: `noel-${index}`, person: "Noel" })),
];

test("createRound returns ten unique photos with four to six Liams", () => {
  for (let index = 0; index < 100; index += 1) {
    const round = createRound(photos);
    const liamCount = round.filter((photo) => photo.person === "Liam").length;

    assert.equal(round.length, 10);
    assert.equal(new Set(round.map((photo) => photo.id)).size, 10);
    assert.ok(liamCount >= 4 && liamCount <= 6);
  }
});

test("createRound rejects an incomplete library", () => {
  assert.throws(() => createRound(photos.slice(0, 5)), /at least six/);
});

test("shuffle does not mutate its input", () => {
  const original = [1, 2, 3];
  shuffle(original, () => 0);
  assert.deepEqual(original, [1, 2, 3]);
});

test("getResult returns the perfect-score verdict", () => {
  assert.equal(getResult(10).title, "SUPERSONIC");
});
