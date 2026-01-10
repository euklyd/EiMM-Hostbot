<script setup lang="ts">
import { computed } from "vue";
import { parseAnswerImages } from "../utils/markdown";
import FormattedText from "./FormattedText.vue";

const props = defineProps<{
  text: string | null;
}>();

const parsed = computed(() => parseAnswerImages(props.text ?? ""));
</script>

<template>
  <div>
    <!-- Text content (if any, with markdown links rendered) -->
    <p v-if="parsed.text" class="whitespace-pre-wrap">
      <FormattedText :text="parsed.text" />
    </p>

    <!-- Images -->
    <div v-if="parsed.images.length > 0" class="mt-3 space-y-3">
      <a
        v-for="(img, idx) in parsed.images"
        :key="idx"
        :href="img.url"
        target="_blank"
        rel="noopener noreferrer"
        class="block rounded overflow-hidden bg-gray-900/50"
      >
        <img
          :src="img.url"
          alt="Answer image"
          class="max-w-full max-h-96 object-contain"
          loading="lazy"
        />
      </a>
    </div>
  </div>
</template>
