<script setup lang="ts">
import { ref, computed, watch } from "vue";
import type { QuestionResponse } from "../api/types";

const props = defineProps<{
  question: QuestionResponse;
  canAnswer: boolean;
  canDelete: boolean;
}>();

const emit = defineEmits<{
  answer: [questionId: number, answerText: string];
  delete: [questionId: number];
}>();

const isExpanded = ref(false);
const isEditing = ref(false);
const editText = ref(props.question.answer_text || "");
const saving = ref(false);

// Character limits for previews
const QUESTION_PREVIEW_LIMIT = 80;
const ANSWER_PREVIEW_LIMIT = 60;

const statusColor = computed(() => {
  if (props.question.is_posted) return "text-green-400";
  if (props.question.answer_text) return "text-yellow-400";
  return "text-gray-500";
});

const statusDotColor = computed(() => {
  if (props.question.is_posted) return "bg-green-400";
  if (props.question.answer_text) return "bg-yellow-400";
  return "bg-gray-500";
});

const statusText = computed(() => {
  if (props.question.is_posted) return "Posted";
  if (props.question.answer_text) return "Answered";
  return "Pending";
});

const questionPreview = computed(() => {
  const text = props.question.question_text;
  if (text.length <= QUESTION_PREVIEW_LIMIT) return text;
  return text.slice(0, QUESTION_PREVIEW_LIMIT) + "...";
});

const answerPreview = computed(() => {
  const text = props.question.answer_text;
  if (!text) return null;
  if (text.length <= ANSWER_PREVIEW_LIMIT) return text;
  return text.slice(0, ANSWER_PREVIEW_LIMIT) + "...";
});

const isQuestionTruncated = computed(() => {
  return props.question.question_text.length > QUESTION_PREVIEW_LIMIT;
});

const isAnswerTruncated = computed(() => {
  const text = props.question.answer_text;
  return text && text.length > ANSWER_PREVIEW_LIMIT;
});

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function formatShortDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function expandAndEdit() {
  if (!props.canAnswer) {
    isExpanded.value = true;
    return;
  }
  isExpanded.value = true;
  startEditing();
}

function toggleExpand() {
  if (isEditing.value) return; // Don't collapse while editing
  isExpanded.value = !isExpanded.value;
}

function startEditing() {
  if (!props.canAnswer) return;
  editText.value = props.question.answer_text || "";
  isEditing.value = true;
}

async function saveAnswer() {
  if (!editText.value.trim()) return;

  saving.value = true;
  try {
    emit("answer", props.question.id, editText.value.trim());
    isEditing.value = false;
  } finally {
    saving.value = false;
  }
}

function cancelEdit() {
  isEditing.value = false;
  editText.value = props.question.answer_text || "";
  // Collapse if no answer exists
  if (!props.question.answer_text) {
    isExpanded.value = false;
  }
}

function confirmDelete() {
  if (confirm("Delete this question? This cannot be undone.")) {
    emit("delete", props.question.id);
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    cancelEdit();
  } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    saveAnswer();
  }
}

// Auto-expand when entering edit mode from external trigger
watch(isEditing, (editing) => {
  if (editing) {
    isExpanded.value = true;
  }
});
</script>

