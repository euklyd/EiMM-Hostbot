<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import type { QuestionResponse } from "../api/types";
import AnswerContent from "./AnswerContent.vue";
import FormattedText from "./FormattedText.vue";
import { stripMarkdownLinks, parseAnswerImages } from "../utils/markdown";
import { useThemeStore } from "../stores/theme";

const themeStore = useThemeStore();
const isSheetsTheme = computed(() => themeStore.theme.startsWith("sheets"));

const props = defineProps<{
  question: QuestionResponse;
  canAnswer: boolean;
  canDelete: boolean;
}>();

const emit = defineEmits<{
  answer: [questionId: number, answerText: string];
  delete: [questionId: number];
  stash: [questionId: number];
  clearAnswer: [questionId: number];
}>();

const isExpanded = ref(false);
const isEditing = ref(false);
const editText = ref(props.question.answer_text || "");
const saving = ref(false);
const mobileTextareaRef = ref<HTMLTextAreaElement | null>(null);
const desktopTextareaRef = ref<HTMLTextAreaElement | null>(null);

// Character limits for previews and Discord
const QUESTION_PREVIEW_LIMIT = 80;
const ANSWER_PREVIEW_LIMIT = 60;
const MAX_IMAGES = 10;
const DISCORD_FIELD_VALUE_LIMIT = 1024;
const MAX_ANSWER_LENGTH = 10000;

// Count images in edit text for validation
const editImageCount = computed(() => {
  const pattern = /^\s*(https?:\/\/\S+\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?\S*)?)\s*$/gim;
  const matches = editText.value.match(pattern);
  return matches ? matches.length : 0;
});

// Get text without image URLs for character counting
const editTextWithoutImages = computed(() => {
  const pattern = /^\s*https?:\/\/\S+\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?\S*)?\s*$/gim;
  return editText.value.replace(pattern, "").trim();
});

const editCharCount = computed(() => editTextWithoutImages.value.length);
const totalLength = computed(() => editText.value.length);
const willBeChunked = computed(() => editCharCount.value > DISCORD_FIELD_VALUE_LIMIT);
const tooManyImages = computed(() => editImageCount.value > MAX_IMAGES);
const tooLong = computed(() => totalLength.value > MAX_ANSWER_LENGTH);
const hasValidationError = computed(() => tooManyImages.value || tooLong.value);

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
  const text = stripMarkdownLinks(props.question.question_text);
  if (text.length <= QUESTION_PREVIEW_LIMIT) return text;
  return text.slice(0, QUESTION_PREVIEW_LIMIT) + "...";
});

