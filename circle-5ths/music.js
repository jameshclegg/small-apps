export const MAJOR_KEYS = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"];
export const MINOR_KEYS = ["Am", "Em", "Bm", "F#m", "C#m", "G#m", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm"];
export const ROMANS = ["I", "ii", "iii", "IV", "V", "vi", "vii°"];

const MAJOR_SCALES = {
  C: ["C", "D", "E", "F", "G", "A", "B"],
  G: ["G", "A", "B", "C", "D", "E", "F#"],
  D: ["D", "E", "F#", "G", "A", "B", "C#"],
  A: ["A", "B", "C#", "D", "E", "F#", "G#"],
  E: ["E", "F#", "G#", "A", "B", "C#", "D#"],
  B: ["B", "C#", "D#", "E", "F#", "G#", "A#"],
  "F#": ["F#", "G#", "A#", "B", "C#", "D#", "E#"],
  Db: ["Db", "Eb", "F", "Gb", "Ab", "Bb", "C"],
  Ab: ["Ab", "Bb", "C", "Db", "Eb", "F", "G"],
  Eb: ["Eb", "F", "G", "Ab", "Bb", "C", "D"],
  Bb: ["Bb", "C", "D", "Eb", "F", "G", "A"],
  F: ["F", "G", "A", "Bb", "C", "D", "E"],
};

const PITCH_CLASS = {
  C: 0, "B#": 0, "C#": 1, Db: 1, D: 2, "D#": 3, Eb: 3,
  E: 4, Fb: 4, "E#": 5, F: 5, "F#": 6, Gb: 6, G: 7,
  "G#": 8, Ab: 8, A: 9, "A#": 10, Bb: 10, B: 11, Cb: 11,
};

export function normalizeNote(value) {
  const cleaned = value.trim().replaceAll("♯", "#").replaceAll("♭", "b");
  if (!cleaned) return "";
  const match = cleaned.match(/^([a-gA-G])([#b]?)(m|°|dim)?$/);
  if (!match) return cleaned;
  const quality = match[3]?.toLowerCase() === "dim" ? "°" : (match[3] || "");
  return `${match[1].toUpperCase()}${match[2]}${quality}`;
}

export function pitchClass(value) {
  const normalized = normalizeNote(value);
  const minor = normalized.endsWith("m");
  const diminished = normalized.endsWith("°");
  const root = normalized.replace(/[m°]$/, "");
  return { pitch: PITCH_CLASS[root], minor, diminished };
}

export function splitAnswer(value) {
  return value
    .split(/[\s,;→]+/)
    .map(normalizeNote)
    .filter(Boolean);
}

export function circleFrom(key, direction, type) {
  const source = type === "minor" ? MINOR_KEYS : MAJOR_KEYS;
  const start = source.indexOf(key);
  const step = direction === "fifths" ? 1 : -1;
  return Array.from({ length: source.length }, (_, index) => {
    const position = (start + index * step + source.length) % source.length;
    return source[position];
  });
}

export function answersMatch(actual, expected) {
  if (actual.length !== expected.length) return false;
  return actual.every((answer, index) => {
    const a = pitchClass(answer);
    const e = pitchClass(expected[index]);
    return a.pitch !== undefined &&
      a.pitch === e.pitch &&
      a.minor === e.minor &&
      a.diminished === e.diminished;
  });
}

export function degreeAnswer(key, degreeIndex) {
  const root = MAJOR_SCALES[key][degreeIndex];
  if ([1, 2, 5].includes(degreeIndex)) return `${root}m`;
  if (degreeIndex === 6) return `${root}°`;
  return root;
}

export function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function randomItem(items) {
  return items[Math.floor(Math.random() * items.length)];
}
