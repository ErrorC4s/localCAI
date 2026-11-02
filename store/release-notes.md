## localCAI v0.8.17 · Extractor 0.5.0

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
