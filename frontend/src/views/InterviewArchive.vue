<script setup lang="ts">
import { onMounted, computed } from "vue";
import { useInterviewStore } from "../stores/interview";

const props = defineProps<{
  serverId: string;
  interviewId: string;
}>();

const store = useInterviewStore();

// Use string for Discord IDs to avoid precision loss
const serverId = computed(() => props.serverId);
const interviewIdNum = computed(() => parseInt(props.interviewId)); // DB ID, safe as int

onMounted(async () => {
  await Promise.all([
    store.fetchServer(serverId.value),
    store.fetchInterview(interviewIdNum.value),
    // Archive view only shows posted questions
    store.fetchQuestions(interviewIdNum.value, "posted"),
  ]);
});

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function formatDateShort(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString();
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
        <div class="flex items-center space-x-3">
          <h1 class="text-2xl font-bold text-white">
            {{ store.currentInterview.interviewee_name }}'s Interview
          </h1>
          <span class="px-2 py-1 bg-gray-700 text-gray-400 text-sm rounded">
            Archived
          </span>
        </div>
        <p class="text-gray-400 mt-1">
          Interview #{{ store.currentInterview.interview_number }}
          <span class="mx-2">·</span>
          {{ formatDateShort(store.currentInterview.started_at) }}
          <template v-if="store.currentInterview.ended_at">
            <span class="mx-2">→</span>
            {{ formatDateShort(store.currentInterview.ended_at) }}
          </template>
        </p>
      </div>

      <!-- Stats -->
      <div class="flex space-x-6 mb-6 text-sm">
        <div>
          <span class="text-gray-400">Questions Answered:</span>
          <span class="text-white ml-1">{{ store.questions.length }}</span>
        </div>
      </div>

      <!-- Questions list (read-only, card format) -->
      <div class="space-y-4">
        <div
          v-for="question in store.questions"
          :key="question.id"
          class="bg-gray-800 rounded-lg p-4 border border-gray-700"
        >
          <!-- Question header -->
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center space-x-2">
              <span class="text-gray-500 font-mono">Q{{ question.question_number }}</span>
              <span class="text-gray-400">{{ question.asker_name }}</span>
            </div>
            <span class="text-gray-500 text-sm">{{ formatDate(question.asked_at) }}</span>
          </div>

          <!-- Question text -->
          <p class="text-gray-200 mb-3">{{ question.question_text }}</p>

          <!-- Answer -->
          <div class="bg-gray-900/50 rounded p-3 border-l-2 border-indigo-500">
            <p class="text-gray-100 whitespace-pre-wrap">{{ question.answer_text }}</p>
            <p v-if="question.answered_at" class="text-gray-500 text-sm mt-2">
              Answered {{ formatDate(question.answered_at) }}
            </p>
          </div>
        </div>

        <!-- Empty state -->
        <div
          v-if="store.questions.length === 0"
          class="text-center py-12 text-gray-500"
        >
          No questions were posted for this interview.
        </div>
      </div>
    </template>
  </div>
</template>
