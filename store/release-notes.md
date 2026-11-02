## localCAI v0.8.4 · Extractor 0.5.0

**Much faster replies**
- Prompts are now built so the engine can reuse its cache: only the newest message is processed each turn instead of the whole conversation. Long chats go from minutes to seconds, even on CPU.
- On PCs with an NVIDIA GPU, the built-in engine now installs the CUDA build of llama.cpp (with its CUDA runtime) instead of Vulkan. Open 🧠 and press **Reinstall / update** to switch.
- The status chip warns "CPU (slow)" when no GPU is being used, and engine.log now records which GPUs were detected and which one is used.
