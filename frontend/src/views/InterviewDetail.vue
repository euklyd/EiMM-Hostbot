<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from "vue";
import { useAuthStore } from "../stores/auth";
import { useInterviewStore } from "../stores/interview";
import { matchesQuestionFilter } from "../utils/questionFilter";
import QuestionRow from "../components/QuestionRow.vue";

const props = defineProps<{
  serverId: string;
  interviewId: string;
}>();

const auth = useAuthStore();
const store = useInterviewStore();

const posting = ref(false);
const postMessage = ref<string | null>(null);
const postMessageType = ref<"success" | "warning" | "error">("success");
const hidePosted = ref(false);
const searchQuery = ref("");

// Filter questions based on hide toggle and search
const visibleQuestions = computed(() => {
  const query = searchQuery.value.trim();

  // If searching, filter by match and ignore hidePosted toggle
  if (query) {
    return store.questions.filter((q) => matchesQuestionFilter(q, query));
  }

  // No search - apply hidePosted toggle
  if (hidePosted.value) {
    return store.questions.filter((q) => !q.is_posted);
  }

  return store.questions;
});

const hiddenCount = computed(() => {
  // When searching, no "hidden" count (search overrides toggle)
  if (searchQuery.value.trim()) return 0;
  return hidePosted.value ? store.postedQuestions.length : 0;
});

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
const showPostSection = computed(
  () => isInterviewee.value && (store.answeredQuestions.length > 0 || store.stashedQuestions.length > 0),
);

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

async function handleStash(questionId: number) {
  await store.toggleStashQuestion(questionId);
}

async function handleClearAnswer(questionId: number) {
  await store.clearAnswer(questionId);
}

async function handleUnpost(questionId: number) {
  await store.unpostQuestion(questionId);
}

