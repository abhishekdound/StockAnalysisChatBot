import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class Chat {

  API = 'http://127.0.0.1:8000/api/chat';

  async sendMessage(message: string): Promise<string> {

    const res = await fetch(this.API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: {
          content: message,
          role: 'user',
          id: '1'
        },
        threadId: 't1',
        responseId: '1'
      })
    });

    const data = await res.json();
    console.log("BACKEND RESPONSE:", data);   // DEBUG

    return data.response ?? "No response from server";
  }
}