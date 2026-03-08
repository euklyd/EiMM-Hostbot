<script setup lang="ts">
import { onMounted, ref, computed, watch } from "vue";
import { useRoute } from "vue-router";
import { useAuthStore } from "./stores/auth";
import NavBar from "./components/NavBar.vue";

const auth = useAuthStore();
const route = useRoute();
const authReady = ref(false);

// Force component recreation on route change to prevent stale data display
const routeKey = computed(() => route.fullPath);

// Debug logging for navigation issues (hidden by default in browser console)
watch(
  () => route.fullPath,
  (newPath, oldPath) => {
    console.debug(`[Router] Navigation: ${oldPath} → ${newPath}`);
  },
);

onMounted(async () => {
  console.debug("[App] Mounted, fetching user...");
  await auth.fetchUser();
  console.debug("[App] Auth ready, user:", auth.user?.username ?? "not logged in");
  authReady.value = true;
});
</script>

<template>
  <div class="min-h-screen flex flex-col md:flex-row">
    <NavBar />
    <main class="flex-1 container mx-auto px-4 py-6 md:ml-56">
      <!-- Wait for auth check before rendering routes -->
      <!-- Key on full path forces component recreation on navigation -->
      <router-view v-if="authReady" :key="routeKey" />
      <div v-else class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    </main>
  </div>
</template>
