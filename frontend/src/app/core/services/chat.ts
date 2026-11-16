
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { SupabaseAuthService } from './supabase-auth';

export interface ChatThread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model: string | null;
  created_at: string;
}

export interface ChatThreadsResponse {
  threads: ChatThread[];
  count: number;
}

export interface ChatHistoryResponse {
  thread_id: string;
  title: string;
  messages: ChatMessage[];
  count: number;
}

export interface ChatReply {
  thread_id: string;
  title: string;
  answer: string;
  model: string;
  meals_considered: number;
}
export interface StreamTokenEvent {
  type: 'token';
  text: string;
}

export interface StreamDoneEvent {
  type: 'done';
  thread_id: string;
  title: string;
  model: string;
  meals_considered: number;
}

export interface StreamErrorEvent {
  type: 'error';
  message: string;
}

export type ChatStreamEvent =
  | StreamTokenEvent
  | StreamDoneEvent
  | StreamErrorEvent;

@Injectable({
  providedIn: 'root',
})
export class ChatService {
  private readonly apiUrl = 'http://127.0.0.1:8000/api/v1/chat';

  constructor(
    private readonly http: HttpClient,
    private readonly authService: SupabaseAuthService,
  ) {}

  private async getHeaders(): Promise<HttpHeaders> {
    const token = await this.authService.getAccessToken();

    if (!token) {
      throw new Error('Please sign in before using HealthGPT chat.');
    }

    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });
  }

private parseSseEvent(rawEvent: string): ChatStreamEvent | null {
  let eventType = 'message';
  const dataLines: string[] = [];

  for (const line of rawEvent.split(/\r?\n/)) {
    // Ignore SSE comments/heartbeats.
    if (line.startsWith(':')) {
      continue;
    }

    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      // SSE permits multiple data lines in one event.
      dataLines.push(line.slice(5).replace(/^ /, ''));
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  let data: any;

  try {
    data = JSON.parse(dataLines.join('\n'));
  } catch {
    throw new Error('HealthGPT received an invalid streaming event.');
  }

  switch (eventType) {
    case 'token':
      if (typeof data.text !== 'string') {
        throw new Error('Invalid token event received from HealthGPT.');
      }

      return {
        type: 'token',
        text: data.text,
      };

    case 'done':
      return {
        type: 'done',
        thread_id: data.thread_id,
        title: data.title,
        model: data.model,
        meals_considered: data.meals_considered,
      };

    case 'error':
      return {
        type: 'error',
        message: data.message ?? 'HealthGPT could not complete the request.',
      };

    default:
      // Ignore events such as an untyped message or heartbeat.
      return null;
  }
}


  async getThreads(): Promise<ChatThreadsResponse> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.get<ChatThreadsResponse>(
        `${this.apiUrl}/threads`,
        { headers },
      ),
    );
  }

  async createThread(title = 'New conversation'): Promise<ChatThread> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.post<ChatThread>(
        `${this.apiUrl}/threads`,
        { title },
        { headers },
      ),
    );
  }

  async getMessages(threadId: string): Promise<ChatHistoryResponse> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.get<ChatHistoryResponse>(
        `${this.apiUrl}/threads/${encodeURIComponent(threadId)}/messages`,
        { headers },
      ),
    );
  }

  async sendMessage(
    message: string,
    threadId: string,
  ): Promise<ChatReply> {
    const headers = await this.getHeaders();

    return firstValueFrom(
      this.http.post<ChatReply>(
        `${this.apiUrl}/message`,
        {
          message,
          thread_id: threadId,
        },
        { headers },
      ),
    );
  }


async *sendMessageStream(
  message: string,
  threadId: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const headers = await this.getHeaders();

  const response = await fetch(
    `${this.apiUrl}/message/stream`,
    {
      method: 'POST',
      headers: {
        Authorization: headers.get('Authorization')!,
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        message,
        thread_id: threadId,
      }),
      signal,
    },
  );

  if (!response.ok) {
    const errorBody = await response.text();

    let message = `Chat request failed (${response.status}).`;

    try {
      const parsed = JSON.parse(errorBody);
      message = parsed.detail ?? parsed.message ?? message;
    } catch {
      if (errorBody.trim()) {
        message = errorBody;
      }
    }

    throw new Error(message);
  }

  if (!response.body) {
    throw new Error('Streaming response body is unavailable.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let buffer = '';
  let streamCompleted = false;

  try {
    while (true) {
      const { value, done } = await reader.read();

      if (done) {
        streamCompleted = true;
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      // Extract complete SSE events.
      const events = buffer.split(/\r?\n\r?\n/);

      // Retain the incomplete event for the next read.
      buffer = events.pop() ?? '';

      for (const rawEvent of events) {
        const event = this.parseSseEvent(rawEvent);

        if (event) {
          yield event;
        }
      }
    }

    // Flush any remaining bytes held by TextDecoder.
    buffer += decoder.decode();

    // Process the last event even if the server did not
    // terminate it with the usual blank line.
    if (buffer.trim()) {
      const event = this.parseSseEvent(buffer);

      if (event) {
        yield event;
      }
    }
  } finally {
    // Cancel the underlying stream if the consumer stops early.
    if (!streamCompleted) {
      try {
        await reader.cancel();
      } catch {
        // Ignore cancellation errors during cleanup.
      }
    }

    reader.releaseLock();
  }
}


}
