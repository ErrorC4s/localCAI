## localCAI v0.8.54 · Extractor 0.5.8

- Extractor 0.5.8: **Clear** now forgets only the collected messages. The character (and its public definition), your personas and the chat's memory stay: C.ai sends them once when the page loads, so after Clear → Load full history the export used to have the messages but no character and no memory (unless you reloaded the page first).

### Earlier in localCAI v0.8.53

- Pinned messages imported from C.ai (kept on the character) now count as pinned messages when the context is small: they're shortened, and the oldest left out, before the example dialogue is cut. Before, they stayed in full and the example dialogue (now often the creator's own definition) was dropped first.

### Earlier in localCAI v0.8.52 · Extractor 0.5.7

- Extractor 0.5.7: exports a character's definition when its creator made it public (C.ai shows it to everyone under "View character details"). Before, only your own characters' definitions were exported. It's read from the character data the page already has; private definitions are still left out.
- The definition becomes the character's example dialogue (C.ai's END_OF_DIALOG and {{random_user_1}} turned into the <START> / {{user}} format other apps use). It replaces example dialogue Learn style had picked, and Learn style leaves it alone from then on.
- Re-importing a character keeps what was written in localCAI and isn't on C.ai: Learn style's notes, your scenario and custom instructions.

### Earlier in localCAI v0.8.51

- Learn style learns from the character's real C.ai replies only (when the chat has enough of them), not from replies written in localCAI, which may have drifted (e.g. pet names the character never used). The example dialogue is picked from the C.ai part too.
- The style notes no longer contradict the habits counted from those replies (how speech is marked, their laugh, what they call you): the model is given them and writes about the rest instead: who the character is, their attitude toward you, how they react in different moods, how they speak.

### Earlier in localCAI v0.8.50

- Fixed: after restoring from the Trash, the restored chat didn't show up in the chat list at the top until you switched characters. It now appears at once, marked "restored".

### Earlier in localCAI v0.8.49

- **Style** (was Learn style) is now a window you can open any time: the learned style notes and the example dialogue, both editable, plus the habits counted from the character's real C.ai replies (with a switch to turn them off). **Learn from this chat** is in the same window; when it's done the window opens again with what was learned, ready to check and change.
- **Trash** (bottom of the character list): see what Delete moved away (characters and their chats, with message counts), **Restore** it or **Delete forever**. Restoring a character that you've imported again keeps its current card and brings the old chats back next to the new ones.
- Learn style no longer overwrites changes made while it was running (it saves onto the card as it is when it finishes), and an example dialogue you edited is yours: Learn style leaves it alone.

### Earlier in localCAI v0.8.48

- **Sounds more like the character from C.ai.** localCAI now counts the character's writing habits from their real C.ai replies in the chat (not the ones written in localCAI): how speech is marked (quotes, bold quotes), bold emphasis, their own laugh, what they call you (and the pet names they never use), stutters, trailing … and —, asides, and stock phrases they never write ("sly grin", "the dim light"…). These go to the model as exact rules, with a one-line reminder on every turn, so the model doesn't drift into its own habits as its replies fill the recent chat.
- Reply length "like their past replies" now follows the character's real C.ai replies, so replies don't grow longer and longer.
- When the context is small, long pinned messages are shortened before the example dialogue, which is the best guide to the character's voice; whole example exchanges are kept.
- Keeps better track of who is doing what to whom (whose hands and mouth are where), and doesn't move the scene further than you took it.
- Fixed: saving in Edit could put back old text in fields you didn't touch, e.g. undo style notes that Learn style had just written. Edit now only saves the fields you changed.

### Earlier in localCAI v0.8.47

- Learn style shows its progress while the model writes (word count), instead of a bar that stopped at a fifth and then vanished, so it no longer looks like it failed halfway.
- When it's done, a window shows the style notes it wrote, where they were saved (the character's Personality) and how many example exchanges it picked, with a button to open Edit.

### Earlier in localCAI v0.8.46

- Reply length is now set per character, in **Edit** (like her past replies, short, medium, long, or no target), instead of one setting for everyone in Settings. A character keeps the setting you had before until you change it. The hard limit per reply (tokens) stays in Settings: it's what the model and its context can handle, the same for every character.

### Earlier in localCAI v0.8.45

- Less stalling: when the character's last reply asked or offered something ("Do you want to…?") and you answer, the model is told your message is the answer and to act on it now, instead of asking again in other words, teasing, or putting a new question in its place.
- Your actions aren't skipped: when you do something (not only talk), the reply starts with how the character's body and feelings respond to it, before her own next move.
- Mood after a peak: right after a climax, a scare, crying or a fight, the character shows the aftermath first (breath, trembling, a dazed or soft moment) instead of jumping straight to a calm, cocky or teasing tone. The scene note records it too ("afterglow, still catching breath").

### Earlier in localCAI v0.8.44

- Fixed "too long for this model's context" in chats with many long pinned messages. What's sent with every reply (the character, memories, pinned messages, example dialogue, guidance) now always leaves room for the chat itself: when it's too long for the context, the example dialogue is shortened first, then each long pinned message, then the story so far; only if that isn't enough are the oldest pinned messages left out. The character's description and personality, memory facts and rules are never cut. Nothing is changed in your chat; this only affects what's sent to the model.
- Chat memory says when pinned messages are long enough to be shortened, and how to keep more of them.

