/**
 * Utility functions for parsing markdown in interview answers.
 */

export interface ParsedImage {
  url: string;
}

export interface ParsedAnswer {
  text: string;
  images: ParsedImage[];
}

// Bare image URL pattern: URL on its own line ending in common image extensions
// Matches URLs like https://example.com/image.png or https://imgur.com/abc.jpg?1
const IMAGE_URL_PATTERN =
  /^\s*(https?:\/\/\S+\.(?:png|jpe?g|gif|webp|bmp|svg)(?:\?\S*)?)\s*$/gim;

// Markdown link pattern: [text](url)
const LINK_PATTERN = /\[([^\]]+)\]\(([^)]+)\)/g;

/**
 * Strip markdown link syntax, keeping just the text.
 *
 * Converts [text](url) to just "text" for use in previews/truncated views.
 */
export function stripMarkdownLinks(text: string): string {
  if (!text) return "";
  return text.replace(LINK_PATTERN, "$1");
}

export interface TextSegment {
  type: "text" | "link";
  content: string;
  url?: string;
}

/**
 * Parse markdown links from text into segments.
 *
 * Converts [text](url) into structured segments for rendering.
 *
 * @param text The text potentially containing markdown links
 * @returns Array of text and link segments
 */
export function parseMarkdownLinks(text: string): TextSegment[] {
  if (!text) {
    return [];
  }

  const segments: TextSegment[] = [];
  let lastIndex = 0;

  // Reset regex state
  LINK_PATTERN.lastIndex = 0;

  let match;
  while ((match = LINK_PATTERN.exec(text)) !== null) {
    // Add text before this match
    if (match.index > lastIndex) {
      segments.push({
        type: "text",
        content: text.slice(lastIndex, match.index),
      });
    }

    // Add the link
    segments.push({
      type: "link",
      content: match[1],
      url: match[2],
    });

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    segments.push({
      type: "text",
      content: text.slice(lastIndex),
    });
  }

  return segments;
}

/**
 * Parse image URLs from answer text.
 *
 * Finds bare image URLs on their own lines and returns cleaned text plus image list.
 *
 * @param text The answer text potentially containing image URLs
 * @returns Object with cleaned text and array of images
 */
export function parseAnswerImages(text: string): ParsedAnswer {
  if (!text) {
    return { text: "", images: [] };
  }

  const images: ParsedImage[] = [];

  // Extract all image URLs
  const cleanedText = text.replace(IMAGE_URL_PATTERN, (_match, url) => {
    images.push({ url });
    return ""; // Remove image URL line from text
  });

  // Clean up extra whitespace left behind
  const normalizedText = cleanedText.replace(/\n\s*\n\s*\n/g, "\n\n").trim();

  return {
    text: normalizedText,
    images,
  };
}
