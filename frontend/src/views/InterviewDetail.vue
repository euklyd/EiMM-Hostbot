<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { useInterviewStore } from "../stores/interview";
import QuestionRow from "../components/QuestionRow.vue";

const props = defineProps<{
  serverId: string;
  interviewId: string;
}>();

const auth = useAuthStore();
const store = useInterviewStore();

const posting = ref(false);
const postMessage = ref<string | null>(null);

// Use strings for Discord IDs to avoid precision loss
const serverId = computed(() => props.serverId);
const interviewIdNum = computed(() => parseInt(props.interviewId)); // DB ID, safe as int

// Check if current user is the interviewee
const isInterviewee = computed(() => {
  if (!auth.user || !store.currentInterview) return false;
  // Compare as strings since interviewee_id is now a string
  return String(auth.user.id) === store.currentInterview.interviewee_id;
});

// Manager status is computed on the backend based on the configured manager role
const isManager = computed(() => store.currentServer?.is_manager ?? false);

const canAnswer = computed(() => isInterviewee.value);
const canDelete = computed(() => isManager.value);
const canPost = computed(() => isInterviewee.value && store.answeredQuestions.length > 0);

onMounted(async () => {
  await Promise.all([
    store.fetchServer(serverId.value),
    store.fetchInterview(interviewIdNum.value),
    store.fetchQuestions(interviewIdNum.value),
  ]);

  // Connect WebSocket for real-time updates
  store.connectWebSocket(serverId.value);
});

onUnmounted(() => {
  store.disconnectWebSocket();
});

async function handleAnswer(questionId: number, answerText: string) {
  await store.answerQuestion(questionId, answerText);
}

async function handleDelete(questionId: number) {
  await store.deleteQuestion(questionId);
}

async function handlePost() {
  posting.value = true;
  postMessage.value = null;

  try {
    const result = await store.postAnswers(interviewIdNum.value);
    postMessage.value = result.message || `Posted ${result.posted_count} answers!`;

    // Clear message after a few seconds
    setTimeout(() => {
      postMessage.value = null;
    }, 5000);
  } catch (e) {
    postMessage.value = e instanceof Error ? e.message : "Failed to post answers";
  } finally {
    posting.value = false;
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}
</script>

<template>
  <div>
    <!-- Back link -->
    <router-link
      :to="{ name: 'server', params: { serverId } }"
      class="text-indigo-400 hover:text-indigo-300 mb-4 inline-block"
    >
      ← Back to server
    </router-link>

    <!-- Loading -->
    <div v-if="store.loading" class="animate-pulse">
      <div class="h-8 bg-gray-700 rounded w-1/3 mb-4"></div>
      <div class="h-64 bg-gray-800 rounded"></div>
    </div>

    <!-- Error -->
    <div v-else-if="store.error" class="bg-red-900/50 border border-red-700 rounded-lg p-6">
      <p class="text-red-200 mb-4">{{ store.error }}</p>
      <button
        @click="store.fetchInterview(interviewIdNum)"
        class="px-4 py-2 bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
      >
        Retry
      </button>
    </div>

    <!-- Content -->
    <template v-else-if="store.currentInterview">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex items-center justify-between">
          <div>
            <div class="flex items-center gap-3">
              <h1 class="text-2xl font-bold text-white">
                {{ store.currentInterview.interviewee_name }}'s Interview
              </h1>
              <span
                v-if="store.currentInterview.is_current"
                class="px-2 py-0.5 text-xs font-medium rounded-full bg-green-600 text-white"
              >
                Active
              </span>
              <span
                v-else
                class="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-600 text-gray-300"
              >
                Ended
              </span>
            </div>
            <p class="text-gray-400">
              Interview #{{ store.currentInterview.interview_number }}
              <span class="mx-2">·</span>
              Started {{ formatDate(store.currentInterview.started_at) }}
              <template v-if="store.currentInterview.ended_at">
                <span class="mx-2">·</span>
                Ended {{ formatDate(store.currentInterview.ended_at) }}
              </template>
            </p>
          </div>

          <!-- WebSocket status -->
          <div class="flex items-center space-x-2">
            <span
              :class="store.wsConnected ? 'bg-green-500' : 'bg-red-500'"
              class="w-2 h-2 rounded-full"
            ></span>
            <span class="text-gray-400 text-sm">
              {{ store.wsConnected ? "Live" : "Disconnected" }}
            </span>
          </div>
        </div>

        <!-- Stats row -->
        <div class="flex space-x-6 mt-4 text-sm">
          <div>
            <span class="text-gray-400">Questions:</span>
            <span class="text-white ml-1">{{ store.questions.length }}</span>
          </div>
          <div>
            <span class="text-gray-400">Answered:</span>
            <span class="text-white ml-1">
              {{ store.answeredQuestions.length + store.postedQuestions.length }}
            </span>
          </div>
          <div>
            <span class="text-gray-400">Posted:</span>
            <span class="text-white ml-1">{{ store.postedQuestions.length }}</span>
          </div>
        </div>
      </div>

      <!-- Post button -->
      <div v-if="canPost" class="mb-6 flex items-center space-x-4">
        <button
          @click="handlePost"
          :disabled="posting"
          class="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg transition-colors"
        >
          {{ posting ? "Posting..." : `Post ${store.answeredQuestions.length} Answers to Discord` }}
        </button>
        <span v-if="postMessage" class="text-green-400">{{ postMessage }}</span>
      </div>

      <!-- Questions table -->
      <div class="bg-gray-800 rounded-lg overflow-hidden">
        <table class="w-full table-fixed">
          <thead class="bg-gray-700">
            <tr>
              <th class="px-3 py-2 text-left text-gray-300 text-xs font-medium w-10">#</th>
              <th class="px-2 py-2 text-left text-gray-300 text-xs font-medium w-16">Date</th>
              <th class="px-2 py-2 text-left text-gray-300 text-xs font-medium w-28">Asker</th>
              <th class="px-2 py-2 text-left text-gray-300 text-xs font-medium">Question</th>
              <th class="px-2 py-2 text-left text-gray-300 text-xs font-medium w-48">Answer</th>
              <th class="px-2 py-2 text-center text-gray-300 text-xs font-medium w-12" title="Status">
                <svg class="w-3 h-3 inline" fill="currentColor" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" />
                </svg>
              </th>
              <th class="px-2 py-2 text-center text-gray-300 text-xs font-medium w-10" title="Jump to message">
                <svg class="w-3 h-3 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </th>
              <th v-if="canDelete" class="px-2 py-2 text-center text-gray-300 text-xs font-medium w-10" title="Delete">
                <svg class="w-3 h-3 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </th>
            </tr>
          </thead>
          <tbody>
            <QuestionRow
              v-for="question in store.questions"
              :key="question.id"
              :question="question"
              :can-answer="canAnswer"
              :can-delete="canDelete"
              @answer="handleAnswer"
              @delete="handleDelete"
            />
          </tbody>
        </table>

        <!-- Empty state -->
        <div
          v-if="store.questions.length === 0"
          class="text-center py-12 text-gray-500"
        >
          No questions yet. Questions will appear here when asked in Discord.
        </div>
      </div>
    </template>
  </div>
</template>
