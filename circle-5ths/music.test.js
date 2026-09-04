import test from "node:test";
import assert from "node:assert/strict";
import {
  answersMatch,
  circleFrom,
  degreeAnswer,
  median,
  normalizeNote,
  splitAnswer,
} from "./music.js";

test("builds the circle in both directions from any key", () => {
  assert.deepEqual(circleFrom("G", "fifths", "major").slice(0, 4), ["G", "D", "A", "E"]);
  assert.deepEqual(circleFrom("G", "fourths", "major").slice(0, 4), ["G", "C", "F", "Bb"]);
  assert.deepEqual(circleFrom("Em", "fourths", "minor").slice(0, 3), ["Em", "Am", "Dm"]);
});

test("accepts enharmonic and unicode answers", () => {
  assert.equal(normalizeNote("f♯m"), "F#m");
  assert.deepEqual(splitAnswer("C, G D; A"), ["C", "G", "D", "A"]);
  assert.equal(answersMatch(["F#", "Db", "Bbm"], ["Gb", "C#", "A#m"]), true);
});

test("returns correctly spelled diatonic chords", () => {
  assert.equal(degreeAnswer("G", 2), "Bm");
  assert.equal(degreeAnswer("F", 3), "Bb");
  assert.equal(degreeAnswer("F#", 6), "E#°");
});

test("calculates median for odd and even sets", () => {
  assert.equal(median([9, 2, 4]), 4);
  assert.equal(median([10, 2, 4, 8]), 6);
});
