const messagesEl = document.getElementById("messages");
const eventsEl = document.getElementById("events");
const healthStateEl = document.getElementById("healthState");
const healthDotEl = document.getElementById("healthDot");
const sessionStateEl = document.getElementById("sessionState");
const conversationStateEl = document.getElementById("conversationState");
const configOutputEl = document.getElementById("configOutput");
const searchOutputEl = document.getElementById("searchOutput");
const userIdEl = document.getElementById("userId");
const chatQuestionEl = document.getElementById("chatQuestion");
const enableWebSearchEl = document.getElementById("enableWebSearch");
const modelNameEl = document.getElementById("modelName");
const modelNameFieldEl = document.getElementById("modelNameField");
const asrModelNameEl = document.getElementById("asrModelName");
const asrModelFieldEl = document.getElementById("asrModelField");
const vadThresholdEl = document.getElementById("vadThreshold");
const agentNameViewEl = document.getElementById("agentNameView");
const voiceNameEl = document.getElementById("voiceName");
const voiceNameFieldEl = document.getElementById("voiceNameField");
const comboAsrStepEl = document.getElementById("comboAsrStep");
const comboLlmStepEl = document.getElementById("comboLlmStep");
const comboTtsStepEl = document.getElementById("comboTtsStep");
const sessionJsonEl = document.getElementById("sessionJson");
const configBodyEl = document.getElementById("configBody");
const advancedSettingsEl = document.getElementById("advancedSettings");
const configToggleBtnEl = document.getElementById("configToggleBtn");
const advancedToggleBtnEl = document.getElementById("advancedToggleBtn");
const toolsBodyEl = document.getElementById("toolsBody");
const toolsToggleBtnEl = document.getElementById("toolsToggleBtn");
const statsBodyEl = document.getElementById("statsBody");
const statsToggleBtnEl = document.getElementById("statsToggleBtn");
const waveActionStatusEl = document.getElementById("waveActionStatus");
const lightActionStatusEl = document.getElementById("lightActionStatus");
const brightnessActionStatusEl = document.getElementById("brightnessActionStatus");
const lastActionStatusEl = document.getElementById("lastActionStatus");
const cameraBtnEl = document.getElementById("cameraBtn");
const cameraPanelEl = document.getElementById("cameraPanel");
const cameraDragHandleEl = document.getElementById("cameraDragHandle");
const cameraVideoEl = document.getElementById("cameraVideo");
const cameraCanvasEl = document.getElementById("cameraCanvas");
const cameraStatusEl = document.getElementById("cameraStatus");
const analyzeCameraBtnEl = document.getElementById("analyzeCameraBtn");
const stopCameraBtnEl = document.getElementById("stopCameraBtn");
const micBtnEl = document.getElementById("micBtn");
const micBtnLabelEl = document.getElementById("micBtnLabel");
const stopVoiceBtnEl = document.getElementById("stopVoiceBtn");
const voiceStatusEl = document.getElementById("voiceStatus");
const voiceModeEl = document.getElementById("voiceMode");
const voiceOrbEl = document.getElementById("voiceOrb");
const voiceLiveTextEl = document.getElementById("voiceLiveText");
const voiceWaveEl = document.getElementById("voiceWave");
const waveBars = Array.from(document.querySelectorAll(".wave-bar"));
const metricEls = {
  inputTextTokens: document.getElementById("statInputTextTokens"),
  textCacheRate: document.getElementById("statTextCacheRate"),
  outputTextTokens: document.getElementById("statOutputTextTokens"),
  totalTokens: document.getElementById("statTotalTokens"),
  voiceTurns: document.getElementById("statVoiceTurns"),
  totalTurns: document.getElementById("statTotalTurns"),
  voiceMin: document.getElementById("statVoiceMin"),
  voiceAvg: document.getElementById("statVoiceAvg"),
  voiceMax: document.getElementById("statVoiceMax"),
  voiceP90: document.getElementById("statVoiceP90"),
  voiceSessionLatency: document.getElementById("statVoiceSessionLatency"),
  agentLatency: document.getElementById("statAgentLatency"),
  kbLatency: document.getElementById("statKbLatency"),
  toolLatency: document.getElementById("statToolLatency"),
  demoLatency: document.getElementById("statDemoLatency"),
};

const toolState = {
  wave: "idle",
  lightOn: false,
  brightness: 55,
  lastAction: "none",
};

const AGENT_MODELS = ["gpt-5.4"];

const metrics = {
  tokens: {
    inputText: 0,
    outputText: 0,
    cachedText: 0,
    total: 0,
  },
  turns: 0,
  voiceTurns: 0,
  voiceRoundTrip: [],
  services: {
    voiceSession: [],
    agent: [],
    kb: [],
    tool: [],
    demo: [],
  },
};

let voiceStream = null;
let voiceAudioContext = null;
let voiceAnalyser = null;
let voiceSource = null;
let voiceProcessor = null;
let voiceAnimationFrame = null;
let voiceSocket = null;
let voiceSessionConfigured = false;
let voiceGreetingRequested = false;
let voiceStopRequested = false;
let playbackQueueTime = 0;
let activeAudioSources = [];
let currentAssistantAudioText = "";
let currentAssistantAudioChunks = 0;
let currentAssistantResponseId = null;
let currentAssistantMessageDomId = null;
let currentAssistantResponseInProgress = false;
let voiceRoundTripStartedAt = 0;
let recognition = null;
let recognitionStopRequested = false;
let isListening = false;
let tracePollFailureLogged = false;
let cameraStream = null;
let cameraStarting = false;
let cameraAnalysisInFlight = false;
let cameraDragState = null;
let cameraFramePushTimer = null;
let cameraFramePushInFlight = false;
let waveResetTimer = null;

const traceState = {
  latestId: 0,
  knowledge: [],
  tools: [],
  polling: false,
};

const VOICE_SAMPLE_RATE = 24000;
const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition || null;

function currentVadThreshold() {
  const value = Number.parseFloat(vadThresholdEl?.value);
  return Number.isFinite(value) ? Math.min(Math.max(value, 0), 1) : 0.26;
}

