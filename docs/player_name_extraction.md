# Player name and VEKN ID extraction

Describes how the pipeline resolves the winner's name and VEKN ID from the VEKN
event calendar page, and when `unconfirmed_winner` is set.

---

## fetch_event_name vs fetch_event_winner

These two functions both fetch the event page but return different things:

| Function | Returns | Log prefix on failure |
| - | - | - |
| `fetch_event_name` | Tournament title (e.g. `"Standard Constructed"`) | `"Could not extract event title from event page"` |
| `fetch_event_winner` | `(player_name, vekn_id)` tuple — see below | `"No winner table found in event page"` |

The word "name" in the first function refers to the *event* name, not a player name.
If you see `"Could not extract event title"` in the logs, the tournament name was not
overridden from the calendar — the winner and routing are unaffected.

---

## fetch_event_winner — return type

```python
fetch_event_winner(client, event_url, delay) -> tuple[str, int | None] | None
```

- **`None`** — the standings table is absent from the event page (results not yet
  published). The caller sets `unconfirmed_winner`.
- **`(name, vekn_id)`** — winner found. `vekn_id` is the integer extracted from the
  player's profile link (`/event-calendar/player/<id>`) in the standings row, or
  `None` if the cell has no link.

The function never returns a plain string. All callers and test mocks must handle
the tuple form.

---

## Pipeline steps 3–4: winner resolution

`pipeline._check_calendar_winner` (step 3):

1. Calls `fetch_event_winner`.
2. If `None` → marks `calendar_winner_missing = True` (becomes `unconfirmed_winner` error).
3. Otherwise unpacks `(calendar_winner, calendar_vekn_id)`:
   - Overrides `tournament.winner` if it differs.
   - Sets `tournament.vekn_number` from `calendar_vekn_id` if not already set.

`pipeline._lookup_player` (step 4):

- Short-circuits immediately when `tournament.vekn_number is not None` — no registry
  lookup needed.
- Otherwise calls `fetch_player(name)` to obtain the canonical name and VEKN number.
  This lookup can fail (return `None`) when the name is ambiguous in the registry.

---

## unconfirmed_winner semantics

`unconfirmed_winner` is set in **exactly two places**:

| Trigger | Meaning |
| - | - |
| `fetch_event_winner` returns `None` | Standings table absent — event results not published yet |
| `validator.error_types`: `not data.get("winner") or not data.get("vekn_number")` | Winner name or VEKN number could not be resolved |

The second trigger was historically reached when `fetch_player` returned `None` due to
ambiguous name matches (e.g., two players named "Alex Romano" in the registry). Since
`fetch_event_winner` now returns the VEKN ID directly from the standings link, this
case is avoided for any event that has published results — the standings link is
authoritative and unambiguous.

`unconfirmed_winner` should **not** appear for events where the standings table is
present and includes player links.

---

## Test mocks

Any test that mocks `fetch_event_winner` must return a tuple or `None`:

The patch target depends on which module uses the function:

```python
# pipeline tests (scrape / import commands)
patch(
  "channel_ten.pipeline.fetch_event_winner",
  return_value=("Jane Doe", None)
)
patch(
  "channel_ten.pipeline.fetch_event_winner",
  return_value=("Alex Romano", 5920001)
)
patch(
  "channel_ten.pipeline.fetch_event_winner",
  return_value=None
)

# validate command tests
patch(
  "channel_ten.cli.validate.fetch_event_winner",
  return_value=("Jane Doe", None)
)

# wrong — will raise TypeError when the caller unpacks
patch(
  "channel_ten.pipeline.fetch_event_winner",
  return_value="Jane Doe"
)
```