async function handlePost() {
  posting.value = true;
  postMessage.value = null;

  try {
    const result = await store.postAnswers(interviewIdNum.value);
    postMessage.value = result.message || `Posted ${result.posted_count} answers!`;

    if (result.skipped_count > 0) {
      // Something didn't make it to Discord - keep this visible, don't auto-dismiss.
      postMessageType.value = "warning";
    } else {
      postMessageType.value = "success";
      // Clear message after a few seconds
      setTimeout(() => {
        postMessage.value = null;
      }, 5000);
    }
  } catch (e) {
    postMessage.value = e instanceof Error ? e.message : "Failed to post answers";
    postMessageType.value = "error";
  } finally {
    posting.value = false;
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

async function retryLoad() {
  await Promise.all([
    store.fetchServer(serverId.value),
    store.fetchInterview(interviewIdNum.value),
    store.fetchQuestions(interviewIdNum.value),
  ]);
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
        @click="retryLoad"
        class="px-4 py-2 bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
      >
        Retry
      </button>
    </div>

    <!-- Content -->
    <template v-else-if="store.currentInterview">
      <!-- Header -->
      <div class="mb-6">
        <!-- Title row -->
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <div class="flex flex-wrap items-center gap-2 sm:gap-3">
              <h1 class="text-xl sm:text-2xl font-bold text-white">
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
            <p class="text-gray-400 text-sm sm:text-base mt-1">
              Interview #{{ store.currentInterview.interview_number }}
              <span class="mx-1 sm:mx-2">·</span>
              <span class="hidden sm:inline">Started </span>{{ formatDate(store.currentInterview.started_at) }}
              <template v-if="store.currentInterview.ended_at">
                <span class="mx-1 sm:mx-2">·</span>
                <span class="hidden sm:inline">Ended </span>{{ formatDate(store.currentInterview.ended_at) }}
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
        <div class="flex flex-wrap gap-3 sm:gap-6 mt-3 sm:mt-4 text-sm">
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
          <!-- Hide posted toggle -->
          <label v-if="store.postedQuestions.length > 0" class="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              v-model="hidePosted"
              class="w-3.5 h-3.5 rounded border-gray-600 bg-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer"
            />
            <span class="text-gray-400">Hide posted</span>
          </label>
        </div>

        <!-- Search -->
        <div class="mt-3 sm:mt-4 flex items-center gap-1.5">
          <div class="relative max-w-xs flex-1">
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search questions..."
              class="w-full bg-gray-700 border border-gray-600 rounded-md pl-8 pr-3 py-1.5 text-sm text-gray-100 placeholder-gray-400 focus:outline-none focus:border-indigo-500"
            />
            <svg
              class="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <button
              v-if="searchQuery"
              @click="searchQuery = ''"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <span
            class="shrink-0 text-gray-500 hover:text-gray-300 cursor-help"
            title='Filter syntax:
asker:name - only questions from a matching asker
content:text - only if question/answer contains text
"exact phrase" - literal phrase match
plain words - same as content: (all terms must match)'
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093M12 17h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </span>
        </div>
        <p v-if="searchQuery && visibleQuestions.length === 0" class="text-gray-500 text-sm mt-2">
          No matches found
        </p>
      </div>

      <!-- Post button -->
      <div v-if="showPostSection" class="mb-6 flex items-center space-x-4">
        <button
          v-if="canPost"
          @click="handlePost"
          :disabled="posting"
          class="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg transition-colors post-btn"
        >
          {{ posting ? "Posting..." : `Post ${store.answeredQuestions.length} Answers to Discord` }}
        </button>
        <span v-if="store.stashedQuestions.length > 0" class="text-yellow-400 text-sm">
          ({{ store.stashedQuestions.length }} stashed answer{{ store.stashedQuestions.length === 1 ? '' : 's' }} not included)
        </span>
        <span
          v-if="postMessage"
          :class="{
            'text-green-400': postMessageType === 'success',
            'text-yellow-400': postMessageType === 'warning',
            'text-red-400': postMessageType === 'error',
          }"
        >
          {{ postMessage }}
        </span>
      </div>

      <!-- Mobile: Card list -->
      <div class="md:hidden space-y-2">
        <!-- Hidden questions notice -->
        <div
          v-if="hidePosted && hiddenCount > 0"
          class="text-center py-2 text-gray-500 text-sm bg-gray-800/50 rounded-lg border border-gray-700"
        >
          {{ hiddenCount }} posted question{{ hiddenCount === 1 ? '' : 's' }} hidden
        </div>

        <QuestionRow
          v-for="question in visibleQuestions"
          :key="question.id"
          :question="question"
          :can-answer="canAnswer"
          :can-delete="canDelete"
          @answer="handleAnswer"
          @delete="handleDelete"
          @stash="handleStash"
          @clear-answer="handleClearAnswer"
          @unpost="handleUnpost"
        />

        <!-- Empty state -->
        <div
          v-if="store.questions.length === 0"
          class="text-center py-12 text-gray-500 bg-gray-800 rounded-lg"
        >
          No questions yet. Questions will appear here when asked in Discord.
        </div>
      </div>

      <!-- Desktop: Table -->
      <div class="hidden md:block bg-gray-800 rounded-lg overflow-hidden">
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
            <!-- Hidden questions notice -->
            <tr v-if="hidePosted && hiddenCount > 0">
              <td :colspan="canDelete ? 8 : 7" class="text-center py-2 text-gray-500 text-sm border-t border-gray-700">
                {{ hiddenCount }} posted question{{ hiddenCount === 1 ? '' : 's' }} hidden
              </td>
            </tr>
            <QuestionRow
              v-for="question in visibleQuestions"
              :key="question.id"
              :question="question"
              :can-answer="canAnswer"
              :can-delete="canDelete"
              @answer="handleAnswer"
              @delete="handleDelete"
              @stash="handleStash"
              @clear-answer="handleClearAnswer"
              @unpost="handleUnpost"
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
