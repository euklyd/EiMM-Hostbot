<script setup lang="ts">
import { ref } from "vue";
import type { QuestionResponse } from "../api/types";

const props = defineProps<{
  questions: QuestionResponse[];
  askerName: string;
  defaultExpanded?: boolean;
}>();

const isExpanded = ref(props.defaultExpanded ?? false);

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function toggleExpand() {
  isExpanded.value = !isExpanded.value;
}

// Expose expand/collapse for parent control
defineExpose({
  expand: () => { isExpanded.value = true; },
  collapse: () => { isExpanded.value = false; },
});
</script>

<template>
  <div class="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden">
    <!-- Group header (always visible, clickable) -->
    <div
      class="flex items-center justify-between px-4 py-2 bg-gray-700/50 cursor-pointer hover:bg-gray-700 transition-colors"
      @click="toggleExpand"
    >
      <div class="flex items-center gap-3">
        <span class="text-gray-300 font-medium">{{ askerName }}</span>
        <span class="text-gray-500 text-sm">
          {{ questions.length }} question{{ questions.length !== 1 ? 's' : '' }}
        </span>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-gray-500 text-xs">
          {{ formatShortDate(questions[0].asked_at) }}
          <template v-if="questions.length > 1 && questions[questions.length - 1].asked_at !== questions[0].asked_at">
            – {{ formatShortDate(questions[questions.length - 1].asked_at) }}
          </template>
        </span>
        <svg
          class="w-4 h-4 text-gray-400 transition-transform"
          :class="{ 'rotate-180': isExpanded }"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>

    <!-- Questions (shown when expanded) -->
    <div v-if="isExpanded" class="divide-y divide-gray-700">
      <div
        v-for="question in questions"
        :key="question.id"
        class="px-4 py-3"
      >
        <!-- Question header -->
        <div class="flex items-center justify-between mb-2">
          <span class="text-gray-500 font-mono text-sm">Q{{ question.question_number }}</span>
          <span class="text-gray-500 text-xs">{{ formatDate(question.asked_at) }}</span>
        </div>

        <!-- Question (quoted) -->
        <div class="bg-gray-900/50 rounded p-3 border-l-2 border-gray-500 mb-3">
          <p class="text-gray-300">{{ question.question_text }}</p>
        </div>

        <!-- Answer -->
        <p class="text-gray-100 whitespace-pre-wrap">{{ question.answer_text }}</p>
        <p v-if="question.answered_at" class="text-gray-500 text-xs mt-2">
          Answered {{ formatDate(question.answered_at) }}
        </p>
      </div>
    </div>

    <!-- Collapsed preview -->
    <div v-else class="px-4 py-2 text-gray-400 text-sm">
      <template v-for="(q, idx) in questions.slice(0, 3)" :key="q.id">
        <span class="text-gray-500">Q{{ q.question_number }}:</span>
        {{ q.question_text.slice(0, 50) }}{{ q.question_text.length > 50 ? '...' : '' }}
        <span v-if="idx < Math.min(questions.length, 3) - 1" class="mx-2 text-gray-600">·</span>
      </template>
      <span v-if="questions.length > 3" class="text-gray-500 ml-2">
        +{{ questions.length - 3 }} more
      </span>
    </div>
  </div>
</template>
