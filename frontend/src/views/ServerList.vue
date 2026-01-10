<script setup lang="ts">
import { onMounted } from "vue";
import { useAuthStore } from "../stores/auth";
import { useInterviewStore } from "../stores/interview";

const auth = useAuthStore();
const store = useInterviewStore();

onMounted(async () => {
  if (auth.isAuthenticated) {
    await store.fetchServers();
  }
});
</script>

<template>
  <div>
    <!-- Loading auth state -->
    <template v-if="auth.loading">
      <div class="text-center py-16">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500 mx-auto"></div>
        <p class="text-gray-400 mt-4">Loading...</p>
      </div>
    </template>

    <!-- Not authenticated -->
    <template v-else-if="!auth.isAuthenticated">
      <div class="text-center py-12 sm:py-16 px-4">
        <h1 class="text-2xl sm:text-3xl font-bold text-white mb-3 sm:mb-4">Discord Interviews</h1>
        <p class="text-gray-400 mb-6 sm:mb-8 text-sm sm:text-base">
          Login with Discord to manage your server's interviews.
        </p>
        <button
          @click="auth.login()"
          class="px-5 sm:px-6 py-2.5 sm:py-3 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white rounded-lg text-base sm:text-lg transition-colors"
        >
          Login with Discord
        </button>
      </div>
    </template>

    <!-- Authenticated -->
    <template v-else>
      <h1 class="text-xl sm:text-2xl font-bold text-white mb-4 sm:mb-6">Your Servers</h1>

      <!-- Loading -->
      <div v-if="store.loading" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
        <div v-for="i in 3" :key="i" class="bg-gray-800 rounded-lg p-4 sm:p-6 animate-pulse">
          <div class="h-5 sm:h-6 bg-gray-700 rounded w-3/4 mb-3 sm:mb-4"></div>
          <div class="h-4 bg-gray-700 rounded w-1/2"></div>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="store.error" class="bg-red-900/50 border border-red-700 rounded-lg p-3 sm:p-4">
        <p class="text-red-200 text-sm sm:text-base">{{ store.error }}</p>
      </div>

      <!-- Empty state -->
      <div
        v-else-if="store.servers.length === 0"
        class="text-center py-12 sm:py-16 bg-gray-800/50 rounded-lg px-4"
      >
        <p class="text-gray-400 text-sm sm:text-base">
          No servers with interview configuration found.
        </p>
        <p class="text-gray-500 text-xs sm:text-sm mt-2">
          Use the <code class="bg-gray-700 px-1 rounded">iv setup</code> command in Discord to set up interviews.
        </p>
      </div>

      <!-- Server grid -->
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
        <router-link
          v-for="item in store.servers"
          :key="item.server.id"
          :to="{ name: 'server', params: { serverId: item.server.id } }"
          class="bg-gray-800 hover:bg-gray-750 active:bg-gray-700 border border-gray-700 hover:border-gray-600 rounded-lg p-4 sm:p-6 transition-colors"
        >
          <div class="flex items-start sm:items-center justify-between gap-2 mb-3 sm:mb-4">
            <h2 class="text-lg sm:text-xl font-semibold text-white">{{ item.server.name }}</h2>
            <span
              v-if="item.server.active"
              class="px-2 py-0.5 sm:py-1 bg-green-900/50 text-green-400 text-xs rounded flex-shrink-0"
            >
              Active
            </span>
            <span v-else class="px-2 py-0.5 sm:py-1 bg-gray-700 text-gray-400 text-xs rounded flex-shrink-0">
              Inactive
            </span>
          </div>

          <!-- Current interview info -->
          <div v-if="item.current_interview" class="text-sm">
            <p class="text-gray-300">
              Current: <span class="text-white">{{ item.current_interview.interviewee_name }}</span>
            </p>
            <p class="text-gray-500 text-xs sm:text-sm">
              Interview #{{ item.current_interview.interview_number }}
            </p>
          </div>
          <div v-else class="text-xs sm:text-sm text-gray-500">
            No active interview
          </div>
        </router-link>
      </div>
    </template>
  </div>
</template>
