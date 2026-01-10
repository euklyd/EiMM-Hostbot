<script setup lang="ts">
import { ref } from "vue";
import type { QuestionResponse } from "../api/types";
import AnswerContent from "./AnswerContent.vue";
import FormattedText from "./FormattedText.vue";
import { stripMarkdownLinks } from "../utils/markdown";

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

function truncateQuestion(text: string, limit: number): string {
  const stripped = stripMarkdownLinks(text);
  if (stripped.length <= limit) return stripped;
  return stripped.slice(0, limit) + "...";
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
      class="flex items-center justify-between px-3 sm:px-4 py-2.5 sm:py-2 bg-gray-700/50 cursor-pointer hover:bg-gray-700 active:bg-gray-600 transition-colors"
      @click="toggleExpand"
    >
      <div class="flex items-center gap-2 sm:gap-3 min-w-0">
        <span class="text-gray-300 font-medium text-sm sm:text-base truncate">{{ askerName }}</span>
        <span class="text-gray-500 text-xs sm:text-sm flex-shrink-0">
          {{ questions.length }} Q{{ questions.length !== 1 ? 's' : '' }}
        </span>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <span class="text-gray-500 text-xs hidden sm:inline">
          {{ formatShortDate(questions[0].asked_at) }}
          <template v-if="questions.length > 1 && questions[questions.length - 1].asked_at !== questions[0].asked_at">
            – {{ formatShortDate(questions[questions.length - 1].asked_at) }}
          </template>
        </span>
        <svg
          class="w-5 h-5 sm:w-4 sm:h-4 text-gray-400 transition-transform"
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
        class="px-3 sm:px-4 py-3"
      >
        <!-- Question header -->
        <div class="flex items-center justify-between mb-2">
          <span class="text-gray-500 font-mono text-xs sm:text-sm">Q{{ question.question_number }}</span>
          <span class="text-gray-500 text-xs">{{ formatDate(question.asked_at) }}</span>
        </div>

        <!-- Question (quoted) -->
        <div class="bg-gray-900/50 rounded p-2 sm:p-3 border-l-2 border-gray-500 mb-3">
          <p class="text-gray-300 text-sm sm:text-base">
            <FormattedText :text="question.question_text" />
          </p>
        </div>

        <!-- Answer -->
        <div class="text-gray-100 text-sm sm:text-base">
          <AnswerContent :text="question.answer_text" />
        </div>
        <p v-if="question.answered_at" class="text-gray-500 text-xs mt-2">
          Answered {{ formatDate(question.answered_at) }}
        </p>
      </div>
    </div>

    <!-- Collapsed preview (simplified on mobile) -->
    <div v-else class="px-3 sm:px-4 py-2 text-gray-400 text-xs sm:text-sm">
      <!-- Mobile: just show first question preview -->
      <span class="sm:hidden">
        <span class="text-gray-500">Q{{ questions[0].question_number }}:</span>
        {{ truncateQuestion(questions[0].question_text, 40) }}
        <span v-if="questions.length > 1" class="text-gray-500"> +{{ questions.length - 1 }} more</span>
      </span>
      <!-- Desktop: show up to 3 questions -->
      <span class="hidden sm:inline">
        <template v-for="(q, idx) in questions.slice(0, 3)" :key="q.id">
          <span class="text-gray-500">Q{{ q.question_number }}:</span>
          {{ truncateQuestion(q.question_text, 50) }}
          <span v-if="idx < Math.min(questions.length, 3) - 1" class="mx-2 text-gray-600">·</span>
        </template>
        <span v-if="questions.length > 3" class="text-gray-500 ml-2">
          +{{ questions.length - 3 }} more
        </span>
      </span>
    </div>
  </div>
</template>
