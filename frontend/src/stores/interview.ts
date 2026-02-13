import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type {
  InterviewResponse,
  QuestionResponse,
  ServerWithInterviewResponse,
  WebSocketMessage,
} from "../api/types";
import * as api from "../api/client";

export const useInterviewStore = defineStore("interview", () => {
  // State
  const servers = ref<ServerWithInterviewResponse[]>([]);
  const currentServer = ref<ServerWithInterviewResponse | null>(null);
  const currentInterview = ref<InterviewResponse | null>(null);
  const questions = ref<QuestionResponse[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  // WebSocket
  let ws: WebSocket | null = null;
  const wsConnected = ref(false);
  let wsServerId: string | null = null;
  let wsReconnectAttempts = 0;
  let wsReconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  const WS_MAX_RECONNECT_DELAY = 30000; // 30 seconds max

  // Computed
  const unansweredQuestions = computed(() =>
    questions.value.filter((q) => !q.answer_text),
  );

  const answeredQuestions = computed(() =>
    questions.value.filter((q) => q.answer_text && !q.is_posted),
  );

  const postedQuestions = computed(() =>
    questions.value.filter((q) => q.is_posted),
  );

  // Actions
  async function fetchServers() {
    loading.value = true;
    error.value = null;

    try {
      servers.value = await api.getServers();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to fetch servers";
    } finally {
      loading.value = false;
    }
  }

  async function fetchServer(serverId: string) {
    loading.value = true;
    error.value = null;
    // Clear stale data to prevent flash of old content
    currentServer.value = null;

    try {
      currentServer.value = await api.getServer(serverId);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to fetch server";
    } finally {
      loading.value = false;
    }
  }

  async function fetchInterview(interviewId: number) {
    loading.value = true;
    error.value = null;
    // Clear stale data to prevent flash of old content
    currentInterview.value = null;
    questions.value = [];

    try {
      currentInterview.value = await api.getInterview(interviewId);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to fetch interview";
    } finally {
      loading.value = false;
    }
  }

  async function fetchQuestions(
    interviewId: number,
    filterBy: "all" | "unanswered" | "answered" | "posted" = "all",
  ) {
    // Only show loading skeleton on initial load, not refreshes
    const isInitialLoad = questions.value.length === 0;
    if (isInitialLoad) {
      loading.value = true;
    }
    error.value = null;

    try {
      questions.value = await api.getQuestions(interviewId, filterBy);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to fetch questions";
    } finally {
      if (isInitialLoad) {
        loading.value = false;
      }
    }
  }

  async function answerQuestion(questionId: number, answerText: string) {
    try {
      const updated = await api.answerQuestion(questionId, answerText);
      // Update local state
      const index = questions.value.findIndex((q) => q.id === questionId);
      if (index !== -1) {
        questions.value[index] = updated;
      }
      return updated;
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to answer question";
      throw e;
    }
  }

  async function deleteQuestion(questionId: number) {
    try {
      await api.deleteQuestion(questionId);
      // Remove from local state
      questions.value = questions.value.filter((q) => q.id !== questionId);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to delete question";
      throw e;
    }
  }

  async function postAnswers(interviewId: number) {
    try {
      const result = await api.postAnswers(interviewId);
      // Refresh questions to update posted status
      await fetchQuestions(interviewId);
      return result;
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to post answers";
      throw e;
    }
  }

  // WebSocket management
  function connectWebSocket(serverId: string) {
    // Clear any pending reconnect
    if (wsReconnectTimeout) {
      clearTimeout(wsReconnectTimeout);
      wsReconnectTimeout = null;
    }

    if (ws) {
      ws.close();
    }

    wsServerId = serverId;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");
    const wsUrl = `${protocol}//${window.location.host}${basePath}/api/ws/${serverId}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      wsConnected.value = true;
      wsReconnectAttempts = 0; // Reset on successful connection
      console.log("WebSocket connected");
    };

    ws.onclose = (event) => {
      wsConnected.value = false;
      console.log("WebSocket disconnected", event.code, event.reason);

      // Auto-reconnect if we have a server ID and weren't intentionally disconnected
      if (wsServerId && event.code !== 4001 && event.code !== 4003) {
        scheduleReconnect();
      }
    };

    ws.onerror = (event) => {
      console.error("WebSocket error:", event);
    };

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        handleWebSocketMessage(message);
      } catch (e) {
        console.error("Failed to parse WebSocket message:", e);
      }
    };
  }

  function scheduleReconnect() {
    if (!wsServerId) return;

    // Exponential backoff: 1s, 2s, 4s, 8s, ... up to max
    const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts), WS_MAX_RECONNECT_DELAY);
    wsReconnectAttempts++;

    console.log(`WebSocket reconnecting in ${delay}ms (attempt ${wsReconnectAttempts})`);

    wsReconnectTimeout = setTimeout(() => {
      if (wsServerId) {
        connectWebSocket(wsServerId);
      }
    }, delay);
  }

  function disconnectWebSocket() {
    // Clear any pending reconnect
    if (wsReconnectTimeout) {
      clearTimeout(wsReconnectTimeout);
      wsReconnectTimeout = null;
    }

    wsServerId = null; // Prevent auto-reconnect
    wsReconnectAttempts = 0;

    if (ws) {
      ws.close();
      ws = null;
    }
    wsConnected.value = false;
  }

  function handleWebSocketMessage(message: WebSocketMessage) {
    console.log("WebSocket message received:", message.type, message.data);
    switch (message.type) {
      case "new_question":
        // Refresh questions list
        if (currentInterview.value) {
          fetchQuestions(currentInterview.value.id);
        }
        break;

      case "question_answered":
        // Refresh questions list
        if (currentInterview.value) {
          fetchQuestions(currentInterview.value.id);
        }
        break;

      case "interview_started":
        // Refresh interview and server data
        if (currentInterview.value) {
          fetchInterview(currentInterview.value.id);
        }
        if (currentServer.value) {
          fetchServer(currentServer.value.server.id);
        }
        break;

      case "interview_ended":
        // Refresh interview and server data
        if (currentInterview.value) {
          fetchInterview(currentInterview.value.id);
        }
        if (currentServer.value) {
          fetchServer(currentServer.value.server.id);
        }
        break;

      default:
        console.log("Unknown WebSocket message type:", message.type);
    }
  }

  // Cleanup
  function $reset() {
    disconnectWebSocket();
    servers.value = [];
    currentServer.value = null;
    currentInterview.value = null;
    questions.value = [];
    loading.value = false;
    error.value = null;
  }

  return {
    // State
    servers,
    currentServer,
    currentInterview,
    questions,
    loading,
    error,
    wsConnected,

    // Computed
    unansweredQuestions,
    answeredQuestions,
    postedQuestions,

    // Actions
    fetchServers,
    fetchServer,
    fetchInterview,
    fetchQuestions,
    answerQuestion,
    deleteQuestion,
    postAnswers,
    connectWebSocket,
    disconnectWebSocket,
    $reset,
  };
});
