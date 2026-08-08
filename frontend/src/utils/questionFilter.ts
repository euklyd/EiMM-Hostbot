import type { QuestionResponse } from "../api/types";

/**
 * Lightweight local filter syntax for the per-interview question list.
 * Not the full boolean grammar from the global /search page - just
 * prefix filters plus implicit AND of remaining terms, so filtering stays
 * instant against the questions already loaded for this interview.
 *
 * Supported tokens (space-separated, quote a phrase to keep it together):
 *   asker:name    - only questions asked by someone matching "name"
 *   content:text  - only questions/answers containing "text"
 *   "exact phrase" - literal phrase match
 *   bareword      - same as content:bareword
 */
export function matchesQuestionFilter(question: QuestionResponse, query: string): boolean {
  const tokens = query.match(/"[^"]*"|\S+/g) ?? [];
  const askerTerms: string[] = [];
  const textTerms: string[] = [];

  for (const raw of tokens) {
    const isQuoted = raw.startsWith('"') && raw.endsWith('"') && raw.length >= 2;
    const value = isQuoted ? raw.slice(1, -1) : raw;

    if (!isQuoted) {
      const askerMatch = /^asker:(.+)$/i.exec(value);
      if (askerMatch) {
        askerTerms.push(askerMatch[1].toLowerCase());
        continue;
      }
      const contentMatch = /^content:(.+)$/i.exec(value);
      if (contentMatch) {
        textTerms.push(contentMatch[1].toLowerCase());
        continue;
      }
    }

    if (value) {
      textTerms.push(value.toLowerCase());
    }
  }

  const askerName = question.asker_name.toLowerCase();
  if (askerTerms.some((term) => !askerName.includes(term))) {
    return false;
  }

  const haystack = `${question.question_text} ${question.answer_text ?? ""}`.toLowerCase();
  return textTerms.every((term) => haystack.includes(term));
}
