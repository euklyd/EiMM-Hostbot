<script setup lang="ts">
import { onMounted } from "vue";
import { useAuthStore } from "./stores/auth";
import NavBar from "./components/NavBar.vue";

const auth = useAuthStore();

onMounted(async () => {
  await auth.fetchUser();
});
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <NavBar />
    <main class="flex-1 container mx-auto px-4 py-6">
      <router-view />
    </main>
  </div>
</template>
