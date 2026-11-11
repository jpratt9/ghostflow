# Character mentions on the migrated image composer (#723, PR #979) — 2026-10-13

**Question.** Can the `flow.google.com` image composer attach a character through the `@`
picker, and how does the driver tell the character apart from media that shares its name?

**Setup.** A contributor account served `flow.google.com`. Scripts (all $0; every submit
is aborted in the browser): `scripts/dev/spike_picker_entity_marker.py`,
`scripts/dev/spike_picker_chip_removal.py`, `scripts/dev/spike_image_submit_references.py`.
Live runs and the e2e are in PR #979's body.

## Observed

| Probe | Result |
|---|---|
| Option subtree, attributes, thumbnail grid membership, picker replies (`spike_picker_entity_marker.py`) | Character and media options are **the same** `button.asset-item[role=option]` with the same subtree. Only a translated subtitle ("Personaje"/"Imagen") differs. Grid membership is no marker (the grid is lazy); the search runs client-side |
| Ranking | An image captioned "Sussy cooking…" ranked **above** the character "Sussy". Flow does not put characters first |
| Each option's `.asset-title` | The asset's own name: user data, not a UI label |
| A click on an option | Commits nothing. ArrowDown + Enter does |
| Chip removal (`spike_picker_chip_removal.py`) | A commit inserts chip + space; two Backspaces remove the chip from the prompt |
| Submit body after a deleted media chip (`spike_image_submit_references.py --trial-media 1`) | The deleted media id **still rides** the `ogiZ0b` body next to the character. Deleting a chip does not detach its reference |
| `ogiZ0b` request entry | Media references at index **2**, characters at index **10** |

## Reading

- Pick the one option whose trimmed `.asset-title` equals the name, reach it with
  ArrowDown, and commit it with a single Enter. Never commit on trial: a deleted chip
  still rides the submit.
- Refuse (exit 32) when zero or several options carry the exact title. A character and a
  media asset with the same title cannot be told apart before a commit.
- Read the committed chip back: its kind must be `entity`, and its text must equal the
  name. A character found by name has no id to check, so the chip's text is the identity
  proof.
- Hold the submit body to **exactly** the requested media (slot 2) plus the committed
  characters (slot 10). Anything missing or extra aborts it before Flow acts.

## Not measured

- How the picker ranks options in other locales. Anchoring on `.asset-title` does not
  depend on ranking.
- The labs host. No account here is served labs.
- Video. Its migrated path still refuses characters (exit 36).
