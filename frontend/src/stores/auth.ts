import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { DiscordUser } from "../api/types";
import { getCurrentUser } from "../api/client";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<DiscordUser | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const isAuthenticated = computed(() => user.value !== null);

  const avatarUrl = computed(() => {
    // Handle null, undefined, and empty string
    if (!user.value?.avatar || user.value.avatar === "") return null;
    return `https://cdn.discordapp.com/avatars/${user.value.id}/${user.value.avatar}.png`;
  });

  async function fetchUser() {
    loading.value = true;
    error.value = null;

    try {
      user.value = await getCurrentUser();
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to fetch user";
      user.value = null;
    } finally {
      loading.value = false;
    }
  }

  function login(redirect = "/") {
    const base = import.meta.env.BASE_URL.replace(/\/$/, ""); // Remove trailing slash
    window.location.href = `${base}/auth/login?redirect=${encodeURIComponent(redirect)}`;
  }

  function logout() {
    const base = import.meta.env.BASE_URL.replace(/\/$/, "");
    window.location.href = `${base}/auth/logout`;
  }

  function isMemberOf(guildId: number | string): boolean {
    if (!user.value) return false;
    const idStr = String(guildId);
    // Check guild_ids first (compact session storage), then fall back to guilds
    if (user.value.guild_ids?.length > 0) {
      return user.value.guild_ids.includes(idStr);
    }
    return user.value.guilds.some((g) => g.id === idStr);
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    avatarUrl,
    fetchUser,
    login,
    logout,
    isMemberOf,
  };
});
