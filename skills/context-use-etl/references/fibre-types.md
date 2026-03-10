# Available Fibre Types

Quick reference for choosing the right payload model from
`context_use/etl/payload/models.py`.

## Activities (user actions)

| Fibre class | `fibreKind` | AS `type` | Use case |
|-------------|-------------|-----------|----------|
| `FibreSendMessage` | `SendMessage` | `Create` | User sent a message (chat, DM) |
| `FibreReceiveMessage` | `ReceiveMessage` | `Create` | User received a message |
| `FibreCreateObject` | `CreateObject` | `Create` | User created media (story, reel, post) |
| `FibreViewObject` | `ViewObject` | `View` | User viewed content (post, video, page) |
| `FibreLike` | `Reaction` | `Like` | User liked content |
| `FibreDislike` | `Reaction` | `Dislike` | User disliked content |
| `FibreComment` | `Comment` | `Create` | User commented on content |
| `FibreSearch` | `Search` | `View` | User performed a search |
| `FibreAddObjectToCollection` | `AddObjectToCollection` | `Add` | User saved/bookmarked content |
| `FibreFollowedBy` | `FollowedBy` | `Follow` | Someone followed the user |
| `FibreFollowing` | `Following` | `Follow` | User followed someone |

## Objects (embedded in activities)

| Fibre class | `fibreKind` | AS `type` | Use case |
|-------------|-------------|-----------|----------|
| `FibreTextMessage` | `TextMessage` | `Note` | A chat message body |
| `FibreImage` | `Image` | `Image` | An image |
| `FibreVideo` | `Video` | `Video` | A video |
| `FibrePost` | `Post` | `Note` | A social post |
| `FibreCollection` | `Collection` | `Collection` | A named collection/folder |
| `FibreCollectionFavourites` | `CollectionFavourites` | `Collection` | The default favourites collection |

## Common combinations

| Pattern | Activity | Object |
|---------|----------|--------|
| Chat message sent | `FibreSendMessage` | `FibreTextMessage` |
| Chat message received | `FibreReceiveMessage` | `FibreTextMessage` |
| Photo/video created | `FibreCreateObject` | `FibreImage` or `FibreVideo` |
| Post liked | `FibreLike` | `FibrePost` |
| Video watched | `FibreViewObject` | `FibreVideo` or `Page` |
| Search performed | `FibreSearch` | `Page` |
| Post saved | `FibreAddObjectToCollection` | `FibrePost` + `FibreCollection` |

## Memory config combinations

| Interaction pattern | Grouper | Prompt builder |
|---------------------|---------|----------------|
| Chat / DM conversations | `CollectionGrouper` | `ConversationMemoryPromptBuilder` |
| Visual media (stories, reels, posts) | `WindowGrouper` | `MediaMemoryPromptBuilder` |
| Likes, views, searches | Usually `memory=None` | — |
