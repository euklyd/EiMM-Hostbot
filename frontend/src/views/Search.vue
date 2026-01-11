<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import { useSearchStore } from "../stores/search";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const store = useSearchStore();

const searchInput = ref("");
const showHelp = ref(false);

// Initialize from URL query parameter
onMounted(() => {
  const q = route.query.q as string;
  if (q) {
    searchInput.value = q;
    store.search(q);
  }
});

// Update URL when query changes
watch(
  () => store.query,
  (newQuery) => {
    if (newQuery) {
      router.replace({ query: { q: newQuery } });
    } else {
      router.replace({ query: {} });
    }
  }
);

function handleSearch() {
  if (searchInput.value.trim()) {
    store.search(searchInput.value.trim());
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter") {
    handleSearch();
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString();
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
</script>

<template>
  <div>
    <!-- Not authenticated -->
    <template v-if="!auth.isAuthenticated && !auth.loading">
      <div class="text-center py-12 sm:py-16 px-4">
        <h1 class="text-2xl sm:text-3xl font-bold text-white mb-3 sm:mb-4">Interview Search</h1>
        <p class="text-gray-400 mb-6 sm:mb-8 text-sm sm:text-base">
          Login with Discord to search across all your servers' interviews.
        </p>
        <button
          @click="auth.login('/search')"
          class="px-5 sm:px-6 py-2.5 sm:py-3 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white rounded-lg text-base sm:text-lg transition-colors"
        >
          Login with Discord
        </button>
      </div>
    </template>

    <!-- Authenticated -->
    <template v-else>
      <div class="mb-6">
        <h1 class="text-xl sm:text-2xl font-bold text-white mb-4">Search Interviews</h1>

        <!-- Search input -->
        <div class="flex gap-2 mb-3">
          <div class="flex-1 relative">
            <input
              v-model="searchInput"
              @keydown="handleKeydown"
              type="text"
              placeholder="Search questions and answers..."
              class="w-full bg-gray-800 border border-gray-600 rounded-lg px-4 py-2.5 text-gray-100 placeholder-gray-400 focus:outline-none focus:border-indigo-500"
            />
          </div>
          <button
            @click="handleSearch"
            :disabled="store.loading || !searchInput.trim()"
            class="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg transition-colors"
          >
            {{ store.loading ? "Searching..." : "Search" }}
          </button>
        </div>

        <!-- Syntax help toggle -->
        <button
          @click="showHelp = !showHelp"
          class="text-sm text-indigo-400 hover:text-indigo-300"
        >
          {{ showHelp ? "Hide" : "Show" }} query syntax
        </button>

        <!-- Syntax help -->
        <div v-if="showHelp" class="mt-3 p-4 bg-gray-800 rounded-lg text-sm">
          <h3 class="font-semibold text-white mb-2">Query Syntax</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-gray-300">
            <div>
              <h4 class="font-medium text-white">Filters</h4>
              <ul class="mt-1 space-y-1">
                <li><code class="bg-gray-700 px-1 rounded">asker:name</code> - by question asker</li>
                <li><code class="bg-gray-700 px-1 rounded">interviewee:name</code> - by interview subject</li>
                <li><code class="bg-gray-700 px-1 rounded">content:text</code> - in question/answer</li>
                <li><code class="bg-gray-700 px-1 rounded">has:image</code> - contains image</li>
                <li><code class="bg-gray-700 px-1 rounded">after:2024-01</code> - date filter</li>
              </ul>
            </div>
            <div>
              <h4 class="font-medium text-white">Match Types</h4>
              <ul class="mt-1 space-y-1">
                <li><code class="bg-gray-700 px-1 rounded">asker:alice</code> - exact match</li>
                <li><code class="bg-gray-700 px-1 rounded">asker~alice</code> - fuzzy match (typo-tolerant)</li>
                <li><code class="bg-gray-700 px-1 rounded">"star wars"</code> - exact phrase</li>
              </ul>
              <h4 class="font-medium text-white mt-3">Operators</h4>
              <ul class="mt-1 space-y-1">
                <li><code class="bg-gray-700 px-1 rounded">a b</code> - implicit AND</li>
                <li><code class="bg-gray-700 px-1 rounded">a or b</code> - OR</li>
                <li><code class="bg-gray-700 px-1 rounded">-term</code> - NOT</li>
                <li><code class="bg-gray-700 px-1 rounded">(a or b) c</code> - grouping</li>
              </ul>
            </div>
          </div>
        </div>
      </div>

      <!-- Error -->
      <div v-if="store.error" class="bg-red-900/50 border border-red-700 rounded-lg p-4 mb-4">
        <p class="text-red-200">{{ store.error }}</p>
      </div>

      <!-- Results -->
      <div v-if="store.hasResults || store.query">
        <!-- Results header -->
        <div class="flex items-center justify-between mb-4">
          <p class="text-gray-400">
            <template v-if="store.totalCount > 0">
              Found {{ store.totalCount }} result{{ store.totalCount === 1 ? "" : "s" }}
            </template>
            <template v-else-if="store.query && !store.loading">
              No results found
            </template>
          </p>
        </div>

        <!-- Results list -->
        <div class="space-y-4">
          <div
            v-for="result in store.results"
            :key="result.question.id"
            class="bg-gray-800 border border-gray-700 rounded-lg p-4"
          >
            <!-- Interview context -->
            <div class="flex items-center gap-2 text-sm text-gray-400 mb-2">
              <span>{{ result.interview.server_name }}</span>
              <span>&middot;</span>
              <router-link
                :to="{ name: 'interview', params: { serverId: result.interview.server_id, interviewId: result.interview.id } }"
                class="text-indigo-400 hover:text-indigo-300"
              >
                {{ result.interview.interviewee_name }}'s Interview #{{ result.interview.interview_number }}
              </router-link>
              <span>&middot;</span>
              <span>Q#{{ result.question.question_number }}</span>
            </div>

            <!-- Question -->
            <div class="mb-2">
              <span class="text-gray-400 text-sm">{{ result.question.asker_name }} asked:</span>
              <p class="text-white">{{ truncate(result.question.question_text, 300) }}</p>
            </div>

            <!-- Answer -->
            <div v-if="result.question.answer_text" class="pl-4 border-l-2 border-gray-600">
              <span class="text-gray-400 text-sm">Answer:</span>
              <p class="text-gray-200">{{ truncate(result.question.answer_text, 300) }}</p>
            </div>

            <!-- Date -->
            <div class="mt-2 text-xs text-gray-500">
              {{ formatDate(result.question.asked_at) }}
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="store.totalPages > 1" class="flex items-center justify-center gap-2 mt-6">
          <button
            @click="store.prevPage()"
            :disabled="store.currentPage === 1"
            class="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors"
          >
            Previous
          </button>
          <span class="text-gray-400 px-3">
            Page {{ store.currentPage }} of {{ store.totalPages }}
          </span>
          <button
            @click="store.nextPage()"
            :disabled="store.currentPage === store.totalPages"
            class="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded transition-colors"
          >
            Next
          </button>
        </div>
      </div>

      <!-- Initial state -->
      <div
        v-else-if="!store.loading"
        class="text-center py-12 bg-gray-800/50 rounded-lg"
      >
        <p class="text-gray-400">
          Enter a search query to find questions and answers across all your servers.
        </p>
      </div>

      <!-- Loading -->
      <div v-if="store.loading" class="space-y-4">
        <div v-for="i in 3" :key="i" class="bg-gray-800 rounded-lg p-4 animate-pulse">
          <div class="h-4 bg-gray-700 rounded w-1/4 mb-3"></div>
          <div class="h-5 bg-gray-700 rounded w-3/4 mb-2"></div>
          <div class="h-4 bg-gray-700 rounded w-1/2"></div>
        </div>
      </div>
    </template>
  </div>
</template>
