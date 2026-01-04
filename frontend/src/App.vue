<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useAuthStore } from "./stores/auth";
import NavBar from "./components/NavBar.vue";

const auth = useAuthStore();
const authReady = ref(false);

onMounted(async () => {
  await auth.fetchUser();
  authReady.value = true;
});
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <NavBar />
    <main class="flex-1 container mx-auto px-4 py-6">
      <!-- Wait for auth check before rendering routes -->
      <router-view v-if="authReady" />
      <div v-else class="flex justify-center py-12">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    </main>
  </div>
</template>
