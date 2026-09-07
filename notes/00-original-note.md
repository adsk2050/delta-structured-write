# 00 — The original handwritten note (verbatim transcription)

Source: handwritten page, transcribed 2026-09-07. `[unclear]` marks words that
could not be read confidently. Kept verbatim on purpose — everything else in
this directory is interpretation, and this is the thing being interpreted.

---

## Main note

> **We need to build something** in which instead of producing the whole JSON
> again & again we just produce part that's delta / changed and somehow still
> use **constrained decoding** structured output — or maybe after the JSON file
> is edited we check the full schema.
>
> → which no need to write full AS again. Problem is full AS can be as
> complicated as possible and c complicated as possible as well and can be
> anywhere in AS as well

## Left-side sketch

```text
AS =

{
  a: a
  b: b

  c: {
       p: p
       q: q
     }

  d: d
}
```

Two boxed partial-object examples appear on the left, roughly:

```text
c: {
  p: p
  q: q
}
```

and a second, similar nested-object sketch below it.

---

## Reading of the abbreviations

- **AS** — used both as the name of the JSON object in the sketch (`AS = { ... }`)
  and as the thing you would otherwise "write in full again". Read throughout
  this directory as **the full structured output object** (Answer Structure /
  Agent State — the note does not say which, and it does not change the problem).
- **delta** — the changed part only.
- **constrained decoding** — the standard term; used correctly in the note.

If "AS" was meant as something narrower, say so and the rest of the notes can be
re-pointed; nothing downstream depends on the expansion.
