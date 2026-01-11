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
  <nav class="bg-gray-800 border-b border-gray-700">
    <div class="container mx-auto px-3 sm:px-4">
      <div class="flex items-center justify-between h-12 sm:h-14">
        <!-- Logo/Title -->
        <router-link to="/" class="flex items-center space-x-2">
          <span class="text-lg sm:text-xl font-bold text-white">Discord Interviews</span>
        </router-link>

        <!-- Nav links -->
        <div class="flex items-center space-x-4">
          <router-link
            to="/search"
            class="text-gray-300 hover:text-white transition-colors text-sm sm:text-base"
          >
            Search
          </router-link>
        </div>

        <!-- User section -->
        <div class="flex items-center space-x-2 sm:space-x-4">
          <template v-if="auth.loading">
            <div class="animate-pulse bg-gray-600 h-8 w-16 sm:w-24 rounded"></div>
          </template>

          <template v-else-if="auth.isAuthenticated && auth.user">
            <div class="flex items-center space-x-2 sm:space-x-3">
              <!-- User avatar -->
              <img
                v-if="auth.avatarUrl && !avatarFailed"
                :src="auth.avatarUrl"
                :alt="auth.user.username"
                class="w-7 h-7 sm:w-8 sm:h-8 rounded-full"
                @error="onAvatarError"
              />
              <div v-else class="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-indigo-500 flex items-center justify-center flex-shrink-0">
                <span class="text-white text-xs sm:text-sm font-medium">
                  {{ auth.user.username.charAt(0).toUpperCase() }}
                </span>
              </div>

              <!-- Username (hidden on small screens) -->
              <span class="hidden sm:inline text-gray-200 text-sm sm:text-base">{{ auth.user.username }}</span>

              <!-- Logout button -->
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
              class="px-3 sm:px-4 py-2 bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white text-sm sm:text-base rounded-md transition-colors"
            >
              <span class="hidden sm:inline">Login with Discord</span>
              <span class="sm:hidden">Login</span>
            </button>
          </template>
        </div>
      </div>
    </div>
  </nav>
</template>
