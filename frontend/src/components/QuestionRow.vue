<script setup lang="ts">
import { ref, computed } from "vue";
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

const isEditing = ref(false);
const editText = ref(props.question.answer_text || "");
const saving = ref(false);

const statusColor = computed(() => {
  if (props.question.is_posted) return "text-green-400";
  if (props.question.answer_text) return "text-yellow-400";
  return "text-gray-500";
});

const statusText = computed(() => {
  if (props.question.is_posted) return "Posted";
  if (props.question.answer_text) return "Answered";
  return "Pending";
});

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
}

function confirmDelete() {
  if (confirm("Delete this question? This cannot be undone.")) {
    emit("delete", props.question.id);
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString();
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    cancelEdit();
  } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    saveAnswer();
  }
}
</script>

<template>
  <tr class="border-t border-gray-700 hover:bg-gray-800/50 transition-colors">
    <!-- Question number -->
    <td class="px-4 py-3 text-gray-400 text-center w-12">
      {{ question.question_number }}
    </td>

    <!-- Question -->
    <td class="px-4 py-3">
      <div class="text-sm text-gray-400 mb-1">
        {{ question.asker_name }}
        <span class="text-gray-600 text-xs ml-2">{{ formatDate(question.asked_at) }}</span>
      </div>
      <div class="text-gray-100">{{ question.question_text }}</div>
      <a
        v-if="question.jump_url"
        :href="question.jump_url"
        target="_blank"
        class="text-xs text-indigo-400 hover:text-indigo-300 mt-1 inline-block"
      >
        Jump to message
      </a>
    </td>

    <!-- Answer -->
    <td class="px-4 py-3">
      <!-- Editing mode -->
      <template v-if="isEditing">
        <div class="space-y-2">
          <textarea
            v-model="editText"
            class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-gray-100 resize-none focus:outline-none focus:border-indigo-500"
            rows="4"
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
          @click="startEditing"
          class="text-indigo-400 hover:text-indigo-300"
        >
          + Add answer
        </button>
        <span v-else class="text-gray-500 italic">Awaiting answer</span>
      </template>
    </td>

    <!-- Status -->
    <td class="px-4 py-3 text-center w-24">
      <span :class="statusColor" class="text-sm font-medium">{{ statusText }}</span>
    </td>

    <!-- Actions -->
    <td v-if="canDelete" class="px-4 py-3 text-center w-20">
      <button
        type="button"
        @click="confirmDelete"
        class="text-red-400 hover:text-red-300 text-sm"
        title="Delete question"
      >
        Delete
      </button>
    </td>
  </tr>
</template>
