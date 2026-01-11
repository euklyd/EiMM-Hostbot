import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { SearchResultEntry } from "../api/types";
import { searchInterviews } from "../api/client";

export const useSearchStore = defineStore("search", () => {
  // State
  const results = ref<SearchResultEntry[]>([]);
  const totalCount = ref(0);
  const query = ref("");
  const loading = ref(false);
  const error = ref<string | null>(null);
  const currentPage = ref(1);
  const pageSize = ref(25);

  // Computed
  const hasResults = computed(() => results.value.length > 0);
  const hasMore = computed(() => results.value.length < totalCount.value);
  const totalPages = computed(() => Math.ceil(totalCount.value / pageSize.value));

  // Actions
  async function search(searchQuery: string, page = 1) {
    if (!searchQuery.trim()) {
      reset();
      return;
    }

    loading.value = true;
    error.value = null;
    query.value = searchQuery;
    currentPage.value = page;

    const offset = (page - 1) * pageSize.value;

    try {
      const response = await searchInterviews({
        query: searchQuery,
        limit: pageSize.value,
        offset: offset,
      });

      results.value = response.results;
      totalCount.value = response.total_count;
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Search failed";
      results.value = [];
      totalCount.value = 0;
    } finally {
      loading.value = false;
    }
  }

  async function nextPage() {
    if (hasMore.value && query.value) {
      await search(query.value, currentPage.value + 1);
    }
  }

  async function prevPage() {
    if (currentPage.value > 1 && query.value) {
      await search(query.value, currentPage.value - 1);
    }
  }

  async function goToPage(page: number) {
    if (page >= 1 && page <= totalPages.value && query.value) {
      await search(query.value, page);
    }
  }

  function reset() {
    results.value = [];
    totalCount.value = 0;
    query.value = "";
    error.value = null;
    currentPage.value = 1;
  }

  return {
    // State
    results,
    totalCount,
    query,
    loading,
    error,
    currentPage,
    pageSize,

    // Computed
    hasResults,
    hasMore,
    totalPages,

    // Actions
    search,
    nextPage,
    prevPage,
    goToPage,
    reset,
  };
});
