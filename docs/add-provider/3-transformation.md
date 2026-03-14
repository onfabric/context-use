# Step 3: Transformation (PR 3)

Transformation answers: *what does this record mean?* It maps each record onto the appropriate fibre model and produces a `ThreadRow`.

## Implementing `transform`

`transform(record, task) → ThreadRow`:

- Map the record's fields onto the appropriate fibre model. **Use all the information the record carries** — do not silently drop fields that have a place in the payload.
- Apply semantic logic where needed: detect system-generated strings, compose the human-readable content field, choose the right fibre type for variation within the pipe.
- **Do not introduce fields that have no basis in the record.** If a fibre field cannot be populated from the record, leave it unset rather than guessing.
- When building a `Collection` context (e.g. for conversations or threads), set its `id` to the **real, user-facing URL** of the conversation or collection whenever possible. If the archive does not expose the public identifier, construct a stable synthetic URL from the data that is available and **add a comment** explaining that the URL is synthetic and why.
- Build the fibre payload and return a `ThreadRow`.

## Payload (fibre) models

Fibre models in `context_use/etl/payload/models.py` are the shared vocabulary of what happened. Most pipes will use one of these:

| Fibre | When to use |
|---|---|
| `FibreSendMessage` | User sent a message to someone |
| `FibreReceiveMessage` | User received a message from someone |
| `FibreCreateObject` | User posted an image or video |
| `FibreViewObject` | User viewed a post, video, or reel |
| `FibreAddObject` | User added something to a collection (liked, saved) |
| `FibreFollowActor` / `FibreFollowedByActor` | Follow/follower events |
| `FibreCommentObject` | User commented on something |

**Do not add a new fibre type to accommodate small differences between records from the same pipe.** Variation within a pipe — a plain text message, a story reply, a shared post — is handled in `transform()` through content composition, not by creating new types. Fibre types represent categorically different kinds of interaction. If you think you need a new type, first check whether an existing one covers the semantic meaning; explain your reasoning in the PR.

## Extending payload models

To add a genuinely new fibre type: subclass the appropriate AS base (`Activity` or `Object`) with `_BaseFibreMixin`, add a `fibreKind` literal field, implement `_get_preview()`, call `model_rebuild()` at module level, and add it to the `FibreByType` union at the bottom of the file. The models have to be compliant with [Activity Streams 2.0](https://www.w3.org/TR/activitystreams-core/).

## Writing previews

`payload.get_preview(provider)` returns a short natural-language string stored in `ThreadRow.preview`. It is the primary input the memory pipeline feeds to the LLM — if the preview is weak, the generated memories will be weak.

A good preview reads like a sentence a person would say:

> Sent message "hey, when are you free?" to alice on Instagram
> Received message "Sure! Here are a few options..." from assistant on ChatGPT
> Posted image on Instagram with caption: "Team at work"
> Viewed page "Best pasta recipes - BBC Good Food" via Google
> Liked post by janedoe on Instagram
> Commented "this is amazing!" on alice's post on Instagram
> Searched "best restaurants nearby" on Google
> Saved to "Trip Ideas" post by traveler on Instagram
> Following bob on Instagram
> Followed by alice on Instagram

Rules for `_get_preview`:

- **Build the preview exclusively from the fibre payload fields** — never from the record, the raw source, or any external state. The payload is the only input available at preview time.
- Write a complete, human-readable sentence — not a label or metadata string.
- Include the provider name.
- Include actor/target names when known.
- For message content, truncate at ~100 characters with `...`.
- Omit technical identifiers: no IDs, URLs, or timestamps.

If the payload fields are too sparse to produce a meaningful sentence, that is a signal that `transform` is not populating the fibre model fully enough — fix the transformation, not the preview.

> **⏸ Stop here.** Open a PR with the `transform()` implementation, `declare_interaction()`, package imports, and the full `PipeTestKit` suite. Request feedback.
