<script setup lang="ts">
import { onMounted, computed, ref } from "vue";
import { useInterviewStore } from "../stores/interview";
import ArchiveQuestionGroup from "../components/ArchiveQuestionGroup.vue";
import type { QuestionResponse } from "../api/types";

const props = defineProps<{
  serverId: string;
  interviewId: string;
}>();

const store = useInterviewStore();
const groupRefs = ref<InstanceType<typeof ArchiveQuestionGroup>[]>([]);
const allExpanded = ref(false);

// Use string for Discord IDs to avoid precision loss
const serverId = computed(() => props.serverId);
const interviewIdNum = computed(() => parseInt(props.interviewId)); // DB ID, safe as int

// Group consecutive questions by asker
interface QuestionGroup {
  askerName: string;
  askerId: string;
  questions: QuestionResponse[];
}

const questionGroups = computed<QuestionGroup[]>(() => {
  const groups: QuestionGroup[] = [];
  let currentGroup: QuestionGroup | null = null;

  for (const q of store.questions) {
    if (currentGroup && currentGroup.askerId === q.asker_id) {
      // Same asker, add to current group
      currentGroup.questions.push(q);
    } else {
      // New asker, start new group
      currentGroup = {
        askerName: q.asker_name,
        askerId: q.asker_id,
        questions: [q],
      };
      groups.push(currentGroup);
    }
  }

  return groups;
});

onMounted(async () => {
  await Promise.all([
    store.fetchServer(serverId.value),
    store.fetchInterview(interviewIdNum.value),
    // Archive view only shows posted questions
    store.fetchQuestions(interviewIdNum.value, "posted"),
  ]);
});

function formatDateShort(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString();
}

function expandAll() {
  groupRefs.value.forEach((ref) => ref?.expand());
  allExpanded.value = true;
}

function collapseAll() {
  groupRefs.value.forEach((ref) => ref?.collapse());
  allExpanded.value = false;
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

      <!-- Stats & Controls -->
      <div class="flex items-center justify-between mb-6">
        <div class="flex space-x-6 text-sm">
          <div>
            <span class="text-gray-400">Questions:</span>
            <span class="text-white ml-1">{{ store.questions.length }}</span>
          </div>
          <div>
            <span class="text-gray-400">Askers:</span>
            <span class="text-white ml-1">{{ questionGroups.length }}</span>
          </div>
        </div>

        <!-- Expand/Collapse buttons -->
        <div v-if="questionGroups.length > 0" class="flex gap-2">
          <button
            type="button"
            @click="expandAll"
            class="px-3 py-1 text-sm text-gray-400 hover:text-white border border-gray-600 hover:border-gray-500 rounded transition-colors"
          >
            Expand All
          </button>
          <button
            type="button"
            @click="collapseAll"
            class="px-3 py-1 text-sm text-gray-400 hover:text-white border border-gray-600 hover:border-gray-500 rounded transition-colors"
          >
            Collapse All
          </button>
        </div>
      </div>

      <!-- Question groups -->
      <div class="space-y-3">
        <ArchiveQuestionGroup
          v-for="(group, idx) in questionGroups"
          :key="`${group.askerId}-${idx}`"
          :ref="(el) => { if (el) groupRefs[idx] = el as InstanceType<typeof ArchiveQuestionGroup> }"
          :questions="group.questions"
          :asker-name="group.askerName"
        />

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
