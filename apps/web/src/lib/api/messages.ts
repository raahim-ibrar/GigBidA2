import type { components } from "./schema";
import { apiRequest } from "./accounts";
export type Conversation = components["schemas"]["ConversationView"];
export type Message = components["schemas"]["MessageView"];
export type Reply = components["schemas"]["ReplyDraftView"];
export const listConversations = () => apiRequest<Conversation[]>("/messages");
export const getConversation = (id: string) => apiRequest<Conversation>(`/messages/${encodeURIComponent(id)}`);
export const getMessages = (id: string) => apiRequest<Message[]>(`/messages/${encodeURIComponent(id)}/history`);
export const getReplies = (id: string) => apiRequest<Reply[]>(`/messages/${encodeURIComponent(id)}/drafts`);
export const createConversation = (body: components["schemas"]["CreateConversation"], csrf: string) => apiRequest<Conversation>("/messages", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
export const addMessage = (id: string, text: string, key: string, csrf: string) => apiRequest<Conversation>(`/messages/${encodeURIComponent(id)}/history`, {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ text, idempotency_key: key }),
});