### Earlier in localCAI v0.8.43

- Fixed "Couldn't reach the model … HTTP Error 400: Bad Request" in long chats with a lot of memory. The prompt was a bit longer than the model's context: localCAI guesses how many tokens text takes, and some chats (and models) use more tokens than the guess. Now, when the model says a prompt is too long, localCAI learns the real size for that model, keeps a little less of the older chat so the prompt fits with room for the reply, and tries again at once. You don't see the first attempt.
- If even the character's setup and memory don't fit, it now says so (with what to change) instead of a bare "Bad Request"; other model errors show the model server's own reason too.

### Earlier in localCAI v0.8.42

- Memory facts now have one tab per person, like C.ai's Memory page: the character, you ("(you)"), and anyone else the facts are about, each with how many facts it has. Facts about you are no longer listed under the character. **Add fact** adds to the tab you're on; **+ Someone else** starts a tab for a new person (a friend, a pet…).

### Earlier in localCAI v0.8.41 · Extractor 0.5.6

- Extractor 0.5.6: after Clear, stopping Load full history while pages in the middle were still missing and then pressing it again could stop at once ("Already at the first message") and leave those pages out. After Clear, the collection only counts as complete once a Load full history run (or a stopped run that you continue) has itself walked every page down to the first message; pressing it again always carries on from where it stopped.
- Memory facts you wrote yourself stay yours: if a later C.ai import has the same fact and then C.ai changes it, you're asked (Use C.ai's / Keep mine) instead of it being overwritten.
- A C.ai fact whose category you renamed (say hometown → home) is still recognised when C.ai updates it: you're asked, no duplicate is added.
- A C.ai fact edited in v0.8.39 and then deleted stays deleted on re-import.

### Earlier in v0.8.40 · Extractor 0.5.5

- Extractor 0.5.5: Load full history no longer leaves a gap when C.ai's page and the extension are loading pages at the same time (for example: Clear, scroll up, then Load full history while the page is still fetching). Before, the oldest page arriving first could end the load early, missing the messages in between while it said it had reached the first message, and pressing it again didn't fill the gap. Each Load full history run now keeps its own place and is only done when it has walked every page itself.
- Memory facts from chats imported before v0.8.39 can now be edited and deleted (before, the first edit or delete said the fact "isn't there any more").
- Re-importing a chat now respects what you did to its C.ai facts: a fact you corrected isn't added back with its old value, and a fact you deleted stays deleted. When C.ai changed a fact you had corrected, the Memory dialog shows "C.ai now says: …" with **Use C.ai's** / **Keep mine**; until you choose, only your version is sent to the model.

### Earlier in v0.8.39

- **Memory facts**, like C.ai's Memory page: in 📖 Chat memory, each chat now has a list of short facts grouped by who they are about (the character, you, anyone else), each with a category (hair, age, pets...). Add, edit or delete any of them; a bar shows how much memory is used. They are sent with every reply.
- Your C.ai memory is imported into this list (marked "C.ai"), and re-importing a chat keeps the facts you added or edited.
- Every few replies, new lasting facts from the chat (names, looks, likes, relationships) are added in the background (marked "auto"). It never changes facts you wrote or edited, and stops when memory is nearly full. You can turn it off in Settings.
- Re-importing a chat no longer drops what you added in localCAI to that chat (the story so far, its background settings).
- Fixed: the labels in the memory and settings dialogs were drawn as numbered circles.

### Earlier in v0.8.38 · Extractor 0.5.4

- Extractor 0.5.4: a shorter extension description that fits the Chrome Web Store's 132-character limit (needed to publish it there). No other changes.

### Earlier in v0.8.37

- Your changes are never undone by a reply: if you edit, rewind or switch versions of messages (or reply from another window) while a reply is being written, the reply isn't saved over them. You get a notice, and the message you sent goes back into the input box.
- Extractor 0.5.3: after Clear, Load full history always starts again from the newest page, even if you scrolled the chat up in between. Before, the newest messages could be missing while it said it had reached the start.
- Scene memory notes belong to the whole chat up to that reply, so editing something further back (say, the place) no longer reuses an old note. A note made in the background is only saved if the chat wasn't changed meanwhile.
- "Set up the extension" also works when localCAI is installed with pip: the extension files are now part of the Python package.
- Releases now also install localCAI with pip in a clean environment, and run the built Windows exe (start, prepare the extension, import a chat, export a character card and chat in SillyTavern formats, quit) before publishing.

### Earlier in v0.8.36

- New start screen with three simple steps, and **Set up the extension**: the app now carries the extractor inside it, gets a ready-to-load folder for your browser (Chrome, Edge, Brave/Opera or Firefox), opens it, copies its path, and shows exactly which buttons to click. No more hunting for the right zip or folder.
- The README's extension instructions are rewritten as short numbered steps.

### Earlier in v0.8.35

- Extractor 0.5.2: pressing Clear while "Load full history" is still running no longer loses the newest messages. Answers to requests sent before Clear are ignored, and the running load stops, so loading again collects the whole chat (before, a late older page could move past the newest one and the collection ended early, "at the first message").
- Releases now also need the app UI, built-in engine and extension end-to-end tests to pass, not only the unit tests.

### Earlier in v0.8.34

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
