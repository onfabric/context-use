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
