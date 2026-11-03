# Promotion kit: localCAI

Ready-to-post texts for telling people about localCAI. Store submission texts are in `listing.md`.

**Ground rules**
- Say you made it ("I made…"). Most communities remove undisclosed self-promotion.
- Read each community's rules first. Some only allow self-promotion on certain days or in a pinned thread.
- Don't post links in Character.AI's own Discord, forums or r/CharacterAI: they usually remove posts about
  exporting or about other apps, and AutoMod blocks the links.
- Only show test characters (Luna, Rex, Mina…) in screenshots and videos, never real chats.
- Post once per community. Answer comments, especially in the first hour.
- Best timing: when Character.AI has an outage, a filter change or a rule change, people go looking for
  alternatives and for ways to back up their chats.

---

## 1. r/SillyTavernAI, r/LocalLLaMA (people who already run local models)

**Title:** I made a free tool to move your Character.AI chats (full history, pins, memories) into local models

**Body:**
> I made localCAI, a free and open-source (MIT) tool for people leaving Character.AI or who just want a backup.
>
> **The browser extension** (Chrome / Edge / Firefox) saves your own C.ai chats to a file: the full history (it pages through tens of thousands of messages in about a minute), swipes, pinned messages, chat memories, your own characters and personas. The format is documented, and it also exports standard character cards and SillyTavern-style .jsonl chats, so you can take everything to SillyTavern if you prefer.
>
> **The desktop app** (Windows) lets you continue those chats on a local model. It has a built-in llama.cpp engine, so there's nothing else to install: pick a model, it downloads it, checks it fits your GPU, and you keep chatting.
>
> A few things I worked on for roleplay quality with small models:
> - A "scene memory" note after each reply (where everyone is, what's still going on, mood), so 8B models stop forgetting ongoing actions
> - An optional in-character check that rewrites replies where the character admits being an AI or knows things outside its world
> - It learns reply length and style from your old C.ai history
>
> Everything runs on your computer. No accounts, no servers, no analytics.
>
> GitHub: https://github.com/ErrorC4s/localCAI
>
> It's an independent project, not affiliated with Character.AI. Feedback and bug reports welcome: I'm especially interested in which models people use and how they run on their GPUs.

---

## 2. Communities of people leaving Character.AI (less technical)

**Title:** Made a free way to keep your Character.AI chats and keep talking to your characters offline

**Body:**
> I didn't want to lose years of chats, so I made localCAI. It's free and open source.
>
> 1. Install the browser extension, open a chat on character.ai, click **Load full history**, then **Export**. You get a file with your whole chat, pins and memories.
> 2. Open the localCAI app (Windows), drag the file in, and keep chatting with the same character. It runs on your own computer, so no filter changes, no outages, and nobody else sees your chats.
>
> You'll want a graphics card with about 6 GB or more for good speed. The app picks a model that fits and tells you if it'll be slow.
>
> Link: https://github.com/ErrorC4s/localCAI
>
> Not affiliated with Character.AI, and it only exports your own chats. Happy to help if you get stuck!

---

## 3. Short version (Discord servers, comments, replies)

> If you want to back up your C.ai chats or keep them going offline: I made localCAI, free and open source. A browser extension exports your full history, pins and memories, and a Windows app continues the chat on a local AI. Nothing leaves your computer. https://github.com/ErrorC4s/localCAI

---

## 4. Short demo video (30–60 s, YouTube Shorts / TikTok, also as a GIF in the README)

Use a test character and test persona only. Vertical 9:16 for Shorts/TikTok, crop to 16:9 for the README.

| Seconds | On screen | Caption |
|---|---|---|
| 0–3 | A long C.ai chat scrolling | "Don't lose your Character.AI chats" |
| 3–12 | Extension popup → Load full history, counter going up → Export | "Save your whole history in about a minute" |
| 12–20 | Drag the file into localCAI, the character appears with its chat | "Drop it into localCAI" |
| 20–35 | Send a message, the reply streams in | "Keep chatting on your own PC" |
| 35–45 | Model picker showing "fits your GPU" | "Free · offline · nothing uploaded" |
| 45–50 | GitHub page | "localCAI, link in bio" |

---

## 5. GitHub repository settings

So people find it by searching GitHub:

- **Description:** `Save your Character.AI chats and keep chatting with your characters on a local AI. Browser extension + Windows app with a built-in llama.cpp engine.`
- **Topics:** `character-ai`, `characterai`, `roleplay`, `chatbot`, `local-llm`, `llama-cpp`, `sillytavern`, `character-card`, `browser-extension`, `chat-export`
- Put a demo GIF at the top of the README, and the store links once the extension is approved.

---

## 6. Order

1. GitHub description and topics (5 minutes)
2. Submit the extension to Firefox Add-ons (free) and the Chrome Web Store (`listing.md`)
3. Record the demo GIF/video
4. Post #1 in r/SillyTavernAI, a few days later in r/LocalLLaMA
5. Post #2 in communities of people leaving C.ai, ideally right after a C.ai outage or rule change
