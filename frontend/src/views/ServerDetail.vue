<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useInterviewStore } from "../stores/interview";
import type { InterviewSummary, ServerStatsResponse } from "../api/types";
import * as api from "../api/client";

const props = defineProps<{
  serverId: string;
}>();

const store = useInterviewStore();

const interviews = ref<InterviewSummary[]>([]);
const stats = ref<ServerStatsResponse | null>(null);
const loadingInterviews = ref(false);

// Use string directly to avoid JavaScript number precision loss
const serverId = computed(() => props.serverId);

onMounted(async () => {
  await Promise.all([
    store.fetchServer(serverId.value),
    fetchInterviews(),
    fetchStats(),
  ]);
});

async function fetchInterviews() {
  loadingInterviews.value = true;
  try {
    interviews.value = await api.getInterviews(serverId.value);
  } catch (e) {
    console.error("Failed to fetch interviews:", e);
  } finally {
    loadingInterviews.value = false;
  }
}

async function fetchStats() {
  try {
    stats.value = await api.getServerStats(serverId.value);
  } catch (e) {
    console.error("Failed to fetch stats:", e);
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString();
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}
</script>

<template>
  <div>
    <!-- Back link -->
    <router-link to="/" class="text-indigo-400 hover:text-indigo-300 mb-4 inline-block">
      ← Back to servers
    </router-link>

    <!-- Loading -->
    <div v-if="store.loading" class="animate-pulse">
      <div class="h-8 bg-gray-700 rounded w-1/3 mb-4"></div>
      <div class="h-4 bg-gray-700 rounded w-1/4 mb-8"></div>
    </div>

    <!-- Error -->
    <div v-else-if="store.error" class="bg-red-900/50 border border-red-700 rounded-lg p-6">
      <p class="text-red-200 mb-4">{{ store.error }}</p>
      <button
        @click="store.fetchServer(serverId)"
        class="px-4 py-2 bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
      >
        Retry
      </button>
    </div>

    <!-- Content -->
    <template v-else-if="store.currentServer">
      <div class="mb-8">
        <h1 class="text-2xl font-bold text-white mb-2">
          {{ store.currentServer.server.name }}
        </h1>
        <span
          v-if="store.currentServer.server.active"
          class="px-2 py-1 bg-green-900/50 text-green-400 text-sm rounded"
        >
          Interviews Active
        </span>
        <span v-else class="px-2 py-1 bg-gray-700 text-gray-400 text-sm rounded">
          Interviews Inactive
        </span>
      </div>

      <!-- Stats cards -->
      <div v-if="stats" class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-2xl font-bold text-white">{{ stats.total_interviews }}</div>
          <div class="text-gray-400 text-sm">Total Interviews</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-2xl font-bold text-white">{{ stats.total_questions }}</div>
          <div class="text-gray-400 text-sm">Total Questions</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-2xl font-bold text-white">
            {{ stats.avg_questions_per_interview.toFixed(1) }}
          </div>
          <div class="text-gray-400 text-sm">Avg Questions/Interview</div>
        </div>
        <div class="bg-gray-800 rounded-lg p-4">
          <div class="text-2xl font-bold text-white">
            {{ formatDuration(stats.avg_answer_time_seconds) }}
          </div>
          <div class="text-gray-400 text-sm">Avg Answer Time</div>
        </div>
      </div>

      <!-- Current interview -->
      <div v-if="store.currentServer.current_interview" class="mb-8">
        <h2 class="text-lg font-semibold text-white mb-3">Current Interview</h2>
        <router-link
          :to="{
            name: 'interview',
            params: {
              serverId: serverId,
              interviewId: store.currentServer.current_interview.id,
            },
          }"
          class="block bg-indigo-900/30 hover:bg-indigo-900/50 border border-indigo-700 rounded-lg p-4 transition-colors"
        >
          <div class="flex items-center justify-between">
            <div>
              <span class="text-xl font-semibold text-white">
                {{ store.currentServer.current_interview.interviewee_name }}
              </span>
              <span class="text-gray-400 ml-2">
                Interview #{{ store.currentServer.current_interview.interview_number }}
              </span>
            </div>
            <span class="text-indigo-400">View →</span>
          </div>
          <p class="text-gray-400 text-sm mt-1">
            Started {{ formatDate(store.currentServer.current_interview.started_at) }}
          </p>
        </router-link>
      </div>

      <!-- Interview history -->
      <div>
        <h2 class="text-lg font-semibold text-white mb-3">Interview History</h2>

        <div v-if="loadingInterviews" class="animate-pulse space-y-2">
          <div v-for="i in 5" :key="i" class="h-12 bg-gray-800 rounded"></div>
        </div>

        <div v-else-if="interviews.length === 0" class="text-gray-500 py-8 text-center">
          No past interviews.
        </div>

        <div v-else class="space-y-2">
          <router-link
            v-for="interview in interviews"
            :key="interview.id"
            :to="{
              name: interview.is_current ? 'interview' : 'archive',
              params: { serverId: serverId, interviewId: interview.id },
            }"
            class="block bg-gray-800 hover:bg-gray-750 border border-gray-700 rounded-lg px-4 py-3 transition-colors"
          >
            <div class="flex items-center justify-between">
              <div>
                <span class="text-white font-medium">
                  {{ interview.interviewee_name }}
                </span>
                <span class="text-gray-500 ml-2">#{{ interview.interview_number }}</span>
              </div>
              <div class="flex items-center space-x-3">
                <span class="text-gray-400 text-sm">
                  {{ formatDate(interview.started_at) }}
                </span>
                <span
                  v-if="interview.is_current"
                  class="px-2 py-0.5 bg-green-900/50 text-green-400 text-xs rounded"
                >
                  Current
                </span>
              </div>
            </div>
          </router-link>
        </div>
      </div>
    </template>
  </div>
</template>
