// API client for the interview backend

import type {
  DiscordUser,
  InterviewResponse,
  InterviewSummary,
  PostAnswersResponse,
  QuestionResponse,
  ServerStatsResponse,
  ServerWithInterviewResponse,
  TopAskerResponse,
} from "./types";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include", // Include session cookies
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(response.status, error.detail || "Request failed");
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Auth endpoints
export async function getCurrentUser(): Promise<DiscordUser | null> {
  return request<DiscordUser | null>("/auth/me");
}

// Server endpoints
export async function getServers(): Promise<ServerWithInterviewResponse[]> {
  return request<ServerWithInterviewResponse[]>("/api/servers");
}

export async function getServer(serverId: number): Promise<ServerWithInterviewResponse> {
  return request<ServerWithInterviewResponse>(`/api/servers/${serverId}`);
}

export async function getServerStats(serverId: number): Promise<ServerStatsResponse> {
  return request<ServerStatsResponse>(`/api/servers/${serverId}/stats`);
}

export async function getTopAskers(
  serverId: number,
  limit = 10,
): Promise<TopAskerResponse[]> {
  return request<TopAskerResponse[]>(`/api/servers/${serverId}/top-askers?limit=${limit}`);
}

// Interview endpoints
export async function getInterviews(
  serverId: number,
  limit = 20,
  offset = 0,
): Promise<InterviewSummary[]> {
  return request<InterviewSummary[]>(
    `/api/servers/${serverId}/interviews?limit=${limit}&offset=${offset}`,
  );
}

export async function getInterview(interviewId: number): Promise<InterviewResponse> {
  return request<InterviewResponse>(`/api/interviews/${interviewId}`);
}

// Question endpoints
export async function getQuestions(
  interviewId: number,
  filterBy: "all" | "unanswered" | "answered" | "posted" = "all",
): Promise<QuestionResponse[]> {
  return request<QuestionResponse[]>(
    `/api/interviews/${interviewId}/questions?filter_by=${filterBy}`,
  );
}

export async function answerQuestion(
  questionId: number,
  answerText: string,
): Promise<QuestionResponse> {
  return request<QuestionResponse>(`/api/questions/${questionId}/answer`, {
    method: "PUT",
    body: JSON.stringify({ answer_text: answerText }),
  });
}

export async function deleteQuestion(questionId: number): Promise<void> {
  return request<void>(`/api/questions/${questionId}`, {
    method: "DELETE",
  });
}

export async function postAnswers(interviewId: number): Promise<PostAnswersResponse> {
  return request<PostAnswersResponse>(`/api/interviews/${interviewId}/post`, {
    method: "POST",
  });
}

// Export error class
export { ApiError };