function markdownToPlainText(value) {
  return String(value || "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`{1,3}([^`]+)`{1,3}/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function messageDomId(prefix, value) {
  return `${prefix}-${String(value || Date.now()).replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

function addMessage(role, text, meta, id = null) {
  let article = id ? document.getElementById(id) : null;
  if (article) {
    const body = article.querySelector(".message-body") || article.querySelector("div");
    if (body) {
      body.textContent = markdownToPlainText(text);
    }
    const details = article.querySelector(".message-meta");
    if (details && meta) {
      details.innerHTML = `<code>${meta}</code>`;
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return article;
  }

  article = document.createElement("article");
  article.className = "message";
  if (id) {
    article.id = id;
  }

  const title = document.createElement("strong");
  title.textContent = role;

  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = markdownToPlainText(text);

  article.append(title, body);

  if (meta) {
    const details = document.createElement("div");
    details.className = "message-meta";
    details.innerHTML = `<code>${meta}</code>`;
    article.append(details);
  }

  messagesEl.append(article);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return article;
}

function addEvent(text) {
  const item = document.createElement("li");
  item.className = "log-item";
  item.textContent = text;
  eventsEl.prepend(item);
}

function setHealthState(ok, label) {
  healthStateEl.textContent = label;
  healthDotEl.classList.remove("ok", "error");
  if (ok === true) {
    healthDotEl.classList.add("ok");
  } else if (ok === false) {
    healthDotEl.classList.add("error");
  }
}

function setConversationState(value) {
  conversationStateEl.textContent = value || "none";
}

function setSessionState(value) {
  sessionStateEl.textContent = value || "not created";
}

function formatJson(value) {
  return JSON.stringify(value, null, 2);
}

function formatKnowledgeResults(results) {
  if (!results?.length) {
    return "Foundry IQ retrieval is handled inside the hosted Agent Knowledge configuration.";
  }

  return results
    .slice(0, 3)
    .map((item, index) => {
      const title = item.title || item.source_file || "Knowledge document";
      const page = item.page_number ? `page ${item.page_number}` : "page unknown";
      const rawPreview = item.content_preview || item.content || "";
      const preview = rawPreview.length > 420 ? `${rawPreview.slice(0, 420)}...` : rawPreview;
      return `[${index + 1}] ${title} | ${page}\n${preview}`;
    })
    .join("\n\n");
}

function formatToolResults(tools) {
  if (!tools?.length) {
    return "No custom tool result yet.";
  }

  return tools
    .slice(0, 4)
    .map((item, index) => {
      const title = item.tool || item.title || item.kind || `tool-${index + 1}`;
      return `[${index + 1}] ${title}\n${formatJson(item)}`;
    })
    .join("\n\n");
}

function setSelectOptions(selectEl, values) {
  const previousValue = selectEl.value;
  selectEl.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    selectEl.append(option);
  });
  if (values.includes(previousValue)) {
    selectEl.value = previousValue;
  }
}

function updateArchitectureDisplay() {
  if (!AGENT_MODELS.includes(modelNameEl.value)) {
    setSelectOptions(modelNameEl, AGENT_MODELS);
    modelNameEl.value = "gpt-5.4";
  }
  asrModelFieldEl.classList.toggle("hidden", false);
  modelNameFieldEl.classList.toggle("hidden", false);
  voiceNameFieldEl.classList.toggle("hidden", false);
  comboAsrStepEl.classList.add("active");
  comboLlmStepEl.classList.add("active");
  comboTtsStepEl.classList.add("active");
}

function updateSessionJson() {
  if (!sessionJsonEl) {
    return;
  }
  const sessionPreview = {
    mode: "voice-live-agent-mode",
    voice_live_connect: {
      agent_config: {
        agent: agentNameViewEl.value,
        agent_model: modelNameEl.value,
        agent_web_tool: enableWebSearchEl.checked,
      },
    },
    session_update: {
      modalities: ["text", "audio"],
      input_audio_transcription: {
        model: asrModelNameEl.value,
        language: voiceNameEl.value.startsWith("zh-") ? "zh-CN" : "en-US",
      },
      voice: {
        name: voiceNameEl.value,
        type: "azure-standard",
      },
      input_audio_format: "pcm16",
      output_audio_format: "pcm16",
      turn_detection: {
        type: "azure_semantic_vad",
        threshold: currentVadThreshold(),
        prefix_padding_ms: 300,
        silence_duration_ms: 220,
      },
    },
    tools_source: "foundry-agent-mcp-definition",
    tools_expected: ["scan_environment", "run_robot_action"],
  };
  sessionJsonEl.value = JSON.stringify(
    sessionPreview,
    null,
    2,
  );
}

function renderGroundingResult({ knowledge = [], tool = null, tools = [] } = {}) {
  const sections = [`Agent Knowledge\n${formatKnowledgeResults(knowledge)}`];
  const toolItems = tools.length ? tools : tool ? [tool] : [];
  if (toolItems.length) {
    sections.push(`Actions / Tools\n${formatToolResults(toolItems)}`);
  }
  searchOutputEl.textContent = sections.join("\n\n---\n\n");
}

function traceEventText(trace) {
  const status = trace.payload?.status_code && !String(trace.title || "").startsWith("HTTP")
    ? ` HTTP ${trace.payload.status_code}`
    : "";
  const level = trace.level && trace.level !== "info" ? `${trace.level.toUpperCase()} ` : "";
  const message = trace.message ? ` - ${trace.message}` : "";
  return `${level}${trace.title || trace.kind}${status}${message}`;
}

function mergeGroundingTrace(trace) {
  const payload = trace.payload || {};
  if (trace.kind === "custom_tool" || trace.kind === "agent_tool_event") {
    traceState.tools = [payload, ...traceState.tools].slice(0, 6);
    if (payload.tool === "run_robot_action") {
      applyActionState(payload);
    }
    if (payload.tool === "scan_environment" && payload.summary) {
      cameraStatusEl.textContent = payload.summary;
    }
    if (payload.tool && payload.duration_ms) {
      recordServiceLatency("tool", payload.duration_ms);
    }
  }

  renderGroundingResult({
    knowledge: traceState.knowledge,
    tools: traceState.tools,
  });
}

async function pollBrokerTraces() {
  if (traceState.polling) {
    return;
  }
  traceState.polling = true;
  try {
    const data = await request(`/api/traces?since_id=${traceState.latestId}`, { method: "GET" });
    traceState.latestId = data.latest_id || traceState.latestId;
    (data.events || []).forEach((trace) => addEvent(traceEventText(trace)));
    (data.grounding || []).forEach((trace) => {
      mergeGroundingTrace(trace);
      addEvent(traceEventText(trace));
    });
    tracePollFailureLogged = false;
  } catch (error) {
    if (!tracePollFailureLogged) {
      addEvent(`trace sync error: ${error.message}`);
      tracePollFailureLogged = true;
    }
  } finally {
    traceState.polling = false;
  }
}

function currentConversationId() {
  return conversationStateEl.textContent === "none" ? null : conversationStateEl.textContent;
}

function average(values) {
  if (!values.length) {
    return 0;
  }
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function percentile(values, pct) {
  if (!values.length) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * pct) - 1);
  return sorted[index];
}

function latestAvg(values) {
  if (!values.length) {
    return "0 / 0";
  }
  return `${values[values.length - 1]} / ${average(values)}`;
}

function recordServiceLatency(service, durationMs) {
  const numeric = Number(durationMs);
  if (!Number.isFinite(numeric) || numeric < 0 || !metrics.services[service]) {
    return;
  }
  metrics.services[service].push(Math.round(numeric));
  renderMetrics();
}

function recordVoiceRoundTrip(durationMs) {
  const numeric = Number(durationMs);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return;
  }
  metrics.voiceRoundTrip.push(Math.round(numeric));
  metrics.voiceTurns += 1;
  renderMetrics();
}

function recordTurn() {
  metrics.turns += 1;
  renderMetrics();
}

function recordUsage(usage) {
  if (!usage) {
    return;
  }

  const inputText = usage.input_tokens || usage.input_text_tokens || 0;
  const outputText = usage.output_tokens || usage.output_text_tokens || 0;
  const total = usage.total_tokens || inputText + outputText;
  const inputDetails = usage.input_tokens_details || usage.input_token_details || {};
  const cachedText = inputDetails.cached_tokens || inputDetails.cached_text_tokens || 0;

  metrics.tokens.inputText += inputText;
  metrics.tokens.outputText += outputText;
  metrics.tokens.total += total;
  metrics.tokens.cachedText += cachedText;
  renderMetrics();
}

function renderMetrics() {
  const voice = metrics.voiceRoundTrip;
  const cacheRate = metrics.tokens.inputText
    ? (metrics.tokens.cachedText / metrics.tokens.inputText) * 100
    : 0;

  metricEls.inputTextTokens.textContent = `${metrics.tokens.inputText} token`;
  metricEls.textCacheRate.textContent = `${cacheRate.toFixed(1)}%`;
  metricEls.outputTextTokens.textContent = `${metrics.tokens.outputText} token`;
  metricEls.totalTokens.textContent = `${metrics.tokens.total} token`;
  metricEls.voiceTurns.textContent = String(metrics.voiceTurns);
  metricEls.totalTurns.textContent = String(metrics.turns);
  metricEls.voiceMin.textContent = String(voice.length ? Math.min(...voice) : 0);
  metricEls.voiceAvg.textContent = String(average(voice));
  metricEls.voiceMax.textContent = String(voice.length ? Math.max(...voice) : 0);
  metricEls.voiceP90.textContent = String(percentile(voice, 0.9));
  metricEls.voiceSessionLatency.textContent = latestAvg(metrics.services.voiceSession);
  metricEls.agentLatency.textContent = latestAvg(metrics.services.agent);
  metricEls.kbLatency.textContent = latestAvg(metrics.services.kb);
  metricEls.toolLatency.textContent = latestAvg(metrics.services.tool);
  metricEls.demoLatency.textContent = latestAvg(metrics.services.demo);
}

function resetMetrics() {
  metrics.tokens.inputText = 0;
  metrics.tokens.outputText = 0;
  metrics.tokens.cachedText = 0;
  metrics.tokens.total = 0;
  metrics.turns = 0;
  metrics.voiceTurns = 0;
  metrics.voiceRoundTrip = [];
  Object.keys(metrics.services).forEach((key) => {
    metrics.services[key] = [];
  });
  renderMetrics();
}

function exportMetrics() {
  const blob = new Blob([formatJson(metrics)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `voice-live-bot-metrics-${new Date().toISOString().replaceAll(":", "-")}.json`;
  link.click();
  URL.revokeObjectURL(url);
  addEvent("metrics exported");
}

function updateToolPanel() {
  waveActionStatusEl.textContent = toolState.wave;
  waveActionStatusEl.classList.toggle("done", toolState.wave === "completed");
  lightActionStatusEl.textContent = toolState.lightOn ? "on" : "off";
  lightActionStatusEl.classList.toggle("active", toolState.lightOn);
  brightnessActionStatusEl.textContent = `${toolState.brightness}%`;
  brightnessActionStatusEl.classList.toggle("active", toolState.brightness > 0);
  lastActionStatusEl.textContent = toolState.lastAction;
}

function resetWaveBars() {
  waveBars.forEach((bar, index) => {
    const idleScale = 0.18 + ((index % 4) * 0.06);
    bar.style.transform = `scaleY(${idleScale})`;
  });
}

function animateWaveform() {
  if (!voiceAnalyser) {
    resetWaveBars();
    return;
  }

  const data = new Uint8Array(voiceAnalyser.frequencyBinCount);
  voiceAnalyser.getByteFrequencyData(data);

  waveBars.forEach((bar, index) => {
    const sampleIndex = Math.min(data.length - 1, index * 3);
    const value = data[sampleIndex] / 255;
    const scale = Math.max(0.18, Math.min(1, 0.18 + value * 0.95));
    bar.style.transform = `scaleY(${scale})`;
  });

  voiceAnimationFrame = window.requestAnimationFrame(animateWaveform);
}

function setVoiceMode(mode, liveText = "") {
  const modeText = mode || "Ready";
  voiceModeEl.textContent = modeText;
  voiceOrbEl.classList.remove("listening", "speaking", "thinking");
  const normalized = modeText.toLowerCase();
  if (normalized.includes("listening") || normalized.includes("connected")) {
    voiceOrbEl.classList.add("listening");
  } else if (normalized.includes("speaking")) {
    voiceOrbEl.classList.add("speaking");
  } else if (normalized.includes("thinking") || normalized.includes("configuring")) {
    voiceOrbEl.classList.add("thinking");
  }
  if (liveText) {
    voiceLiveTextEl.textContent = liveText;
  }
}

function setVoiceUi(listening, status, mode = null) {
  isListening = listening;
  micBtnEl.title = listening ? "Voice conversation is live" : "Start voice conversation";
  micBtnEl.setAttribute("aria-label", listening ? "Voice conversation is live" : "Start voice conversation");
  micBtnEl.disabled = listening;
  micBtnLabelEl.textContent = listening ? "Live" : "Start voice";
  micBtnEl.classList.toggle("listening", listening);
  stopVoiceBtnEl.title = listening ? "End voice conversation" : "End is available after start";
  stopVoiceBtnEl.setAttribute("aria-label", listening ? "End voice conversation" : "End is available after start");
  stopVoiceBtnEl.disabled = !listening;
  voiceWaveEl.classList.toggle("listening", listening);
  voiceStatusEl.textContent = status;
  setVoiceMode(mode || (listening ? "Listening" : "Ready"));
  if (!listening) {
    resetWaveBars();
    voiceLiveTextEl.textContent = "Start voice, then speak when ready.";
  }
}

function cleanupVoiceAudio() {
  if (voiceAnimationFrame) {
    window.cancelAnimationFrame(voiceAnimationFrame);
    voiceAnimationFrame = null;
  }

  if (voiceSource) {
    voiceSource.disconnect();
    voiceSource = null;
  }

  if (voiceProcessor) {
    voiceProcessor.disconnect();
    voiceProcessor = null;
  }

  if (voiceAnalyser) {
    voiceAnalyser.disconnect();
    voiceAnalyser = null;
  }

  if (voiceStream) {
    voiceStream.getTracks().forEach((track) => track.stop());
    voiceStream = null;
  }

  if (voiceAudioContext) {
    voiceAudioContext.close();
    voiceAudioContext = null;
  }
}

function resetVoiceRuntime(status = null) {
  voiceStopRequested = true;

  if (voiceSocket && voiceSocket.readyState !== WebSocket.CLOSED) {
    try {
      voiceSocket.close();
    } catch {
      // no-op
    }
  }
  voiceSocket = null;
  voiceSessionConfigured = false;
  voiceGreetingRequested = false;
  currentAssistantAudioText = "";
  currentAssistantAudioChunks = 0;
  currentAssistantResponseId = null;
  currentAssistantMessageDomId = null;
  currentAssistantResponseInProgress = false;
  voiceRoundTripStartedAt = 0;
  playbackQueueTime = 0;

  stopAssistantPlayback();

  if (recognition) {
    recognitionStopRequested = true;
    try {
      recognition.stop();
    } catch {
      // no-op
    }
    recognition = null;
  }

  cleanupVoiceAudio();

  if (status) {
    setVoiceUi(false, status);
  }
}

function stopVoiceCapture(status = "Voice input stopped.") {
  if (!isListening) {
    resetVoiceRuntime(status);
    return;
  }

  resetVoiceRuntime(status);
}

function floatTo16BitPcm(float32) {
  const output = new Int16Array(float32.length);
  for (let index = 0; index < float32.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, float32[index]));
    output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function base64FromPcm(int16) {
  const bytes = new Uint8Array(int16.buffer);
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index]);
  }
  return btoa(binary);
}

function pcmFromBase64(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Int16Array(bytes.buffer);
}

function playPcmAudio(int16) {
  if (!voiceAudioContext) {
    return;
  }

  if (voiceAudioContext.state === "suspended") {
    voiceAudioContext.resume().catch(() => undefined);
  }

  const float32 = new Float32Array(int16.length);
  for (let index = 0; index < int16.length; index += 1) {
    float32[index] = int16[index] / 0x7fff;
  }

  const buffer = voiceAudioContext.createBuffer(1, float32.length, VOICE_SAMPLE_RATE);
  buffer.copyToChannel(float32, 0);
  const source = voiceAudioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(voiceAudioContext.destination);
  activeAudioSources.push(source);
  source.onended = () => {
    activeAudioSources = activeAudioSources.filter((item) => item !== source);
  };

  const startAt = Math.max(voiceAudioContext.currentTime, playbackQueueTime);
  source.start(startAt);
  playbackQueueTime = startAt + buffer.duration;
}

function stopAssistantPlayback() {
  activeAudioSources.forEach((source) => {
    try {
      source.stop();
    } catch {
      // Already stopped.
    }
  });
  activeAudioSources = [];
  if (voiceAudioContext) {
    playbackQueueTime = voiceAudioContext.currentTime;
  }
}

function cancelAssistantResponseForInterrupt() {
  if (!currentAssistantResponseInProgress || !voiceSocket || voiceSocket.readyState !== WebSocket.OPEN || !voiceSessionConfigured) {
    return;
  }
  voiceSocket.send(JSON.stringify({ type: "response.cancel" }));
  currentAssistantResponseId = null;
  currentAssistantAudioText = "";
  currentAssistantAudioChunks = 0;
  currentAssistantMessageDomId = null;
  currentAssistantResponseInProgress = false;
  addEvent("assistant response cancelled by user speech");
}

function requestVoiceLiveGreeting() {
  if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN || !voiceSessionConfigured || voiceGreetingRequested) {
    return;
  }

  voiceGreetingRequested = true;
  voiceStatusEl.textContent = "Voice Live is greeting...";
  setVoiceMode("Speaking", "Voice Live is greeting...");
  voiceSocket.send(
    JSON.stringify({
      type: "response.create",
      response: {
        modalities: ["text", "audio"],
      },
    }),
  );
  addEvent("Voice Live response.create sent; Foundry Agent instructions control the greeting");
}

function sendVisionResultToVoiceLive(data, question) {
  if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN || !voiceSessionConfigured) {
    addEvent("vision result ready but Voice Live session is not connected");
    return;
  }

  const visualContext = [
    "这是 scan_environment 摄像头视觉工具返回的结果。",
    `用户问题：${question}`,
    `画面摘要：${data.summary}`,
    data.objects?.length ? `识别对象：${data.objects.join("、")}` : "",
    "请基于这个真实摄像头结果，用简短中文回复用户。不要说你没有摄像头数据。",
  ]
    .filter(Boolean)
    .join("\n");

  voiceSocket.send(
    JSON.stringify({
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [
          {
            type: "input_text",
            text: visualContext,
          },
        ],
      },
    }),
  );
  voiceSocket.send(
    JSON.stringify({
      type: "response.create",
      response: {
        modalities: ["text", "audio"],
      },
    }),
  );
  addEvent("vision result sent back to Voice Live conversation");
}

function parseToolArguments(rawArguments) {
  if (!rawArguments) {
    return {};
  }
  if (typeof rawArguments === "object") {
    return rawArguments;
  }
  try {
    return JSON.parse(rawArguments);
  } catch (_error) {
    return {};
  }
}

function parseFirstJsonObject(value) {
  const text = String(value || "").trim();
  if (!text.startsWith("{")) {
    return null;
  }

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (escaped) {
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (char === '"') {
      inString = !inString;
      continue;
    }
    if (inString) {
      continue;
    }
    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        try {
          return JSON.parse(text.slice(0, index + 1));
        } catch (_error) {
          return null;
        }
      }
    }
  }
  return null;
}

function extractAssistantTextFromResponse(event) {
  const output = event.response?.output || [];
  const parts = [];
  output.forEach((item) => {
    if (item?.type !== "message" || item.role !== "assistant") {
      return;
    }
    (item.content || []).forEach((content) => {
      const text = content.transcript || content.text || content.output_text || "";
      if (text) {
        parts.push(text);
      }
    });
  });
  return parts.join("").trim();
}

function applyMcpOutputsFromResponse(event) {
  const output = event.response?.output || [];
  output.forEach((item) => {
    if (item?.type !== "mcp_call" || item.name !== "run_robot_action" || !item.output) {
      return;
    }
    const parsed = parseFirstJsonObject(item.output);
    const data = parsed?.structuredResponse || parsed;
    if (!data?.tool) {
      return;
    }
    applyActionState(data);
    traceState.tools = [data, ...traceState.tools].slice(0, 6);
    renderGroundingResult({
      knowledge: traceState.knowledge,
      tools: traceState.tools,
    });
    addEvent(`MCP action: ${data.action || item.name} status=${data.status || "completed"}`);
  });
}

function extractVoiceLiveToolCall(event) {
  const item = event.item || event.output_item || event.response_item || null;
  const candidates = [event, item].filter(Boolean);
  const eventType = String(event.type || "");
  const supportedTools = new Set(["scan_environment", "run_robot_action"]);
  for (const candidate of candidates) {
    const itemType = String(candidate.type || "");
    const name = candidate.name || candidate.tool_name || candidate.function?.name;
    if (!supportedTools.has(name)) {
      continue;
    }
    const looksLikeToolCall =
      eventType.includes("function") ||
      eventType.includes("tool") ||
      itemType === "function_call" ||
      itemType.includes("function") ||
      itemType.includes("tool");
    if (!looksLikeToolCall) {
      continue;
    }
    return {
      name,
      callId: candidate.call_id || candidate.callId || candidate.id || event.call_id || event.callId || null,
      arguments: candidate.arguments || candidate.function?.arguments || event.arguments || {},
    };
  }
  return null;
}

function sendFunctionToolOutputToVoiceLive(toolCall, output) {
  if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN || !voiceSessionConfigured || !toolCall.callId) {
    addEvent(`${toolCall.name} output ready but Voice Live session is not connected`);
    return;
  }

  voiceSocket.send(
    JSON.stringify({
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: toolCall.callId,
        output: JSON.stringify(output),
      },
    }),
  );
  voiceSocket.send(
    JSON.stringify({
      type: "response.create",
      response: {
        modalities: ["text", "audio"],
      },
    }),
  );
  addEvent(`${toolCall.name} tool output sent to Voice Live`);
}

function sendVisionToolOutputToVoiceLive(data, toolCall, question) {
  if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN || !voiceSessionConfigured) {
    addEvent("scan_environment output ready but Voice Live session is not connected");
    return;
  }
  if (!toolCall.callId) {
    sendVisionResultToVoiceLive(data, question);
    return;
  }

  const output = {
    ok: true,
    tool: "scan_environment",
    question,
    summary: data.summary,
    objects: data.objects || [],
    actions: data.actions || [],
    suggested_reply: data.suggested_reply,
  };
  sendFunctionToolOutputToVoiceLive(toolCall, output);
}

function applyActionState(data) {
  const state = data.state || data.action_state || {};
  if (state.wave) {
    toolState.wave = state.wave;
    if (waveResetTimer) {
      window.clearTimeout(waveResetTimer);
      waveResetTimer = null;
    }
    if (state.wave === "completed") {
      waveResetTimer = window.setTimeout(() => {
        toolState.wave = "idle";
        updateToolPanel();
        waveResetTimer = null;
      }, 2200);
    }
  }
  if (typeof state.light_on === "boolean") {
    toolState.lightOn = state.light_on;
  }
  if (typeof state.brightness === "number") {
    toolState.brightness = state.brightness;
  }
  if (state.last_action || data.action) {
    toolState.lastAction = state.last_action || data.action;
  }
  updateToolPanel();
}

async function runRobotAction(action, args = {}, source = "manual") {
  const startedAt = performance.now();
  const data = await request("/api/tools/mock-robot-action", {
    method: "POST",
    body: JSON.stringify({
      action,
      target: args.target || (action === "wave" ? "user" : "room_light"),
      brightness: args.brightness,
      location: args.location || "front",
    }),
  });
  recordServiceLatency("tool", data.duration_ms || performance.now() - startedAt);
  applyActionState(data);
  addMessage("tool", data.message, `tool=${data.tool} source=${source}`);
  addEvent(`Action: ${data.action} status=${data.status || "completed"}`);
  renderGroundingResult({
    knowledge: traceState.knowledge,
    tools: [data, ...traceState.tools],
  });
  return data;
}

async function handleVoiceLiveToolCall(toolCall) {
  const args = parseToolArguments(toolCall.arguments);
  addEvent(`Agent -> ${toolCall.name}`);
  if (toolCall.name === "run_robot_action") {
    const data = await runRobotAction(args.action || "wave", args, "agent-tool-call");
    if (toolCall.callId) {
      sendFunctionToolOutputToVoiceLive(toolCall, {
        ok: true,
        tool: "run_robot_action",
        action: data.action,
        status: data.status,
        state: data.state,
        message: data.message,
      });
    }
    return;
  }

  const question = args.question || chatQuestionEl?.value || "Analyze the current camera view.";
  const data = await analyzeCurrentCameraView(question, {
    addUserMessage: false,
    sendToVoiceLive: false,
    source: "agent-tool-call",
  });
  if (data) {
    sendVisionToolOutputToVoiceLive(data, toolCall, question);
  }
}

function handleVoiceLiveEvent(event) {
  const toolCall = extractVoiceLiveToolCall(event);
  if (toolCall) {
    handleVoiceLiveToolCall(toolCall);
    return;
  }

  switch (event.type) {
    case "broker.connecting":
    case "broker.upstream_connected":
      voiceStatusEl.textContent = event.message || event.type;
      setVoiceMode("Connecting", event.message || "Connecting to Voice Live...");
      addEvent(event.type);
      break;
    case "session.created":
    case "session.updated":
      setSessionState(event.session?.id || event.type);
      if (event.type === "session.updated") {
        voiceSessionConfigured = true;
        voiceStatusEl.textContent = "Requesting Voice Live greeting...";
        setVoiceMode("Thinking", "Requesting Voice Live greeting...");
        requestVoiceLiveGreeting();
      }
      addEvent(`voice live ${event.type}`);
      break;
    case "input_audio_buffer.speech_started":
      stopAssistantPlayback();
      cancelAssistantResponseForInterrupt();
      voiceStatusEl.textContent = "Listening...";
      setVoiceMode("Listening", "Listening...");
      break;
    case "input_audio_buffer.speech_stopped":
      voiceStatusEl.textContent = "Thinking...";
      setVoiceMode("Thinking", "Thinking...");
      break;
    case "conversation.item.input_audio_transcription.completed":
      if (event.transcript) {
        if (chatQuestionEl) {
          chatQuestionEl.value = event.transcript;
        }
        voiceLiveTextEl.textContent = "User speech captured.";
        addMessage("user", event.transcript, "voice-live-transcript");
      }
      break;
    case "response.created":
      stopAssistantPlayback();
      currentAssistantResponseInProgress = true;
      currentAssistantResponseId = event.response?.id || null;
      currentAssistantAudioText = "";
      currentAssistantAudioChunks = 0;
      currentAssistantMessageDomId = messageDomId("assistant", currentAssistantResponseId || `stream-${Date.now()}`);
      voiceStatusEl.textContent = "Assistant is responding...";
      setVoiceMode("Speaking", "Speaking...");
      voiceLiveTextEl.textContent = "Assistant is preparing a response...";
      break;
    case "response.text.delta":
    case "response.output_text.delta":
    case "response.audio_transcript.delta":
      currentAssistantResponseId = event.response_id || currentAssistantResponseId;
      currentAssistantAudioText += event.delta || "";
      voiceStatusEl.textContent = "Assistant is speaking...";
      setVoiceMode("Speaking", "Speaking...");
      if (!currentAssistantMessageDomId) {
        currentAssistantMessageDomId = messageDomId("assistant", currentAssistantResponseId || `stream-${Date.now()}`);
      }
      addMessage("Assistant", currentAssistantAudioText, "voice-live-agent-mode", currentAssistantMessageDomId);
      break;
    case "response.audio.delta":
      if (event.delta) {
        currentAssistantAudioChunks += 1;
        if (currentAssistantAudioChunks === 1) {
          addEvent("voice audio delta received");
        }
        playPcmAudio(pcmFromBase64(event.delta));
      }
      break;
    case "response.done":
      applyMcpOutputsFromResponse(event);
      if (!currentAssistantAudioText.trim()) {
        currentAssistantAudioText = extractAssistantTextFromResponse(event);
      }
      if (currentAssistantAudioText.trim()) {
        if (currentAssistantMessageDomId) {
          addMessage("Assistant", currentAssistantAudioText.trim(), "voice-live-agent-mode", currentAssistantMessageDomId);
        }
        if (currentAssistantAudioChunks === 0) {
          addEvent("voice live response had no audio delta; text displayed only");
        }
      }
      if (voiceRoundTripStartedAt) {
        recordVoiceRoundTrip(performance.now() - voiceRoundTripStartedAt);
        voiceRoundTripStartedAt = 0;
      }
      recordTurn();
      currentAssistantAudioText = "";
      currentAssistantResponseId = null;
      currentAssistantMessageDomId = null;
      currentAssistantResponseInProgress = false;
      voiceStatusEl.textContent = "Listening... ask another question or stop.";
      setVoiceMode("Listening", "Listening...");
      break;
    case "error":
      {
        const message = event.error?.message || "unknown";
        if (/Cancellation failed: no active response found/i.test(message)) {
          addEvent("voice cancel ignored: no active response");
          currentAssistantResponseInProgress = false;
          break;
        }
        voiceStatusEl.textContent = `Voice Live error: ${message}`;
        setVoiceMode("Error", message);
        addMessage("system", `Voice Live error: ${message}`, "voice-live-error");
        addEvent(`voice live error: ${message}`);
      }
      break;
    default:
      break;
  }
}

async function request(path, init) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = `Request failed: ${response.status}`;
    try {
      const errorBody = await response.json();
      message = errorBody.error || errorBody.detail || formatJson(errorBody);
    } catch {
      message = await response.text();
    }
    throw new Error(message);
  }

  return response.json();
}

function setCameraUi(enabled, status = "") {
  cameraPanelEl.classList.toggle("hidden", !enabled);
  cameraBtnEl.classList.toggle("active", enabled);
  cameraBtnEl.title = enabled ? "Camera is on" : "Start camera";
  cameraBtnEl.setAttribute("aria-label", enabled ? "Camera is on" : "Start camera");
  cameraBtnEl.querySelector("span").textContent = enabled ? "Camera on" : "Camera";
  if (status) {
    cameraStatusEl.textContent = status;
  }
}

function clampCameraPanel(left, top) {
  const rect = cameraPanelEl.getBoundingClientRect();
  const margin = 12;
  const maxLeft = Math.max(margin, window.innerWidth - rect.width - margin);
  const maxTop = Math.max(margin, window.innerHeight - rect.height - margin);
  return {
    left: Math.min(Math.max(left, margin), maxLeft),
    top: Math.min(Math.max(top, margin), maxTop),
  };
}

function placeCameraPanel(left, top) {
  const position = clampCameraPanel(left, top);
  cameraPanelEl.style.left = `${position.left}px`;
  cameraPanelEl.style.top = `${position.top}px`;
  cameraPanelEl.style.right = "auto";
  cameraPanelEl.style.bottom = "auto";
}

function keepCameraPanelInView() {
  if (cameraPanelEl.classList.contains("hidden") || !cameraPanelEl.style.left || !cameraPanelEl.style.top) {
    return;
  }
  placeCameraPanel(parseFloat(cameraPanelEl.style.left), parseFloat(cameraPanelEl.style.top));
}

function startCameraDrag(event) {
  if (event.button !== undefined && event.button !== 0) {
    return;
  }
  const rect = cameraPanelEl.getBoundingClientRect();
  cameraDragState = {
    pointerId: event.pointerId,
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
  };
  cameraPanelEl.classList.add("dragging");
  cameraDragHandleEl.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function moveCameraDrag(event) {
  if (!cameraDragState || event.pointerId !== cameraDragState.pointerId) {
    return;
  }
  placeCameraPanel(event.clientX - cameraDragState.offsetX, event.clientY - cameraDragState.offsetY);
}

function stopCameraDrag(event) {
  if (!cameraDragState || event.pointerId !== cameraDragState.pointerId) {
    return;
  }
  cameraDragState = null;
  cameraPanelEl.classList.remove("dragging");
  cameraDragHandleEl.releasePointerCapture?.(event.pointerId);
}

async function startCamera() {
  if (cameraStream || cameraStarting) {
    setCameraUi(true, "Camera is already on.");
    return;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    const message = "This browser cannot access the camera. Use localhost or HTTPS.";
    cameraStatusEl.textContent = message;
    addEvent("camera unsupported in browser");
    return;
  }

  cameraStarting = true;
  cameraBtnEl.disabled = true;
  cameraStatusEl.textContent = "Requesting camera permission...";
  setCameraUi(true);

  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: "environment",
      },
      audio: false,
    });
    cameraVideoEl.srcObject = cameraStream;
    await cameraVideoEl.play();
    startCameraFramePush();
    await pushLatestCameraFrame();
    setCameraUi(true, "Camera is on. Agent can use scan_environment via MCP.");
    addEvent("camera started");
  } catch (error) {
    stopCamera("Camera is off.");
    const message = `Camera error: ${error.message}`;
    cameraStatusEl.textContent = message;
    addMessage("system", message, "camera");
    addEvent(message);
  } finally {
    cameraStarting = false;
    cameraBtnEl.disabled = false;
  }
}

function stopCamera(status = "Camera stopped.") {
  stopCameraFramePush();
  cameraStream?.getTracks().forEach((track) => track.stop());
  cameraStream = null;
  cameraVideoEl.srcObject = null;
  setCameraUi(false, status);
}

function captureCameraFrame() {
  if (!cameraVideoEl.videoWidth || !cameraVideoEl.videoHeight) {
    return null;
  }

  const maxWidth = 960;
  const scale = Math.min(1, maxWidth / cameraVideoEl.videoWidth);
  cameraCanvasEl.width = Math.round(cameraVideoEl.videoWidth * scale);
  cameraCanvasEl.height = Math.round(cameraVideoEl.videoHeight * scale);
  const context = cameraCanvasEl.getContext("2d");
  context.drawImage(cameraVideoEl, 0, 0, cameraCanvasEl.width, cameraCanvasEl.height);
  return cameraCanvasEl.toDataURL("image/jpeg", 0.72);
}

async function pushLatestCameraFrame(frame = null) {
  if (!cameraStream || cameraFramePushInFlight) {
    return;
  }
  const image = frame || captureCameraFrame();
  if (!image) {
    return;
  }

  cameraFramePushInFlight = true;
  try {
    await request("/api/vision/latest-frame", {
      method: "POST",
      body: JSON.stringify({
        image_base64: image,
        user_id: userIdEl.value,
        conversation_id: currentConversationId(),
      }),
    });
  } catch (error) {
    addEvent(`camera frame sync error: ${error.message}`);
  } finally {
    cameraFramePushInFlight = false;
  }
}

function startCameraFramePush() {
  if (cameraFramePushTimer) {
    return;
  }
  cameraFramePushTimer = window.setInterval(() => {
    pushLatestCameraFrame();
  }, 1800);
}

function stopCameraFramePush() {
  if (!cameraFramePushTimer) {
    return;
  }
  window.clearInterval(cameraFramePushTimer);
  cameraFramePushTimer = null;
}

async function analyzeCurrentCameraView(question = "看看桌上有什么？", options = {}) {
  if (cameraAnalysisInFlight) {
    addEvent("camera analysis already running");
    return null;
  }

  if (!cameraStream) {
    await startCamera();
  }
  const frame = captureCameraFrame();
  if (!frame) {
    cameraStatusEl.textContent = "Camera frame is not ready yet.";
    addEvent("camera frame not ready");
    return null;
  }

  const startedAt = performance.now();
  cameraAnalysisInFlight = true;
  analyzeCameraBtnEl.disabled = true;
  cameraStatusEl.textContent = "Calling scan_environment with current camera frame...";
  if (options.addUserMessage !== false) {
    addMessage("user", question, "voice-live transcript");
  }
  if (options.sendToVoiceLive) {
    stopAssistantPlayback();
    cancelAssistantResponseForInterrupt();
  }
  addEvent(options.source === "agent-tool-call" ? "Broker: executing scan_environment" : "Manual -> scan_environment");
  addEvent("Broker: captured current camera frame");

  try {
    await pushLatestCameraFrame(frame);
    const data = await request("/api/vision/analyze-frame", {
      method: "POST",
      body: JSON.stringify({
        image_base64: frame,
        question,
        user_id: userIdEl.value,
        conversation_id: currentConversationId(),
      }),
    });

    recordServiceLatency("tool", data.duration_ms || performance.now() - startedAt);
    addEvent(`Vision model (${data.model}): ${data.summary}`);
    (data.actions || []).forEach((action) => {
      addEvent(`Action: ${action.name} target=${action.target} status=${action.status}`);
    });
    if (options.sendToVoiceLive) {
      sendVisionResultToVoiceLive(data, question);
    } else {
      addMessage("Assistant", data.suggested_reply, `tool=${data.tool} model=${data.model}`);
    }
    renderGroundingResult({
      knowledge: traceState.knowledge,
      tools: [data, ...traceState.tools],
    });
    cameraStatusEl.textContent = data.summary;
    return data;
  } catch (error) {
    const message =
      error.message === "Not Found"
        ? "Vision route not loaded. Please restart the broker so /api/vision/analyze-frame is registered."
        : error.message;
    cameraStatusEl.textContent = message;
    addMessage("system", `Vision error: ${message}`, "scan_environment");
    addEvent(`vision error: ${message}`);
    return null;
  } finally {
    cameraAnalysisInFlight = false;
    analyzeCameraBtnEl.disabled = false;
  }
}

async function createVoiceSession() {
  const startedAt = performance.now();
  const data = await request("/api/session", {
    method: "POST",
    body: JSON.stringify({ conversation_id: currentConversationId() }),
  });
  recordServiceLatency("voiceSession", data.duration_ms || performance.now() - startedAt);

  setSessionState(data.session_id || data.event_type || "ready");
  setConversationState(data.conversation_id);
  addMessage("voice-live", data.message, `event=${data.event_type || "unknown"}`);
  addEvent(`voice live session ready: ${data.event_type || "connected"}`);
  return data;
}

async function runAgentQuestion(question, source = "user") {
  const startedAt = performance.now();
  addMessage(source, question);
  const data = await request("/api/agent/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: userIdEl.value,
      question,
      conversation_id: currentConversationId(),
    }),
  });
  recordServiceLatency("agent", data.duration_ms || performance.now() - startedAt);
  recordUsage(data.usage);
  recordTurn();
  setConversationState(data.conversation_id);
  addMessage("foundry-agent", data.answer, `mode=${data.mode} model=${data.model || "managed"}`);
  addEvent(`foundry agent replied via ${data.mode}`);
  return data;
}

async function runDemoQuestion(question, source = "user") {
  const data = await runAgentQuestion(question, source);
  renderGroundingResult();
  return data;
}

function buildRecognition() {
  if (!SpeechRecognitionCtor) {
    return null;
  }

  const instance = new SpeechRecognitionCtor();
  instance.lang = "zh-CN";
  instance.interimResults = true;
  instance.continuous = false;
  instance.maxAlternatives = 1;
  return instance;
}

async function startVoiceCapture() {
  if (isListening) {
    return;
  }

  resetVoiceRuntime();
  voiceStopRequested = false;

  if (!navigator.mediaDevices?.getUserMedia) {
    setVoiceUi(false, "This browser cannot access the microphone.");
    addEvent("microphone unsupported in browser");
    return;
  }

  try {
    setVoiceUi(true, "Opening microphone and Voice Live session...", "Connecting");
    setVoiceMode("Connecting", "Opening microphone and Voice Live session...");
    const configUrl = new URL("/api/voice/config", window.location.href);
    configUrl.searchParams.set("voice", voiceNameEl.value);
    configUrl.searchParams.set("asr_model", asrModelNameEl.value);
    configUrl.searchParams.set("agent_model", modelNameEl.value);
    configUrl.searchParams.set("language", voiceNameEl.value.startsWith("zh-") ? "zh-CN" : "en-US");
    configUrl.searchParams.set("vad_threshold", String(currentVadThreshold()));
    configUrl.searchParams.set("prefix_padding_ms", "300");
    configUrl.searchParams.set("silence_duration_ms", "220");
    const sessionUpdate = await fetch(configUrl).then((response) => {
      if (!response.ok) {
        throw new Error(`Voice config failed: ${response.status}`);
      }
      return response.json();
    });

    voiceStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: VOICE_SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    voiceAudioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: VOICE_SAMPLE_RATE });
    if (voiceAudioContext.state === "suspended") {
      await voiceAudioContext.resume().catch(() => undefined);
    }
    playbackQueueTime = voiceAudioContext.currentTime;
    voiceAnalyser = voiceAudioContext.createAnalyser();
    voiceAnalyser.fftSize = 64;
    voiceSource = voiceAudioContext.createMediaStreamSource(voiceStream);
    voiceSource.connect(voiceAnalyser);
    voiceProcessor = voiceAudioContext.createScriptProcessor(2048, 1, 1);
    voiceProcessor.onaudioprocess = (event) => {
      if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN) {
        return;
      }
      if (!voiceSessionConfigured) {
        return;
      }
      const float32 = event.inputBuffer.getChannelData(0);
      voiceSocket.send(
        JSON.stringify({
          type: "input_audio_buffer.append",
          audio: base64FromPcm(floatTo16BitPcm(float32)),
        }),
      );
    };
    voiceSource.connect(voiceProcessor);
    voiceProcessor.connect(voiceAudioContext.destination);

    if (voiceAnimationFrame) {
      window.cancelAnimationFrame(voiceAnimationFrame);
    }
    voiceAnimationFrame = window.requestAnimationFrame(animateWaveform);

    const socketUrl = new URL("/api/voice/ws", window.location.href);
    socketUrl.protocol = socketUrl.protocol === "https:" ? "wss:" : "ws:";
    voiceSocket = new WebSocket(socketUrl.toString());
    voiceSocket.binaryType = "arraybuffer";

    voiceSocket.onopen = () => {
      voiceSessionConfigured = false;
      voiceGreetingRequested = false;
      voiceSocket.send(JSON.stringify(sessionUpdate));
      voiceRoundTripStartedAt = performance.now();
      setVoiceUi(true, "Configuring Voice Live Agent Mode...", "Configuring");
      addEvent("voice live websocket connected");
    };

    voiceSocket.onmessage = (event) => {
      try {
        handleVoiceLiveEvent(JSON.parse(event.data));
      } catch {
        addEvent("voice live non-json frame ignored");
      }
    };

    voiceSocket.onerror = () => {
      const message = "Voice Live websocket error. Check broker .env, Entra/Managed Identity permissions, browser microphone permission, and selected model.";
      setVoiceUi(false, message);
      addMessage("system", message, "voice-live-websocket");
      addEvent("voice live websocket error");
    };

    voiceSocket.onclose = (event) => {
      const wasStopRequested = voiceStopRequested;
      voiceSessionConfigured = false;
      voiceGreetingRequested = false;
      stopAssistantPlayback();
      cleanupVoiceAudio();
      voiceSocket = null;
      voiceStopRequested = false;
      if (wasStopRequested) {
        setVoiceUi(false, "Voice input stopped.");
        addEvent("voice live websocket closed by user");
        return;
      }
      const detail = event.code ? `code=${event.code}${event.reason ? ` reason=${event.reason}` : ""}` : "";
      const message = `Voice Live connection closed.${detail ? ` ${detail}` : ""}`;
      setVoiceUi(false, message);
      addEvent(message);
    };
  } catch (error) {
    if (voiceSocket && voiceSocket.readyState !== WebSocket.CLOSED) {
      voiceSocket.close();
    }
    voiceSocket = null;
    voiceSessionConfigured = false;
    voiceGreetingRequested = false;
    voiceStopRequested = false;
    stopAssistantPlayback();
    cleanupVoiceAudio();
    setVoiceUi(false, `Microphone error: ${error.message}`);
    addMessage("system", `Microphone error: ${error.message}`, "microphone");
    addEvent(`microphone error: ${error.message}`);
  }
}

document.getElementById("pingBtn").addEventListener("click", async () => {
  try {
    const data = await request("/health");
    setHealthState(Boolean(data.ok), data.ok ? "ok" : "down");
    addEvent(`broker health: ${healthStateEl.textContent}`);
  } catch (error) {
    setHealthState(false, "error");
    addEvent(`health error: ${error.message}`);
  }
});

async function loadBrokerConfig() {
  try {
    const data = await request("/api/config");
    const agentToolsActive = Boolean(data.features?.agentToolsEnabled || data.serviceStatus?.foundryAgentConfigured);
    const activeAgentName = data.resources.foundryAgentName || "avlb-bot-agent";
    const activeAgentVersion = data.resources.foundryAgentVersion;
    enableWebSearchEl.checked = agentToolsActive;
    enableWebSearchEl.disabled = true;
    if (data.resources.voiceLiveAsrModel && [...asrModelNameEl.options].some((option) => option.value === data.resources.voiceLiveAsrModel)) {
      asrModelNameEl.value = data.resources.voiceLiveAsrModel;
    }
    if (data.resources.voiceLiveAgentModel && [...modelNameEl.options].some((option) => option.value === data.resources.voiceLiveAgentModel)) {
      modelNameEl.value = data.resources.voiceLiveAgentModel;
    }
    if (data.resources.voiceLiveTtsVoice && [...voiceNameEl.options].some((option) => option.value === data.resources.voiceLiveTtsVoice)) {
      voiceNameEl.value = data.resources.voiceLiveTtsVoice;
    }
    if (!modelNameEl.value) {
      modelNameEl.value = "gpt-5.4";
    }
    agentNameViewEl.value = activeAgentName;
    updateSessionJson();
    configOutputEl.textContent = `Broker ready | agent=${activeAgentName}${activeAgentVersion ? `@${activeAgentVersion}` : ""} | Foundry IQ=${data.serviceStatus.foundryIqConfigured ? "ready" : "missing"} | agent tools=${agentToolsActive ? "active" : "not configured"} | mcp=${data.serviceStatus.mcpServerConfigured ? "configured" : "local only"} | voice auth=Entra`;
    addEvent("broker config loaded");
  } catch (error) {
    configOutputEl.textContent = "Broker configuration unavailable. Check local .env or Azure identity permissions.";
    addEvent(`config error: ${error.message}`);
  }
}

const sessionBtnEl = document.getElementById("sessionBtn");
if (sessionBtnEl) {
  sessionBtnEl.addEventListener("click", async () => {
    try {
      await createVoiceSession();
    } catch (error) {
      addEvent(`session error: ${error.message}`);
    }
  });
}

const demoBtnEl = document.getElementById("demoBtn");
if (demoBtnEl && chatQuestionEl) {
  demoBtnEl.addEventListener("click", async () => {
    const question = chatQuestionEl.value.trim();
    if (!question) {
      chatQuestionEl.focus();
      return;
    }
    chatQuestionEl.value = "";
    try {
      await runDemoQuestion(question);
    } catch (error) {
      chatQuestionEl.value = question;
      addEvent(`demo error: ${error.message}`);
    }
  });
}

configToggleBtnEl.addEventListener("click", () => {
  const collapsed = configBodyEl.classList.toggle("collapsed");
  configToggleBtnEl.textContent = collapsed ? "v" : "^";
});

function wirePanelToggle(button, body) {
  button.addEventListener("click", () => {
    const collapsed = body.classList.toggle("collapsed");
    button.textContent = collapsed ? "v" : "^";
  });
}

wirePanelToggle(toolsToggleBtnEl, toolsBodyEl);
wirePanelToggle(statsToggleBtnEl, statsBodyEl);

advancedToggleBtnEl.addEventListener("click", () => {
  advancedSettingsEl.classList.toggle("open");
});

[modelNameEl, asrModelNameEl, voiceNameEl].forEach((element) => {
  element.addEventListener("change", () => {
    updateSessionJson();
  });
});

document.getElementById("resetMetricsBtn").addEventListener("click", () => {
  resetMetrics();
  addEvent("metrics reset");
});

document.getElementById("exportMetricsBtn").addEventListener("click", exportMetrics);

cameraDragHandleEl.addEventListener("pointerdown", startCameraDrag);
window.addEventListener("pointermove", moveCameraDrag);
window.addEventListener("pointerup", stopCameraDrag);
window.addEventListener("pointercancel", stopCameraDrag);
window.addEventListener("resize", keepCameraPanelInView);

cameraBtnEl.addEventListener("click", async () => {
  try {
    if (cameraStream) {
      setCameraUi(true, "Camera is already on.");
      return;
    }
    await startCamera();
  } catch (error) {
    addEvent(`camera start error: ${error.message}`);
  }
});

analyzeCameraBtnEl.addEventListener("click", () => analyzeCurrentCameraView());

stopCameraBtnEl.addEventListener("click", () => {
  stopCamera();
  addEvent("camera stopped");
});

micBtnEl.addEventListener("click", async () => {
  if (isListening) {
    voiceLiveTextEl.textContent = "Voice is already live.";
    return;
  }

  try {
    addMessage("system", "Starting microphone. Please allow browser microphone permission, then speak after connected.", "voice-live");
    await startVoiceCapture();
    addEvent("voice input started");
  } catch (error) {
    addEvent(`voice start error: ${error.message}`);
  }
});

stopVoiceBtnEl.addEventListener("click", async () => {
  if (!isListening) {
    return;
  }
  stopVoiceCapture("Voice input stopped.");
  addMessage("system", "Voice input stopped.", "voice-live");
  addEvent("voice input stopped");
});

window.addEventListener("beforeunload", () => {
  if (cameraStream) {
    stopCamera();
  }
  if (isListening) {
    stopVoiceCapture("Voice input stopped.");
  }
});

updateToolPanel();
resetWaveBars();
updateArchitectureDisplay();
updateSessionJson();
renderMetrics();
setHealthState(null, "unchecked");
loadBrokerConfig();
renderGroundingResult();
pollBrokerTraces();
window.setInterval(pollBrokerTraces, 2500);
addEvent("voice + tool-call demo layout loaded");
