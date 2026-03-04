<script setup lang="ts">
import { ref } from "vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const avatarFailed = ref(false);

function onAvatarError() {
  avatarFailed.value = true;
}
</script>

<template>
  <!-- Mobile: horizontal top bar. Desktop (md+): vertical left sidebar. -->
  <nav
    class="bg-gray-800 border-b border-gray-700
           flex items-center px-3 sm:px-4 h-12 sm:h-14
           md:flex-col md:items-stretch md:h-auto md:min-h-screen md:w-56
           md:border-b-0 md:border-r md:px-0 md:py-0"
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
