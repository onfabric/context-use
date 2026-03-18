## [0.9.0] - 2026-03-18

### 🚀 Features

- Add /v1/responses API proxy support alongside /v1/chat/completions (#228)

### 🐛 Bug Fixes

- Proxy rich logging (#231)

### ⚙️ Miscellaneous Tasks

- Skip release commits in changelog (#232)

## [0.8.0] - 2026-03-18

### 🚀 Features

- Generate session id if not set in the header (#229)
- Add `--upstream-url` to the proxy command (#225)
- Filters for memory generation (#226)
- Context proxy as first class citizen (#221)
- Semantic facets for memories (#222)
- *(test)* Add payload test to pipe test kit (#223)

### 🐛 Bug Fixes

- Debug log request and more details on memories ops (#227)

## [0.7.0] - 2026-03-17

### 🚀 Features

- Add Netflix provider with 6 interaction types (#209)
- Add Airbnb provider including additional scopes (#210)
- Resolve asset_uri in pipe.run (#217)

### 🐛 Bug Fixes

- Use InstagramBaseModel in media pipe (#219)

## [0.6.1] - 2026-03-16

### 🐛 Bug Fixes

- *(chatgpt)* Update schema based on different types of archives (#215)

### ⚙️ Miscellaneous Tasks

- Group dependencies changes in changelog (#214)

## [0.6.0] - 2026-03-16

### 🚀 Features

- Proxy stores threads and generates memories in the background (#206)
- Add user profile as context to memory generation prompt (#205)

### 🐛 Bug Fixes

- Upsert memory embeddings (#207)

### 💼 Other

- [**breaking**] Downgrade `google-adk` to >=1.22 (#212)

### 🧪 Testing

- Move tests using llm to evals (#208)
- Basic memory unit and integration tests (#204)

## [0.5.0] - 2026-03-15

### 🚀 Features

- Banner on root and help commands (#199)
- Context proxy (#193)
- Claude conversations with autogen schema guidelines (#194)
- Memories from agent and human conversations (#177)

### 🐛 Bug Fixes

- *(proxy)* Do not enrich request if `max_tokens` is below a threshold (#202)
- Parse ig story likes with v0 pipe (#185)
- Update ig etls according to guidelines (#180)

### 🚜 Refactor

- Chatgpt conversations with autogen schema (#198)
- Google interactions with autogen schema (#195)
- Split pipes, schemas and records into separate files (#189)
- Chatgpt etl according to guidelines (#188)
- Input file items schema validation for google (#181)
- Input file items schema validation for claude (#186)
- Input file items schema validation for chatgpt (#183)
- Input file schema validation for ig (#182)
- *(test)* Uniform provider etls testing (#175)

### 📚 Documentation

- Add demo to readme (#201)
- Guidelines for automatic schema generation from exports (#192)
- Update guidelines for input schema validation (#187)
- Simplify provider guidelines for new etls (#178)
- Skill.md ai optimization (#176)

### ⚡ Performance

- Stream ig interactions in etl (#184)

### ⚙️ Miscellaneous Tasks

- Update readme (#191)

## [0.4.0] - 2026-03-11

### 🚀 Features

- Etl to process IG DMs (#173)
- Memory batch status spinners (#170)

### 📚 Documentation

- Agents skill (#165)

### ⚡ Performance

- Improve cli startup speed (#167)

### ⚙️ Miscellaneous Tasks

- Check build is working across python versions (#169)
- Simplify agents.md and extract the guide to add a provider (#164)

## [0.3.1] - 2026-03-11

### ⚙️ Miscellaneous Tasks

- Remove data folder placeholder (#163)

### ◀️ Revert

- Bring back future annotations (#166)

## [0.3.0] - 2026-03-10

### 🚀 Features

- [**breaking**] Only require zip path on quick mode (#151)
- Add ETL for instagram_posts interaction type (#159)
- [**breaking**] Change data folder to `context-use-data` (#152)
- Memories commands prompt for api key if not set (#147)
- Add --version command to cli (#144)

### 🐛 Bug Fixes

- Generalize archive path pattern for post comments (#160)
- Rename data folder where missing (#158)
- Do not sleep after batch on quickstart (#150)

### 🚜 Refactor

- Remove future annotations imports where not needed (#154)

### 📚 Documentation

- Update readme (#161)

### ⚙️ Miscellaneous Tasks

- Run check PR title on all PR events (#157)
- Pypi page details (#155)
- Ensure conventional commits (#156)
- Update uv.lock on prepare-release (#145)

## [0.2.0] - 2026-03-09

### 🚀 Features

- [**breaking**] Remove mcp (#138)
- [**breaking**] Adk is now required (#136)
- [**breaking**] Remove quickstart command (#134)
- Make db path configurable (#133)
- [**breaking**] Remove in-memory store (#132)
- [**breaking**] Remove postgres (#131)
- [**breaking**] Remove set-store config command (#130)
- [**breaking**] Use sqlite for all commands (#129)
- [**breaking**] Sqlite store as default (#128)

### 📚 Documentation

- Update readme (#141)

### ⚙️ Miscellaneous Tasks

- Remove `v` prefix from generate version (#140)
- Mit license (#142)
- Update readme (#137)
- Make sure we don't bump major when major is 0 (#135)

## [0.1.0] - 2026-03-09

First release of context-use.
