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

const serverIdNum = computed(() => parseInt(props.serverId));
const interviewIdNum = computed(() => parseInt(props.interviewId));

// Check if current user is the interviewee
const isInterviewee = computed(() => {
  if (!auth.user || !store.currentInterview) return false;
  return auth.user.id === store.currentInterview.interviewee_id;
});

// Check if current user is a manager (simplified - would need backend check for full accuracy)
const isManager = computed(() => {
  if (!auth.user) return false;
  // For now, assume managers based on guild admin permission from OAuth
  const guild = auth.user.guilds.find((g) => parseInt(g.id) === serverIdNum.value);
  return guild ? (parseInt(guild.permissions) & 0x8) !== 0 : false;
});

const canAnswer = computed(() => isInterviewee.value);
const canDelete = computed(() => isManager.value);
const canPost = computed(() => isInterviewee.value && store.answeredQuestions.length > 0);

onMounted(async () => {
  await Promise.all([
    store.fetchServer(serverIdNum.value),
    store.fetchInterview(interviewIdNum.value),
    store.fetchQuestions(interviewIdNum.value),
  ]);

  // Connect WebSocket for real-time updates
  store.connectWebSocket(serverIdNum.value);
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

    <!-- Content -->
    <template v-else-if="store.currentInterview">
      <!-- Header -->
      <div class="mb-6">
        <div class="flex items-center justify-between">
          <div>
            <h1 class="text-2xl font-bold text-white">
              {{ store.currentInterview.interviewee_name }}'s Interview
            </h1>
            <p class="text-gray-400">
              Interview #{{ store.currentInterview.interview_number }}
              <span class="mx-2">·</span>
              Started {{ formatDate(store.currentInterview.started_at) }}
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
        <table class="w-full">
          <thead class="bg-gray-700">
            <tr>
              <th class="px-4 py-3 text-left text-gray-300 text-sm font-medium w-12">#</th>
              <th class="px-4 py-3 text-left text-gray-300 text-sm font-medium">Question</th>
              <th class="px-4 py-3 text-left text-gray-300 text-sm font-medium">Answer</th>
              <th class="px-4 py-3 text-center text-gray-300 text-sm font-medium w-24">Status</th>
              <th v-if="canDelete" class="px-4 py-3 text-center text-gray-300 text-sm font-medium w-20">Actions</th>
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
