<script setup lang="ts">
import { ref, computed } from "vue";
import { useAuthStore } from "../stores/auth";
import { useThemeStore, THEMES } from "../stores/theme";

const auth = useAuthStore();
const themeStore = useThemeStore();
const avatarFailed = ref(false);
const showThemePicker = ref(false);

const activeThemeSwatch = computed(
  () => THEMES.find((t) => t.id === themeStore.theme)?.swatch ?? "#2b2d31"
);

function onAvatarError() {
  avatarFailed.value = true;
}
</script>

<template>
  <!-- Mobile: horizontal top bar. Desktop (md+): vertical left sidebar. -->
  <nav
    class="bg-gray-800 border-b border-gray-700
           flex items-center px-3 sm:px-4 h-12 sm:h-14
           md:fixed md:top-0 md:left-0 md:flex-col md:items-stretch md:h-screen md:w-56
           md:border-b-0 md:border-r md:px-0 md:py-0 md:z-50"
  >
    <!-- Logo -->
    <router-link
      to="/"
      class="flex items-center space-x-2
             md:px-4 md:py-3 md:border-b md:border-gray-700 md:flex-shrink-0"
    >
      <span class="text-lg font-bold text-white">Discord Interviews</span>
    </router-link>

    <!-- Nav links -->
    <div
      class="flex items-center space-x-4 ml-4
             md:flex-col md:items-stretch md:space-x-0 md:ml-0 md:p-2 md:flex-1"
    >
      <router-link
        to="/search"
        class="text-gray-300 hover:text-white transition-colors text-sm
               md:px-3 md:py-2 md:rounded md:hover:bg-gray-700"
      >
        Search
      </router-link>
    </div>

    <!-- TODO(mobile-nav): The mobile top bar is intentionally kept minimal for now.
         As nav links and features grow, reconsider freely — a hamburger drawer,
         bottom tab bar, or collapsible menu are all on the table. -->

    <!-- Theme selector (desktop only) -->
    <div class="hidden md:block px-3 py-3 border-t border-gray-700">
      <p class="text-gray-400 text-xs mb-2 px-1">Theme</p>
      <div class="flex gap-2">
        <button
          v-for="t in THEMES"
          :key="t.id"
          :title="t.label"
          @click="themeStore.setTheme(t.id)"
          class="w-6 h-6 rounded-full border-2 transition-all"
          :style="{ backgroundColor: t.swatch }"
          :class="themeStore.theme === t.id
            ? 'border-indigo-500 scale-110'
            : 'border-gray-600 hover:border-gray-400'"
        />
      </div>
    </div>

    <!-- Mobile theme picker -->
    <div class="relative md:hidden mr-1">
      <!-- Transparent overlay closes the picker on outside click -->
      <div v-if="showThemePicker" class="fixed inset-0 z-40" @click="showThemePicker = false" />

      <button
        @click="showThemePicker = !showThemePicker"
        class="p-1 rounded hover:bg-gray-700 transition-colors"
        title="Change theme"
      >
        <!-- Current theme shown as a colored dot -->
        <span
          class="block w-5 h-5 rounded-full border-2 border-gray-500"
          :style="{ backgroundColor: activeThemeSwatch }"
        />
      </button>

      <div
        v-if="showThemePicker"
        class="absolute right-0 top-full mt-1 bg-gray-800 border border-gray-700 rounded-lg p-2 flex gap-2 shadow-lg z-50"
      >
        <button
          v-for="t in THEMES"
          :key="t.id"
          :title="t.label"
          @click="themeStore.setTheme(t.id); showThemePicker = false"
          class="w-6 h-6 rounded-full border-2 transition-all"
          :style="{ backgroundColor: t.swatch }"
          :class="themeStore.theme === t.id
            ? 'border-indigo-500 scale-110'
            : 'border-gray-600 hover:border-gray-400'"
        />
      </div>
    </div>

    <!-- User section -->
    <div
      class="ml-auto flex items-center space-x-2 sm:space-x-4
             md:ml-0 md:mt-auto md:p-3 md:border-t md:border-gray-700"
    >
      <template v-if="auth.loading">
        <div class="animate-pulse bg-gray-600 h-8 w-16 sm:w-24 rounded"></div>
      </template>

      <template v-else-if="auth.isAuthenticated && auth.user">
        <div class="flex items-center space-x-2 sm:space-x-3">
          <!-- Avatar -->
          <img
            v-if="auth.avatarUrl && !avatarFailed"
            :src="auth.avatarUrl"
            :alt="auth.user.username"
            class="w-7 h-7 sm:w-8 sm:h-8 rounded-full flex-shrink-0"
            @error="onAvatarError"
          />
          <div
            v-else
            class="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-indigo-500 flex items-center justify-center flex-shrink-0"
          >
            <span class="text-white text-xs font-medium">
              {{ auth.user.username.charAt(0).toUpperCase() }}
            </span>
          </div>

          <!-- Username -->
          <span class="hidden sm:inline text-gray-200 text-sm flex-1 truncate">
            {{ auth.user.username }}
          </span>

          <!-- Logout -->
          <button
            @click="auth.logout()"
            class="px-2 sm:px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:bg-gray-700 active:bg-gray-600 rounded transition-colors"
          >
            Logout
          </button>
        </div>
      </template>

      <template v-else>
        <button
          @click="auth.login()"
          class="px-3 sm:px-4 py-2 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white text-sm rounded-md transition-colors md:w-full"
        >
          <span class="hidden sm:inline">Login with Discord</span>
          <span class="sm:hidden">Login</span>
        </button>
      </template>
    </div>
  </nav>
</template>
