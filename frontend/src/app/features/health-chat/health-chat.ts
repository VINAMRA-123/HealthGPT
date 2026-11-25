
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import {
    ChatService,
    ChatThread,
    ChatMessage,
} from '../../core/services/chat';

@Component({
    selector: 'app-health-chat',
    standalone: true,
    imports: [CommonModule, FormsModule, RouterLink],
    templateUrl: './health-chat.html',
    styleUrl: './health-chat.css',
})
export class ChatComponent implements OnInit {
    threads: ChatThread[] = [];
    messages: ChatMessage[] = [];
    activeThreadId: string | null = null;
    draft = '';

    loadingThreads = false;
    loadingMessages = false;
    sending = false;
    error = '';
    private historyRequestId = 0;
    private activeSendId = 0;
private streamAbortController?: AbortController;

streaming = false;

    constructor(
  private readonly chatService: ChatService,
  private readonly cdr: ChangeDetectorRef,
) {}

    ngOnInit(): void {
        void this.loadThreads();
    }
    private cancelActiveStream(): void {
    ++this.activeSendId;

    this.streamAbortController?.abort();
    this.streamAbortController = undefined;

    this.sending = false;
    this.streaming = false;
}

    async loadThreads(): Promise<void> {
        this.loadingThreads = true;
        this.error = '';

        try {
            const response = await this.chatService.getThreads();
            this.threads = response.threads;
            this.cdr.detectChanges();

            if (this.activeThreadId) {
                const stillExists = this.threads.some(
                    (thread) => thread.id === this.activeThreadId,
                );

                if (!stillExists) {
                    this.activeThreadId = null;
                    this.messages = [];
                }
            }
        } catch (err: unknown) {
            this.error = this.getErrorMessage(err);
        } finally {
            this.loadingThreads = false;
            this.cdr.detectChanges();
        }
    }

    newChat(): void {
    this.cancelActiveStream();

    ++this.historyRequestId;

    this.activeThreadId = null;
    this.messages = [];
    this.draft = '';
    this.error = '';
    this.loadingMessages = false;

    this.cdr.detectChanges();
}

    async openThread(thread: ChatThread): Promise<void> {
        this.cancelActiveStream();
        const requestId = ++this.historyRequestId;

        this.activeThreadId = thread.id;
        this.loadingMessages = true;
        this.error = '';
        this.messages = [];

        try {
            const history = await this.chatService.getMessages(thread.id);

            // Ignore stale responses if the user switched threads.
            if (
                requestId !== this.historyRequestId ||
                this.activeThreadId !== thread.id
            ) {
                return;
            }

            this.messages = history.messages;
            this.activeThreadId = history.thread_id;
            this.cdr.detectChanges();
        } catch (err: unknown) {
            if (requestId === this.historyRequestId) {
                this.error = this.getErrorMessage(err);
            }
        } finally {
            if (requestId === this.historyRequestId) {
                this.loadingMessages = false;
                this.cdr.detectChanges();
            }
        }
    }


async sendMessage(): Promise<void> {
    const message = this.draft.trim();

    if (!message || this.sending) {
        return;
    }

    this.error = '';
    this.sending = true;
    this.streaming = false;
    this.draft = '';

    const sendId = ++this.activeSendId;
    const timestamp = new Date().toISOString();
    const localId = `local-${Date.now()}`;

    let threadId = this.activeThreadId;
    let assistantMessage: ChatMessage | undefined;

    this.streamAbortController = new AbortController();

    try {
        // 1. Create a thread if this is a new conversation.
        if (!threadId) {
            const thread = await this.chatService.createThread();

            // Ignore the result if this request was cancelled.
            if (sendId !== this.activeSendId) {
                return;
            }

            threadId = thread.id;
            this.activeThreadId = threadId;
        }

        if (sendId !== this.activeSendId) {
            return;
        }

        // 2. Invalidate any pending history requests.
        ++this.historyRequestId;

        // 3. Display the user's message immediately.
        if (this.activeThreadId === threadId) {
            this.messages = [
                ...this.messages,
                {
                    id: `${localId}-user`,
                    role: 'user',
                    content: message,
                    model: null,
                    created_at: timestamp,
                },
            ];

            // 4. Create an empty assistant message.
            assistantMessage = {
                id: `${localId}-assistant`,
                role: 'assistant',
                content: '',
                model: null,
                created_at: new Date().toISOString(),
            };

            this.messages = [
                ...this.messages,
                assistantMessage,
            ];
        }

        this.cdr.detectChanges();

        // 5. Start consuming the SSE stream.
        for await (const event of this.chatService.sendMessageStream(
            message,
            threadId,
            this.streamAbortController.signal,
        )) {
            // Ignore events belonging to an older request.
            if (sendId !== this.activeSendId) {
                break;
            }

            // Never update a conversation that is no longer selected.
            if (this.activeThreadId !== threadId) {
                continue;
            }

            if (event.type === 'token') {
                this.streaming = true;

                if (assistantMessage) {
                    assistantMessage.content += event.text;
                }
            }

            if (event.type === 'done') {
                if (assistantMessage) {
                    assistantMessage.model = event.model;
                }

                this.streaming = false;
            }

            if (event.type === 'error') {
                this.error = event.message;
                this.streaming = false;
            }

            this.cdr.detectChanges();
        }

        // 6. Refresh saved history after streaming finishes.
        if (sendId === this.activeSendId) {
            void this.refreshHistory(threadId);
            void this.loadThreads();
        }

    } catch (err: unknown) {
        if (sendId !== this.activeSendId) {
            return;
        }

        const isAbort =
            err instanceof DOMException &&
            err.name === 'AbortError';

        if (!isAbort) {
            this.draft = message;
            this.error = this.getErrorMessage(err);

            // Refresh because the backend might have saved the user message.
            if (threadId) {
                void this.refreshHistory(threadId);
                void this.loadThreads();
            }
        }

    } finally {
        // An older request must not reset the state of a newer request.
        if (sendId === this.activeSendId) {
            this.sending = false;
            this.streaming = false;
            this.streamAbortController = undefined;

            this.cdr.detectChanges();
        }
    }
}

    private async refreshHistory(threadId: string): Promise<void> {
        const requestId = ++this.historyRequestId;

        try {
            const history = await this.chatService.getMessages(threadId);

            // Only update the currently selected thread.
            if (
                requestId !== this.historyRequestId ||
                this.activeThreadId !== threadId
            ) {
                return;
            }

            this.messages = history.messages;
            this.cdr.markForCheck();
        } catch {
            // Keep the messages already displayed if background refresh fails.
        }
    }

    trackMessage(_: number, message: ChatMessage): string {
        return message.id;
    }

    private getErrorMessage(err: unknown): string {
        if (err instanceof HttpErrorResponse) {
            if (err.status === 401) {
                return 'Your session may have expired. Please sign in again.';
            }

            if (err.status === 0) {
                return 'Cannot reach the HealthGPT server. It may be waking up, so please try again in a few seconds.';
            }

            if (err.status === 404) {
                return 'This conversation could not be found.';
            }

            if (err.status >= 500) {
                return 'HealthGPT could not process that request. Please try again.';
            }

            return err.error?.detail ?? 'The request failed. Please try again.';
        }

        return err instanceof Error
            ? err.message
            : 'Something went wrong. Please try again.';
    }
    handleEnterKey(event: Event): void {
        const keyboardEvent = event as KeyboardEvent;

        if (!keyboardEvent.shiftKey) {
            keyboardEvent.preventDefault();
            void this.sendMessage();
        }
    }
}
