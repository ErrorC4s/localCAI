## localCAI v0.8.11 · Extractor 0.5.0

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