const answerPreview = computed(() => {
  const text = props.question.answer_text;
  if (!text) return null;

  // Strip images and markdown links
  const { text: textWithoutImages, images } = parseAnswerImages(text);
  const stripped = stripMarkdownLinks(textWithoutImages);

  // Build preview with optional image indicator
  let preview = stripped.length <= ANSWER_PREVIEW_LIMIT
    ? stripped
    : stripped.slice(0, ANSWER_PREVIEW_LIMIT) + "...";

  if (images.length > 0) {
    const imgIndicator = images.length === 1 ? "{img}" : `{img x${images.length}}`;
    preview = preview ? `${preview} ${imgIndicator}` : imgIndicator;
  }

  return preview;
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

function toggleStash() {
  emit("stash", props.question.id);
}

function confirmClearAnswer() {
  if (confirm("Clear this answer? The question will return to unanswered.")) {
    isEditing.value = false;
    emit("clearAnswer", props.question.id);
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") {
    cancelEdit();
  } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    if (!hasValidationError.value && editText.value.trim()) {
      saveAnswer();
    }
  }
}

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function onTextareaInput(event: Event) {
  autoResize(event.target as HTMLTextAreaElement);
}

// Auto-expand when entering edit mode from external trigger
watch(isEditing, (editing) => {
  if (editing) {
    isExpanded.value = true;
    nextTick(() => {
      autoResize(mobileTextareaRef.value);
      autoResize(desktopTextareaRef.value);
    });
  }
});
</script>

<template>
  <!-- Mobile Card View (shown on small screens) -->
  <div class="md:hidden">
    <!-- Collapsed Card -->
    <div
      v-if="!isExpanded"
      class="bg-gray-800 border border-gray-700 rounded-lg p-3 cursor-pointer active:bg-gray-750"
      @click="toggleExpand"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="flex-1 min-w-0">
          <!-- Header: number, asker, status -->
          <div class="flex items-center gap-2 mb-1">
            <span class="text-gray-400 text-sm font-medium">#{{ question.question_number }}</span>
            <span class="text-gray-400 text-sm truncate">{{ question.asker_name }}</span>
            <!-- Status: dot (default) or Sheets-style checkbox -->
            <template v-if="isSheetsTheme">
              <svg v-if="question.is_posted" class="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 18 18" fill="none">
                <rect x="1" y="1" width="16" height="16" rx="2" fill="#34a853"/>
                <path d="M4.5 9l3 3 6-6" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <svg v-else-if="question.answer_text" class="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 18 18" fill="none">
                <rect x="1" y="1" width="16" height="16" rx="2" fill="#fbbc04"/>
                <path d="M5 9h8" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
              </svg>
              <svg v-else class="w-3.5 h-3.5 flex-shrink-0" viewBox="0 0 18 18" fill="none">
                <rect x="1" y="1" width="16" height="16" rx="2" stroke="#9aa0a6" stroke-width="1.5"/>
              </svg>
            </template>
            <span v-else :class="statusDotColor" class="inline-block w-2 h-2 rounded-full flex-shrink-0"></span>
          </div>
          <!-- Question preview -->
          <p class="text-gray-100 text-sm line-clamp-2">{{ question.question_text }}</p>
          <!-- Answer preview or action -->
          <div class="mt-1.5">
            <p v-if="answerPreview" class="text-gray-400 text-sm line-clamp-1">{{ answerPreview }}</p>
            <button
              v-else-if="canAnswer"
              type="button"
              class="text-indigo-400 text-sm font-medium"
              @click.stop="expandAndEdit"
            >
              + Answer
            </button>
            <span v-else class="text-gray-600 text-sm italic">Awaiting answer</span>
          </div>
        </div>
        <!-- Expand chevron -->
        <svg class="w-5 h-5 text-gray-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>

    <!-- Expanded Card -->
    <div
      v-else
      class="bg-gray-800 border border-gray-600 rounded-lg overflow-hidden"
    >
      <!-- Header -->
      <div
        class="flex items-center justify-between px-3 py-2 bg-gray-700/50 cursor-pointer active:bg-gray-700"
        @click="toggleExpand"
      >
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-gray-300 font-medium">#{{ question.question_number }}</span>
          <span class="text-gray-400 text-sm">{{ question.asker_name }}</span>
          <span :class="statusColor" class="text-sm">{{ statusText }}</span>
        </div>
        <svg class="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
        </svg>
      </div>

      <!-- Content -->
      <div class="px-3 py-3">
        <!-- Meta info -->
        <div class="flex items-center gap-3 text-xs text-gray-500 mb-2">
          <span>{{ formatDate(question.asked_at) }}</span>
          <a
            v-if="question.jump_url"
            :href="question.jump_url"
            target="_blank"
            class="text-indigo-400 jump-link"
            @click.stop
          >
            Jump to Discord
          </a>
        </div>

        <!-- Question text (quoted) -->
        <div class="bg-gray-900/50 rounded p-2 border-l-2 border-gray-500 mb-3">
          <p class="text-gray-300 text-sm">
            <FormattedText :text="question.question_text" />
          </p>
        </div>

        <!-- Answer section -->
        <div class="pl-3">
          <!-- Editing mode -->
          <template v-if="isEditing">
            <div class="space-y-2">
              <textarea
                ref="mobileTextareaRef"
                v-model="editText"
                class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-gray-100 text-sm resize-none max-h-64 overflow-y-auto focus:outline-none focus:border-indigo-500"
                rows="4"
                placeholder="Type your answer..."
                :disabled="saving"
                @input="onTextareaInput"
              ></textarea>
              <!-- Validation feedback -->
              <div class="flex flex-wrap items-center gap-2 text-xs">
                <span :class="willBeChunked ? 'text-yellow-400' : 'text-gray-500'">
                  {{ editCharCount }} chars
                  <span v-if="willBeChunked">(will be split)</span>
                </span>
                <span v-if="editImageCount > 0" :class="tooManyImages ? 'text-red-400' : 'text-gray-500'">
                  · {{ editImageCount }}/{{ MAX_IMAGES }} images
                </span>
              </div>
              <p v-if="tooManyImages" class="text-red-400 text-xs font-medium">
                Too many images — reduce to {{ MAX_IMAGES }} or fewer to save
              </p>
              <p v-if="tooLong" class="text-red-400 text-xs font-medium">
                Answer too long ({{ totalLength.toLocaleString() }}/{{ MAX_ANSWER_LENGTH.toLocaleString() }} chars)
              </p>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="saveAnswer"
                  :disabled="saving || !editText.trim() || hasValidationError"
                  class="flex-1 px-3 py-2 bg-green-600 hover:bg-green-700 active:bg-green-800 disabled:opacity-50 text-white text-sm rounded transition-colors"
                >
                  {{ saving ? "Saving..." : "Save" }}
                </button>
                <button
                  type="button"
                  @click="cancelEdit"
                  :disabled="saving"
                  class="px-3 py-2 bg-gray-600 hover:bg-gray-500 active:bg-gray-400 text-white text-sm rounded transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </template>

          <!-- Display mode with answer -->
          <template v-else-if="question.answer_text">
            <div class="text-gray-100 text-sm">
              <AnswerContent :text="question.answer_text" />
            </div>
            <div v-if="canAnswer && !question.is_posted" class="flex gap-3 mt-2">
              <button type="button" @click="startEditing" class="text-indigo-400 text-sm">
                Edit answer
              </button>
              <button type="button" @click="confirmClearAnswer" class="text-gray-400 text-sm">
                Clear answer
              </button>
            </div>
          </template>

          <!-- Display mode without answer -->
          <template v-else>
            <button
              v-if="canAnswer"
              type="button"
              @click="startEditing"
              class="text-indigo-400 text-sm py-1"
            >
              + Add answer
            </button>
            <span v-else class="text-gray-500 text-sm italic">Awaiting answer</span>
          </template>
        </div>

        <!-- Action buttons -->
        <div v-if="canAnswer || canDelete" class="mt-3 flex gap-3">
          <button
            v-if="canAnswer && !question.is_posted"
            type="button"
            @click.stop="toggleStash"
            class="text-sm"
            :class="question.is_stashed ? 'text-yellow-400' : 'text-gray-400'"
          >
            {{ question.is_stashed ? 'Unstash' : 'Stash' }}
          </button>
          <button
            v-if="canDelete"
            type="button"
            @click.stop="confirmDelete"
            class="text-red-400 text-sm"
          >
            Delete question
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Desktop Table Row (hidden on small screens) -->
  <template class="hidden md:contents">
    <!-- Collapsed Row -->
    <tr
      v-if="!isExpanded"
      class="hidden md:table-row border-t border-gray-700 hover:bg-gray-800/50 transition-colors cursor-pointer"
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
      <td class="px-2 py-1.5 text-gray-400 text-sm w-28 truncate asker-cell">
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
        :class="{ 'empty-answer-cell': isSheetsTheme && !question.answer_text }"
        :title="isAnswerTruncated ? (question.answer_text ?? undefined) : undefined"
        @click.stop="expandAndEdit"
      >
        <span v-if="answerPreview" class="text-gray-300">{{ answerPreview }}</span>
        <span v-else-if="canAnswer" class="text-indigo-400 hover:text-indigo-300">+ Answer</span>
        <span v-else class="text-gray-600 italic">—</span>
      </td>

      <!-- Status -->
      <td class="px-2 py-1.5 text-center w-12" :title="statusText">
        <template v-if="isSheetsTheme">
          <svg v-if="question.is_posted" class="w-4 h-4 inline" viewBox="0 0 18 18" fill="none">
            <rect x="1" y="1" width="16" height="16" rx="2" fill="#34a853"/>
            <path d="M4.5 9l3 3 6-6" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <svg v-else-if="question.answer_text" class="w-4 h-4 inline" viewBox="0 0 18 18" fill="none">
            <rect x="1" y="1" width="16" height="16" rx="2" fill="#fbbc04"/>
            <path d="M5 9h8" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
          <svg v-else class="w-4 h-4 inline" viewBox="0 0 18 18" fill="none">
            <rect x="1" y="1" width="16" height="16" rx="2" stroke="#9aa0a6" stroke-width="1.5"/>
          </svg>
        </template>
        <span v-else :class="statusDotColor" class="inline-block w-2 h-2 rounded-full"></span>
      </td>

      <!-- Jump link -->
      <td class="px-2 py-1.5 text-center w-10">
        <a
          v-if="question.jump_url"
          :href="question.jump_url"
          target="_blank"
          class="text-indigo-400 hover:text-indigo-300 jump-link"
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
      class="hidden md:table-row border-t border-gray-700"
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
                class="text-indigo-400 hover:text-indigo-300 text-xs jump-link"
                @click.stop
              >
                Jump to message
              </a>
              <button
                v-if="canAnswer && !question.is_posted"
                type="button"
                @click.stop="toggleStash"
                class="text-xs"
                :class="question.is_stashed ? 'text-yellow-400 hover:text-yellow-300' : 'text-gray-400 hover:text-gray-300'"
              >
                {{ question.is_stashed ? 'Unstash' : 'Stash' }}
              </button>
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
            <!-- Question text (quoted) -->
            <div class="bg-gray-900/50 rounded p-3 border-l-2 border-gray-500 mb-3">
              <p class="text-gray-300">
                <FormattedText :text="question.question_text" />
              </p>
            </div>

            <!-- Answer section -->
            <div class="pl-4">
              <!-- Editing mode -->
              <template v-if="isEditing">
                <div class="space-y-2">
                  <textarea
                    ref="desktopTextareaRef"
                    v-model="editText"
                    class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-gray-100 resize-none max-h-64 overflow-y-auto focus:outline-none focus:border-indigo-500"
                    rows="3"
                    placeholder="Type your answer... (Ctrl+Enter to save, Esc to cancel)"
                    :disabled="saving"
                    @keydown="handleKeydown"
                    @input="onTextareaInput"
                  ></textarea>
                  <!-- Validation feedback -->
                  <div class="flex flex-wrap items-center gap-3 text-xs">
                    <span :class="willBeChunked ? 'text-yellow-400' : 'text-gray-500'">
                      {{ editCharCount }} chars
                      <span v-if="willBeChunked">(will be split into multiple fields)</span>
                    </span>
                    <span v-if="editImageCount > 0" :class="tooManyImages ? 'text-red-400' : 'text-gray-500'">
                      {{ editImageCount }}/{{ MAX_IMAGES }} images
                    </span>
                  </div>
                  <p v-if="tooManyImages" class="text-red-400 text-xs font-medium">
                    Too many images — reduce to {{ MAX_IMAGES }} or fewer to save
                  </p>
                  <p v-if="tooLong" class="text-red-400 text-xs font-medium">
                    Answer too long ({{ totalLength.toLocaleString() }}/{{ MAX_ANSWER_LENGTH.toLocaleString() }} chars)
                  </p>
                  <div class="flex space-x-2">
                    <button
                      type="button"
                      @click="saveAnswer"
                      :disabled="saving || !editText.trim() || hasValidationError"
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
                <div class="text-gray-100">
                  <AnswerContent :text="question.answer_text" />
                </div>
                <div v-if="canAnswer && !question.is_posted" class="flex gap-3 mt-2">
                  <button
                    type="button"
                    @click="startEditing"
                    class="text-xs text-indigo-400 hover:text-indigo-300"
                  >
                    Edit answer
                  </button>
                  <button
                    type="button"
                    @click="confirmClearAnswer"
                    class="text-xs text-gray-400 hover:text-gray-300"
                  >
                    Clear answer
                  </button>
                </div>
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
</template>
