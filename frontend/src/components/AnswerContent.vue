<script setup lang="ts">
import { computed } from "vue";
import { parseAnswerImages } from "../utils/markdown";
import FormattedText from "./FormattedText.vue";

const props = defineProps<{
  text: string | null;
}>();

const parsed = computed(() => parseAnswerImages(props.text ?? ""));

// Limit displayed images to 4 (Discord gallery limit)
const displayedImages = computed(() => parsed.value.images.slice(0, 4));
const extraImageCount = computed(() => Math.max(0, parsed.value.images.length - 4));
</script>

<template>
  <div>
    <!-- Text content (if any, with markdown links rendered) -->
    <p v-if="parsed.text" class="whitespace-pre-wrap">
      <FormattedText :text="parsed.text" />
    </p>

    <!-- Image gallery (max 400px wide) -->
    <div v-if="displayedImages.length > 0" class="mt-3 max-w-md">
      <!-- Single image: full width -->
      <div v-if="displayedImages.length === 1" class="rounded overflow-hidden">
        <a
          :href="displayedImages[0].url"
          target="_blank"
          rel="noopener noreferrer"
          class="block"
        >
          <img
            :src="displayedImages[0].url"
            alt="Answer image"
            class="max-w-full max-h-96 object-contain rounded"
            loading="lazy"
          />
        </a>
      </div>

      <!-- Two images: side by side -->
      <div v-else-if="displayedImages.length === 2" class="grid grid-cols-2 gap-1 rounded overflow-hidden">
        <a
          v-for="(img, idx) in displayedImages"
          :key="idx"
          :href="img.url"
          target="_blank"
          rel="noopener noreferrer"
          class="block aspect-square"
        >
          <img
            :src="img.url"
            alt="Answer image"
            class="w-full h-full object-cover"
            loading="lazy"
          />
        </a>
      </div>

      <!-- Three images: one large left, two stacked right -->
      <div v-else-if="displayedImages.length === 3" class="grid grid-cols-3 gap-1 rounded overflow-hidden">
        <a
          :href="displayedImages[0].url"
          target="_blank"
          rel="noopener noreferrer"
          class="block col-span-2 row-span-2 aspect-square"
        >
          <img
            :src="displayedImages[0].url"
            alt="Answer image"
            class="w-full h-full object-cover"
            loading="lazy"
          />
        </a>
        <a
          v-for="(img, idx) in displayedImages.slice(1)"
          :key="idx"
          :href="img.url"
          target="_blank"
          rel="noopener noreferrer"
          class="block aspect-square"
        >
          <img
            :src="img.url"
            alt="Answer image"
            class="w-full h-full object-cover"
            loading="lazy"
          />
        </a>
      </div>

      <!-- Four+ images: 2x2 grid -->
      <div v-else class="grid grid-cols-2 gap-1 rounded overflow-hidden">
        <a
          v-for="(img, idx) in displayedImages"
          :key="idx"
          :href="img.url"
          target="_blank"
          rel="noopener noreferrer"
          class="block aspect-square"
        >
          <img
            :src="img.url"
            alt="Answer image"
            class="w-full h-full object-cover"
            loading="lazy"
          />
        </a>
      </div>

      <!-- Links to additional images beyond the first 4 -->
      <div v-if="extraImageCount > 0" class="text-xs text-gray-500 mt-1">
        +{{ extraImageCount }} more:
        <a
          v-for="(img, idx) in parsed.images.slice(4)"
          :key="idx"
          :href="img.url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-indigo-400 hover:text-indigo-300 ml-1"
        >[{{ idx + 5 }}]</a>
      </div>
    </div>
  </div>
</template>
