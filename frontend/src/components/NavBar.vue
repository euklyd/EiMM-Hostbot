<script setup lang="ts">
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
</script>

<template>
  <nav class="bg-gray-800 border-b border-gray-700">
    <div class="container mx-auto px-4">
      <div class="flex items-center justify-between h-14">
        <!-- Logo/Title -->
        <router-link to="/" class="flex items-center space-x-2">
          <span class="text-xl font-bold text-white">Discord Interviews</span>
        </router-link>

        <!-- User section -->
        <div class="flex items-center space-x-4">
          <template v-if="auth.loading">
            <div class="animate-pulse bg-gray-600 h-8 w-24 rounded"></div>
          </template>

          <template v-else-if="auth.isAuthenticated && auth.user">
            <div class="flex items-center space-x-3">
              <!-- User avatar -->
              <img
                v-if="auth.avatarUrl"
                :src="auth.avatarUrl"
                :alt="auth.user.username"
                class="w-8 h-8 rounded-full"
              />
              <div v-else class="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center">
                <span class="text-white text-sm font-medium">
                  {{ auth.user.username.charAt(0).toUpperCase() }}
                </span>
              </div>

              <!-- Username -->
              <span class="text-gray-200">{{ auth.user.username }}</span>

              <!-- Logout button -->
              <button
                @click="auth.logout()"
                class="px-3 py-1.5 text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded transition-colors"
              >
                Logout
              </button>
            </div>
          </template>

          <template v-else>
            <button
              @click="auth.login()"
              class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md transition-colors"
            >
              Login with Discord
            </button>
          </template>
        </div>
      </div>
    </div>
  </nav>
</template>
