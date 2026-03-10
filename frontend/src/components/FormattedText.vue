<script setup lang="ts">
import { computed } from "vue";
import { parseMarkdownLinks } from "../utils/markdown";

const props = defineProps<{
  text: string;
}>();

const segments = computed(() => parseMarkdownLinks(props.text));
</script>

<template>
  <template v-for="(segment, idx) in segments" :key="idx">
    <a
      v-if="segment.type === 'link'"
      :href="segment.url"
      target="_blank"
      rel="noopener noreferrer"
      class="text-indigo-400 hover:text-indigo-300 underline"
      @click.stop
    >{{ segment.content }}</a>
    <img
      v-else-if="segment.type === 'emoji'"
      :src="segment.emojiUrl"
      :alt="`:${segment.content}:`"
      :title="`:${segment.content}:`"
      class="inline h-5 w-5 align-middle"
    />
    <template v-else>{{ segment.content }}</template>
  </template>
</template>
