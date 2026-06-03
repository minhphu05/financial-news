import { apiClient } from "./client";
import type { ChatRequest, ChatResponse, ModelsResponse } from "@/types";

/**
 * Send a single question to the RAG chatbot and wait for the full response.
 */
export async function askChatbot(request: ChatRequest): Promise<ChatResponse> {
  const { data } = await apiClient.post<ChatResponse>("/chat", request);
  return data;
}

/**
 * Fetch the list of available OpenRouter LLM models from the backend.
 */
export async function fetchModels(): Promise<ModelsResponse> {
  const { data } = await apiClient.get<ModelsResponse>("/models");
  return data;
}
