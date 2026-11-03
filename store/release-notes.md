## localCAI v0.8.34 · Extractor 0.5.1

- Built-in engine: before loading a model, localCAI checks how much graphics memory is actually free (browsers, Discord and other apps use some too). If the model plus your context size wouldn't fit, the context is shrunk to the largest size that does, so the whole model stays on the GPU. Without this the driver quietly moved part of it into system memory and replies got 5-7x slower (measured on an 8B model with an 8 GB laptop GPU: 7.5 tokens/s at 8192 context, 51 at 6144). The engine chip shows when this happens (e.g. "ready · 6K context"); close some apps and reload the model to get the full context back. The engine log now records free VRAM at start.

### Earlier in v0.8.33

- Built-in engine: a model that fits on the graphics card goes fully on it again (much faster: 55-63 vs 10-11 tokens/s measured on an 8B model). Only a model that doesn't fit uses llama.cpp's --fit, which places layers by the card's free memory and keeps your context size.
- "(Continues)" / "[continued]" labels some models put between paragraphs are removed.

### Earlier in v0.8.31

- Importing a chat for a character that's already in your library no longer replaces its card with a bare one rebuilt from the chat: the description, personality, greeting, example dialogue, memories, rules and pronouns stay as they are, and the chat's pinned memories are added (without duplicates). Importing a new version of a card keeps the rules, pronouns and memories you set in the app, and the avatar if the new card has none.
- Re-importing a chat file that has no message ids saves it as a new chat instead of over the existing one (which you may have continued in localCAI).
- Scene memory notes are tied to the reply and the few messages before it, so the same short reply ("*nods* Okay.") at two points of a chat keeps two separate notes.
- Extractor 0.5.1: after Clear, Load full history starts over instead of saying it's already at the first message (or asks you to reload the page when it can't fetch directly).
- Releases are only published when the tests pass.

### Earlier in v0.8.30

- Scene memory now also notes the character's mood and how intense the moment is. The next reply keeps that mood unless something that just happened gives a reason to change it: a real reason (a surprise, a hurtful word, a climax, danger) can change it at once, otherwise it shifts gradually instead of flipping out of nowhere.
- Fixed doubled ";;" in scene notes.

### Earlier in v0.8.29

- Scene memory: after each reply, a one-line note of where everyone is and what's still going on (positions, ongoing actions, clothing) is made from the last 5 rounds plus the previous note, in the background. The next reply gets it, so actions that started a few replies ago aren't forgotten. Kept per reply, so regenerated or swiped replies never get a note that doesn't match. Settings → Scene memory (on by default).

### Earlier in v0.8.28

- Chat memory format: Automatic is back to 16-bit. 8-bit turned out slower when part of the model runs on the CPU (measured about 6.5 → 4.2 tokens/s on a 12B model with an 8 GB GPU). 8-bit is still in Settings for cards where it helps.

### Earlier in v0.8.27

- Faster replies when the model is a little too big for your graphics card: the chat memory (KV cache) is kept at 8-bit, about half the VRAM, so more of the model fits on the GPU. Replies read practically the same. Settings → Built-in engine → Chat memory format (Automatic / 8-bit / 16-bit); Automatic only uses 8-bit when the model doesn't fit otherwise.

### Earlier in v0.8.26

- Replies no longer end with the model reviewing itself ("[What the reply does:]", "Notes:", "(OOC: …)", "Analysis:" and the like): that part is cut off, and the hidden per-turn direction now tells the model to follow it silently instead of listing it back.

### Earlier in v0.8.25

- OOC guard: a rewrite that only moves the *actions* around while the character says the same words is dropped. Actions aren't reviewed, so it wasn't a real fix (no extra swipe, no "auto-fixed" badge).

### Earlier in v0.8.24

- Regenerating (↻ / ▶) now gives genuinely different versions: the model sees the start of the earlier versions and is asked for a clearly different take (actions, wording, direction), with a little more randomness. Long chats used to produce near-copies.

### Earlier in v0.8.23