<template>
  <!-- Collapsed Row -->
  <tr
    v-if="!isExpanded"
    class="border-t border-gray-700 hover:bg-gray-800/50 transition-colors cursor-pointer"
    @click="toggleExpand"
  >
    <!-- Question number -->
    <td class="px-3 py-1.5 text-gray-400 text-center text-sm w-10">
      {{ question.question_number }}
    </td>

    <!-- Date -->
    <td class="px-2 py-1.5 text-gray-500 text-xs w-16" :title="formatDate(question.asked_at)">
      {{ formatShortDate(question.asked_at) }}
    </td>

    <!-- Asker -->
    <td class="px-2 py-1.5 text-gray-400 text-sm w-28 truncate">
      {{ question.asker_name }}
    </td>

    <!-- Question preview -->
    <td
      class="px-2 py-1.5 text-gray-100 text-sm"
      :title="isQuestionTruncated ? question.question_text : undefined"
    >
      {{ questionPreview }}
    </td>

    <!-- Answer preview -->
    <td
      class="px-2 py-1.5 text-sm w-48 cursor-pointer"
      :title="isAnswerTruncated ? (question.answer_text ?? undefined) : undefined"
      @click.stop="expandAndEdit"
    >
      <span v-if="answerPreview" class="text-gray-300">{{ answerPreview }}</span>
      <span v-else-if="canAnswer" class="text-indigo-400 hover:text-indigo-300">+ Answer</span>
      <span v-else class="text-gray-600 italic">—</span>
    </td>

    <!-- Status -->
    <td class="px-2 py-1.5 text-center w-12" :title="statusText">
      <span :class="statusDotColor" class="inline-block w-2 h-2 rounded-full"></span>
    </td>

    <!-- Jump link -->
    <td class="px-2 py-1.5 text-center w-10">
      <a
        v-if="question.jump_url"
        :href="question.jump_url"
        target="_blank"
        class="text-indigo-400 hover:text-indigo-300"
        title="Jump to message"
        @click.stop
      >
        <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      </a>
    </td>

    <!-- Actions (delete) -->
    <td v-if="canDelete" class="px-2 py-1.5 text-center w-10">
      <button
        type="button"
        @click.stop="confirmDelete"
        class="text-red-400 hover:text-red-300"
        title="Delete question"
      >
        <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
        </svg>
      </button>
    </td>
  </tr>

  <!-- Expanded Row -->
  <tr
    v-else
    class="border-t border-gray-700"
  >
    <td :colspan="canDelete ? 8 : 7" class="p-2">
      <div class="bg-gray-750 border border-gray-600 rounded-lg overflow-hidden">
        <!-- Collapsible header -->
        <div
          class="flex items-center justify-between px-4 py-2 bg-gray-700/50 cursor-pointer hover:bg-gray-700 transition-colors"
          @click="toggleExpand"
        >
          <div class="flex items-center gap-4">
            <span class="text-gray-300 font-medium">#{{ question.question_number }}</span>
            <span class="text-gray-400 text-sm">{{ question.asker_name }}</span>
            <span class="text-gray-500 text-xs">{{ formatDate(question.asked_at) }}</span>
            <span :class="statusColor" class="text-sm font-medium">{{ statusText }}</span>
          </div>
          <div class="flex items-center gap-3">
            <a
              v-if="question.jump_url"
              :href="question.jump_url"
              target="_blank"
              class="text-indigo-400 hover:text-indigo-300 text-xs"
              @click.stop
            >
              Jump to message
            </a>
            <button
              v-if="canDelete"
              type="button"
              @click.stop="confirmDelete"
              class="text-red-400 hover:text-red-300 text-xs"
            >
              Delete
            </button>
            <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
            </svg>
          </div>
        </div>

        <!-- Content -->
        <div class="px-4 py-3">
          <!-- Question text -->
          <div class="text-gray-100 mb-3">{{ question.question_text }}</div>

          <!-- Answer section -->
          <div class="pl-4 border-l-2 border-indigo-500/50">
        <!-- Editing mode -->
        <template v-if="isEditing">
          <div class="space-y-2">
            <textarea
              v-model="editText"
              class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-gray-100 resize-none focus:outline-none focus:border-indigo-500"
              rows="3"
              placeholder="Type your answer... (Ctrl+Enter to save, Esc to cancel)"
              :disabled="saving"
              @keydown="handleKeydown"
            ></textarea>
            <div class="flex space-x-2">
              <button
                type="button"
                @click="saveAnswer"
                :disabled="saving || !editText.trim()"
                class="px-3 py-1 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm rounded transition-colors"
              >
                {{ saving ? "Saving..." : "Save" }}
              </button>
              <button
                type="button"
                @click="cancelEdit"
                :disabled="saving"
                class="px-3 py-1 bg-gray-600 hover:bg-gray-500 text-white text-sm rounded transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </template>

        <!-- Display mode with answer -->
        <template v-else-if="question.answer_text">
          <div class="text-gray-100 whitespace-pre-wrap">{{ question.answer_text }}</div>
          <button
            v-if="canAnswer && !question.is_posted"
            type="button"
            @click="startEditing"
            class="text-xs text-indigo-400 hover:text-indigo-300 mt-2"
          >
            Edit answer
          </button>
        </template>

        <!-- Display mode without answer -->
        <template v-else>
          <button
            v-if="canAnswer"
            type="button"
            @click="startEditing"
            class="text-indigo-400 hover:text-indigo-300"
          >
            + Add answer
          </button>
          <span v-else class="text-gray-500 italic">Awaiting answer</span>
        </template>
          </div>
        </div>
      </div>
    </td>
  </tr>
</template>
