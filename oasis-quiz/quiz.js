export const ROUND_SIZE = 10;

export function shuffle(items, random = Math.random) {
  const result = [...items];

  for (let index = result.length - 1; index > 0; index -= 1) {
    const target = Math.floor(random() * (index + 1));
    [result[index], result[target]] = [result[target], result[index]];
  }

  return result;
}

export function createRound(photos, random = Math.random) {
  const liams = photos.filter((photo) => photo.person === "Liam");
  const noels = photos.filter((photo) => photo.person === "Noel");

  if (liams.length < 6 || noels.length < 6) {
    throw new Error("The photo library needs at least six photos of each brother.");
  }

  const liamCount = 4 + Math.floor(random() * 3);
  const selected = [
    ...shuffle(liams, random).slice(0, liamCount),
    ...shuffle(noels, random).slice(0, ROUND_SIZE - liamCount),
  ];

  return shuffle(selected, random);
}

export function getResult(score) {
  if (score === 10) {
    return {
      title: "SUPERSONIC",
      copy: "Perfect. You know every parka, sideburn and suspicious squint.",
    };
  }

  if (score >= 8) {
    return {
      title: "MAD FER IT",
      copy: "Nearly flawless. You'd survive a backstage identity check.",
    };
  }

  if (score >= 5) {
    return {
      title: "SOME MIGHT SAY",
      copy: "A respectable score, but the eyebrows got the better of you.",
    };
  }

  return {
    title: "DEFINITELY MAYBE",
    copy: "You know it's a Gallagher. Which Gallagher remains a mystery.",
  };
}