- OOC guard now only reviews what the character *says*: *actions* and narration are left out of the check (and out of the length check), and a reply that is only action isn't checked at all.

### Earlier in v0.8.22

- OOC guard: if the rewrite comes out (nearly) the same as the first try, it's dropped: no duplicate reply and no misleading "auto-fixed" badge.

### Earlier in v0.8.21

**Staying in character, for every character**
- **World boundary:** every character is told it only knows what someone in its own world would know. Things from outside (other games, AI, tech the setting doesn't have) get an in-character reaction, and the character never turns into an assistant or admits to being an AI.
- **OOC guard** (on by default, ⚙ Settings): after each reply, the model double-checks it as a strict editor: AI talk, assistant behaviour, out-of-world knowledge, writing your actions, or a reply far longer than usual. If something's off, the reply is rewritten once; the first try stays one swipe back and the reply gets an "auto-fixed" badge explaining why. Adds a second or two.
- **New chats sound right from the first reply:** until a chat has its own history, the reply length follows the character card's greeting and example dialogue (so a quiet character answers in a line or two).
- **Rules that stick:** tick "Always do this" in ✨ to save an instruction as a permanent rule for that character; see and edit the rules in Edit.

### Earlier in v0.8.20

**Own icon set**
- All emoji in the app are replaced by localCAI's own line icons (engine, settings, background, edit, learn style, memory, pin, rewind, rewrite…). They look the same on every Windows version and follow the theme colours.

### Earlier in v0.8.19

**✨ Change a reply with an instruction**
- New ✨ button on the character's latest reply: type what should be different ("Shorter.", "She gets jealous.", "More teasing, less talking.", "讓她哭出來") and the reply is rewritten to follow it.
- The rewrite is added as another version, so the original is still there behind ◀ ▶.
- Your last few instructions are kept as one-click chips.

### Earlier in v0.8.18

**The character can take the lead**
- The character now builds on its own last action to make the next move, instead of only reacting — while still never inventing what *you* do.
- Hand the scene over any time with "your turn", "go on", "take the lead", "妳來", "繼續", or just "...": the character continues from where things stand and moves one clear step forward.
- New ⚙ Settings → "Who leads the scene": Auto (default), Me (the character mostly reacts), or The character (it makes the next move every turn).

### Earlier in v0.8.17

**Scenes don't jump any more**
- Each turn the model is reminded where the last reply left off (the last actions in it), and told to continue from there: same place, same positions, nothing skipped.
- When you only *say* something (no *action*), the model is told you did nothing new physically, so it stops inventing moves for you ("your fingers slide…").

### Earlier in v0.8.16

**Cleaner replies with ChatML models**
- Models that write chat-format markers as plain text (e.g. `<|im_end|>` from Rocinante) now stop there, and any leaked marker is cut from the saved reply.

**Fewer body / role mix-ups**
- If you haven't set your pronouns, localCAI now guesses them from how the character addresses you in your history ("hubby", "my lady", 老公 …), and each turn tells the model which of you is a man or a woman.
- Recommended: still set your pronouns in ⚙ Settings, it's the most reliable.

### Earlier in v0.8.15

**Fixes models that wrote nonsense (e.g. Rocinante 12B)**
- Some model files ship without a chat template. llama.cpp then can't lay out the conversation and the model only sees a few stray tokens, so it rambles about something unrelated. localCAI now reads the file's header before loading and uses ChatML when no template is inside.
- Conversations are always sent as strict user/character turns (a chat that opens with the character's greeting gets a short opening line), which strict Mistral-style templates require.

**Honest hardware estimates**
- 🧠 Engine shows, for every model, roughly how much memory it needs at your context size and whether it fits on your GPU (🟢), runs partly on the CPU (🟡, slower) or mostly on the CPU (🔴).
- The recommended-model labels no longer promise "8+ GB VRAM" for 12B models.

### Earlier in v0.8.14

**Custom backgrounds, redone**
- 🖼 Background opens a panel with a live preview: choose a picture for this chat only or for every chat with the character, remove it, or hide the one imported from Character.AI.
- Darken and Blur sliders (saved per chat) so long messages stay readable.
- The picture now fills the whole chat (header and message box included), and message bubbles are see-through so you can actually see it.
- Replacing a picture shows the new one immediately (no stale cache).

### Earlier in v0.8.13

**Pronouns you can see and fix, for every character and persona**
- Each character's pronouns are guessed from its description and greeting, shown in the chat header (e.g. "she/her (guessed)"), and can be set in ✎ Edit: she/her, he/him, they/them, or "Several characters" for group / narrator bots (then no pronouns are assumed).
- Your pronouns are saved per persona in ⚙ Settings, so different personas can differ.
- If nothing can be guessed, the header says so instead of the model quietly assuming.

### Earlier in v0.8.12

**Fewer role mix-ups**
- C.ai chats are written in first person on both sides, which confuses small models ("I" in your message is you, "I" in the reply is the character). The prompt now spells out who is who, and each turn reminds the model that "I" in your message means you.
- The character's pronouns are detected from its description; set yours in ⚙ Settings → "Your pronouns" (or let it guess from your persona).

### Earlier in v0.8.11

**Group scenes keep their speaker names**
- Only the label at the very start of a reply ("Mira Vale: …") is removed. If the reply turns out to be a group scene with other characters talking ("Bram: … / Tess: …"), the opening label is put back so every line says who's speaking.
- Speaker names at the start of a line are now highlighted in the bubble.
- Works for every character (and for your own name: the model stops instead of writing your lines).

### Earlier in v0.8.10

**No more "Name:" at the start of replies**
- Roleplay-tuned models (e.g. Stheno) like to begin with "Mira Vale:" in chat-log style. localCAI now removes that label at the start of any line — even while the reply is streaming — since the bubble already shows who is talking.
- Replies also stop if the model starts writing your next line ("Sam: …") for you.

### Earlier in v0.8.9

**A cleaner chat screen**
- Messages look closer to C.ai: the character's picture sits beside the bubble, paragraphs are evenly spaced, and there's no more empty strip inside each bubble (the ✏ 📌 ⤺ 🗑 tools now appear just under the message).
- Text styling tells the parts apart: *actions* in soft italics, "spoken words" bright, and (scene / narration) paragraphs dimmed.
- Top bar tidied: the engine status sits next to the model, "You are" and ⚙ move to the right.
- Chat header buttons have names (Background, Edit, Learn style, Memory) on wide windows.

### Earlier in v0.8.8

**Recommended models, one click away**
- 🧠 Engine → Download now offers roleplay-tuned community models next to Qwen3 4B: **Stheno 8B v3.2**, **Mag Mell 12B R1** and **Rocinante 12B v1.1** (Q4_K_M GGUF from Hugging Face). They write more like C.ai and refuse much less than general assistant models.
- Models too big to fit entirely on your GPU (e.g. a 12B on an 8 GB card) no longer fail to load: llama.cpp now decides how many layers fit on the GPU and runs the rest on the CPU.

### Earlier in v0.8.7

**Pacing that reads the moment**
- Each turn, localCAI looks at what you just did and gives the model a hint: cuddling, kissing, holding or going to sleep → mostly gentle actions with one or two soft lines at most; fighting or running → short beats; a question or plain talk → mostly dialogue. Works for English and Chinese. Turn it off with "Natural pacing" in ⚙ Settings.

### Earlier in v0.8.6

**More natural replies**
- New "Natural pacing" guide (on by default, in ⚙ Settings): the model keeps actions (*asterisks*), spoken words ("quotes") and scene description apart, and fits the balance to the moment — quiet moments get mostly gentle actions, conversations get mostly dialogue, fast scenes get short beats. No more a line of speech glued to every gesture.

**Updating is smoother**
- Opening a newer localCAI.exe while an older one is still open now closes the old one and takes over, instead of showing the old version's window. (Works from v0.8.6 onward; for older versions, close them first.)
