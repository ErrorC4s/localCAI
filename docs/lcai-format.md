# `.lcai.json`: the localCAI interchange format (v1)

The browser extension writes this; `localcai import` reads it with **no guessing**.
Everything else (official exports, CAI Tools, Wilds) is converted on a best-effort basis.

```jsonc
{
  "format": "localcai",
  "version": 1,
  "exported_at": "2026-11-02T01:45:00Z",
  "exporter": { "name": "localCAI extension", "version": "0.1.0", "source": "character.ai" },

  "characters": [
    {
      "id": "abc123",                 // source-platform id
      "name": "Luna",
      "tagline": "A sleepy moon witch",
      "description": "…",
      "greeting": "*yawns* Oh, {{user}}…",
      "alternate_greetings": [],
      "definition": "{{user}}: Hi\n{{char}}: …",   // "" when not available to this user
      "definition_withheld": false,   // true = the character's creator kept it private
      "avatar_url": "https://…",
      "creator": "alex",
      "is_own": true                  // created by the exporting user
    }
  ],

  "chats": [
    {
      "id": "chat-uuid",
      "character_id": "abc123",
      "character_name": "Luna",
      "title": "Moon night",
      "created": "2026-10-01T10:00:00Z",
      "user_name": "Alex",
      "memories": [                   // C.ai's own chat memory ("conversation facts")
        { "about": "Luna", "category": "likes", "value": "Earl Grey tea" }
      ],
      "turns": [                      // oldest first
        {
          "id": "turn-uuid",
          "created": "2026-10-01T10:01:00Z",
          "author": { "name": "Luna", "is_user": false },
          "pinned": false,
          "candidates": ["Earl Grey, obviously.", "Fine, chamomile."],
          "primary": 0                // index into candidates of the chosen reply
        }
      ]
    }
  ],

  "personas": [                       // the user's own personas, if captured
    { "name": "Alex", "description": "…" }
  ]
}
```

## Rules
- `turns` are **oldest first**.
- `candidates[primary]` is the reply that was shown in the chat. The others become swipes.
- `pinned: true` turns and chat `memories` become constant lorebook entries on import.
- Private definitions of **other creators'** characters are never exported (`definition: ""`,
  `definition_withheld: true`).
- Unknown extra fields must be ignored by readers. Bump `version` only for breaking changes.
