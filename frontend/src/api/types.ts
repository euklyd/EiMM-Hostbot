// API response types matching the Pydantic schemas

export interface DiscordGuild {
  id: string;
  name: string;
  icon: string | null;
  owner: boolean;
  permissions: string;
}

export interface DiscordUser {
  id: number;
  username: string;
  discriminator: string;
  avatar: string | null;
  guilds: DiscordGuild[];
  guild_ids: number[]; // Compact storage for session (used for membership checks)
}

export interface ServerResponse {
  id: string; // Discord ID as string to avoid JS precision loss
  name: string;
  active: boolean;
  answer_channel_id: string | null;
  backstage_channel_id: string | null;
  voting_channel_id: string | null;
  manager_role_id: string | null;
  default_question: string;
}

export interface InterviewSummary {
  id: number; // Database ID
  interview_number: number;
  interviewee_id: string; // Discord ID
  interviewee_name: string;
  started_at: string;
  ended_at: string | null;
  is_current: boolean;
}

export interface InterviewResponse {
  id: number; // Database ID
  interview_number: number;
  server_id: string; // Discord ID
  interviewee_id: string; // Discord ID
  interviewee_name: string;
  started_at: string;
  ended_at: string | null;
  is_current: boolean;
  questions_asked: number;
  questions_answered: number;
}

export interface QuestionResponse {
  id: number; // Database ID
  interview_id: number; // Database ID
  question_number: number;
  asker_id: string; // Discord ID
  asker_name: string;
  question_text: string;
  answer_text: string | null;
  is_posted: boolean;
  asked_at: string;
  answered_at: string | null;
  jump_url: string;
}

export interface ServerWithInterviewResponse {
  server: ServerResponse;
  current_interview: InterviewSummary | null;
}

export interface ServerStatsResponse {
  total_interviews: number;
  total_questions: number;
  total_answered: number;
  avg_questions_per_interview: number;
  avg_answer_time_seconds: number | null;
}

export interface TopAskerResponse {
  user_id: string; // Discord ID
  user_name: string;
  question_count: number;
}

export interface PostAnswersResponse {
  success: boolean;
  posted_count: number;
  message: string | null;
}

// WebSocket message types
export interface WebSocketMessage {
  type: string;
  data: unknown;
  timestamp: string;
}

export interface NewQuestionMessage extends WebSocketMessage {
  type: "new_question";
  data: {
    question_id: number;
    question_number: number;
    asker_name: string;
  };
}

export interface QuestionAnsweredMessage extends WebSocketMessage {
  type: "question_answered";
  data: {
    question_id: number;
  };
}
