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
    loading.value = true;
    error.value = null;

    try {
      questions.value = await api.getQuestions(interviewId, filterBy);
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to fetch questions";
    } finally {
      loading.value = false;
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
    if (ws) {
      ws.close();
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/ws/${serverId}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      wsConnected.value = true;
      console.log("WebSocket connected");
    };

    ws.onclose = () => {
      wsConnected.value = false;
      console.log("WebSocket disconnected");
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

  function disconnectWebSocket() {
    if (ws) {
      ws.close();
      ws = null;
    }
    wsConnected.value = false;
  }

  function handleWebSocketMessage(message: WebSocketMessage) {
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
