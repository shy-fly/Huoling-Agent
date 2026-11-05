"""Read cell words without reordering decimal and uncertainty glyphs."""


def cellText(words: list[tuple], box: tuple | None) -> str:
    if box is None:
        return ""
    x0, y0, x1, y1 = box
    inside = [word for word in words if
              x0 <= (word[0] + word[2]) / 2 < x1 and y0 <= (word[1] + word[3]) / 2 < y1]
    inside.sort(key=lambda word: (word[5], word[6], word[7]))
    return " ".join(word[4] for word in inside)
